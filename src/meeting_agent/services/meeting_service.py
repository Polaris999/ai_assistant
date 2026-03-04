"""
会议业务服务接口：查询会议室、预定会议由本接口对接，可替换为 HTTP 调用业务后端。

- IMeetingService：协议定义，对接业务服务（本进程实现或远程 API）。
- DefaultMeetingService：默认实现（RAG + MeetingStore + ReminderScheduler），生产可替换为 HTTP 客户端。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional, Protocol, runtime_checkable

from meeting_agent.models.meeting import MeetingBooking
from meeting_agent.rag.meeting_rag import MeetingRAG
from meeting_agent.services.meeting_store import MeetingStore
from meeting_agent.services.reminder_scheduler import ReminderScheduler

logger = logging.getLogger(__name__)


@runtime_checkable
class IMeetingService(Protocol):
    """会议业务服务协议：查询会议室、预定会议。实现方可为本地逻辑或 HTTP 调用业务后端。"""

    def query_meeting_rooms(self, query: str = "") -> str:
        """查询会议室/预约信息，返回可展示给用户的文本。"""
        ...

    def book_meeting(
        self,
        title: str,
        start_time: datetime,
        duration_minutes: int = 60,
        room: Optional[str] = None,
        participants: Optional[List[str]] = None,
        remind_minutes_before: int = 15,
    ) -> dict[str, Any]:
        """
        预定会议。返回 dict：success (bool), booking (dict 或 None), error (str 或 None)。
        调用方可根据 success 与 booking 组装回复。
        """
        ...


class DefaultMeetingService:
    """默认实现：使用 RAG 查会议室，使用 MeetingStore + ReminderScheduler 创建预定。生产可替换为调用业务 HTTP 接口的实现。"""

    def __init__(
        self,
        meeting_store: Optional[MeetingStore] = None,
        reminder_scheduler: Optional[ReminderScheduler] = None,
        meeting_rag: Optional[MeetingRAG] = None,
    ):
        self._store = meeting_store or MeetingStore()
        self._scheduler = reminder_scheduler or ReminderScheduler()
        self._rag = meeting_rag or MeetingRAG()

    @property
    def scheduler(self) -> ReminderScheduler:
        """供 lifespan 优雅关闭时 shutdown(wait=True)。"""
        return self._scheduler

    def query_meeting_rooms(self, query: str = "") -> str:
        context = self._rag.retrieve_context(query or "会议室 预约", k=6)
        if not context.strip():
            return "当前暂无会议室信息。您可以直接说会议时间、主题和时长，我帮您预定。"
        return context.strip()

    def book_meeting(
        self,
        title: str,
        start_time: datetime,
        duration_minutes: int = 60,
        room: Optional[str] = None,
        participants: Optional[List[str]] = None,
        remind_minutes_before: int = 15,
    ) -> dict[str, Any]:
        try:
            reminder_at = start_time - timedelta(minutes=remind_minutes_before)
            if reminder_at <= datetime.now():
                reminder_at = datetime.now()
            booking = self._store.create_booking(
                title=title or "未命名会议",
                start_time=start_time,
                duration_minutes=duration_minutes,
                room=room,
                participants=participants or [],
                remind_minutes_before=remind_minutes_before,
            )
            job_id = self._scheduler.schedule_reminder(
                run_at=reminder_at,
                booking_id=booking.id,
                title=booking.title,
                start_time=booking.start_time,
            )
            booking.reminder_job_id = job_id
            self._store.add(booking)
            return {
                "success": True,
                "booking": booking.model_dump(mode="json"),
                "error": None,
            }
        except Exception as e:
            logger.exception("book_meeting 失败: %s", e)
            return {"success": False, "booking": None, "error": str(e)}
