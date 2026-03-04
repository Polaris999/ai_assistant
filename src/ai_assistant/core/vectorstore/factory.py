# core/vectorstore/factory.py
"""向量库工厂：chroma / qdrant / weaviate；进程内单例缓存复用连接。"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

from ai_assistant.config import settings
from ai_assistant.core.embeddings.base import BaseEmbeddings
from ai_assistant.core.embeddings.factory import get_embeddings
from ai_assistant.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

VECTOR_STORE_CHROMA = "chroma"
VECTOR_STORE_QDRANT = "qdrant"
VECTOR_STORE_WEAVIATE = "weaviate"

# 进程内缓存：相同配置复用同一 VectorStoreWrapper，避免重复建连
_vector_store_cache: dict[Tuple[str, ...], VectorStoreWrapper] = {}
_vector_store_cache_lock = threading.Lock()


class VectorStoreWrapper:
    """统一封装：add_documents、similarity_search、get_count（可选），便于 RAG 判断是否已有数据。"""

    def __init__(
        self,
        store: VectorStore,
        get_count: Optional[Callable[[], int]] = None,
    ) -> None:
        self._store = store
        self._get_count = get_count

    def add_documents(self, documents: List[Document], **kwargs: Any) -> List[str]:
        return self._store.add_documents(documents, **kwargs)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> List[Document]:
        return self._store.similarity_search(query, k=k, **kwargs)

    def get_count(self) -> Optional[int]:
        """返回当前集合中的文档/点数量，若不可用则返回 None。"""
        if self._get_count is None:
            return None
        try:
            return self._get_count()
        except Exception as e:
            logger.debug("向量库 get_count 失败: %s", e)
            return None


def get_vector_store(
    collection_name: str,
    embedding: Optional[BaseEmbeddings] = None,
    vector_store_type: Optional[str] = None,
    *,
    persist_dir: Optional[str] = None,
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
    weaviate_url: Optional[str] = None,
    weaviate_api_key: Optional[str] = None,
) -> VectorStoreWrapper:
    """
    根据配置返回向量库封装（Chroma / Qdrant / Weaviate）；相同配置复用进程内缓存连接。
    缓存 key 为 (type, collection_name, persist_dir, urls)，不区分 embedding 实例，同配置共享连接。
    若未传 embedding 则使用 get_embeddings()；未传 type/persist_dir/url 等则从 settings 读取。
    """
    t = (vector_store_type or getattr(settings, "vector_store_type", None) or VECTOR_STORE_CHROMA).strip().lower()
    persist = (persist_dir or getattr(settings, "chroma_persist_dir", "") or "").strip()
    qurl = (qdrant_url or getattr(settings, "qdrant_url", "") or "").strip().rstrip("/")
    wurl = (weaviate_url or getattr(settings, "weaviate_url", "") or "").strip().rstrip("/")
    cache_key: Tuple[str, ...] = (t, collection_name, persist, qurl, wurl)
    with _vector_store_cache_lock:
        if cache_key in _vector_store_cache:
            logger.debug("向量库复用缓存连接 cache_key=%s", cache_key[:3])
            return _vector_store_cache[cache_key]

    if embedding is None:
        try:
            embedding = get_embeddings()
        except (ConfigError, ImportError) as e:
            logger.warning("向量库需 Embeddings，当前不可用: %s", e)
            raise

    if t == VECTOR_STORE_CHROMA:
        from langchain_chroma import Chroma

        persist_dir_resolved = persist_dir or getattr(settings, "chroma_persist_dir", "./data/chroma_db")
        store = Chroma(
            collection_name=collection_name,
            embedding_function=embedding,
            persist_directory=str(persist_dir_resolved),
        )

        def _chroma_count() -> int:
            return store._collection.count()

        wrapper = VectorStoreWrapper(store, get_count=_chroma_count)
        with _vector_store_cache_lock:
            _vector_store_cache[cache_key] = wrapper
        return wrapper
    if t == VECTOR_STORE_QDRANT:
        try:
            from langchain_qdrant import QdrantVectorStore
            from qdrant_client import QdrantClient
        except ImportError as e:
            raise ConfigError(
                "使用 Qdrant 需安装: pip install -e '.[qdrant]' 或 pip install langchain-qdrant qdrant-client"
            ) from e
        url = qurl or (getattr(settings, "qdrant_url", None) or "").strip()
        if not url:
            raise ConfigError("使用 Qdrant 需配置 QDRANT_URL（例如 http://localhost:6333）")
        api_key = (qdrant_api_key or getattr(settings, "qdrant_api_key", None) or "").strip() or None
        client = QdrantClient(url=url, api_key=api_key or None)
        store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embedding,
        )

        def _qdrant_count() -> int:
            try:
                return client.get_collection(collection_name).points_count
            except Exception:
                return 0

        wrapper = VectorStoreWrapper(store, get_count=_qdrant_count)
        with _vector_store_cache_lock:
            _vector_store_cache[cache_key] = wrapper
        return wrapper
    if t == VECTOR_STORE_WEAVIATE:
        try:
            import weaviate
            from weaviate.classes.init import Auth
            from langchain_weaviate import WeaviateVectorStore
        except ImportError as e:
            raise ConfigError(
                "使用 Weaviate 需安装: pip install -e '.[weaviate]' 或 pip install langchain-weaviate weaviate-client"
            ) from e
        url = wurl or (getattr(settings, "weaviate_url", None) or "").strip()
        if not url:
            raise ConfigError("使用 Weaviate 需配置 WEAVIATE_URL（例如 http://localhost:8080，Dify 默认可用）")
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8080)
        secure = parsed.scheme == "https"
        # 同一 host 下 http.port 与 grpc.port 必须不同；若 URL 端口为 50051 则视为 gRPC，HTTP 用 8080
        grpc_port = 50051
        http_port = 8080 if port == grpc_port else port
        api_key = (weaviate_api_key or getattr(settings, "weaviate_api_key", None) or "").strip() or None
        auth = Auth.api_key(api_key) if api_key else None
        # skip_init_checks=True：当 gRPC(50051) 不可达或超时时仍可连接，仅用 REST 做检索/写入
        client = weaviate.connect_to_custom(
            http_host=host,
            http_port=http_port,
            http_secure=secure,
            grpc_host=host,
            grpc_port=grpc_port,
            grpc_secure=secure,
            auth_credentials=auth,
            skip_init_checks=True,
        )
        text_key = getattr(settings, "weaviate_text_key", "content") or "content"
        store = WeaviateVectorStore(
            client=client,
            index_name=collection_name,
            text_key=text_key,
            embedding=embedding,
        )

        def _weaviate_count() -> int:
            try:
                coll = client.collections.use(collection_name)
                total = coll.aggregate.over_all(total_count=True).total_count
                return total if total is not None else 0
            except Exception:
                return 0

        wrapper = VectorStoreWrapper(store, get_count=_weaviate_count)
        with _vector_store_cache_lock:
            _vector_store_cache[cache_key] = wrapper
        return wrapper
    raise ConfigError(f"不支持的 vector_store_type: {t}，可选: chroma, qdrant, weaviate")
