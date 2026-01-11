"""
饮食分析 Bot 实现
"""
import base64
import logging
from typing import Any, Dict, List, Optional

from bots.base import BaseBot
from core.batcher import MessagePart
from core.ai_client import AIClient
from core.utils import preprocess_markdown_for_feishu

logger = logging.getLogger(__name__)


class FoodAnalyzerBot(BaseBot):
    """饮食分析机器人"""

    def __init__(self, config: Dict[str, Any], client, ai_client: AIClient):
        super().__init__(config, client)
        self.ai_client = ai_client
        self.openai_model = config.get("openai", {}).get("model", "gpt-4o-mini")
        self.openai_temperature = config.get("openai", {}).get("temperature", 0.7)
        self.openai_max_tokens = config.get("openai", {}).get("max_tokens")

        logger.info(f"[{self.name}] OpenAI 配置: model={self.openai_model}, temperature={self.openai_temperature}, max_tokens={self.openai_max_tokens}")

        # 多维表格配置
        self.bitable_enabled = config.get("bitable", {}).get("enabled", False)
        if self.bitable_enabled:
            logger.info(f"[{self.name}] 多维表格集成已启用")

    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """处理消息并返回分析结果"""
        logger.info(f"[{self.name}] 开始分析饮食，消息片段数: {len(parts)}")

        # 更新状态
        if status_msg_id:
            self._update_status(chat_id, status_msg_id, "**🔍 正在分析饮食...**\n\n识别食物中...")

        # 构建消息
        messages = self._build_ai_messages(parts)

        # 调用 AI 进行流式分析
        if status_msg_id:
            result = self._call_ai_streaming(chat_id, messages, status_msg_id)
        else:
            result = self.ai_client.call(
                messages=messages,
                model=self.openai_model,
                temperature=self.openai_temperature,
                max_tokens=self.openai_max_tokens,
            )

        # 如果启用了多维表格，保存数据
        if self.bitable_enabled and self.config.get("business", {}).get("auto_save"):
            self._save_to_bitable(result)

        return result

    def _build_ai_messages(self, parts: List[MessagePart]) -> List[Dict[str, Any]]:
        """构建 AI 消息"""
        content: List[Dict[str, Any]] = []

        for part in parts:
            if part.kind == "text" and part.text:
                content.append({"type": "text", "text": part.text})
            elif part.kind == "image" and part.image_key and part.message_id:
                # 获取图片
                image_data = self.client.get_image_resource(part.message_id, part.image_key)
                if image_data:
                    # 转换为 data URL
                    encoded = base64.b64encode(image_data).decode("utf-8")
                    data_url = f"data:image/png;base64,{encoded}"
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    content.append({"type": "text", "text": f"[图片: {part.image_key}]"})

        return [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": content},
        ]

    def _call_ai_streaming(
        self, chat_id: str, messages: List[Dict[str, Any]], status_msg_id: str
    ) -> str:
        """调用 AI API（流式）"""
        # 更新状态
        self._update_status(chat_id, status_msg_id, "**🚀 正在请求 AI 分析...**\n\n等待响应中...")

        def update_callback(content: str):
            """流式更新回调"""
            self._update_status(
                chat_id,
                status_msg_id,
                f"**📝 正在分析中...**\n\n{preprocess_markdown_for_feishu(content)}\n\n_正在生成中..._",
            )

        result = self.ai_client.call_streaming(
            messages=messages,
            model=self.openai_model,
            temperature=self.openai_temperature,
            max_tokens=self.openai_max_tokens,
            update_callback=update_callback,
            update_interval=0.5,
        )

        return result

    def _update_status(self, chat_id: str, message_id: str, content: str) -> None:
        """更新状态消息"""
        content_json = {
            "config": {"wide_screen_mode": True},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
        }
        self.client.update_message(message_id, content_json)

    def _save_to_bitable(self, analysis_result: str) -> None:
        """保存分析结果到多维表格"""
        # TODO: 实现多维表格保存逻辑
        logger.info(f"[{self.name}] 保存到多维表格: {analysis_result[:50]}...")
        pass
