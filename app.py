import base64
import json
import logging
import mimetypes
import os
import ssl
import sys
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    PatchMessageRequest,
    PatchMessageRequestBody,
    DeleteMessageRequest,
)

import importlib.metadata
import requests
import websockets

load_dotenv()

# 配置详细的日志输出
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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
INSECURE_WS = os.getenv("LARK_WS_INSECURE", "").lower() in {"1", "true", "yes"}
SKIP_IMAGE_DOWNLOAD = os.getenv("SKIP_IMAGE_DOWNLOAD", "").lower() in {"1", "true", "yes"}
WS_CA_BUNDLE = (
    os.getenv("LARK_WS_CA_BUNDLE", "")
    or os.getenv("SSL_CERT_FILE", "")
    or os.getenv("REQUESTS_CA_BUNDLE", "")
)

logger.info("=" * 60)
logger.info("环境变量配置加载完成:")
logger.info(f"  LARK_APP_ID: {APP_ID[:10]}..." if APP_ID else "  LARK_APP_ID: 未设置")
logger.info(f"  LARK_APP_SECRET: {'已设置' if APP_SECRET else '未设置'}")
logger.info(f"  OPENAI_API_KEY: {'已设置' if OPENAI_API_KEY else '未设置'}")
logger.info(f"  OPENAI_BASE_URL: {OPENAI_BASE_URL}")
logger.info(f"  OPENAI_MODEL: {OPENAI_MODEL}")
logger.info(f"  BATCH_WINDOW_SECONDS: {BATCH_WINDOW_SECONDS}")
logger.info(f"  LARK_WS_INSECURE: {INSECURE_WS}")
logger.info(f"  WS_CA_BUNDLE: {WS_CA_BUNDLE if WS_CA_BUNDLE else '未设置'}")
logger.info("=" * 60)

_original_ws_connect = websockets.connect


def _patched_ws_connect(*args, **kwargs):  # type: ignore[no-untyped-def]
    if "ssl" not in kwargs:
        if INSECURE_WS:
            kwargs["ssl"] = ssl._create_unverified_context()
        elif WS_CA_BUNDLE:
            kwargs["ssl"] = ssl.create_default_context(cafile=WS_CA_BUNDLE)
    return _original_ws_connect(*args, **kwargs)


websockets.connect = _patched_ws_connect  # type: ignore[assignment]

client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()


@dataclass
class MessagePart:
    kind: str
    text: Optional[str] = None
    image_key: Optional[str] = None
    message_id: Optional[str] = None  # 用于获取图片资源


@dataclass
class BatchState:
    """批处理状态，用于跟踪和更新"""
    chat_id: str
    parts: List[MessagePart]
    status_message_id: Optional[str] = None
    countdown: int = 0


