"""
对话历史管理器
用于存储和管理用户的对话历史记录
"""
import time
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """单条对话消息"""
    role: str  # "user" 或 "assistant"
    content: str  # 消息内容
    timestamp: float = field(default_factory=time.time)


class ChatHistoryManager:
    """对话历史管理器"""

    def __init__(self, max_messages_per_chat: int = 20, expire_seconds: int = 3600):
        """
        初始化对话历史管理器

        Args:
            max_messages_per_chat: 每个会话最多保存的消息数量
            expire_seconds: 对话历史过期时间（秒），默认1小时
        """
        self._histories: Dict[str, List[ChatMessage]] = {}
        self._last_access: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._max_messages = max_messages_per_chat
        self._expire_seconds = expire_seconds

        # 启动清理线程
        self._cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self._cleanup_thread.start()

    def add_message(self, chat_id: str, role: str, content: str):
        """
        添加一条消息到历史记录

        Args:
            chat_id: 会话 ID
            role: 角色（"user" 或 "assistant"）
            content: 消息内容
        """
        with self._lock:
            if chat_id not in self._histories:
                self._histories[chat_id] = []

            message = ChatMessage(role=role, content=content)
            self._histories[chat_id].append(message)

            # 限制历史记录数量
            if len(self._histories[chat_id]) > self._max_messages:
                self._histories[chat_id] = self._histories[chat_id][-self._max_messages:]

            # 更新最后访问时间
            self._last_access[chat_id] = time.time()

    def get_history(self, chat_id: str, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """
        获取对话历史记录

        Args:
            chat_id: 会话 ID
            max_messages: 最多返回的消息数量，None 表示返回所有

        Returns:
            List[Dict]: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
        """
        with self._lock:
            if chat_id not in self._histories:
                return []

            # 更新最后访问时间
            self._last_access[chat_id] = time.time()

            messages = self._histories[chat_id]
            if max_messages:
                messages = messages[-max_messages:]

            return [{"role": msg.role, "content": msg.content} for msg in messages]

    def clear_history(self, chat_id: str):
        """
        清空指定会话的历史记录

        Args:
            chat_id: 会话 ID
        """
        with self._lock:
            if chat_id in self._histories:
                del self._histories[chat_id]
            if chat_id in self._last_access:
                del self._last_access[chat_id]

    def has_history(self, chat_id: str) -> bool:
        """
        检查是否有历史记录

        Args:
            chat_id: 会话 ID

        Returns:
            bool: 是否有历史记录
        """
        with self._lock:
            return chat_id in self._histories and len(self._histories[chat_id]) > 0

    def get_recent_context(self, chat_id: str, max_turns: int = 3) -> str:
        """
        获取最近几轮对话的文本摘要

        Args:
            chat_id: 会话 ID
            max_turns: 最多返回的对话轮数

        Returns:
            str: 对话摘要文本
        """
        history = self.get_history(chat_id, max_messages=max_turns * 2)
        if not history:
            return ""

        context_lines = []
        for msg in history:
            role_name = "用户" if msg["role"] == "user" else "助手"
            context_lines.append(f"{role_name}: {msg['content'][:200]}")  # 限制每条消息长度

        return "\n".join(context_lines)

    def _cleanup_expired(self):
        """定期清理过期的对话历史（后台线程）"""
        while True:
            time.sleep(600)  # 每10分钟清理一次
            current_time = time.time()
            with self._lock:
                expired_chats = [
                    chat_id for chat_id, last_time in self._last_access.items()
                    if current_time - last_time > self._expire_seconds
                ]
                for chat_id in expired_chats:
                    if chat_id in self._histories:
                        del self._histories[chat_id]
                    if chat_id in self._last_access:
                        del self._last_access[chat_id]

    def get_all_chats(self) -> List[str]:
        """获取所有有历史记录的会话 ID（用于调试）"""
        with self._lock:
            return list(self._histories.keys())
