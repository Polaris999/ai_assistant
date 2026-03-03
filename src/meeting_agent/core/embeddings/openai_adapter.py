"""OpenAI Embeddings 适配器，供 RAG 等模块使用。"""
from typing import List

from langchain_openai import OpenAIEmbeddings

from meeting_agent.core.embeddings.base import BaseEmbeddings


class OpenAIEmbeddingsAdapter(BaseEmbeddings):
    """通过 LangChain OpenAIEmbeddings 调用 OpenAI 向量接口。"""

    def __init__(self, model: str = "text-embedding-3-small", api_key: str = "", **kwargs):
        self._embeddings = OpenAIEmbeddings(model=model, api_key=api_key or None, **kwargs)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)
