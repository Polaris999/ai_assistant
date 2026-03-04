"""配置校验：按 LLM_TYPE/EMBEDDING_TYPE 检查必填项。"""
import logging

from ai_assistant.config import settings
from ai_assistant.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


def validate_settings() -> list[str]:
    """校验必填项，不发起请求。通过返回 []，否则返回错误列表。"""
    errors: list[str] = []
    llm_type = (getattr(settings, "llm_type", None) or "vllm").strip().lower()
    embedding_type = (getattr(settings, "embedding_type", None) or "api").strip().lower()

    # LLM 必填
    if llm_type == "vllm":
        if not (getattr(settings, "vllm_base_url", None) or "").strip():
            errors.append("LLM_TYPE=vllm 时需配置 VLLM_BASE_URL")
    elif llm_type == "openai":
        if not (getattr(settings, "openai_api_key", None) or "").strip():
            errors.append("LLM_TYPE=openai 时需配置 OPENAI_API_KEY")
    elif llm_type == "dify":
        if not (getattr(settings, "dify_api_key", None) or "").strip():
            errors.append("LLM_TYPE=dify 时需配置 DIFY_API_KEY")
    else:
        errors.append(f"不支持的 llm_type: {llm_type}，可选: vllm, openai, dify")

    # Embedding 必填
    if embedding_type == "api":
        if not (getattr(settings, "embedding_base_url", None) or "").strip():
            errors.append("EMBEDDING_TYPE=api 时需配置 EMBEDDING_BASE_URL")
    elif embedding_type == "openai":
        if not (getattr(settings, "openai_api_key", None) or "").strip():
            errors.append("EMBEDDING_TYPE=openai 时需配置 OPENAI_API_KEY")
    else:
        errors.append(f"不支持的 embedding_type: {embedding_type}，可选: openai, api")

    return errors


def validate_settings_or_raise() -> None:
    """校验配置，失败抛 ConfigError。"""
    errs = validate_settings()
    if errs:
        raise ConfigError("配置校验未通过：" + "；".join(errs), details={"errors": errs})
