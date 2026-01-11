"""
Bot 基类
所有具体的 Bot 都继承这个基类
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.client import FeishuClient
from core.batcher import MessagePart

logger = logging.getLogger(__name__)


class BaseBot(ABC):
    """Bot 基类"""

    def __init__(self, config: Dict[str, Any], client: FeishuClient):
        self.config = config
        self.client = client
        self.name = config.get("name", "UnnamedBot")
        self.system_prompt = config.get("system_prompt", "你是一个智能助手")
        logger.info(f"Bot 初始化: {self.name}")

    @abstractmethod
    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """
        处理批量消息，返回回复内容

        Args:
            chat_id: 会话 ID
            parts: 消息片段列表
            status_msg_id: 状态消息 ID

        Returns:
            str: 要回复的内容（Markdown 格式）
        """
        pass

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.system_prompt

    def on_error(self, error: Exception, chat_id: str) -> str:
        """错误处理，返回错误提示"""
        logger.error(f"[{self.name}] 处理消息出错: {error}", exc_info=True)
        return "抱歉，处理您的请求时出现了错误，请稍后重试。"

    def validate_config(self) -> bool:
        """验证配置是否有效"""
        required_fields = ["name"]
        for field in required_fields:
            if field not in self.config:
                logger.error(f"Bot 配置缺少必需字段: {field}")
                return False
        return True
