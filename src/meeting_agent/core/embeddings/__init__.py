# 仅导出 base、factory；OpenAI 适配器在 factory 中按需 import，避免未用 openai/api 时加载 torch
from meeting_agent.core.embeddings.base import BaseEmbeddings
from meeting_agent.core.embeddings.factory import get_embeddings

__all__ = ["BaseEmbeddings", "get_embeddings"]