class MessageBatcher:
    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buffers: Dict[str, List[MessagePart]] = {}
        self._timers: Dict[str, threading.Timer] = {}
        self._states: Dict[str, BatchState] = {}  # 存储批处理状态
        self._update_timers: Dict[str, threading.Timer] = {}  # 状态更新定时器
        logger.info(f"MessageBatcher 初始化完成，批处理窗口时间: {window_seconds} 秒")

    def add(self, chat_id: str, parts: List[MessagePart], callback) -> None:
        with self._lock:
            self._buffers.setdefault(chat_id, []).extend(parts)

            # 如果是新的批处理，发送初始状态消息
            if chat_id not in self._states:
                state = BatchState(chat_id=chat_id, parts=[], countdown=int(self.window_seconds))
                self._states[chat_id] = state
                # 发送初始状态消息
                status_msg_id = self._send_initial_status(chat_id)
                state.status_message_id = status_msg_id
                # 启动倒计时更新
                self._start_countdown(chat_id)
            else:
                # 已有批处理进行中，用户发送了新消息
                # 撤回旧的状态消息，发送新的
                state = self._states[chat_id]
                if state.status_message_id:
                    logger.info(f"[chat_id={chat_id}] 用户发送新消息，撤回旧状态消息并重新发送")
                    self._delete_status_message(chat_id, state.status_message_id)

                    # 取消旧的倒计时定时器
                    old_update_timer = self._update_timers.pop(chat_id, None)
                    if old_update_timer:
                        old_update_timer.cancel()

                    # 发送新的状态消息
                    status_msg_id = self._send_initial_status(chat_id)
                    state.status_message_id = status_msg_id

                    # 重新启动倒计时更新
                    self._start_countdown(chat_id)

            # 更新状态中的消息片段
            self._states[chat_id].parts = self._buffers[chat_id].copy()

            existing = self._timers.get(chat_id)
            if existing:
                existing.cancel()
                logger.debug(f"[chat_id={chat_id}] 取消之前的定时器，重置倒计时")
                # 重置倒计时
                self._states[chat_id].countdown = int(self.window_seconds)

            timer = threading.Timer(self.window_seconds, self._flush, args=(chat_id, callback))
            self._timers[chat_id] = timer
            timer.start()

            logger.info(f"[chat_id={chat_id}] 添加消息片段: {len(parts)} 个, 当前缓冲区共: {len(self._buffers[chat_id])} 个消息片段")
            for i, part in enumerate(parts):
                if part.kind == "text":
                    logger.debug(f"  片段 {i+1}: [文本] {part.text}")
                elif part.kind == "image":
                    logger.debug(f"  片段 {i+1}: [图片] key={part.image_key}")

    def _send_initial_status(self, chat_id: str) -> Optional[str]:
        """发送初始状态消息"""
        try:
            content = self._build_status_content(chat_id)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(content, ensure_ascii=False))
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.create(request)
            if response.success() and response.data:
                msg_id = response.data.message_id
                logger.info(f"[chat_id={chat_id}] 发送初始状态消息成功, message_id={msg_id}")
                return msg_id
            else:
                logger.error(f"[chat_id={chat_id}] 发送初始状态消息失败")
                return None
        except Exception as e:
            logger.error(f"[chat_id={chat_id}] 发送初始状态消息异常: {e}", exc_info=True)
            return None

    def _delete_status_message(self, chat_id: str, message_id: str) -> None:
        """撤回状态消息"""
        try:
            request = DeleteMessageRequest.builder().message_id(message_id).build()
            response = client.im.v1.message.delete(request)
            if response.success():
                logger.info(f"[chat_id={chat_id}] 撤回状态消息成功, message_id={message_id}")
            else:
                logger.warning(f"[chat_id={chat_id}] 撤回状态消息失败: {response.code} {response.msg}")
        except Exception as e:
            logger.error(f"[chat_id={chat_id}] 撤回状态消息异常: {e}", exc_info=True)

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
                    "text": {
                        "tag": "lark_md",
                        "content": status_text
                    }
                }
            ]
        }

    def _update_status(self, chat_id: str) -> None:
        """更新状态消息"""
        state = self._states.get(chat_id)
        if not state or not state.status_message_id:
            return

        try:
            content = self._build_status_content(chat_id)
            request = (
                PatchMessageRequest.builder()
                .message_id(state.status_message_id)
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(json.dumps(content, ensure_ascii=False))
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.patch(request)
            if not response.success():
                logger.warning(f"[chat_id={chat_id}] 更新状态消息失败: {response.code} {response.msg}")
        except Exception as e:
            logger.error(f"[chat_id={chat_id}] 更新状态消息异常: {e}", exc_info=True)

    def _start_countdown(self, chat_id: str) -> None:
        """启动倒计时更新"""
        def countdown_tick():
            with self._lock:
                state = self._states.get(chat_id)
                if not state or state.countdown <= 0:
                    return

                state.countdown -= 1
                self._update_status(chat_id)

                # 如果还有时间，继续倒计时
                if state.countdown > 0:
                    timer = threading.Timer(1.0, countdown_tick)
                    self._update_timers[chat_id] = timer
                    timer.start()

        # 启动第一次倒计时
        timer = threading.Timer(1.0, countdown_tick)
        self._update_timers[chat_id] = timer
        timer.start()

    def _flush(self, chat_id: str, callback) -> None:
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
            # 传递状态消息 ID 给回调函数
            status_msg_id = state.status_message_id if state else None
            callback(chat_id, parts, status_msg_id)
        else:
            logger.warning(f"[chat_id={chat_id}] 批处理触发但没有消息片段")


batcher = MessageBatcher(BATCH_WINDOW_SECONDS)


def fetch_image_as_data_url(message_id: str, image_key: str) -> Optional[str]:
    logger.debug(f"开始获取图片: message_id={message_id}, image_key={image_key}")
    try:
        request = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(image_key)
            .type("image")
            .build()
        )
        response = client.im.v1.message_resource.get(request)
        if not response.success():
            logger.error(f"获取图片失败: message_id={message_id}, image_key={image_key}, code={response.code}, msg={response.msg}")
            logger.debug(f"响应详情: {response}")
            return None
        if not response.file:
            logger.error(f"获取图片失败: message_id={message_id}, image_key={image_key}, 响应中没有文件内容")
            return None
        content_type, _ = mimetypes.guess_type(response.file_name or "")
        if not content_type:
            content_type = "image/png"
        file_content = response.file.read()
        encoded = base64.b64encode(file_content).decode("utf-8")
        logger.info(f"图片获取成功: message_id={message_id}, image_key={image_key}, content_type={content_type}, size={len(file_content)} bytes")
        return f"data:{content_type};base64,{encoded}"
    except Exception as e:
        logger.error(f"获取图片时发生异常: message_id={message_id}, image_key={image_key}, error={e}", exc_info=True)
        return None


