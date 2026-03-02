# core/llm/openai_adapter.py
import logging
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from meeting_agent.core.exceptions import LLMError
from meeting_agent.core.llm.base import BaseLLM

logger = logging.getLogger(__name__)

# 模块级模板，避免每次 invoke 重复创建
_SYSTEM_HUMAN_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "{system}"),
    ("human", "{prompt}"),
])


class OpenAILLMAdapter(BaseLLM):
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ):
        self._model_name = model
        self._default_temperature = temperature
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=temperature,
            **kwargs,
        )

    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        if system:
            chain = _SYSTEM_HUMAN_TEMPLATE | self._llm.with_config(temperature=temperature)
            msg = chain.invoke({"system": system, "prompt": prompt})
        else:
            msg = self._llm.with_config(temperature=temperature).invoke(prompt)
        content = getattr(msg, "content", None) or str(msg)
        if not content:
            raise LLMError("OpenAI 返回为空")
        return content.strip()
