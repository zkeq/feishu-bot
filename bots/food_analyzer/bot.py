"""
饮食分析 Bot 实现
"""
import base64
import json
import logging
import re
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

from bots.base import BaseBot
from core.batcher import MessagePart
from core.ai_client import AIClient
from core.utils import preprocess_markdown_for_feishu

logger = logging.getLogger(__name__)


class FoodAnalyzerBot(BaseBot):
    """饮食分析机器人"""

    def __init__(self, config: Dict[str, Any], client, ai_client: AIClient):
        super().__init__(config, client)
        self.ai_client = ai_client
        self.openai_model = config.get("openai", {}).get("model", "gpt-4o-mini")
        self.openai_temperature = config.get("openai", {}).get("temperature", 0.7)
        self.openai_max_tokens = config.get("openai", {}).get("max_tokens")

        logger.info(f"[{self.name}] OpenAI 配置: model={self.openai_model}, temperature={self.openai_temperature}, max_tokens={self.openai_max_tokens}")

        # 多维表格配置
        self.bitable_enabled = config.get("bitable", {}).get("enabled", False)
        self.bitable_app_token = config.get("bitable", {}).get("app_token", "")
        self.bitable_table_id = config.get("bitable", {}).get("table_id", "")
        self.bitable_fields = config.get("bitable", {}).get("fields", {})

        if self.bitable_enabled:
            logger.info(f"[{self.name}] 多维表格集成已启用")
            logger.info(f"[{self.name}] app_token={self.bitable_app_token}, table_id={self.bitable_table_id}")

    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """处理消息并返回分析结果

        支持批量处理多张图片：
        - 如果有多张图片，每张图片作为独立的一餐分析
        - 文字内容会附加到每张图片的分析中
        """
        logger.info(f"[{self.name}] 开始分析饮食，消息片段数: {len(parts)}")

        # 分离图片和文字
        images = [part for part in parts if part.kind == "image" and part.image_key]
        texts = [part for part in parts if part.kind == "text" and part.text]

        # 合并所有文字内容
        combined_text = " ".join([t.text for t in texts]) if texts else ""

        logger.info(f"[{self.name}] 检测到 {len(images)} 张图片，{len(texts)} 条文字")

        # 如果没有图片，当作一条普通消息处理
        if not images:
            return self._process_single_meal(chat_id, parts, status_msg_id, combined_text)

        # 如果只有一张图片，按原逻辑处理
        if len(images) == 1:
            return self._process_single_meal(chat_id, parts, status_msg_id, combined_text)

        # 多张图片：分别处理每张图片
        logger.info(f"[{self.name}] 批量处理模式：{len(images)} 张图片")
        return self._process_multiple_meals(chat_id, images, combined_text, status_msg_id)

    def _process_single_meal(
        self,
        chat_id: str,
        parts: List[MessagePart],
        status_msg_id: Optional[str],
        user_comment: str
    ) -> str:
        """处理单条饮食记录（原有逻辑）"""
        logger.info(f"[{self.name}] 单条记录处理模式")

        # 更新状态
        if status_msg_id:
            self._update_status(chat_id, status_msg_id, "**🔍 正在分析饮食...**\n\n识别食物中...")

        # 构建消息
        messages = self._build_ai_messages(parts)

        # 调用 AI 进行流式分析
        if status_msg_id:
            result = self._call_ai_streaming(chat_id, messages, status_msg_id)
        else:
            result = self.ai_client.call(
                messages=messages,
                model=self.openai_model,
                temperature=self.openai_temperature,
                max_tokens=self.openai_max_tokens,
            )

        # 提取 JSON 数据
        meal_data = self._extract_json_data(result)

        # 添加用户附言
        if meal_data and user_comment:
            meal_data["user_comment"] = user_comment

        # 提取图片信息（保存第一张图片）
        if meal_data:
            images = [part for part in parts if part.kind == "image" and part.image_key]
            if images:
                meal_data["image_key"] = images[0].image_key
                meal_data["image_message_id"] = images[0].message_id

        # 生成带按钮的交互式卡片
        if meal_data and self.bitable_enabled:
            card_content = self._build_interactive_card(result, meal_data)
            if status_msg_id:
                self.client.update_message(status_msg_id, card_content)
            return result
        else:
            # 如果没有启用多维表格或提取失败，返回普通格式
            final_content = preprocess_markdown_for_feishu(result)
            if status_msg_id:
                self._update_status(chat_id, status_msg_id, final_content)
            return result

    def _process_multiple_meals(
        self,
        chat_id: str,
        images: List[MessagePart],
        combined_text: str,
        status_msg_id: Optional[str]
    ) -> str:
        """处理多张图片，每张图片作为独立的一餐

        Args:
            chat_id: 聊天 ID
            images: 图片列表
            combined_text: 合并的文字内容（会附加到每张图片）
            status_msg_id: 状态消息 ID（会被删除，每张图片发送独立消息）

        Returns:
            处理结果摘要
        """
        logger.info(f"[{self.name}] 批量处理 {len(images)} 张图片")

        # 更新初始状态
        if status_msg_id:
            self._update_status(
                chat_id,
                status_msg_id,
                f"**🔍 批量分析模式**\n\n检测到 {len(images)} 张图片，正在逐个分析..."
            )

        # 存储每张图片的分析结果
        all_meal_data = []

        # 逐个处理每张图片，每张图片发送独立消息
        for idx, image_part in enumerate(images, start=1):
            logger.info(f"[{self.name}] 处理第 {idx}/{len(images)} 张图片")

            # 为单张图片构建消息（图片 + 文字）
            single_parts = [image_part]
            if combined_text:
                single_parts.append(MessagePart(kind="text", text=combined_text))

            messages = self._build_ai_messages(single_parts)

            # 调用 AI 分析（流式）
            try:
                # 为这张图片创建独立的状态消息
                single_status_msg = self.client.send_message(
                    chat_id,
                    {
                        "config": {"wide_screen_mode": True},
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**🔍 正在分析第 {idx}/{len(images)} 张图片...**\n\n识别食物中..."
                                }
                            }
                        ]
                    },
                    msg_type="interactive"
                )

                # 流式调用 AI 分析这张图片
                result = self._call_ai_streaming(chat_id, messages, single_status_msg)

                # 提取 JSON 数据
                meal_data = self._extract_json_data(result)

                if meal_data:
                    # 添加用户附言
                    if combined_text:
                        meal_data["user_comment"] = combined_text

                    # 添加图片信息
                    meal_data["image_key"] = image_part.image_key
                    meal_data["image_message_id"] = image_part.message_id

                    all_meal_data.append(meal_data)

                    # 更新这条消息为完整的分析结果（带单独导入按钮）
                    if self.bitable_enabled:
                        card_content = self._build_interactive_card(result, meal_data)
                        self.client.update_message(single_status_msg, card_content)
                    else:
                        final_content = preprocess_markdown_for_feishu(result)
                        self._update_status(chat_id, single_status_msg, final_content)

                    logger.info(f"[{self.name}] 第 {idx} 张图片分析完成")
                else:
                    logger.warning(f"[{self.name}] 第 {idx} 张图片未能提取数据")
                    # 更新为失败消息
                    self._update_status(
                        chat_id,
                        single_status_msg,
                        f"**❌ 第 {idx} 张图片分析失败**\n\n无法识别食物内容，请确保图片清晰。"
                    )

            except Exception as e:
                logger.error(f"[{self.name}] 分析第 {idx} 张图片时出错: {e}", exc_info=True)
                # 发送错误消息
                self.client.send_message(
                    chat_id,
                    {
                        "config": {"wide_screen_mode": True},
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**❌ 第 {idx} 张图片分析出错**\n\n{str(e)}"
                                }
                            }
                        ]
                    },
                    msg_type="interactive"
                )

        # 生成汇总结果
        logger.info(f"[{self.name}] 批量分析完成，成功: {len(all_meal_data)}/{len(images)}")

        # 删除初始状态消息（已被各个独立消息替代）
        if status_msg_id:
            try:
                self.client.delete_message(status_msg_id)
                logger.info(f"[{self.name}] 已删除初始状态消息")
            except Exception as e:
                logger.warning(f"[{self.name}] 删除初始状态消息失败: {e}")

        # 发送最终汇总消息（带批量导入按钮）
        summary_text = self._build_batch_summary(all_meal_data)

        if all_meal_data and self.bitable_enabled:
            # 发送带批量导入按钮的汇总卡片
            card_content = self._build_batch_interactive_card(summary_text, all_meal_data)
            self.client.send_message(chat_id, card_content, msg_type="interactive")
        else:
            # 发送普通格式汇总
            final_content = preprocess_markdown_for_feishu(summary_text)
            summary_card = {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": final_content}
                    }
                ]
            }
            self.client.send_message(chat_id, summary_card, msg_type="interactive")

        return summary_text

    def _build_batch_summary(self, all_meal_data: List[Dict[str, Any]]) -> str:
        """构建批量分析结果的汇总文本

        Args:
            all_meal_data: 所有成功分析的饮食数据

        Returns:
            汇总文本
        """
        if not all_meal_data:
            return "**❌ 批量分析失败**\n\n所有图片都未能成功分析，请检查图片内容是否清晰。"

        # 计算总计数据
        total_calories = sum(meal.get("calories", 0) for meal in all_meal_data)
        total_protein = sum(meal.get("protein", 0) for meal in all_meal_data)
        total_carbs = sum(meal.get("carbs", 0) for meal in all_meal_data)
        total_fat = sum(meal.get("fat", 0) for meal in all_meal_data)
        avg_score = sum(meal.get("score", 0) for meal in all_meal_data) / len(all_meal_data)

        # 构建汇总文本
        summary = f"**📊 批量分析完成**\n\n成功分析 **{len(all_meal_data)}** 条饮食记录！\n\n"

        # 添加每条记录的摘要
        summary += "**📝 记录明细**\n\n"
        for idx, meal in enumerate(all_meal_data, start=1):
            date_str = meal.get("date", "未知日期")
            time_str = meal.get("time", "")
            meal_type = meal.get("meal_type", "未知")
            main_dish = meal.get("main_dish", "未知")
            calories = meal.get("calories", 0)

            time_display = f" {time_str}" if time_str else ""
            summary += f"{idx}. **{date_str}{time_display}** - {meal_type}：{main_dish} ({calories} kcal)\n"

        # 添加总计数据
        summary += f"\n**🔢 营养总计**\n\n"
        summary += f"• 总热量：{total_calories} kcal\n"
        summary += f"• 总蛋白质：{total_protein} g\n"
        summary += f"• 总碳水：{total_carbs} g\n"
        summary += f"• 总脂肪：{total_fat} g\n"
        summary += f"• 平均评分：{avg_score:.1f}/10\n"

        return summary

    def _build_batch_interactive_card(
        self, summary_text: str, all_meal_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建批量导入的交互式卡片

        Args:
            summary_text: 汇总文本
            all_meal_data: 所有饮食数据（数组）

        Returns:
            飞书卡片 JSON
        """
        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": summary_text}
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": f"📥 批量导入 {len(all_meal_data)} 条记录到多维表格"
                            },
                            "type": "primary",
                            "value": {"batch": True, "meals": all_meal_data},  # 批量数据标记
                            "confirm": {
                                "title": {"tag": "plain_text", "content": "确认批量导入"},
                                "text": {
                                    "tag": "plain_text",
                                    "content": f"确定要将这 {len(all_meal_data)} 条饮食记录导入到多维表格吗？"
                                }
                            }
                        }
                    ]
                }
            ]
        }

    def _build_ai_messages(self, parts: List[MessagePart]) -> List[Dict[str, Any]]:
        """构建 AI 消息"""
        content: List[Dict[str, Any]] = []

        for part in parts:
            if part.kind == "text" and part.text:
                content.append({"type": "text", "text": part.text})
            elif part.kind == "image" and part.image_key and part.message_id:
                # 获取图片
                image_data = self.client.get_image_resource(part.message_id, part.image_key)
                if image_data:
                    # 转换为 data URL
                    encoded = base64.b64encode(image_data).decode("utf-8")
                    data_url = f"data:image/png;base64,{encoded}"
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    content.append({"type": "text", "text": f"[图片: {part.image_key}]"})

        # 获取当前日期信息
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        current_weekday = weekday_names[now.weekday()]

        # 将日期信息添加到系统提示词
        system_prompt_with_date = f"{self.get_system_prompt()}\n\n**当前时间信息**：今天是 {current_date} {current_weekday}。用户可能会提及日期（如'上周五'、'1月20日'等），请根据当前日期计算并在 JSON 的 date 字段中返回对应的 YYYY-MM-DD 格式日期。如果用户没有指定日期，则使用当前日期。"

        return [
            {"role": "system", "content": system_prompt_with_date},
            {"role": "user", "content": content},
        ]

    def _call_ai_streaming(
        self, chat_id: str, messages: List[Dict[str, Any]], status_msg_id: str
    ) -> str:
        """调用 AI API（流式）"""
        # 更新状态
        self._update_status(chat_id, status_msg_id, "**🚀 正在请求 AI 分析...**\n\n等待响应中...")

        def update_callback(content: str):
            """流式更新回调"""
            self._update_status(
                chat_id,
                status_msg_id,
                f"**📝 正在分析中...**\n\n{preprocess_markdown_for_feishu(content)}\n\n_正在生成中..._",
            )

        result = self.ai_client.call_streaming(
            messages=messages,
            model=self.openai_model,
            temperature=self.openai_temperature,
            max_tokens=self.openai_max_tokens,
            update_callback=update_callback,
            update_interval=0.5,
        )

        return result

    def _update_status(self, chat_id: str, message_id: str, content: str) -> None:
        """更新状态消息"""
        content_json = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
        }
        self.client.update_message(message_id, content_json)

    def _extract_json_data(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """从 AI 响应中提取 JSON 数据"""
        try:
            # 使用正则表达式提取 JSON 代码块
            pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
            matches = re.findall(pattern, ai_response)

            if matches:
                json_str = matches[-1]  # 取最后一个匹配
                meal_data = json.loads(json_str)
                logger.info(f"[{self.name}] 成功提取饮食数据: {meal_data}")
                return meal_data
            else:
                logger.warning(f"[{self.name}] 未找到 JSON 数据块")
                return None
        except Exception as e:
            logger.error(f"[{self.name}] 提取 JSON 数据失败: {e}")
            return None

    def _build_interactive_card(self, ai_response: str, meal_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成带按钮的交互式卡片"""
        # 移除 JSON 代码块，只保留分析内容
        clean_response = re.sub(r'```json[\s\S]*?```', '', ai_response).strip()
        clean_response = preprocess_markdown_for_feishu(clean_response)

        # 构建数据展示
        data_display = (
            f"\n\n---\n\n"
            f"**📊 数据摘要**\n\n"
            f"• 餐次：{meal_data.get('meal_type', '未知')}\n"
            f"• 主餐：{meal_data.get('main_dish', '无')}\n"
        )

        if meal_data.get('snacks'):
            data_display += f"• 小食：{meal_data['snacks']}\n"
        if meal_data.get('drinks'):
            data_display += f"• 饮品：{meal_data['drinks']}\n"

        data_display += (
            f"• 热量：{meal_data.get('calories', 0)} kcal\n"
            f"• 蛋白质：{meal_data.get('protein', 0)} g\n"
            f"• 碳水：{meal_data.get('carbs', 0)} g\n"
            f"• 脂肪：{meal_data.get('fat', 0)} g\n"
            f"• 评分：{meal_data.get('score', 0)}/10"
        )

        # 将 meal_data 序列化为 JSON 字符串作为按钮的 value
        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": clean_response + data_display}
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📥 导入到多维表格"},
                            "type": "primary",
                            "value": meal_data,  # SDK 期望字典类型，不要序列化
                            "confirm": {
                                "title": {"tag": "plain_text", "content": "确认导入"},
                                "text": {"tag": "plain_text", "content": "确定要将这条饮食记录导入到多维表格吗？"}
                            }
                        }
                    ]
                }
            ]
        }

    def _save_to_bitable(self, meal_data: Dict[str, Any]) -> bool:
        """保存分析结果到多维表格"""
        try:
            logger.info(f"[{self.name}] 开始保存到多维表格...")

            # 获取 access_token
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            token_response = requests.post(token_url, json={
                "app_id": self.client.app_id,
                "app_secret": self.client.app_secret
            })

            if token_response.status_code != 200:
                logger.error(f"[{self.name}] 获取 access_token 失败: {token_response.text}")
                return False

            access_token = token_response.json()["tenant_access_token"]
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            # 先获取表格字段信息
            fields_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.bitable_app_token}/tables/{self.bitable_table_id}/fields"
            fields_response = requests.get(fields_url, headers=headers)

            if fields_response.status_code == 200:
                fields_info = fields_response.json()
                logger.info(f"[{self.name}] 表格字段信息: {json.dumps(fields_info, ensure_ascii=False, indent=2)}")
            else:
                logger.warning(f"[{self.name}] 获取字段信息失败: {fields_response.text}")

            # 处理图片上传
            image_token = None
            if "image_key" in meal_data and "image_message_id" in meal_data:
                image_token = self._upload_image_to_bitable(
                    access_token,
                    meal_data["image_message_id"],
                    meal_data["image_key"]
                )
                if image_token:
                    logger.info(f"[{self.name}] 图片上传成功，file_token={image_token}")

            # 构建记录数据
            fields_mapping = self.bitable_fields
            record_fields = {}

            # 映射时间字段（合并日期和时间，转换为时间戳）
            if "time" in fields_mapping:
                date_str = meal_data.get("date", "")
                time_str = meal_data.get("time", "")

                # 如果没有日期，使用当前日期
                if not date_str:
                    date_str = datetime.now().strftime("%Y-%m-%d")

                try:
                    # 组合日期和时间并转换为时间戳
                    if time_str:
                        # 有时间：解析 YYYY-MM-DD HH:MM
                        datetime_str = f"{date_str} {time_str}"
                        datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                    else:
                        # 没有时间：只解析日期，时间设为 00:00
                        datetime_obj = datetime.strptime(date_str, "%Y-%m-%d")

                    # 转换为毫秒时间戳
                    timestamp_ms = int(datetime_obj.timestamp() * 1000)
                    record_fields[fields_mapping["time"]] = timestamp_ms
                    logger.info(f"[{self.name}] 时间字段: {date_str} {time_str if time_str else '00:00'} -> {timestamp_ms}")
                except Exception as e:
                    logger.warning(f"[{self.name}] 时间转换失败: {e}，使用当前时间")
                    record_fields[fields_mapping["time"]] = int(datetime.now().timestamp() * 1000)

            # 映射其他字段
            if "meal_type" in meal_data and "meal_type" in fields_mapping:
                record_fields[fields_mapping["meal_type"]] = meal_data["meal_type"]
            if "main_dish" in meal_data and "main_dish" in fields_mapping:
                record_fields[fields_mapping["main_dish"]] = meal_data.get("main_dish", "")
            if "snacks" in meal_data and "snacks" in fields_mapping:
                record_fields[fields_mapping["snacks"]] = meal_data.get("snacks", "")
            if "drinks" in meal_data and "drinks" in fields_mapping:
                record_fields[fields_mapping["drinks"]] = meal_data.get("drinks", "")
            if "calories" in meal_data and "calories" in fields_mapping:
                record_fields[fields_mapping["calories"]] = meal_data.get("calories", 0)
            if "protein" in meal_data and "protein" in fields_mapping:
                record_fields[fields_mapping["protein"]] = meal_data.get("protein", 0)
            if "carbs" in meal_data and "carbs" in fields_mapping:
                record_fields[fields_mapping["carbs"]] = meal_data.get("carbs", 0)
            if "fat" in meal_data and "fat" in fields_mapping:
                record_fields[fields_mapping["fat"]] = meal_data.get("fat", 0)
            if "score" in meal_data and "score" in fields_mapping:
                record_fields[fields_mapping["score"]] = meal_data.get("score", 0)
            if "notes" in meal_data and "notes" in fields_mapping:
                record_fields[fields_mapping["notes"]] = meal_data.get("notes", "")

            # 添加附言字段
            if "user_comment" in meal_data and "user_comment" in fields_mapping:
                record_fields[fields_mapping["user_comment"]] = meal_data.get("user_comment", "")

            # 添加图片字段（飞书多维表格附件字段格式）
            if image_token and "image" in fields_mapping:
                record_fields[fields_mapping["image"]] = [{
                    "file_token": image_token
                }]

            # 添加记录
            add_record_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.bitable_app_token}/tables/{self.bitable_table_id}/records"
            payload = {"fields": record_fields}

            logger.info(f"[{self.name}] 发送数据到多维表格: {record_fields}")

            response = requests.post(add_record_url, headers=headers, json=payload)

            if response.status_code == 200 and response.json().get("code") == 0:
                logger.info(f"[{self.name}] 保存到多维表格成功")
                return True
            else:
                logger.error(f"[{self.name}] 保存到多维表格失败: {response.text}")
                return False

        except Exception as e:
            logger.error(f"[{self.name}] 保存到多维表格异常: {e}", exc_info=True)
            return False

    def _upload_image_to_bitable(self, access_token: str, message_id: str, image_key: str) -> Optional[str]:
        """上传图片到多维表格并返回 file_token"""
        try:
            logger.info(f"[{self.name}] 开始上传图片: message_id={message_id}, image_key={image_key}")

            # 1. 从飞书消息中获取图片数据
            image_data = self.client.get_image_resource(message_id, image_key)
            if not image_data:
                logger.error(f"[{self.name}] 获取图片数据失败")
                return None

            # 2. 上传图片到飞书文件系统
            upload_url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"

            files = {
                'file': ('food_image.jpg', image_data, 'image/jpeg')
            }
            data = {
                'file_name': 'food_image.jpg',
                'parent_type': 'bitable_image',
                'parent_node': self.bitable_app_token,
                'size': str(len(image_data))
            }
            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            upload_response = requests.post(upload_url, headers=headers, files=files, data=data)

            if upload_response.status_code == 200:
                result = upload_response.json()
                if result.get("code") == 0:
                    file_token = result.get("data", {}).get("file_token")
                    logger.info(f"[{self.name}] 图片上传成功: file_token={file_token}")
                    return file_token
                else:
                    logger.error(f"[{self.name}] 图片上传失败: {result}")
                    return None
            else:
                logger.error(f"[{self.name}] 图片上传请求失败: {upload_response.text}")
                return None

        except Exception as e:
            logger.error(f"[{self.name}] 上传图片异常: {e}", exc_info=True)
            return None
