# core/llm/factory.py
"""LLM 胶水层工厂：openai / vllm（OpenAI 兼容）/ dify，符合业内通用选型。"""
from typing import Optional

from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.dify_adapter import DifyLLMAdapter
from meeting_agent.core.llm.openai_adapter import OpenAILLMAdapter

LLM_TYPE_OPENAI = "openai"
LLM_TYPE_VLLM = "vllm"
LLM_TYPE_DIFY = "dify"


def get_llm(llm_type: Optional[str] = None) -> BaseLLM:
    t = (llm_type or getattr(settings, "llm_type", None) or LLM_TYPE_OPENAI).strip().lower()
    if t == LLM_TYPE_OPENAI:
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 OpenAI 适配器需配置 OPENAI_API_KEY")
        model = getattr(settings, "openai_chat_model", "gpt-4o-mini")
        base_url = getattr(settings, "openai_base_url", None) or None
        return OpenAILLMAdapter(model=model, api_key=api_key, base_url=base_url)
    if t == LLM_TYPE_VLLM:
        base_url = (getattr(settings, "vllm_base_url", None) or "").strip()
        if not base_url:
            raise ConfigError("使用 vLLM 适配器需配置 VLLM_BASE_URL（vLLM 服务 OpenAI 兼容端点）")
        model = (getattr(settings, "vllm_chat_model", None) or "").strip() or "default"
        api_key = (getattr(settings, "vllm_api_key", None) or "").strip() or "no-key"
        return OpenAILLMAdapter(model=model, api_key=api_key, base_url=base_url.rstrip("/"))
    if t == LLM_TYPE_DIFY:
        api_key = getattr(settings, "dify_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 Dify 适配器需配置 DIFY_API_KEY")
        return DifyLLMAdapter(
            api_key=api_key,
            base_url=getattr(settings, "dify_base_url", None),
            app_type=getattr(settings, "dify_chat_app_type", "chat-messages"),
        )
    raise ConfigError(f"不支持的 llm_type: {t}，可选: openai, vllm, dify")