def parse_message_content(msg_type: str, content: str, message_id: str) -> List[MessagePart]:
    logger.debug(f"开始解析消息: msg_type={msg_type}, message_id={message_id}")
    logger.debug(f"消息内容 (原始): {content}")
    parts: List[MessagePart] = []
    data = json.loads(content) if content else {}
    logger.debug(f"消息内容 (解析后): {json.dumps(data, ensure_ascii=False, indent=2)}")

    if msg_type == "text":
        text = data.get("text", "")
        parts.append(MessagePart(kind="text", text=text))
        logger.info(f"解析文本消息: {text}")
    elif msg_type == "image":
        image_key = data.get("image_key")
        parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id))
        logger.info(f"解析图片消息: image_key={image_key}")
    elif msg_type == "post":
        logger.debug(f"解析富文本消息，内容块数: {len(data.get('content', []))}")
        for block_idx, block in enumerate(data.get("content", [])):
            logger.debug(f"  块 {block_idx + 1}: {len(block)} 个元素")
            for element_idx, element in enumerate(block):
                tag = element.get("tag")
                logger.debug(f"    元素 {element_idx + 1}: tag={tag}")
                if tag == "text":
                    text = element.get("text", "")
                    parts.append(MessagePart(kind="text", text=text))
                    logger.info(f"    解析文本元素: {text}")
                elif tag == "img":
                    image_key = element.get("image_key")
                    parts.append(MessagePart(kind="image", image_key=image_key, message_id=message_id))
                    logger.info(f"    解析图片元素: image_key={image_key}")
    else:
        logger.warning(f"未知的消息类型: {msg_type}")

    logger.info(f"消息解析完成，共 {len(parts)} 个消息片段")
    return parts


def build_openai_messages(parts: List[MessagePart]) -> List[Dict[str, Any]]:
    logger.debug(f"开始构建 OpenAI 消息，共 {len(parts)} 个消息片段")
    content: List[Dict[str, Any]] = []
    for i, part in enumerate(parts):
        if part.kind == "text" and part.text:
            content.append({"type": "text", "text": part.text})
            logger.debug(f"  片段 {i+1}: [文本] {part.text[:50]}...")
        elif part.kind == "image" and part.image_key and part.message_id:
            data_url = fetch_image_as_data_url(part.message_id, part.image_key)
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
                logger.debug(f"  片段 {i+1}: [图片] 已获取 data_url")
            else:
                content.append({"type": "text", "text": f"[图片: {part.image_key}]"})
                logger.warning(f"  片段 {i+1}: [图片] 获取失败，使用占位符")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
    logger.info(f"OpenAI 消息构建完成，内容元素数: {len(content)}")
    logger.debug(f"完整消息结构: {json.dumps(messages, ensure_ascii=False, indent=2)[:500]}...")
    return messages


