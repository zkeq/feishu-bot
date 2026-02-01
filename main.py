"""
飞书机器人框架 - 多连接管理模式
一个进程管理多个 WebSocket 连接，每个 Bot 独立配置飞书应用
"""
import importlib
import json
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import lark_oapi as lark
import nest_asyncio
import yaml
from dotenv import load_dotenv

# 允许嵌套事件循环
nest_asyncio.apply()

from core.client import FeishuClient
from core.batcher import MessageBatcher, MessagePart
from core.ai_client import AIClient
from bots.base import BaseBot

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class BotInstance:
    """Bot 实例，包含一个 Bot 的所有组件"""

    def __init__(
        self,
        bot_name: str,
        bot: BaseBot,
        client: FeishuClient,
        batcher: MessageBatcher,
        config: Dict[str, Any],
    ):
        self.bot_name = bot_name
        self.bot = bot
        self.client = client
        self.batcher = batcher
        self.config = config
        self.ws_client = None

        # 消息去重：记录最近处理过的 message_id
        self._processed_messages: Dict[str, float] = {}
        self._dedup_lock = threading.Lock()
        self._dedup_expire_seconds = 600  # 10分钟过期

        # 卡片交互去重：记录最近处理过的 action_id
        self._processed_actions: Dict[str, float] = {}
        self._action_dedup_lock = threading.Lock()
        self._action_dedup_expire_seconds = 60  # 1分钟过期（卡片交互通常更快）

        logger.info(f"BotInstance 创建: {bot_name} ({bot.name})")

    def handle_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """处理消息接收事件"""
        try:
            logger.info("=" * 60)
            logger.info(f"[{self.bot_name}] 收到新消息事件")

            message = data.event.message
            sender = data.event.sender
            chat_id = message.chat_id
            message_id = getattr(message, "message_id", "N/A")
            msg_type = message.message_type
            content = message.content

            # 消息去重检查
            if message_id != "N/A":
                if self._is_duplicate_message(message_id):
                    logger.warning(f"[{self.bot_name}] 检测到重复消息，跳过处理: message_id={message_id}")
                    return
                self._mark_message_processed(message_id)

            # 获取发送者 ID（优先使用 user_id，没有则使用 open_id）
            sender_id = None
            if sender and sender.sender_id:
                sender_id = sender.sender_id.user_id or sender.sender_id.open_id

            logger.info(f"[{self.bot_name}] 消息详情:")
            logger.info(f"  chat_id: {chat_id}")
            logger.info(f"  message_id: {message_id}")
            logger.info(f"  message_type: {msg_type}")
            logger.info(f"  sender_id: {sender_id}")

            # 解析消息
            parts = self._parse_message_content(msg_type, content, message_id, sender_id)

            if parts:
                # 检查是否是斜杠命令（以 / 开头）
                is_command = False
                if parts and parts[0].kind == "text" and parts[0].text:
                    is_command = parts[0].text.strip().startswith("/")

                if is_command:
                    # 斜杠命令立即执行，不等待批处理
                    logger.info(f"[{self.bot_name}] 检测到斜杠命令，立即执行")
                    self._handle_batch(chat_id, parts, None)
                else:
                    # 普通消息添加到批处理队列
                    logger.info(f"[{self.bot_name}] 消息解析成功，添加到批处理队列")
                    self.batcher.add(chat_id, parts, self._handle_batch)
            else:
                logger.warning(f"[{self.bot_name}] 消息解析后没有有效的消息片段")

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"[{self.bot_name}] 处理消息接收事件时发生错误: {e}", exc_info=True)

    def _parse_message_content(self, msg_type: str, content: str, message_id: str, sender_id: Optional[str] = None) -> List[MessagePart]:
        """解析消息内容"""
        parts: List[MessagePart] = []
        data = json.loads(content) if content else {}

        if msg_type == "text":
            text = data.get("text", "")
            parts.append(MessagePart(kind="text", text=text, sender_id=sender_id))
        elif msg_type == "image":
            image_key = data.get("image_key")
            parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id, sender_id=sender_id))
        elif msg_type == "post":
            for block in data.get("content", []):
                for element in block:
                    tag = element.get("tag")
                    if tag == "text":
                        text = element.get("text", "")
                        parts.append(MessagePart(kind="text", text=text, sender_id=sender_id))
                    elif tag == "img":
                        image_key = element.get("image_key")
                        parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id, sender_id=sender_id))

        return parts

    def _is_duplicate_message(self, message_id: str) -> bool:
        """检查消息是否已处理过"""
        with self._dedup_lock:
            # 清理过期的消息记录
            current_time = time.time()
            expired_ids = [
                mid for mid, timestamp in self._processed_messages.items()
                if current_time - timestamp > self._dedup_expire_seconds
            ]
            for mid in expired_ids:
                del self._processed_messages[mid]

            # 检查是否重复
            return message_id in self._processed_messages

    def _mark_message_processed(self, message_id: str) -> None:
        """标记消息已处理"""
        with self._dedup_lock:
            self._processed_messages[message_id] = time.time()

    def _is_duplicate_action(self, action_id: str) -> bool:
        """检查卡片交互是否已处理过"""
        with self._action_dedup_lock:
            # 清理过期的交互记录
            current_time = time.time()
            expired_ids = [
                aid for aid, timestamp in self._processed_actions.items()
                if current_time - timestamp > self._action_dedup_expire_seconds
            ]
            for aid in expired_ids:
                del self._processed_actions[aid]

            # 检查是否重复
            return action_id in self._processed_actions

    def _mark_action_processed(self, action_id: str) -> None:
        """标记卡片交互已处理"""
        with self._action_dedup_lock:
            self._processed_actions[action_id] = time.time()

    def _handle_batch(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> None:
        """处理批量消息"""
        logger.info(f"[{self.bot_name}] ========== 开始处理批量消息 ==========")

        try:
            # 检查是否有活跃的会话（等待用户补充信息）
            if self.bot.conversation_manager.has_active_conversation(chat_id):
                logger.info(f"[{self.bot_name}] 检测到活跃会话，处理用户补充信息")

                # 获取发送者ID（从第一个part中获取）
                user_id = parts[0].sender_id if parts else None

                # 处理用户的补充回复
                answer = self.bot.handle_user_response(chat_id, parts, user_id)

                if answer:
                    # 如果有返回结果，发送消息
                    if status_msg_id:
                        # 更新状态消息
                        content = {
                            "config": {"wide_screen_mode": True},
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {"tag": "lark_md", "content": answer},
                                }
                            ],
                        }
                        self.client.update_message(status_msg_id, content)
                    else:
                        # 发送新消息
                        self.client.send_message(chat_id, answer)
            else:
                # 正常处理消息（Bot 内部会负责更新最终消息）
                answer = self.bot.process_messages(chat_id, parts, status_msg_id)

            logger.info(f"[{self.bot_name}] ========== 批量消息处理完成 ==========")

        except Exception as e:
            logger.error(f"[{self.bot_name}] 处理消息时发生错误: {e}", exc_info=True)
            if status_msg_id:
                error_content = {
                    "config": {"wide_screen_mode": True},
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": "**❌ 错误**\n\n处理消息时发生错误，请稍后重试。"},
                        }
                    ],
                }
                self.client.update_message(status_msg_id, error_content)

    def handle_card_action(self, data):
        """处理卡片交互事件（按钮点击）"""
        from lark_oapi.event.callback.model.p2_card_action_trigger import (
            P2CardActionTriggerResponse,
            CallBackToast
        )

        try:
            logger.info("=" * 60)
            logger.info(f"[{self.bot_name}] 收到卡片交互事件")

            # 获取按钮的值（SDK 已解析为字典对象）
            action = data.event.action
            action_value = action.value  # 直接使用字典，SDK 已处理

            logger.info(f"[{self.bot_name}] 按钮数据: {action_value}")

            # 获取上下文信息
            context = data.event.context
            message_id = context.open_message_id if hasattr(context, 'open_message_id') else None
            chat_id = context.open_chat_id if hasattr(context, 'open_chat_id') else None

            # 获取用户 ID
            user_id = None
            if hasattr(data.event, 'operator') and data.event.operator:
                operator = data.event.operator
                if hasattr(operator, 'user_id'):
                    user_id = operator.user_id

            # 卡片交互去重检查
            # 对于某些操作（如刷新、查看详情），使用 chat_id + action 来去重
            # 对于其他操作，使用 message_id + action_value + user_id
            action_type = action_value.get("action", "") if isinstance(action_value, dict) else ""

            # 刷新、查看类操作使用简化的去重键（避免 message_id 变化导致去重失效）
            if action_type in ["refresh", "view_details", "view_accounts", "view_debts", "get_advice"]:
                action_id = f"{chat_id}_{action_type}_{user_id}"
            else:
                # 其他操作使用完整的去重键
                action_id = f"{message_id}_{json.dumps(action_value, sort_keys=True)}_{user_id}"

            if self._is_duplicate_action(action_id):
                logger.warning(f"[{self.bot_name}] 检测到重复的卡片交互，跳过处理: action_id={action_id[:100]}...")
                # 返回一个空响应，不显示任何提示
                response = P2CardActionTriggerResponse()
                return response
            self._mark_action_processed(action_id)
            logger.info(f"[{self.bot_name}] 卡片交互已标记为处理中")

            # 检查 Bot 是否有自定义的 handle_card_action 方法
            if hasattr(self.bot, 'handle_card_action') and callable(getattr(self.bot, 'handle_card_action')):
                logger.info(f"[{self.bot_name}] 使用 Bot 自定义的卡片交互处理器（异步模式）")

                # 立即返回响应，提示正在处理
                toast = CallBackToast()
                toast.type = "info"
                toast.content = "⏳ 正在处理中，请稍候..."

                response = P2CardActionTriggerResponse()
                response.toast = toast

                logger.info(f"[{self.bot_name}] 立即返回响应，开始异步处理")

                # 在后台线程中异步处理
                def async_handle():
                    try:
                        logger.info(f"[{self.bot_name}] 后台线程开始处理卡片交互...")

                        # 调用 Bot 的 handle_card_action 方法
                        result = self.bot.handle_card_action(action_value, user_id, chat_id)

                        # 处理结果
                        if isinstance(result, dict):
                            # 如果返回了新卡片，更新原卡片
                            if "card" in result and message_id:
                                self.client.update_message(message_id, result["card"])
                                logger.info(f"[{self.bot_name}] 已更新卡片")

                            # 如果需要发送通知消息
                            if "toast" in result and chat_id:
                                # 通过新消息通知用户结果
                                toast_content = result["toast"].get("content", "处理完成")
                                toast_type = result["toast"].get("type", "info")

                                # 根据类型选择图标
                                icon_map = {
                                    "success": "✅",
                                    "error": "❌",
                                    "warning": "⚠️",
                                    "info": "ℹ️"
                                }
                                icon = icon_map.get(toast_type, "ℹ️")

                                content = {
                                    "config": {"wide_screen_mode": True},
                                    "elements": [
                                        {
                                            "tag": "div",
                                            "text": {"tag": "lark_md", "content": f"{icon} {toast_content}"}
                                        }
                                    ]
                                }
                                self.client.send_message(chat_id, content, msg_type="interactive")
                                logger.info(f"[{self.bot_name}] 已发送处理结果通知")

                        logger.info(f"[{self.bot_name}] 后台处理完成")

                    except Exception as e:
                        logger.error(f"[{self.bot_name}] 后台处理异常: {e}", exc_info=True)
                        # 发送错误通知
                        if chat_id:
                            error_msg = f"❌ **处理失败**\\n\\n{str(e)}"
                            content = {
                                "config": {"wide_screen_mode": True},
                                "elements": [
                                    {
                                        "tag": "div",
                                        "text": {"tag": "lark_md", "content": error_msg}
                                    }
                                ]
                            }
                            self.client.send_message(chat_id, content, msg_type="interactive")

                # 启动后台线程
                bg_thread = threading.Thread(target=async_handle, daemon=True)
                bg_thread.start()

                logger.info(f"[{self.bot_name}] 卡片交互处理完成（已启动后台处理）")
                logger.info("=" * 60)
                return response

            # 如果 Bot 没有自定义处理器，使用默认的 food_analyzer 逻辑
            logger.info(f"[{self.bot_name}] 使用默认的卡片交互处理器（food_analyzer 模式）")

            # 立即返回响应，提示正在处理
            toast = CallBackToast()
            toast.type = "info"
            toast.content = "⏳ 正在保存中，请稍候..."

            response = P2CardActionTriggerResponse()
            response.toast = toast

            logger.info(f"[{self.bot_name}] 立即返回响应，开始异步保存")

            # 在后台线程中异步处理保存
            def async_save():
                try:
                    logger.info(f"[{self.bot_name}] 后台线程开始保存...")

                    # 检查是否为批量导入
                    is_batch = isinstance(action_value, dict) and action_value.get("batch") == True

                    if is_batch:
                        # 批量导入模式
                        meals = action_value.get("meals", [])
                        logger.info(f"[{self.bot_name}] 批量导入模式，共 {len(meals)} 条记录")

                        success_count = 0
                        fail_count = 0

                        for idx, single_meal in enumerate(meals, start=1):
                            logger.info(f"[{self.bot_name}] 保存第 {idx}/{len(meals)} 条记录...")
                            if self.bot._save_to_bitable(single_meal):
                                success_count += 1
                            else:
                                fail_count += 1

                        logger.info(f"[{self.bot_name}] 批量导入完成: 成功 {success_count}/{len(meals)}")

                        # 发送批量结果通知
                        if chat_id:
                            if fail_count == 0:
                                result_msg = f"✅ **批量导入成功！**\n\n已成功保存 {success_count} 条饮食记录到多维表格"
                            else:
                                result_msg = f"⚠️ **批量导入部分完成**\n\n成功：{success_count} 条\n失败：{fail_count} 条\n\n请检查多维表格配置或稍后重试失败的记录"

                            content = {
                                "config": {"wide_screen_mode": True},
                                "elements": [
                                    {
                                        "tag": "div",
                                        "text": {"tag": "lark_md", "content": result_msg}
                                    }
                                ]
                            }
                            self.client.send_message(chat_id, content, msg_type="interactive")
                            logger.info(f"[{self.bot_name}] 已发送批量保存结果通知")
                    else:
                        # 单条导入模式（原有逻辑）
                        success = self.bot._save_to_bitable(action_value)

                        # 保存完成后，通过新消息通知用户结果
                        if chat_id:
                            if success:
                                result_msg = "✅ **导入成功！**\n\n数据已保存到多维表格"
                            else:
                                result_msg = "❌ **导入失败**\n\n请检查多维表格配置或稍后重试"

                            # 发送结果通知消息
                            content = {
                                "config": {"wide_screen_mode": True},
                                "elements": [
                                    {
                                        "tag": "div",
                                        "text": {"tag": "lark_md", "content": result_msg}
                                    }
                                ]
                            }
                            self.client.send_message(chat_id, content, msg_type="interactive")
                            logger.info(f"[{self.bot_name}] 已发送保存结果通知")

                        logger.info(f"[{self.bot_name}] 后台保存完成: {success}")

                except Exception as e:
                    logger.error(f"[{self.bot_name}] 后台保存异常: {e}", exc_info=True)
                    # 发送错误通知
                    if chat_id:
                        error_msg = f"❌ **保存异常**\n\n{str(e)}"
                        content = {
                            "config": {"wide_screen_mode": True},
                            "elements": [
                                {
                                    "tag": "div",
                                    "text": {"tag": "lark_md", "content": error_msg}
                                }
                            ]
                        }
                        self.client.send_message(chat_id, content, msg_type="interactive")

            # 启动后台线程
            thread = threading.Thread(target=async_save, daemon=True)
            thread.start()

            logger.info(f"[{self.bot_name}] 卡片交互处理完成（已启动后台保存）")
            logger.info("=" * 60)

            return response

        except Exception as e:
            logger.error(f"[{self.bot_name}] 处理卡片交互时发生错误: {e}", exc_info=True)

            # 返回错误响应
            toast = CallBackToast()
            toast.type = "error"
            toast.content = f"处理失败: {str(e)}"

            response = P2CardActionTriggerResponse()
            response.toast = toast
            return response


