"""
AI 客户端 - 支持 OpenAI 和其他 LLM 的统一接口
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Callable

import requests

from core.utils import preprocess_markdown_for_feishu

logger = logging.getLogger(__name__)


class AIClient:
    """AI 客户端，支持流式和非流式调用"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        logger.info(f"AIClient 初始化: base_url={base_url}")

    def call(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """非流式调用"""
        try:
            logger.debug(f"发送请求到 {self.base_url}/chat/completions")

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            logger.debug(f"收到响应: status_code={response.status_code}")

            response.raise_for_status()
            payload = response.json()

            result = payload["choices"][0]["message"]["content"].strip()
            logger.info(f"AI API 调用成功，响应长度: {len(result)} 字符")
            return result

        except requests.exceptions.Timeout as e:
            logger.error(f"AI API 调用超时: {e}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"AI API HTTP 错误: status_code={response.status_code}, response={response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"AI API 请求失败: {e}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"解析 AI 响应失败: {e}")
            raise

    def call_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        update_callback: Optional[Callable[[str], None]] = None,
        update_interval: float = 0.5,
    ) -> str:
        """
        流式调用 AI API

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            update_callback: 更新回调函数，接收当前完整内容
            update_interval: 更新间隔（秒）

        Returns:
            完整的响应内容
        """
        try:
            logger.debug(f"发送流式请求到 {self.base_url}/chat/completions")

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            # 打印请求参数（不包含消息内容）
            logger.info(f"AI 请求参数: model={model}, temperature={temperature}, max_tokens={max_tokens}, stream=True")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
                stream=True,
            )
            logger.debug(f"收到流式响应: status_code={response.status_code}")

            response.raise_for_status()

            # 处理流式响应
            full_content = ""
            last_update_time = 0

            for line in response.iter_lines():
                if not line:
                    continue

                line_text = line.decode("utf-8")
                if not line_text.startswith("data: "):
                    continue

                data_str = line_text[6:]  # 移除 'data: ' 前缀
                if data_str == "[DONE]":
                    logger.debug("收到 [DONE] 标记，流式响应结束")
                    break

                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])

                    # 安全检查：确保 choices 不为空
                    if not choices:
                        logger.debug(f"choices 为空，跳过这一行")
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")

                    # 检查是否有 finish_reason
                    finish_reason = choices[0].get("finish_reason")
                    if finish_reason:
                        logger.debug(f"收到 finish_reason: {finish_reason}")
                        if finish_reason == "stop":
                            break

                    if content:
                        full_content += content
                        logger.debug(f"收到内容片段: {len(content)} 字符，总计: {len(full_content)} 字符")

                        # 定期调用更新回调
                        if update_callback:
                            current_time = time.time()
                            if current_time - last_update_time >= update_interval:
                                update_callback(full_content)
                                last_update_time = current_time

                except json.JSONDecodeError as e:
                    logger.warning(f"解析流式响应失败: {e}, line={data_str[:100]}")
                    continue
                except Exception as e:
                    logger.warning(f"处理流式响应行时出错: {e}")
                    continue

            # 最后一次更新
            if update_callback and full_content:
                update_callback(full_content)

            if not full_content:
                raise ValueError("流式响应未返回任何内容")

            logger.info(f"AI API 流式调用成功，总响应长度: {len(full_content)} 字符")
            return full_content.strip()

        except requests.exceptions.Timeout as e:
            logger.error(f"AI API 调用超时: {e}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"AI API HTTP 错误: status_code={response.status_code}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"AI API 请求失败: {e}")
            raise
        except (KeyError, IndexError, ValueError) as e:
            logger.error(f"解析 AI 响应失败: {e}")
            raise
