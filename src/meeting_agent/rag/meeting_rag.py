"""会议知识 RAG：支持 Chroma / Qdrant / Weaviate（按配置切换）+ 默认会议室/规则知识。"""
import logging
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from meeting_agent.config import settings
from meeting_agent.core.embeddings.base import BaseEmbeddings
from meeting_agent.core.embeddings.factory import get_embeddings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.vectorstore.factory import VectorStoreWrapper, get_vector_store

logger = logging.getLogger(__name__)

# 首次初始化时写入向量库的默认会议知识
DEFAULT_MEETING_KNOWLEDGE = [
    "会议室A：容纳10人，支持投影，工作日上午9点到下午6点可预约。",
    "会议室B：容纳4人，支持视频会议，全天可预约。",
    "会议室C：容纳20人，带白板，需提前一天预约。",
    "预约规则：单次会议不超过4小时，可提前7天内预约。",
    "取消规则：会议开始前2小时可免费取消，否则计入违约。",
]


class MeetingRAG:
    """会议知识检索：按配置使用 Chroma / Qdrant / Weaviate，支持默认知识初始化与按 query 检索。"""

    COLLECTION_NAME = "meeting_knowledge"

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embeddings: Optional[BaseEmbeddings] = None,
        vector_store_type: Optional[str] = None,
    ):
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
                self._embeddings = get_embeddings()
            except (ConfigError, ImportError) as e:
                logger.warning(
                    "RAG 降级为无向量检索（不崩溃）: %s；若需本地向量检索请安装: pip install -e \".[local]\"",
                    e,
                )
                self._no_rag = True
                return None
        try:
            self._vector_store = get_vector_store(
                collection_name=self.COLLECTION_NAME,
                embedding=self._embeddings,
                vector_store_type=self._vector_store_type,
                persist_dir=str(self.persist_dir),
            )
        except (ConfigError, ImportError) as e:
            logger.warning("RAG 降级为无向量检索（不崩溃）: %s", e)
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
            logger.info("RAG 添加 %s 个 chunk", len(chunks))
        except ImportError as e:
            logger.warning(
                "RAG 降级为无向量检索（不崩溃）: %s；若需本地向量检索请安装: pip install -e \".[local]\"",
                e,
            )
            self._no_rag = True
            self._vector_store = None

    def init_default_knowledge(self) -> None:
        vs = self._get_vector_store()
        if vs is None:
            logger.info("RAG 未就绪（未配置 Embeddings），跳过默认知识初始化，意图解析将无会议知识上下文")
            return
        count = vs.get_count()
        if count is not None and count > 0:
            logger.info("RAG 已有数据，跳过默认知识初始化")
            return
        self.add_documents(DEFAULT_MEETING_KNOWLEDGE)

    def retrieve(self, query: str, k: int = 4) -> List[Document]:
        vs = self._get_vector_store()
        if vs is None:
            return []
        return vs.similarity_search(query, k=k)

    def retrieve_context(self, query: str, k: int = 4) -> str:
        docs = self.retrieve(query, k=k)
        return "\n\n".join(d.page_content for d in docs)
