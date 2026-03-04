"""知识库路由：只返回 success；出错由抛异常 + 全局处理器统一返回。"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ai_assistant.api.deps import get_rag_by_kb_name, get_request_id
from ai_assistant.api.response import success
from ai_assistant.core.exceptions import ServiceUnavailableError, ValidationError
from ai_assistant.rag.meeting_rag import ALLOWED_KB_NAMES, MeetingRAG

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_kb(kb: str) -> str:
    """校验 kb 并返回规范名；非法时抛 ValidationError，由全局异常处理器返回 422。"""
    k = (kb or "meeting").strip().lower()
    if k not in ALLOWED_KB_NAMES:
        raise ValidationError(
            f"不支持的知识库: {kb}，可选: {ALLOWED_KB_NAMES}",
            details={"kb": kb, "allowed": list(ALLOWED_KB_NAMES)},
        )
    return k


class KnowledgeAppendBody(BaseModel):
    """追加知识：texts 与 text 二选一或同时传，均会拆分后写入向量库。"""
    texts: Optional[List[str]] = Field(None, description="多段文本，每段会按规则分块后写入")
    text: Optional[str] = Field(None, description="单段文本，将按换行或整段分块后写入")


def _normalize_texts(body: KnowledgeAppendBody) -> List[str]:
    out: List[str] = []
    if body.texts:
        for t in body.texts:
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
    if body.text and body.text.strip():
        for line in body.text.strip().split("\n"):
            if line.strip():
                out.append(line.strip())
    return out


@router.get(
    "/knowledge/bases",
    summary="知识库列表",
    description="返回已登记的知识库名称列表（meeting、ops_ticket 等），用于 CRUD 时指定 kb 参数。",
)
async def list_knowledge_bases(request_id: str = Depends(get_request_id)) -> JSONResponse:
    return success({"bases": list(ALLOWED_KB_NAMES)}, request_id)


@router.post(
    "/knowledge",
    summary="追加知识库",
    description="向指定 kb 的向量库追加文本；kb 默认 meeting，可选 ops_ticket。建议由网关限制为管理端。",
)
async def append_knowledge(
    request: Request,
    body: KnowledgeAppendBody,
    kb: str = "meeting",
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    kb_name = _validate_kb(kb)
    rag = get_rag_by_kb_name(request, kb_name)
    texts = _normalize_texts(body)
    if not texts:
        raise ValidationError(
            "请提供 texts 或 text，且至少包含一段非空内容",
            details={"appended": 0, "kb": kb_name},
        )
    rag.add_documents(texts)
    logger.info("knowledge append kb=%s texts_count=%s", kb_name, len(texts))
    return success({"appended": len(texts), "kb": kb_name}, request_id, status_code=201)


@router.get(
    "/knowledge",
    summary="知识库统计",
    description="返回指定 kb 的 chunk 数量；kb 默认 meeting。",
)
async def get_knowledge_stats(
    request: Request,
    kb: str = "meeting",
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    kb_name = _validate_kb(kb)
    rag = get_rag_by_kb_name(request, kb_name)
    count = rag.get_count()
    if count is None:
        return success(
            {"kb": kb_name, "ready": False, "count": None, "message": "向量库未就绪或不可用"},
            request_id,
        )
    return success({"kb": kb_name, "ready": True, "count": count}, request_id)


@router.get(
    "/knowledge/search",
    summary="知识库检索预览",
    description="按关键词/问句检索指定 kb；kb 默认 meeting。",
)
async def search_knowledge(
    request: Request,
    q: str = "",
    k: int = 5,
    kb: str = "meeting",
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    kb_name = _validate_kb(kb)
    rag = get_rag_by_kb_name(request, kb_name)
    if not (q or "").strip():
        return success({"kb": kb_name, "query": "", "documents": []}, request_id)
    docs = rag.retrieve((q or "").strip(), k=min(max(1, k), 20))
    items = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
    return success({"kb": kb_name, "query": q.strip(), "documents": items}, request_id)


@router.delete(
    "/knowledge",
    summary="清空知识库",
    description="清空指定 kb 内全部文档；kb 默认 meeting。Chroma 支持；其他向量库可能不支持。建议由网关限制为管理端。",
)
async def clear_knowledge(
    request: Request,
    kb: str = "meeting",
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    kb_name = _validate_kb(kb)
    rag = get_rag_by_kb_name(request, kb_name)
    ok = rag.clear_all()
    if not ok:
        raise ServiceUnavailableError(
            "知识库未就绪或当前向量库不支持清空",
            details={"cleared": False, "kb": kb_name},
        )
    logger.info("knowledge clear_all kb=%s", kb_name)
    return success({"cleared": True, "kb": kb_name}, request_id)
