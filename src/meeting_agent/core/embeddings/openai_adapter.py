from typing import List

from langchain_openai import OpenAIEmbeddings

from meeting_agent.core.embeddings.base import BaseEmbeddings


class OpenAIEmbeddingsAdapter(BaseEmbeddings):
    def __init__(self, model: str = "text-embedding-3-small", api_key: str = "", **kwargs):
        self._embeddings = OpenAIEmbeddings(model=model, api_key=api_key or None, **kwargs)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)
