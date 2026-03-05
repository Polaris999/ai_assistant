# core/llm/factory.py
"""LLM 工厂：统一使用 LangChain ChatOpenAI（vLLM/OpenAI 兼容），Dify 保留专用适配器。"""
from typing import Any, Optional

from ai_assistant.config import settings
from ai_assistant.core.exceptions import ConfigError
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.langchain_adapter import LangChainChatModelAdapter

LLM_TYPE_OPENAI = "openai"
LLM_TYPE_VLLM = "vllm"
LLM_TYPE_DIFY = "dify"


def _chat_openai_for_vllm() -> BaseLLM:
    from langchain_openai import ChatOpenAI
    base_url = (getattr(settings, "vllm_base_url", None) or "").strip()
    if not base_url:
        raise ConfigError("LLM_TYPE=vllm 时需配置 VLLM_BASE_URL")
    model = (getattr(settings, "vllm_chat_model", None) or "").strip() or "default"
    api_key = (getattr(settings, "vllm_api_key", None) or "").strip() or "no-key"
    timeout = int(getattr(settings, "llm_request_timeout_seconds", 0) or 120)
    chat = ChatOpenAI(
        model=model,
        base_url=base_url.rstrip("/"),
        api_key=api_key if api_key != "no-key" else None,
        temperature=0,
        timeout=timeout,
    )
    return LangChainChatModelAdapter(chat)


def _chat_openai_for_openai() -> BaseLLM:
    from langchain_openai import ChatOpenAI
    api_key = getattr(settings, "openai_api_key", None) or ""
    if not api_key:
        raise ConfigError("LLM_TYPE=openai 时需配置 OPENAI_API_KEY")
    model = getattr(settings, "openai_chat_model", "gpt-4o-mini")
    base_url = (getattr(settings, "openai_base_url", None) or "").strip() or None
    timeout = int(getattr(settings, "llm_request_timeout_seconds", 0) or 120)
    chat = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=timeout,
    )
    return LangChainChatModelAdapter(chat)


def get_llm(llm_type: Optional[str] = None) -> BaseLLM:
    t = (llm_type or getattr(settings, "llm_type", None) or LLM_TYPE_VLLM).strip().lower()
    if t == LLM_TYPE_VLLM:
        return _chat_openai_for_vllm()
    if t == LLM_TYPE_OPENAI:
        return _chat_openai_for_openai()
    if t == LLM_TYPE_DIFY:
        from ai_assistant.core.llm.dify_adapter import DifyLLMAdapter
        api_key = getattr(settings, "dify_api_key", None) or ""
        if not api_key:
            raise ConfigError("LLM_TYPE=dify 时需配置 DIFY_API_KEY")
        return DifyLLMAdapter(
            api_key=api_key,
            base_url=getattr(settings, "dify_base_url", None),
            app_type=getattr(settings, "dify_chat_app_type", "chat-messages"),
        )
    raise ConfigError(f"不支持的 llm_type: {t}，可选: openai, vllm, dify")


def get_chat_model_for_langgraph(llm_type: Optional[str] = None) -> Any:
    """
    返回可供 LangGraph create_react_agent 使用的 LangChain ChatModel。
    仅当 llm_type 为 openai 或 vllm 时可用；dify 不支持 LangGraph 工具调用路径。
    """
    llm = get_llm(llm_type)
    get_native = getattr(llm, "get_native_chat_model", None)
    if callable(get_native):
        return get_native()
    raise ConfigError(
        "LangGraph 仅支持 llm_type=openai 或 vllm，当前 llm_type 为 dify 时不可用。"
    )