class FeishuBotFramework:
    """飞书机器人框架 - 多连接管理"""

    def __init__(self, config_file: str = "config/bots.yaml"):
        logger.info("*" * 60)
        logger.info("飞书机器人框架启动中...")
        logger.info("*" * 60)

        # 加载配置
        self.config = self._load_config(config_file)

        # 全局 AI 客户端（所有 Bot 共享）
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        # 备用 API 配置
        backup_api_key = os.getenv("OPENAI_API_KEY_BACKUP", "")
        backup_base_url = os.getenv("OPENAI_BASE_URL_BACKUP", "")

        # 重试配置
        max_retries = int(os.getenv("API_MAX_RETRIES", "3"))
        retry_delay = float(os.getenv("API_RETRY_DELAY", "2"))

        self.ai_client = AIClient(
            openai_api_key,
            openai_base_url,
            backup_api_key=backup_api_key if backup_api_key else None,
            backup_base_url=backup_base_url if backup_base_url else None,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # Bot 实例字典
        self.bot_instances: Dict[str, BotInstance] = {}

        # 日志配置
        self._log_config(openai_api_key, openai_base_url)

    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                logger.info(f"加载框架配置成功: {config_file}")
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _log_config(self, openai_api_key: str, openai_base_url: str):
        """记录配置信息"""
        logger.info("=" * 60)
        logger.info("全局配置:")
        logger.info(f"  主 API - OPENAI_API_KEY: {'已设置' if openai_api_key else '未设置'}")
        logger.info(f"  主 API - OPENAI_BASE_URL: {openai_base_url}")

        backup_api_key = os.getenv("OPENAI_API_KEY_BACKUP", "")
        backup_base_url = os.getenv("OPENAI_BASE_URL_BACKUP", "")
        logger.info(f"  备用 API - OPENAI_API_KEY_BACKUP: {'已设置' if backup_api_key else '未设置'}")
        logger.info(f"  备用 API - OPENAI_BASE_URL_BACKUP: {backup_base_url if backup_base_url else '未设置'}")

        max_retries = int(os.getenv("API_MAX_RETRIES", "3"))
        retry_delay = float(os.getenv("API_RETRY_DELAY", "2"))
        logger.info(f"  重试配置 - API_MAX_RETRIES: {max_retries}")
        logger.info(f"  重试配置 - API_RETRY_DELAY: {retry_delay}s")
        logger.info("=" * 60)

    def load_bots(self):
        """加载所有启用的 Bot"""
        logger.info("开始加载 Bot...")

        for bot_name, bot_config in self.config.get("bots", {}).items():
            if not bot_config.get("enabled", False):
                logger.info(f"跳过未启用的 Bot: {bot_name}")
                continue

            try:
                logger.info(f"加载 Bot: {bot_name}")

                # 加载 Bot 配置文件
                config_file = bot_config.get("config_file")
                with open(config_file, "r", encoding="utf-8") as f:
                    bot_specific_config = yaml.safe_load(f)

                # 验证飞书配置
                feishu_config = bot_specific_config.get("feishu", {})
                app_id = feishu_config.get("app_id")
                app_secret = feishu_config.get("app_secret")

                if not app_id or not app_secret:
                    logger.error(f"Bot {bot_name} 缺少飞书应用配置 (app_id/app_secret)")
                    continue

                # 创建飞书客户端
                client = FeishuClient(app_id, app_secret)

                # 创建消息批处理器
                batch_config = bot_specific_config.get("batch", {})
                window_seconds = batch_config.get("window_seconds", 12)
                batcher = MessageBatcher(window_seconds, client)

                # 动态加载 Bot 类
                module_name = bot_config["module"]
                class_name = bot_config["class"]
                module = importlib.import_module(module_name)
                bot_class = getattr(module, class_name)

                # 实例化 Bot
                bot = bot_class(bot_specific_config, client, self.ai_client)

                # 创建 Bot 实例
                instance = BotInstance(bot_name, bot, client, batcher, bot_specific_config)
                self.bot_instances[bot_name] = instance

                logger.info(f"Bot 加载成功: {bot_name} ({bot.name})")
                logger.info(f"  飞书应用: {app_id[:10]}...")
                logger.info(f"  批处理窗口: {window_seconds} 秒")

            except Exception as e:
                logger.error(f"加载 Bot {bot_name} 失败: {e}", exc_info=True)

        if not self.bot_instances:
            raise RuntimeError("没有可用的 Bot，请检查配置")

        logger.info(f"共加载 {len(self.bot_instances)} 个 Bot")

    def start(self):
        """启动所有 Bot 的 WebSocket 连接"""
        if not self.bot_instances:
            raise RuntimeError("请先调用 load_bots() 加载 Bot")

        logger.info("*" * 60)
        logger.info("启动所有 Bot 的 WebSocket 连接...")
        logger.info("*" * 60)

        threads = []

        for bot_name, instance in self.bot_instances.items():
            try:
                logger.info(f"为 Bot {bot_name} 创建 WebSocket 连接...")

                # 创建事件处理器
                handler = (
                    lark.EventDispatcherHandler.builder(
                        instance.client.app_id, instance.client.app_secret
                    )
                    .register_p2_im_message_receive_v1(instance.handle_message_receive)
                    .register_p2_card_action_trigger(instance.handle_card_action)
                    .build()
                )

                # 创建 WebSocket 客户端
                ws_client = lark.ws.Client(
                    instance.client.app_id, instance.client.app_secret, event_handler=handler
                )
                instance.ws_client = ws_client

                # 在独立线程中启动
                def start_ws(client, name):
                    try:
                        logger.info(f"Bot {name} WebSocket 连接已启动")
                        client.start()
                    except Exception as e:
                        logger.error(f"Bot {name} WebSocket 连接异常: {e}", exc_info=True)

                thread = threading.Thread(
                    target=start_ws, args=(ws_client, bot_name), name=f"Bot-{bot_name}", daemon=True
                )
                thread.start()
                threads.append(thread)

                logger.info(f"Bot {bot_name} 启动成功")

            except Exception as e:
                logger.error(f"启动 Bot {bot_name} 失败: {e}", exc_info=True)

        logger.info("*" * 60)
        logger.info(f"所有 Bot 已启动 ({len(threads)} 个连接)，等待消息...")
        logger.info("*" * 60)

        # 等待所有线程
        try:
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")


def main():
    """主入口"""
    framework = FeishuBotFramework()
    framework.load_bots()
    framework.start()


if __name__ == "__main__":
    main()
