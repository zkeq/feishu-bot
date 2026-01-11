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
from typing import Any, Dict, List, Optional

import lark_oapi as lark
import yaml
from dotenv import load_dotenv

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
        logger.info(f"BotInstance 创建: {bot_name} ({bot.name})")

    def handle_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """处理消息接收事件"""
        try:
            logger.info("=" * 60)
            logger.info(f"[{self.bot_name}] 收到新消息事件")

            message = data.event.message
            chat_id = message.chat_id
            message_id = getattr(message, "message_id", "N/A")
            msg_type = message.message_type
            content = message.content

            logger.info(f"[{self.bot_name}] 消息详情:")
            logger.info(f"  chat_id: {chat_id}")
            logger.info(f"  message_id: {message_id}")
            logger.info(f"  message_type: {msg_type}")

            # 解析消息
            parts = self._parse_message_content(msg_type, content, message_id)

            if parts:
                logger.info(f"[{self.bot_name}] 消息解析成功，添加到批处理队列")
                self.batcher.add(chat_id, parts, self._handle_batch)
            else:
                logger.warning(f"[{self.bot_name}] 消息解析后没有有效的消息片段")

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"[{self.bot_name}] 处理消息接收事件时发生错误: {e}", exc_info=True)

    def _parse_message_content(self, msg_type: str, content: str, message_id: str) -> List[MessagePart]:
        """解析消息内容"""
        parts: List[MessagePart] = []
        data = json.loads(content) if content else {}

        if msg_type == "text":
            text = data.get("text", "")
            parts.append(MessagePart(kind="text", text=text))
        elif msg_type == "image":
            image_key = data.get("image_key")
            parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id))
        elif msg_type == "post":
            for block in data.get("content", []):
                for element in block:
                    tag = element.get("tag")
                    if tag == "text":
                        text = element.get("text", "")
                        parts.append(MessagePart(kind="text", text=text))
                    elif tag == "img":
                        image_key = element.get("image_key")
                        parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id))

        return parts

    def _handle_batch(self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> None:
        """处理批量消息"""
        logger.info(f"[{self.bot_name}] ========== 开始处理批量消息 ==========")

        try:
            # Bot 处理消息（Bot 内部会负责更新最终消息）
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

            # 获取按钮的值（应该是字典格式的 meal_data）
            action = data.event.action
            meal_data = action.value  # 直接是字典，不需要 JSON 解析

            logger.info(f"[{self.bot_name}] 按钮数据: {meal_data}")

            # 调用 bot 的保存方法
            success = self.bot._save_to_bitable(meal_data)

            # 创建响应
            if success:
                toast = CallBackToast()
                toast.type = "success"
                toast.content = "✅ 导入成功！数据已保存到多维表格"
            else:
                toast = CallBackToast()
                toast.type = "error"
                toast.content = "❌ 导入失败，请检查多维表格配置或稍后重试"

            response = P2CardActionTriggerResponse()
            response.toast = toast

            logger.info(f"[{self.bot_name}] 卡片交互处理完成")
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
        self.ai_client = AIClient(openai_api_key, openai_base_url)

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
        logger.info(f"  OPENAI_API_KEY: {'已设置' if openai_api_key else '未设置'}")
        logger.info(f"  OPENAI_BASE_URL: {openai_base_url}")
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
