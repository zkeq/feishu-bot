"""
演示多轮对话功能的示例 Bot
展示如何使用 ask_user 方法向用户询问补充信息
"""
import logging
from typing import Any, Dict, List, Optional

from core.client import FeishuClient
from core.batcher import MessagePart
from core.ai_client import AIClient
from bots.base import BaseBot

logger = logging.getLogger(__name__)


class DemoConversationBot(BaseBot):
    """演示多轮对话的 Bot"""

    def __init__(self, config: Dict[str, Any], client: FeishuClient, ai_client: AIClient):
        super().__init__(config, client, ai_client)
        self.ai_client = ai_client
        self.openai_model = config.get("openai", {}).get("model", "gpt-4o-mini")
        logger.info(f"[{self.name}] 初始化完成，模型: {self.openai_model}")

    def process_messages(
        self, chat_id: str, parts: List[MessagePart], status_msg_id: Optional[str]
    ) -> str:
        """
        处理消息
        演示场景：用户要求创建任务，但没有提供截止日期时，询问用户
        """
        logger.info(f"[{self.name}] 开始处理消息")

        # 提取文本内容
        text_parts = [part.text for part in parts if part.kind == "text" and part.text]
        user_message = " ".join(text_parts).strip()

        logger.info(f"[{self.name}] 用户消息: {user_message}")

        # 检查是否是创建任务的请求
        if "创建任务" in user_message or "新建任务" in user_message or "添加任务" in user_message:
            # 检查是否包含截止日期
            has_deadline = any(keyword in user_message for keyword in ["截止", "deadline", "日期", "明天", "下周", "月底"])

            if not has_deadline:
                # 信息不足，询问用户
                logger.info(f"[{self.name}] 检测到缺少截止日期，询问用户")

                # 保存任务描述到 callback_data
                callback_data = {
                    "task_description": user_message,
                    "action": "create_task"
                }

                # 获取发送者ID
                user_id = parts[0].sender_id if parts else None

                # 询问用户
                question = self.ask_user(
                    chat_id=chat_id,
                    question="请问这个任务的截止日期是什么时候？\n\n例如：明天、下周五、2024-12-31",
                    original_parts=parts,
                    callback_data=callback_data,
                    original_user_id=user_id
                )

                # 发送提问消息
                if status_msg_id:
                    content = {
                        "config": {"wide_screen_mode": True},
                        "elements": [
                            {
                                "tag": "div",
                                "text": {"tag": "lark_md", "content": question},
                            }
                        ],
                    }
                    self.client.update_message(status_msg_id, content)
                else:
                    self.client.send_message(chat_id, question)

                return question

        # 正常处理消息（使用 AI）
        return self._process_with_ai(chat_id, user_message, status_msg_id)

    def handle_user_response(
        self,
        chat_id: str,
        parts: List[MessagePart],
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        处理用户的补充回复
        重写此方法以自定义处理逻辑
        """
        context = self.conversation_manager.get_conversation(chat_id)
        if not context:
            return None

        logger.info(f"[{self.name}] 收到用户补充信息，继续处理任务创建")

        # 提取用户回复的截止日期
        text_parts = [part.text for part in parts if part.kind == "text" and part.text]
        deadline = " ".join(text_parts).strip()

        # 获取原始任务描述
        task_description = context.callback_data.get("task_description", "")

        # 完成会话
        self.conversation_manager.complete_conversation(chat_id)

        # 创建任务（这里只是演示，实际应该调用真实的任务创建 API）
        result = f"""✅ **任务创建成功！**

**任务描述：** {task_description}
**截止日期：** {deadline}

_这是一个演示 Bot，实际使用时会调用真实的任务管理系统。_
"""

        return result

    def _process_with_ai(self, chat_id: str, user_message: str, status_msg_id: Optional[str]) -> str:
        """使用 AI 处理普通消息"""
        try:
            logger.info(f"[{self.name}] 使用 AI 处理消息")

            # 构建消息
            messages = [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": user_message}
            ]

            # 调用 AI
            response = self.ai_client.chat_completion(
                messages=messages,
                model=self.openai_model,
                stream=False
            )

            answer = response.choices[0].message.content

            # 发送回复
            if status_msg_id:
                content = {
                    "config": {"wide_screen_mode": True},
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": answer},
                        }
                    ],
                }
                self.client.update_message(status_msg_id, content)
            else:
                self.client.send_message(chat_id, answer)

            return answer

        except Exception as e:
            logger.error(f"[{self.name}] AI 处理失败: {e}", exc_info=True)
            error_msg = f"抱歉，处理您的请求时出现了错误：{str(e)}"

            if status_msg_id:
                content = {
                    "config": {"wide_screen_mode": True},
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": error_msg},
                        }
                    ],
                }
                self.client.update_message(status_msg_id, content)
            else:
                self.client.send_message(chat_id, error_msg)

            return error_msg
