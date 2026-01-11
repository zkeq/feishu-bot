import base64
import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, ImageGetRequest

import requests

load_dotenv()

APP_ID = os.getenv("LARK_APP_ID", "")
APP_SECRET = os.getenv("LARK_APP_SECRET", "")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是一个群聊里的智能助手，需要根据用户的文字和图片内容进行总结、分析并给出美观的回复。",
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BATCH_WINDOW_SECONDS = float(os.getenv("BATCH_WINDOW_SECONDS", "3"))

client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()


@dataclass
class MessagePart:
    kind: str
    text: Optional[str] = None
    image_key: Optional[str] = None


class MessageBatcher:
    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buffers: Dict[str, List[MessagePart]] = {}
        self._timers: Dict[str, threading.Timer] = {}

    def add(self, chat_id: str, parts: List[MessagePart], callback) -> None:
        with self._lock:
            self._buffers.setdefault(chat_id, []).extend(parts)
            existing = self._timers.get(chat_id)
            if existing:
                existing.cancel()
            timer = threading.Timer(self.window_seconds, self._flush, args=(chat_id, callback))
            self._timers[chat_id] = timer
            timer.start()

    def _flush(self, chat_id: str, callback) -> None:
        with self._lock:
            parts = self._buffers.pop(chat_id, [])
            timer = self._timers.pop(chat_id, None)
            if timer:
                timer.cancel()
        if parts:
            callback(chat_id, parts)


batcher = MessageBatcher(BATCH_WINDOW_SECONDS)


def _read_image_bytes(response: Any) -> Optional[bytes]:
    if hasattr(response, "file") and response.file is not None:
        return response.file.read()
    raw = getattr(response, "raw", None)
    if raw is not None:
        return getattr(raw, "content", None)
    return None


def fetch_image_as_data_url(image_key: str) -> Optional[str]:
    request = ImageGetRequest.builder().image_key(image_key).build()
    response = client.im.v1.image.get(request)
    if not response.success():
        return None
    content = _read_image_bytes(response)
    if not content:
        return None
    content_type = "image/png"
    if hasattr(response, "content_type") and response.content_type:
        content_type = response.content_type
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def parse_message_content(msg_type: str, content: str) -> List[MessagePart]:
    parts: List[MessagePart] = []
    data = json.loads(content) if content else {}
    if msg_type == "text":
        parts.append(MessagePart(kind="text", text=data.get("text", "")))
    elif msg_type == "image":
        parts.append(MessagePart(kind="image", image_key=data.get("image_key")))
    elif msg_type == "post":
        for block in data.get("content", []):
            for element in block:
                if element.get("tag") == "text":
                    parts.append(MessagePart(kind="text", text=element.get("text", "")))
                elif element.get("tag") == "img":
                    parts.append(MessagePart(kind="image", image_key=element.get("image_key")))
    return parts


def build_openai_messages(parts: List[MessagePart]) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = []
    for part in parts:
        if part.kind == "text" and part.text:
            content.append({"type": "text", "text": part.text})
        elif part.kind == "image" and part.image_key:
            data_url = fetch_image_as_data_url(part.image_key)
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
            else:
                content.append({"type": "text", "text": f"[图片: {part.image_key}]"})
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def call_openai(parts: List[MessagePart]) -> str:
    messages = build_openai_messages(parts)
    response = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": 0.7,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"].strip()


def reply_to_chat(chat_id: str, text: str) -> None:
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )
    response = client.im.v1.message.create(request)
    if not response.success():
        lark.logger.error(
            "reply failed, code=%s msg=%s", response.code, response.msg
        )


def handle_batch(chat_id: str, parts: List[MessagePart]) -> None:
    if not OPENAI_API_KEY:
        reply_to_chat(chat_id, "未配置 OPENAI_API_KEY，暂时无法生成回复。")
        return
    try:
        answer = call_openai(parts)
    except requests.RequestException:
        reply_to_chat(chat_id, "调用模型失败，请稍后重试。")
        return
    reply_to_chat(chat_id, answer)


def handle_message_receive(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    message = data.event.message
    chat_id = message.chat_id
    parts = parse_message_content(message.message_type, message.content)
    if parts:
        batcher.add(chat_id, parts, handle_batch)


def main() -> None:
    if not APP_ID or not APP_SECRET:
        raise RuntimeError("请先设置 LARK_APP_ID 和 LARK_APP_SECRET")

    handler = (
        lark.EventDispatcherHandler.builder(APP_ID, APP_SECRET)
        .register_p2_im_message_receive_v1(handle_message_receive)
        .build()
    )
    lark.ws_client.start(handler)


if __name__ == "__main__":
    main()
