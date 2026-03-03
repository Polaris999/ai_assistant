"""Embeddings 抽象：文档/查询向量化，可选异步。"""
from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddings(ABC):
    """向量化基类，子类可覆盖 aembed_* 做并发优化。"""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        pass

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        return self.embed_query(text)
