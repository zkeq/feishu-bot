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
        """处理消息并返回分析结果"""
        logger.info(f"[{self.name}] 开始分析饮食，消息片段数: {len(parts)}")

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

        # 生成带按钮的交互式卡片
        if meal_data and self.bitable_enabled:
            # 更新消息为交互式卡片
            card_content = self._build_interactive_card(result, meal_data, chat_id)
            if status_msg_id:
                self.client.update_message(status_msg_id, card_content)
            return result
        else:
            # 如果没有启用多维表格或提取失败，返回普通格式
            final_content = preprocess_markdown_for_feishu(result)
            if status_msg_id:
                self._update_status(chat_id, status_msg_id, final_content)
            return result

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

        return [
            {"role": "system", "content": self.get_system_prompt()},
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

    def _build_interactive_card(self, ai_response: str, meal_data: Dict[str, Any], chat_id: str) -> Dict[str, Any]:
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
                "app_id": self.client.client.app_id,
                "app_secret": self.client.client.app_secret
            })

            if token_response.status_code != 200:
                logger.error(f"[{self.name}] 获取 access_token 失败: {token_response.text}")
                return False

            access_token = token_response.json()["tenant_access_token"]

            # 构建记录数据
            fields_mapping = self.bitable_fields
            record_fields = {}

            # 映射字段
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

            # 添加记录
            add_record_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.bitable_app_token}/tables/{self.bitable_table_id}/records"
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

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
