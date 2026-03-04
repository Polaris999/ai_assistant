"""向量库胶水层：按配置返回 Chroma 或 Qdrant，供 RAG 使用。"""
from ai_assistant.core.vectorstore.factory import get_vector_store

__all__ = ["get_vector_store"]
