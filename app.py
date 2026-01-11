import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request

APP_ID = os.getenv("LARK_APP_ID", "")
APP_SECRET = os.getenv("LARK_APP_SECRET", "")
ENCRYPT_KEY = os.getenv("LARK_ENCRYPT_KEY", "")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是一个群聊里的智能助手，需要根据用户的文字和图片内容进行总结、分析并给出美观的回复。",
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BATCH_WINDOW_SECONDS = float(os.getenv("BATCH_WINDOW_SECONDS", "3"))

app = Flask(__name__)

_token_lock = threading.Lock()
_token_cache: Tuple[str, float] = ("", 0.0)


@dataclass
class MessagePart:
    kind: str
    text: Optional[str] = None
    image_key: Optional[str] = None
    image_data_url: Optional[str] = None


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


def verify_signature(timestamp: str, nonce: str, body: str, signature: str) -> bool:
    if not ENCRYPT_KEY:
        return True
    import hashlib
    import hmac

    sign_payload = f"{timestamp}{nonce}{body}".encode("utf-8")
    digest = hmac.new(ENCRYPT_KEY.encode("utf-8"), sign_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def get_tenant_access_token() -> str:
    global _token_cache
    with _token_lock:
        token, expiry = _token_cache
        if token and expiry > time.time() + 60:
            return token
        response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("tenant_access_token", "")
        expires_in = payload.get("expire", 0)
        _token_cache = (token, time.time() + expires_in)
        return token


def fetch_image_as_data_url(image_key: str) -> Optional[str]:
    token = get_tenant_access_token()
    if not token:
        return None
    response = requests.get(
        f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if response.status_code != 200:
        return None
    content_type = response.headers.get("Content-Type", "image/png")
    encoded = base64.b64encode(response.content).decode("utf-8")
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
    token = get_tenant_access_token()
    if not token:
        return
    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=10,
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


@app.route("/webhook", methods=["POST"])
def webhook() -> Any:
    body = request.get_data(as_text=True)
    data = request.json or {}

    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})

    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")

    if not verify_signature(timestamp, nonce, body, signature):
        return jsonify({"message": "invalid signature"}), 403

    event = data.get("event", {})
    if event.get("type") != "message":
        return jsonify({"message": "ignored"})

    message = event.get("message", {})
    chat_id = message.get("chat_id")
    if not chat_id:
        return jsonify({"message": "missing chat"})

    parts = parse_message_content(message.get("message_type", ""), message.get("content", ""))
    if parts:
        batcher.add(chat_id, parts, handle_batch)

    return jsonify({"message": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
