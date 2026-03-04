"""API 依赖：settings、Agent、知识库 RAG。"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from ai_assistant.rag.meeting_rag import MeetingRAG

from ai_assistant.config import settings
from ai_assistant.config.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return settings


def get_agent(request: Request) -> Any:
    """从 app.state 取 Agent，未设置时懒创建占位。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is not None:
        return agent
    from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
    request.app.state.agent = create_agent_or_placeholder()
    return request.app.state.agent


def get_meeting_rag(request: Request) -> MeetingRAG:
    """供知识库 API 使用：默认会议库（向后兼容）。"""
    return get_rag_by_kb_name(request, "meeting")


def get_rag_by_kb_name(request: Request, kb_name: str) -> MeetingRAG:
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
