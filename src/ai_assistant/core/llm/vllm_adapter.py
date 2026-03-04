"""vLLM 推理适配器：HTTP 调用 /chat/completions（OpenAI 兼容）。"""
import logging
from typing import Any, Optional

import requests

from ai_assistant.core.exceptions import LLMError
from ai_assistant.core.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class VllmLLMAdapter(BaseLLM):
    """调用 vLLM 或任意 OpenAI 兼容的 chat/completions 端点。"""

    def __init__(
        self,
        base_url: str,
        model: str = "default",
        api_key: Optional[str] = None,
        timeout: int = 120,
        **kwargs: Any,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model or "default"
        self._api_key = api_key or "no-key"
        self._timeout = timeout
        self._session = requests.Session()
        if self._api_key and self._api_key != "no-key":
            self._session.headers["Authorization"] = f"Bearer {self._api_key}"
        self._session.headers["Content-Type"] = "application/json"

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            **{k: v for k, v in kwargs.items() if k in ("max_tokens", "stream")},
        }
        try:
            r = self._session.post(
                self._chat_url(),
                json=body,
                timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.exception("vLLM 请求失败: %s", e)
            raise LLMError(f"vLLM 请求失败: {e}") from e
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("vLLM 返回无 choices")
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        if not content.strip():
            raise LLMError("vLLM 返回内容为空")
        return content.strip()
