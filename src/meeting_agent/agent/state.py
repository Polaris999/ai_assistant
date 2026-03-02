from __future__ import annotations
from typing import TYPE_CHECKING, Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from meeting_agent.models.meeting import MeetingBooking, MeetingIntent

if TYPE_CHECKING:
    from meeting_agent.core.llm.base import BaseLLM
    from meeting_agent.services.meeting_store import MeetingStore
    from meeting_agent.services.reminder_scheduler import ReminderScheduler
    from meeting_agent.rag.meeting_rag import MeetingRAG


class MeetingAgentState(TypedDict, total=False):
    user_input: str
    rag_context: str
    intent: Optional[MeetingIntent]
    booking: Optional[MeetingBooking]
    reply: str
    error: Optional[str]
    messages: Annotated[list[BaseMessage], add_messages]
    _llm: "BaseLLM"
    _reply_llm: Optional["BaseLLM"]
    _store: "MeetingStore"
    _scheduler: "ReminderScheduler"
    _rag: "MeetingRAG"
