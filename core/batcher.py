"""
消息批处理器
自动合并时间窗口内的多条消息
"""
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class MessagePart:
    """消息片段"""
    kind: str
    text: Optional[str] = None
    image_key: Optional[str] = None
    message_id: Optional[str] = None
    sender_id: Optional[str] = None  # 发送者的 user_id 或 open_id


@dataclass
class BatchState:
    """批处理状态"""
    chat_id: str
    parts: List[MessagePart]
    status_message_id: Optional[str] = None
    countdown: int = 0


class MessageBatcher:
    """消息批处理器"""

    def __init__(self, window_seconds: float, client):
        self.window_seconds = window_seconds
        self.client = client
        self._lock = threading.Lock()
        self._buffers: Dict[str, List[MessagePart]] = {}
        self._timers: Dict[str, threading.Timer] = {}
        self._states: Dict[str, BatchState] = {}
        self._update_timers: Dict[str, threading.Timer] = {}
        logger.info(f"MessageBatcher 初始化完成，批处理窗口时间: {window_seconds} 秒")

    def add(self, chat_id: str, parts: List[MessagePart], callback: Callable) -> None:
        """添加消息到批处理队列"""
        with self._lock:
            self._buffers.setdefault(chat_id, []).extend(parts)

            # 如果是新的批处理，发送初始状态消息
            if chat_id not in self._states:
                state = BatchState(chat_id=chat_id, parts=[], countdown=int(self.window_seconds))
                self._states[chat_id] = state
                status_msg_id = self._send_initial_status(chat_id)
                state.status_message_id = status_msg_id
                self._start_countdown(chat_id)
            else:
                # 已有批处理进行中，撤回旧消息并发送新的
                state = self._states[chat_id]
                if state.status_message_id:
                    logger.info(f"[chat_id={chat_id}] 用户发送新消息，撤回旧状态消息并重新发送")
                    self.client.delete_message(state.status_message_id)

                    # 取消旧的倒计时定时器
                    old_update_timer = self._update_timers.pop(chat_id, None)
                    if old_update_timer:
                        old_update_timer.cancel()

                    # 发送新的状态消息
                    status_msg_id = self._send_initial_status(chat_id)
                    state.status_message_id = status_msg_id
                    self._start_countdown(chat_id)

            # 更新状态中的消息片段
            self._states[chat_id].parts = self._buffers[chat_id].copy()

            existing = self._timers.get(chat_id)
            if existing:
                existing.cancel()
                logger.debug(f"[chat_id={chat_id}] 取消之前的定时器，重置倒计时")
                self._states[chat_id].countdown = int(self.window_seconds)

            timer = threading.Timer(self.window_seconds, self._flush, args=(chat_id, callback))
            self._timers[chat_id] = timer
            timer.start()

            logger.info(f"[chat_id={chat_id}] 添加消息片段: {len(parts)} 个, 当前缓冲区共: {len(self._buffers[chat_id])} 个")

    def _send_initial_status(self, chat_id: str) -> Optional[str]:
        """发送初始状态消息"""
        content = self._build_status_content(chat_id)
        return self.client.send_message(chat_id, content, "interactive")

    def _build_status_content(self, chat_id: str) -> Dict[str, Any]:
        """构建状态消息内容"""
        state = self._states.get(chat_id)
        if not state:
            return {}

        parts_count = len(state.parts)
        text_count = sum(1 for p in state.parts if p.kind == "text")
        image_count = sum(1 for p in state.parts if p.kind == "image")

        status_text = f"**📝 收到您的请求，正在准备处理...**\n\n"
        status_text += f"⏱️ 倒计时: **{state.countdown}** 秒\n"
        status_text += f"📊 当前窗口消息: **{parts_count}** 条\n"
        if text_count > 0:
            status_text += f"  • 文本: {text_count} 条\n"
        if image_count > 0:
            status_text += f"  • 图片: {image_count} 张\n"
        status_text += f"\n💡 继续发送消息将自动合并处理"

        return {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": status_text}
                }
            ]
        }

    def _update_status(self, chat_id: str) -> None:
        """更新状态消息"""
        state = self._states.get(chat_id)
        if not state or not state.status_message_id:
            return

        content = self._build_status_content(chat_id)
        self.client.update_message(state.status_message_id, content)

    def _start_countdown(self, chat_id: str) -> None:
        """启动倒计时更新"""
        def countdown_tick():
            with self._lock:
                state = self._states.get(chat_id)
                if not state or state.countdown <= 0:
                    return

                state.countdown -= 1
                self._update_status(chat_id)

                if state.countdown > 0:
                    timer = threading.Timer(1.0, countdown_tick)
                    self._update_timers[chat_id] = timer
                    timer.start()

        timer = threading.Timer(1.0, countdown_tick)
        self._update_timers[chat_id] = timer
        timer.start()

    def _flush(self, chat_id: str, callback: Callable) -> None:
        """触发批处理"""
        with self._lock:
            parts = self._buffers.pop(chat_id, [])
            timer = self._timers.pop(chat_id, None)
            state = self._states.pop(chat_id, None)
            update_timer = self._update_timers.pop(chat_id, None)

            if timer:
                timer.cancel()
            if update_timer:
                update_timer.cancel()

        if parts:
            logger.info(f"[chat_id={chat_id}] 触发批处理，共 {len(parts)} 个消息片段")
            status_msg_id = state.status_message_id if state else None
            callback(chat_id, parts, status_msg_id)
        else:
            logger.warning(f"[chat_id={chat_id}] 批处理触发但没有消息片段")
