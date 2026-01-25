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
    """AI 客户端，支持流式和非流式调用，带主备双源和重试机制"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        backup_api_key: Optional[str] = None,
        backup_base_url: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        """
        初始化 AI 客户端

        Args:
            api_key: 主 API Key
            base_url: 主 API Base URL
            backup_api_key: 备用 API Key
            backup_base_url: 备用 API Base URL
            max_retries: 每个源的最大重试次数
            retry_delay: 重试基础延迟（秒），使用指数退避
        """
        # 主 API 配置
        self.api_key = api_key
        self.base_url = base_url

        # 备用 API 配置
        self.backup_api_key = backup_api_key
        self.backup_base_url = backup_base_url

        # 重试配置
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 是否启用备用源
        self.has_backup = bool(backup_api_key and backup_base_url)

        logger.info(f"AIClient 初始化: base_url={base_url}")
        if self.has_backup:
            logger.info(f"  备用 API: base_url={backup_base_url}")
            logger.info(f"  重试配置: max_retries={max_retries}, retry_delay={retry_delay}s")
        else:
            logger.info(f"  未配置备用 API")
            logger.info(f"  重试配置: max_retries={max_retries}, retry_delay={retry_delay}s")

    def _call_with_retry(
        self,
        api_key: str,
        base_url: str,
        source_name: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> requests.Response:
        """带重试的 API 调用

        Args:
            api_key: API Key
            base_url: API Base URL
            source_name: 源名称（用于日志）
            payload: 请求体
            stream: 是否流式调用

        Returns:
            响应对象

        Raises:
            最后一次失败的异常
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"[{source_name}] 第 {attempt}/{self.max_retries} 次尝试")

                response = requests.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=60,
                    stream=stream,
                )

                logger.debug(f"[{source_name}] 收到响应: status_code={response.status_code}")
                response.raise_for_status()

                logger.info(f"[{source_name}] 调用成功")
                return response

            except Exception as e:
                last_exception = e
                logger.warning(f"[{source_name}] 第 {attempt} 次尝试失败: {type(e).__name__}: {str(e)}")

                # 如果还有重试机会，等待后重试
                if attempt < self.max_retries:
                    # 指数退避：delay * (2 ^ (attempt - 1))
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.info(f"[{source_name}] 等待 {delay:.1f} 秒后重试...")
                    time.sleep(delay)

        # 所有重试都失败了
        logger.error(f"[{source_name}] 所有 {self.max_retries} 次尝试均失败")
        raise last_exception

    def call(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """非流式调用，支持主备双源和重试"""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # 先尝试主 API
        try:
            logger.info("使用主 API 调用")
            response = self._call_with_retry(
                self.api_key,
                self.base_url,
                "主API",
                payload,
                stream=False,
            )

            result_payload = response.json()
            result = result_payload["choices"][0]["message"]["content"].strip()
            logger.info(f"AI API 调用成功，响应长度: {len(result)} 字符")
            return result

        except Exception as e:
            logger.error(f"主 API 调用失败: {type(e).__name__}: {str(e)}")

            # 如果有备用 API，尝试使用备用
            if self.has_backup:
                logger.info("主 API 失败，切换到备用 API")
                try:
                    response = self._call_with_retry(
                        self.backup_api_key,
                        self.backup_base_url,
                        "备用API",
                        payload,
                        stream=False,
                    )

                    result_payload = response.json()
                    result = result_payload["choices"][0]["message"]["content"].strip()
                    logger.info(f"备用 API 调用成功，响应长度: {len(result)} 字符")
                    return result

                except Exception as backup_e:
                    logger.error(f"备用 API 也失败: {type(backup_e).__name__}: {str(backup_e)}")
                    raise backup_e
            else:
                logger.error("没有配置备用 API，调用失败")
                raise e

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
        流式调用 AI API，支持主备双源和重试

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
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        logger.info(f"AI 请求参数: model={model}, temperature={temperature}, max_tokens={max_tokens}, stream=True")

        # 先尝试主 API
        try:
            logger.info("使用主 API 流式调用")
            response = self._call_with_retry(
                self.api_key,
                self.base_url,
                "主API",
                payload,
                stream=True,
            )

            # 处理流式响应
            full_content = self._process_streaming_response(
                response, update_callback, update_interval
            )
            logger.info(f"主 API 流式调用成功，总响应长度: {len(full_content)} 字符")
            return full_content

        except Exception as e:
            logger.error(f"主 API 流式调用失败: {type(e).__name__}: {str(e)}")

            # 如果有备用 API，尝试使用备用
            if self.has_backup:
                logger.info("主 API 失败，切换到备用 API 流式调用")
                try:
                    response = self._call_with_retry(
                        self.backup_api_key,
                        self.backup_base_url,
                        "备用API",
                        payload,
                        stream=True,
                    )

                    # 处理流式响应
                    full_content = self._process_streaming_response(
                        response, update_callback, update_interval
                    )
                    logger.info(f"备用 API 流式调用成功，总响应长度: {len(full_content)} 字符")
                    return full_content

                except Exception as backup_e:
                    logger.error(f"备用 API 流式调用也失败: {type(backup_e).__name__}: {str(backup_e)}")
                    raise backup_e
            else:
                logger.error("没有配置备用 API，流式调用失败")
                raise e

    def _process_streaming_response(
        self,
        response: requests.Response,
        update_callback: Optional[Callable[[str], None]],
        update_interval: float,
    ) -> str:
        """处理流式响应

        Args:
            response: 响应对象
            update_callback: 更新回调函数
            update_interval: 更新间隔

        Returns:
            完整内容
        """
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
                    logger.debug("choices 为空，跳过这一行")
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

        # 注意：不要在这里调用最后一次 update_callback
        # 因为 Bot 可能需要生成交互式卡片，这里的更新会覆盖掉交互卡片
        # Bot 会在处理完成后自行更新最终消息

        if not full_content:
            raise ValueError("流式响应未返回任何内容")

        return full_content.strip()
