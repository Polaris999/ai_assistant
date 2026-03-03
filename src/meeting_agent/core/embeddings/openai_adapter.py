"""OpenAI 兼容 Embeddings 适配器：支持官方 OpenAI 或私有化/自托管向量接口（同 API 规范）。"""
from typing import List, Optional

from langchain_openai import OpenAIEmbeddings

from meeting_agent.core.embeddings.base import BaseEmbeddings


class OpenAIEmbeddingsAdapter(BaseEmbeddings):
    """通过 LangChain OpenAIEmbeddings 调用 OpenAI 或任意 OpenAI 兼容的向量接口（可配 base_url 做私有化）。"""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str = "",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self._embeddings = OpenAIEmbeddings(
            model=model,
            api_key=api_key or None,
            base_url=base_url,
            **kwargs,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)
