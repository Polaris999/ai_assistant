from typing import Optional

from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.embeddings.base import BaseEmbeddings
from meeting_agent.core.embeddings.openai_adapter import OpenAIEmbeddingsAdapter

EMBEDDING_TYPE_OPENAI = "openai"


def get_embeddings(embedding_type: Optional[str] = None) -> BaseEmbeddings:
    t = embedding_type or getattr(settings, "embedding_type", None) or EMBEDDING_TYPE_OPENAI
    if t == EMBEDDING_TYPE_OPENAI:
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("使用 OpenAI Embeddings 需配置 OPENAI_API_KEY")
        model = getattr(settings, "openai_embedding_model", "text-embedding-3-small")
        return OpenAIEmbeddingsAdapter(model=model, api_key=api_key)
    raise ConfigError(f"不支持的 embedding_type: {t}，可选: openai")
