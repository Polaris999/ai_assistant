# core/llm/factory.py
from typing import Optional

from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.dify_adapter import DifyLLMAdapter
from meeting_agent.core.llm.openai_adapter import OpenAILLMAdapter

LLM_TYPE_OPENAI = "openai"
LLM_TYPE_DIFY = "dify"


def get_llm(llm_type: Optional[str] = None) -> BaseLLM:
    t = llm_type or getattr(settings, "llm_type", None) or LLM_TYPE_OPENAI
    if t == LLM_TYPE_OPENAI:
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 OpenAI 适配器需配置 OPENAI_API_KEY")
        model = getattr(settings, "openai_chat_model", "gpt-4o-mini")
        base_url = getattr(settings, "openai_base_url", None)
        return OpenAILLMAdapter(model=model, api_key=api_key, base_url=base_url)
    if t == LLM_TYPE_DIFY:
        api_key = getattr(settings, "dify_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 Dify 适配器需配置 DIFY_API_KEY")
        return DifyLLMAdapter(
            api_key=api_key,
            base_url=getattr(settings, "dify_base_url", None),
            app_type=getattr(settings, "dify_chat_app_type", "chat-messages"),
        )
    raise ConfigError(f"不支持的 llm_type: {t}，可选: openai, dify")
