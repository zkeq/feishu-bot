"""
Bot 基类
所有具体的 Bot 都继承这个基类
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable

from core.client import FeishuClient
from core.batcher import MessagePart
from core.conversation_manager import ConversationManager, ConversationState

logger = logging.getLogger(__name__)


class BaseBot(ABC):
    """Bot 基类"""

    def __init__(self, config: Dict[str, Any], client: FeishuClient, ai_client=None, conversation_manager: Optional[ConversationManager] = None):
        self.config = config
        self.client = client
        self.ai_client = ai_client  # 添加 ai_client 支持（可选）
        self.name = config.get("name", "UnnamedBot")
        self.system_prompt = config.get("system_prompt", "你是一个智能助手")
        self.conversation_manager = conversation_manager or ConversationManager()
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

    def ask_user(
        self,
        chat_id: str,
        question: str,
        original_parts: List[MessagePart],
        callback_data: Optional[Dict[str, Any]] = None,
        original_user_id: Optional[str] = None
    ) -> str:
        """
        向用户询问补充信息

        Args:
            chat_id: 会话 ID
            question: 要问的问题
            original_parts: 原始消息内容
            callback_data: 回调需要的数据（用于继续处理）
            original_user_id: 原始发送者ID

        Returns:
            str: 提问消息（会发送给用户）
        """
        # 创建会话上下文
        context = self.conversation_manager.create_conversation(
            chat_id=chat_id,
            original_parts=original_parts,
            waiting_for=question,
            original_user_id=original_user_id,
            callback_data=callback_data or {}
        )

        logger.info(f"[{self.name}] 创建会话等待用户补充信息: {chat_id}")

        # 返回提问消息
        return f"**需要补充信息**\n\n{question}\n\n_请直接回复您的答案，我会继续处理您的请求。_"

    def handle_user_response(
        self,
        chat_id: str,
        parts: List[MessagePart],
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        处理用户的补充回复
        子类可以重写此方法来自定义处理逻辑

        Args:
            chat_id: 会话 ID
            parts: 用户回复的消息内容
            user_id: 用户ID

        Returns:
            Optional[str]: 处理结果消息，如果返回 None 则表示需要子类自行处理
        """
        context = self.conversation_manager.get_conversation(chat_id)
        if not context:
            return None

        # 默认实现：将原始消息和用户回复合并后重新处理
        logger.info(f"[{self.name}] 收到用户补充信息，继续处理: {chat_id}")

        # 合并原始消息和用户回复
        combined_parts = context.original_parts + parts

        # 完成会话
        self.conversation_manager.complete_conversation(chat_id)

        # 重新处理消息（不传 status_msg_id，因为这是继续处理）
        return self.process_messages(chat_id, combined_parts, None)
