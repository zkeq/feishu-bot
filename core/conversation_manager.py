"""
会话状态管理器
用于支持多轮对话和信息补充功能
"""
import time
import threading
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class ConversationState(Enum):
    """会话状态枚举"""
    WAITING_FOR_INPUT = "waiting_for_input"  # 等待用户补充信息
    PROCESSING = "processing"  # 正在处理中
    COMPLETED = "completed"  # 已完成


@dataclass
class ConversationContext:
    """会话上下文"""
    chat_id: str
    state: ConversationState
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default=0)

    # 原始任务信息
    original_parts: list = field(default_factory=list)  # 原始消息内容
    original_user_id: Optional[str] = None  # 原始发送者ID

    # 等待补充的信息
    waiting_for: str = ""  # 等待补充的信息描述
    question_message_id: Optional[str] = None  # 提问消息的ID

    # 回调处理
    callback_data: Dict[str, Any] = field(default_factory=dict)  # 回调需要的数据

    def __post_init__(self):
        if self.expires_at == 0:
            # 默认30分钟过期
            self.expires_at = self.created_at + 1800

    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return time.time() > self.expires_at

    def extend_expiry(self, seconds: int = 1800):
        """延长过期时间"""
        self.expires_at = time.time() + seconds


class ConversationManager:
    """会话管理器"""

    def __init__(self):
        self._conversations: Dict[str, ConversationContext] = {}
        self._lock = threading.Lock()

        # 启动清理线程
        self._cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self._cleanup_thread.start()

    def create_conversation(
        self,
        chat_id: str,
        original_parts: list,
        waiting_for: str,
        original_user_id: Optional[str] = None,
        callback_data: Optional[Dict[str, Any]] = None,
        expires_in: int = 1800
    ) -> ConversationContext:
        """
        创建新会话

        Args:
            chat_id: 聊天ID
            original_parts: 原始消息内容
            waiting_for: 等待补充的信息描述
            original_user_id: 原始发送者ID
            callback_data: 回调需要的数据
            expires_in: 过期时间（秒），默认30分钟

        Returns:
            ConversationContext: 会话上下文
        """
        with self._lock:
            context = ConversationContext(
                chat_id=chat_id,
                state=ConversationState.WAITING_FOR_INPUT,
                original_parts=original_parts,
                original_user_id=original_user_id,
                waiting_for=waiting_for,
                callback_data=callback_data or {},
                expires_at=time.time() + expires_in
            )
            self._conversations[chat_id] = context
            return context

    def get_conversation(self, chat_id: str) -> Optional[ConversationContext]:
        """
        获取会话上下文

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[ConversationContext]: 会话上下文，如果不存在或已过期则返回None
        """
        with self._lock:
            context = self._conversations.get(chat_id)
            if context and context.is_expired():
                # 自动清理过期会话
                del self._conversations[chat_id]
                return None
            return context

    def has_active_conversation(self, chat_id: str) -> bool:
        """
        检查是否有活跃的会话

        Args:
            chat_id: 聊天ID

        Returns:
            bool: 是否有活跃会话
        """
        context = self.get_conversation(chat_id)
        return context is not None and context.state == ConversationState.WAITING_FOR_INPUT

    def update_conversation(
        self,
        chat_id: str,
        state: Optional[ConversationState] = None,
        question_message_id: Optional[str] = None,
        callback_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新会话状态

        Args:
            chat_id: 聊天ID
            state: 新状态
            question_message_id: 提问消息ID
            callback_data: 更新回调数据

        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            context = self._conversations.get(chat_id)
            if not context:
                return False

            if state is not None:
                context.state = state
            if question_message_id is not None:
                context.question_message_id = question_message_id
            if callback_data is not None:
                context.callback_data.update(callback_data)

            # 延长过期时间
            context.extend_expiry()
            return True

    def complete_conversation(self, chat_id: str) -> Optional[ConversationContext]:
        """
        完成并移除会话

        Args:
            chat_id: 聊天ID

        Returns:
            Optional[ConversationContext]: 被移除的会话上下文
        """
        with self._lock:
            return self._conversations.pop(chat_id, None)

    def _cleanup_expired(self):
        """定期清理过期会话（后台线程）"""
        while True:
            time.sleep(300)  # 每5分钟清理一次
            with self._lock:
                expired_chats = [
                    chat_id for chat_id, ctx in self._conversations.items()
                    if ctx.is_expired()
                ]
                for chat_id in expired_chats:
                    del self._conversations[chat_id]

    def get_all_conversations(self) -> Dict[str, ConversationContext]:
        """获取所有活跃会话（用于调试）"""
        with self._lock:
            return self._conversations.copy()

    def clear_all(self):
        """清空所有会话（用于测试）"""
        with self._lock:
            self._conversations.clear()
