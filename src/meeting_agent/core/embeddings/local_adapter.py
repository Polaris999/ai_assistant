"""本地 Embeddings 适配器：HuggingFace/sentence-transformers。"""
from typing import List

from meeting_agent.core.embeddings.base import BaseEmbeddings


class LocalEmbeddingsAdapter(BaseEmbeddings):
    """基于 sentence-transformers 的本地向量化。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", **kwargs):
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        except ImportError as e:
            raise ImportError(
                "使用本地 Embeddings 需安装: pip install sentence-transformers（或 pip install -e '.[local]'）"
            ) from e
        self._embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=kwargs.get("model_kwargs") or {},
            encode_kwargs=kwargs.get("encode_kwargs") or {"normalize_embeddings": True},
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)
