"""Embeddings 胶水层抽象：统一文档/查询向量化接口。"""
from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddings(ABC):
    """向量化抽象基类，由 openai 等适配器实现。"""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文档向量化。"""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """单条查询向量化。"""
        pass
