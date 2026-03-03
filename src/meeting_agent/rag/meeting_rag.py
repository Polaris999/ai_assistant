"""会议知识 RAG：Chroma 向量库 + 默认会议室/规则知识，供意图解析节点检索。"""
import logging
from pathlib import Path
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from meeting_agent.config import settings
from meeting_agent.core.embeddings.base import BaseEmbeddings
from meeting_agent.core.embeddings.factory import get_embeddings

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
    """基于 Chroma 的会议知识检索：支持默认知识初始化与按 query 检索上下文。"""

    COLLECTION_NAME = "meeting_knowledge"

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embeddings: Optional[BaseEmbeddings] = None,
    ):
        self.persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._embeddings = embeddings or get_embeddings()
        self._vector_store: Optional[Chroma] = None

    def _get_vector_store(self) -> Chroma:
        if self._vector_store is None:
            self._vector_store = Chroma(
                collection_name=self.COLLECTION_NAME,
                embedding_function=self._embeddings,
                persist_directory=str(self.persist_dir),
            )
        return self._vector_store

    def add_documents(self, texts: List[str], metadatas: Optional[List[dict]] = None) -> None:
        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
        docs = [Document(page_content=t, metadata=metadatas[i] if metadatas else {}) for i, t in enumerate(texts)]
        chunks = splitter.split_documents(docs)
        vs = self._get_vector_store()
        vs.add_documents(chunks)
        logger.info("RAG 添加 %s 个 chunk", len(chunks))

    def init_default_knowledge(self) -> None:
        vs = self._get_vector_store()
        try:
            existing = vs._collection.count()
            if existing > 0:
                logger.info("RAG 已有数据，跳过默认知识初始化")
                return
        except Exception:
            pass
        self.add_documents(DEFAULT_MEETING_KNOWLEDGE)

    def retrieve(self, query: str, k: int = 4) -> List[Document]:
        vs = self._get_vector_store()
        return vs.similarity_search(query, k=k)

    def retrieve_context(self, query: str, k: int = 4) -> str:
        docs = self.retrieve(query, k=k)
        return "\n\n".join(d.page_content for d in docs)