def update_status_message(chat_id: str, message_id: str, content: str) -> None:
    """更新状态消息"""
    try:
        content_json = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                }
            ]
        }
        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(json.dumps(content_json, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = client.im.v1.message.patch(request)
        if not response.success():
            logger.warning(f"[chat_id={chat_id}] 更新状态消息失败: {response.code} {response.msg}")
    except Exception as e:
        logger.error(f"[chat_id={chat_id}] 更新状态消息异常: {e}", exc_info=True)


def call_openai(parts: List[MessagePart], status_msg_id: Optional[str], chat_id: str) -> str:
    logger.info(f"开始调用 OpenAI API: model={OPENAI_MODEL}, base_url={OPENAI_BASE_URL}")
    messages = build_openai_messages(parts)

    # 更新状态：正在构建请求
    if status_msg_id:
        update_status_message(chat_id, status_msg_id, "**🔧 正在构建请求...**\n\n准备调用 AI API")

    try:
        logger.debug(f"发送流式请求到 {OPENAI_BASE_URL}/chat/completions")

        # 更新状态：正在请求
        if status_msg_id:
            update_status_message(chat_id, status_msg_id, "**🚀 正在请求 AI API...**\n\n等待响应中...")

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
                "stream": True,  # 启用流式响应
            },
            timeout=60,
            stream=True,  # 重要：requests 也要设置 stream=True
        )
        logger.debug(f"收到流式响应: status_code={response.status_code}")

        response.raise_for_status()

        # 更新状态：正在接收
        if status_msg_id:
            update_status_message(chat_id, status_msg_id, "**📥 正在接收 AI 回复...**\n\n")

        # 处理流式响应
        full_content = ""
        last_update_time = 0
        UPDATE_INTERVAL = 0.5  # 每 0.5 秒更新一次消息
        import time

        for line in response.iter_lines():
            if not line:
                continue

            line_text = line.decode('utf-8')
            if not line_text.startswith('data: '):
                continue

            data_str = line_text[6:]  # 移除 'data: ' 前缀
            if data_str == '[DONE]':
                break

            try:
                data = json.loads(data_str)
                choices = data.get('choices', [])

                # 安全检查：确保 choices 不为空
                if not choices:
                    continue

                delta = choices[0].get('delta', {})
                content = delta.get('content', '')

                if content:
                    full_content += content

                    # 定期更新消息
                    current_time = time.time()
                    if status_msg_id and (current_time - last_update_time) >= UPDATE_INTERVAL:
                        update_status_message(
                            chat_id,
                            status_msg_id,
                            f"**📝 AI 正在回复中...**\n\n{preprocess_markdown_for_feishu(full_content)}\n\n_正在生成中..._"
                        )
                        last_update_time = current_time

            except json.JSONDecodeError as e:
                logger.warning(f"解析流式响应失败: {e}, line={data_str[:100]}")
                continue
            except Exception as e:
                logger.warning(f"处理流式响应行时出错: {e}, line={data_str[:100]}")
                continue

        if not full_content:
            raise ValueError("流式响应未返回任何内容")

        logger.info(f"OpenAI API 流式调用成功，总响应长度: {len(full_content)} 字符")
        logger.debug(f"完整响应内容: {full_content[:200]}...")
        return full_content.strip()

    except requests.exceptions.Timeout as e:
        logger.error(f"OpenAI API 调用超时: {e}")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"OpenAI API HTTP 错误: status_code={response.status_code}, response={response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenAI API 请求失败: {e}")
        raise
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"解析 OpenAI 响应失败: {e}")
        raise


def preprocess_markdown_for_feishu(text: str) -> str:
    """
    预处理 Markdown 文本，适配飞书 lark_md 格式
    - 将标题 (# H1, ## H2 等) 转换为加粗格式
    - 保留其他 Markdown 语法
    """
    logger.debug("开始预处理 Markdown 文本")

    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        # 匹配标题格式 (# Title, ## Title, ### Title 等)
        if line.strip().startswith('#'):
            # 移除 # 符号，提取标题文本
            title_text = line.lstrip('#').strip()
            if title_text:
                # 转换为加粗格式，并在前后添加空行以保持段落分隔
                processed_lines.append(f"**{title_text}**")
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)

    result = '\n'.join(processed_lines)
    logger.debug(f"Markdown 预处理完成，原始长度: {len(text)}, 处理后长度: {len(result)}")
    return result


def reply_to_chat(chat_id: str, text: str) -> None:
    logger.info(f"[chat_id={chat_id}] 开始发送回复消息，长度: {len(text)} 字符")
    logger.debug(f"[chat_id={chat_id}] 回复内容: {text[:200]}...")

    # 预处理 Markdown，将标题转换为加粗
    processed_text = preprocess_markdown_for_feishu(text)

    # 使用交互式卡片 + lark_md 直接支持 Markdown
    try:
        content_json = {
            "config": {
                "wide_screen_mode": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": processed_text
                    }
                }
            ]
        }
        msg_type = "interactive"
        logger.debug(f"[chat_id={chat_id}] 使用交互式卡片 + Markdown 格式")
    except Exception as e:
        logger.warning(f"[chat_id={chat_id}] 构建交互式卡片失败，回退到纯文本: {e}")
        msg_type = "text"
        content_json = {"text": text}

    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type(msg_type)
            .content(json.dumps(content_json, ensure_ascii=False))
            .build()
        )
        .build()
    )
    response = client.im.v1.message.create(request)
    if not response.success():
        logger.error(
            f"[chat_id={chat_id}] 发送回复失败, code={response.code}, msg={response.msg}"
        )
    else:
        logger.info(f"[chat_id={chat_id}] 回复消息发送成功")


