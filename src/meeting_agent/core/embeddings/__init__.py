# OpenAI 适配器在 factory 内按需 import
from meeting_agent.core.embeddings.base import BaseEmbeddings
from meeting_agent.core.embeddings.factory import get_embeddings

__all__ = ["BaseEmbeddings", "get_embeddings"]
