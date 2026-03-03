# core/llm/factory.py
"""LLM 胶水层工厂：vllm / openai / dify。"""
from typing import Optional

from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.dify_adapter import DifyLLMAdapter
from meeting_agent.core.llm.vllm_adapter import VllmLLMAdapter

LLM_TYPE_OPENAI = "openai"
LLM_TYPE_VLLM = "vllm"
LLM_TYPE_DIFY = "dify"


def get_llm(llm_type: Optional[str] = None) -> BaseLLM:
    t = (llm_type or getattr(settings, "llm_type", None) or LLM_TYPE_VLLM).strip().lower()
    if t == LLM_TYPE_VLLM:
        base_url = (getattr(settings, "vllm_base_url", None) or "").strip()
        if not base_url:
            raise ConfigError("使用 vLLM 适配器需配置 VLLM_BASE_URL（本地/自托管模型服务地址）")
        model = (getattr(settings, "vllm_chat_model", None) or "").strip() or "default"
        api_key = (getattr(settings, "vllm_api_key", None) or "").strip() or "no-key"
        timeout = int(getattr(settings, "vllm_timeout", 0) or 120)
        return VllmLLMAdapter(base_url=base_url, model=model, api_key=api_key, timeout=timeout)
    if t == LLM_TYPE_OPENAI:
        try:
            from meeting_agent.core.llm.openai_adapter import OpenAILLMAdapter
        except ImportError as e:
            raise ConfigError(
                "使用 OpenAI 适配器需安装: pip install -e '.[openai]' 或 pip install openai langchain-openai"
            ) from e
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 OpenAI 适配器需配置 OPENAI_API_KEY")
        model = getattr(settings, "openai_chat_model", "gpt-4o-mini")
        base_url = getattr(settings, "openai_base_url", None) or None
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
    raise ConfigError(f"不支持的 llm_type: {t}，可选: openai, vllm, dify")