def handle_batch(chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]) -> None:
    logger.info(f"[chat_id={chat_id}] ========== 开始处理批量消息 ==========")
    logger.info(f"[chat_id={chat_id}] 消息片段数: {len(parts)}, status_msg_id={status_msg_id}")

    if not OPENAI_API_KEY:
        logger.warning(f"[chat_id={chat_id}] OPENAI_API_KEY 未配置")
        if status_msg_id:
            update_status_message(chat_id, status_msg_id, "**❌ 错误**\n\n未配置 OPENAI_API_KEY，暂时无法生成回复。")
        else:
            reply_to_chat(chat_id, "未配置 OPENAI_API_KEY，暂时无法生成回复。")
        return

    try:
        answer = call_openai(parts, status_msg_id, chat_id)

        # 更新最终消息
        if status_msg_id:
            final_content = preprocess_markdown_for_feishu(answer)
            update_status_message(chat_id, status_msg_id, final_content)
        else:
            reply_to_chat(chat_id, answer)

        logger.info(f"[chat_id={chat_id}] ========== 批量消息处理完成 ==========")
    except requests.RequestException as e:
        logger.error(f"[chat_id={chat_id}] 调用模型失败: {e}")
        if status_msg_id:
            update_status_message(chat_id, status_msg_id, "**❌ 错误**\n\n调用模型失败，请稍后重试。")
        else:
            reply_to_chat(chat_id, "调用模型失败，请稍后重试。")
    except Exception as e:
        logger.error(f"[chat_id={chat_id}] 处理消息时发生未知错误: {e}", exc_info=True)
        if status_msg_id:
            update_status_message(chat_id, status_msg_id, "**❌ 错误**\n\n处理消息时发生错误，请稍后重试。")
        else:
            reply_to_chat(chat_id, "处理消息时发生错误，请稍后重试。")


def handle_message_receive(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    try:
        logger.info("=" * 60)
        logger.info("收到新消息事件")

        message = data.event.message
        chat_id = message.chat_id
        message_id = getattr(message, 'message_id', 'N/A')
        msg_type = message.message_type
        content = message.content

        logger.info(f"消息详情:")
        logger.info(f"  chat_id: {chat_id}")
        logger.info(f"  message_id: {message_id}")
        logger.info(f"  message_type: {msg_type}")

        # 安全地访问 sender 属性
        sender = getattr(data.event, 'sender', None)
        if sender:
            logger.info(f"  sender.sender_id: {getattr(sender, 'sender_id', 'N/A')}")
            logger.info(f"  sender.sender_type: {getattr(sender, 'sender_type', 'N/A')}")
        else:
            logger.info(f"  sender: N/A")

        logger.info(f"  create_time: {getattr(message, 'create_time', 'N/A')}")
        logger.debug(f"  原始内容: {content}")

        parts = parse_message_content(msg_type, content, message_id)

        if parts:
            logger.info(f"消息解析成功，添加到批处理队列")
            batcher.add(chat_id, parts, handle_batch)
        else:
            logger.warning(f"消息解析后没有有效的消息片段，跳过处理")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"处理消息接收事件时发生错误: {e}", exc_info=True)


def ensure_websockets_compat() -> None:
    try:
        version = importlib.metadata.version("websockets")
        logger.info(f"检测到 websockets 版本: {version}")
    except importlib.metadata.PackageNotFoundError:
        logger.warning("未找到 websockets 包")
        return
    major = int(version.split(".", 1)[0])
    if major >= 13:
        error_msg = f"当前 websockets 版本 {version} 与 lark-oapi 不兼容，请安装 websockets<13。"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    logger.info(f"websockets 版本兼容性检查通过")


def main() -> None:
    logger.info("*" * 60)
    logger.info("飞书机器人启动中...")
    logger.info("*" * 60)

    if not APP_ID or not APP_SECRET:
        error_msg = "请先设置 LARK_APP_ID 和 LARK_APP_SECRET"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info("环境变量检查通过")

    ensure_websockets_compat()

    logger.info("正在初始化事件处理器...")
    handler = (
        lark.EventDispatcherHandler.builder(APP_ID, APP_SECRET)
        .register_p2_im_message_receive_v1(handle_message_receive)
        .build()
    )
    logger.info("事件处理器初始化完成")

    logger.info("正在初始化 WebSocket 客户端...")
    ws_client = lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler)
    logger.info("WebSocket 客户端初始化完成")

    logger.info("*" * 60)
    logger.info("飞书机器人已启动，等待消息...")
    logger.info("*" * 60)

    try:
        ws_client.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"运行时发生错误: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
