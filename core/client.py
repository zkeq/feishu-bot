"""
飞书客户端封装
"""
import json
import logging
from typing import Any, Dict, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    PatchMessageRequest,
    PatchMessageRequestBody,
    DeleteMessageRequest,
)

logger = logging.getLogger(__name__)


class FeishuClient:
    """飞书客户端封装类"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        logger.info(f"FeishuClient 初始化完成: app_id={app_id[:10]}...")

    def send_message(
        self, chat_id: str, content: Dict[str, Any], msg_type: str = "interactive"
    ) -> Optional[str]:
        """发送消息"""
        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(msg_type)
                    .content(json.dumps(content, ensure_ascii=False))
                    .build()
                )
                .build()
            )
            response = self.client.im.v1.message.create(request)
            if response.success() and response.data:
                msg_id = response.data.message_id
                logger.info(f"[chat_id={chat_id}] 发送消息成功, message_id={msg_id}")
                return msg_id
            else:
                logger.error(f"[chat_id={chat_id}] 发送消息失败: {response.code} {response.msg}")
                return None
        except Exception as e:
            logger.error(f"[chat_id={chat_id}] 发送消息异常: {e}", exc_info=True)
            return None

    def update_message(self, message_id: str, content: Dict[str, Any]) -> bool:
        """更新消息"""
        try:
            request = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(json.dumps(content, ensure_ascii=False))
                    .build()
                )
                .build()
            )
            response = self.client.im.v1.message.patch(request)
            if response.success():
                logger.debug(f"更新消息成功: message_id={message_id}")
                return True
            else:
                logger.warning(f"更新消息失败: {response.code} {response.msg}")
                return False
        except Exception as e:
            logger.error(f"更新消息异常: {e}", exc_info=True)
            return False

    def delete_message(self, message_id: str) -> bool:
        """撤回消息"""
        try:
            request = DeleteMessageRequest.builder().message_id(message_id).build()
            response = self.client.im.v1.message.delete(request)
            if response.success():
                logger.info(f"撤回消息成功: message_id={message_id}")
                return True
            else:
                logger.warning(f"撤回消息失败: {response.code} {response.msg}")
                return False
        except Exception as e:
            logger.error(f"撤回消息异常: {e}", exc_info=True)
            return False

    def get_image_resource(self, message_id: str, image_key: str) -> Optional[bytes]:
        """获取图片资源"""
        try:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(image_key)
                .type("image")
                .build()
            )
            response = self.client.im.v1.message_resource.get(request)
            if response.success() and response.file:
                file_content = response.file.read()
                logger.info(f"获取图片成功: message_id={message_id}, size={len(file_content)}")
                return file_content
            else:
                logger.error(f"获取图片失败: {response.code} {response.msg}")
                return None
        except Exception as e:
            logger.error(f"获取图片异常: {e}", exc_info=True)
            return None
