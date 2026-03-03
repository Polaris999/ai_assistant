"""Dify 应用作为 LLM 的适配器，通过 chat-messages API 调用。"""
import logging
from typing import Any, Optional

from meeting_agent.clients.dify_client import DifyClient
from meeting_agent.core.exceptions import LLMError
from meeting_agent.core.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class DifyLLMAdapter(BaseLLM):
    """将 Dify 对话应用封装为 BaseLLM，支持 system + user 拼接为单次请求。"""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        app_type: str = "chat-messages",
        **kwargs: Any,
    ):
        self._client = DifyClient(
            api_key=api_key,
            base_url=base_url,
            app_type=app_type,
            **kwargs,
        )

    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        user_id: str = "default",
        **kwargs: Any,
    ) -> str:
        query = f"{system}\n\n{prompt}" if system else prompt
        try:
            out = self._client.chat(query=query, user_id=user_id, **kwargs)
        except Exception as e:
            logger.exception("Dify 调用失败: %s", e)
            raise LLMError(f"Dify 调用失败: {e}") from e
        if not (out and out.strip()):
            raise LLMError("Dify 返回为空")
        return out.strip()
