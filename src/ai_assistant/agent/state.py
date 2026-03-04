"""Agent 图状态定义：业务字段与注入依赖（_llm、_store 等）统一由 TypedDict 描述。"""
from __future__ import annotations
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from ai_assistant.models.meeting import MeetingBooking, MeetingIntent


class MeetingAgentState(TypedDict, total=False):
    """LangGraph 状态：user_input/rag_context/intent/booking/reply/error，及运行时注入的 _llm/_store 等。"""
    user_input: str
    rag_context: str
    intent: Optional[MeetingIntent]
    booking: Optional[MeetingBooking]
    reply: str
    error: Optional[str]
    messages: Annotated[list[BaseMessage], add_messages]
    _llm: Any
    _reply_llm: Any
    _store: Any
    _scheduler: Any
    _rag: Any
