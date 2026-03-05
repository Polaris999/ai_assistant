"""将 LangChain ChatModel 适配为 BaseLLM，统一 vLLM/OpenAI 为 ChatOpenAI。"""
from __future__ import annotations

from typing import Any, Optional

from ai_assistant.core.exceptions import LLMError
from ai_assistant.core.llm.base import BaseLLM


class LangChainChatModelAdapter(BaseLLM):
    """LangChain ChatModel 的 BaseLLM 适配器，供 get_llm 统一返回。"""

    def __init__(self, chat_model: Any) -> None:
        self._chat = chat_model

    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        if system:
            messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
        else:
            messages = [HumanMessage(content=prompt)]
        try:
            msg = self._chat.with_config(temperature=temperature).invoke(messages)
            content = getattr(msg, "content", None) or str(msg) or ""
            if not content.strip():
                raise LLMError("LLM 返回内容为空")
            return content.strip()
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM 调用失败: {e}") from e

    @property
    def name(self) -> str:
        return getattr(self._chat, "model_name", None) or getattr(self._chat, "model", None) or "LangChainChat"

    def get_native_chat_model(self) -> Any:
        """返回底层 LangChain ChatModel，供 LangGraph create_react_agent 等直接使用。"""
        return self._chat
