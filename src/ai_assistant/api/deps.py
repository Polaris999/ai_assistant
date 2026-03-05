"""API 依赖：供 FastAPI 路由通过 Depends() 注入 settings、Agent、request_id、知识库 RAG 等。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from ai_assistant.rag.meeting_rag import MeetingRAG

from ai_assistant.config import settings
from ai_assistant.config.settings import Settings


def get_settings() -> Settings:
    """返回全局 settings 单例，供 FastAPI Depends 注入。未使用 lru_cache，因已是模块级单例。"""
    return settings


def get_request_id(request: Request) -> str:
    """从中间件写入的 request.state 取 request_id，供响应与日志使用。"""
    return getattr(request.state, "request_id", "") or ""


def get_agent(request: Request) -> Any:
    """从 app.state 取 Agent，未设置时懒创建占位。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is not None:
        return agent
    from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
    request.app.state.agent = create_agent_or_placeholder()
    return request.app.state.agent


def get_rag_by_kb_name(request: Request, kb_name: str) -> "MeetingRAG":
    """按知识库名称返回 RAG 实例；kb_name 对应独立 collection（meeting -> meeting_knowledge，ops_ticket -> ops_ticket_knowledge）。"""
    from ai_assistant.rag.meeting_rag import MeetingRAG, collection_name_for
    kb_name = (kb_name or "meeting").strip().lower()
    cache_key = f"_rag_{kb_name}"
    rag = getattr(request.app.state, cache_key, None)
    if rag is not None:
        return rag
    coll = collection_name_for(kb_name)
    setattr(request.app.state, cache_key, MeetingRAG(collection_name=coll))
    return getattr(request.app.state, cache_key)
