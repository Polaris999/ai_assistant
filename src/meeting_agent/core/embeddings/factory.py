"""Embeddings 工厂：openai | api。"""
from typing import Optional

from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.embeddings.base import BaseEmbeddings

EMBEDDING_TYPE_OPENAI = "openai"
EMBEDDING_TYPE_API = "api"


def _openai_compat_adapter(model: str, api_key: str, base_url: Optional[str]):
    try:
        from meeting_agent.core.embeddings.openai_adapter import OpenAIEmbeddingsAdapter
    except ImportError as e:
        raise ConfigError(
            "Embeddings 需安装: pip install -e '.[openai]' 或 pip install openai langchain-openai"
        ) from e
    return OpenAIEmbeddingsAdapter(model=model, api_key=api_key or "no-key", base_url=base_url)


def get_embeddings(embedding_type: Optional[str] = None) -> BaseEmbeddings:
    """按配置返回 Embeddings，默认 api。"""
    t = (embedding_type or getattr(settings, "embedding_type", None) or EMBEDDING_TYPE_API).strip().lower()
    if t == EMBEDDING_TYPE_API:
        base_url = (getattr(settings, "embedding_base_url", None) or "").strip()
        if not base_url:
            raise ConfigError("EMBEDDING_TYPE=api 时需配置 EMBEDDING_BASE_URL（自建 embedding 服务地址）")
        api_key = (getattr(settings, "embedding_api_key", None) or "").strip()
        model = (getattr(settings, "embedding_model", None) or "").strip() or "default"
        return _openai_compat_adapter(model=model, api_key=api_key, base_url=base_url.rstrip("/"))
    if t == EMBEDDING_TYPE_OPENAI:
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("EMBEDDING_TYPE=openai 时需配置 OPENAI_API_KEY")
        model = getattr(settings, "openai_embedding_model", "text-embedding-3-small")
        base_url = (
            getattr(settings, "openai_embedding_base_url", None)
            or getattr(settings, "openai_base_url", None)
            or None
        )
        base_url = (base_url or "").strip() or None
        return _openai_compat_adapter(model=model, api_key=api_key, base_url=base_url)
    raise ConfigError(f"不支持的 embedding_type: {t}，可选: openai, api")
