"""会议知识 RAG：支持 Chroma / Qdrant / Weaviate（按配置切换）+ 默认会议室/规则知识。
多知识库：按 kb_name 分集合（meeting / ops_ticket 等），每个业务独立 collection，与 Langchain-Chatchat 多 KB 一致。
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import List, Optional

# Chroma get_count() 超时（秒），超时则跳过默认知识写入，避免请求卡死
RAG_GET_COUNT_TIMEOUT = 15

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ai_assistant.config import settings
from ai_assistant.core.embeddings.base import BaseEmbeddings
from ai_assistant.core.embeddings.factory import get_embeddings
from ai_assistant.core.exceptions import ConfigError
from ai_assistant.core.vectorstore.factory import VectorStoreWrapper, get_vector_store

logger = logging.getLogger(__name__)

# 知识库名称与集合名：按库名分集合，后续运维工单等新增 kb 在此登记
KB_MEETING = "meeting"
KB_OPS_TICKET = "ops_ticket"
ALLOWED_KB_NAMES = [KB_MEETING, KB_OPS_TICKET]


def collection_name_for(kb_name: str) -> str:
    """知识库名称 -> 向量库 collection 名；未登记的名称仍可生成（如自定义库），建议用白名单校验。"""
    return f"{kb_name.strip().lower()}_knowledge"


# 首次初始化时写入向量库的默认会议知识
DEFAULT_MEETING_KNOWLEDGE = [
    "会议室A：容纳10人，支持投影，工作日上午9点到下午6点可预约。",
    "会议室B：容纳4人，支持视频会议，全天可预约。",
    "会议室C：容纳20人，带白板，需提前一天预约。",
    "预约规则：单次会议不超过4小时，可提前7天内预约。",
    "取消规则：会议开始前2小时可免费取消，否则计入违约。",
]


class MeetingRAG:
    """按集合维度的知识检索：支持默认会议知识初始化与按 query 检索。多知识库时通过 collection_name 区分（如 meeting / ops_ticket）。"""

    DEFAULT_COLLECTION_NAME = "meeting_knowledge"

    def __init__(
        self,
        collection_name: Optional[str] = None,
        persist_dir: Optional[str] = None,
        embeddings: Optional[BaseEmbeddings] = None,
        vector_store_type: Optional[str] = None,
    ):
        self._collection_name = (collection_name or "").strip() or self.DEFAULT_COLLECTION_NAME
        self.persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        if getattr(settings, "vector_store_type", "chroma").strip().lower() == "chroma":
            self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._embeddings: Optional[BaseEmbeddings] = embeddings
        self._vector_store: Optional[VectorStoreWrapper] = None
        self._no_rag = False
        self._vector_store_type = vector_store_type

    def _get_vector_store(self) -> Optional[VectorStoreWrapper]:
        if self._vector_store is not None:
            return self._vector_store
        if self._no_rag:
            return None
        if self._embeddings is None:
            try:
                t0 = time.perf_counter()
                self._embeddings = get_embeddings()
                logger.debug("RAG embeddings %.0fms", (time.perf_counter() - t0) * 1000)
            except (ConfigError, ImportError) as e:
                logger.warning("RAG 无向量检索: %s", e)
                self._no_rag = True
                return None
        try:
            t0 = time.perf_counter()
            self._vector_store = get_vector_store(
                collection_name=self._collection_name,
                embedding=self._embeddings,
                vector_store_type=self._vector_store_type,
                persist_dir=str(self.persist_dir),
            )
            logger.debug("RAG 向量库 %.0fms", (time.perf_counter() - t0) * 1000)
        except (ConfigError, ImportError) as e:
            logger.warning("RAG 无向量检索: %s", e)
            self._no_rag = True
            return None
        return self._vector_store

    def add_documents(self, texts: List[str], metadatas: Optional[List[dict]] = None) -> None:
        vs = self._get_vector_store()
        if vs is None:
            logger.debug("RAG 未就绪，跳过 add_documents")
            return
        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
        docs = [Document(page_content=t, metadata=metadatas[i] if metadatas else {}) for i, t in enumerate(texts)]
        chunks = splitter.split_documents(docs)
        try:
            vs.add_documents(chunks)
            logger.debug("RAG add %s chunks", len(chunks))
        except ImportError as e:
            logger.warning("RAG 无向量检索: %s；需配置 EMBEDDING_BASE_URL（单独 embedding 服务）", e)
            self._no_rag = True
            self._vector_store = None

    def init_default_knowledge(self) -> None:
        vs = self._get_vector_store()
        if vs is None:
            return
        t0 = time.perf_counter()
        count: Optional[int] = None
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                count = ex.submit(vs.get_count).result(timeout=RAG_GET_COUNT_TIMEOUT)
        except FuturesTimeoutError:
            logger.warning("RAG get_count 超时 %ss，跳过默认知识", RAG_GET_COUNT_TIMEOUT)
            return
        except Exception as e:
            logger.warning("RAG get_count 异常: %s", e)
            return
        if count is not None and count > 0:
            logger.debug("RAG 已有数据 count=%s，跳过默认知识", count)
            return
        self.add_documents(DEFAULT_MEETING_KNOWLEDGE)
        logger.info("RAG 默认知识写入 %.0fms", (time.perf_counter() - t0) * 1000)

    def retrieve(self, query: str, k: int = 4) -> List[Document]:
        vs = self._get_vector_store()
        if vs is None:
            return []
        return vs.similarity_search(query, k=k)

    def retrieve_context(self, query: str, k: int = 4) -> str:
        docs = self.retrieve(query, k=k)
        return "\n\n".join(d.page_content for d in docs)

    def get_count(self) -> Optional[int]:
        """返回当前向量库中的 chunk 数量，未就绪或不可用时返回 None。"""
        vs = self._get_vector_store()
        if vs is None:
            return None
        return vs.get_count()

    def clear_all(self) -> bool:
        """清空当前集合内全部文档。Chroma 支持；Qdrant/Weaviate 暂无 get_ids 时返回 False。"""
        vs = self._get_vector_store()
        if vs is None:
            return False
        ids = vs.get_ids(limit=50_000)
        if not ids:
            if (vs.get_count() or 0) > 0:
                logger.warning("RAG clear_all 无法获取 id 列表，当前向量库可能不支持清空")
                return False
            return True
        vs.delete_ids(ids)
        logger.info("RAG clear_all deleted count=%s", len(ids))
        return True
