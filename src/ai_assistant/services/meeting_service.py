"""会议业务：查会议室、订会、取消。IMeetingService 可本地实现或 HTTP 调后端。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional, Protocol, runtime_checkable

from ai_assistant.models.meeting import MeetingBooking
from ai_assistant.rag.meeting_rag import MeetingRAG
from ai_assistant.services.meeting_store import MeetingStore
from ai_assistant.services.reminder_scheduler import ReminderScheduler

logger = logging.getLogger(__name__)


@runtime_checkable
class IMeetingService(Protocol):
    def query_meeting_rooms(self, query: str = "") -> str:
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
        """返回 success, booking?, error?"""
        ...

    def cancel_booking(self, booking_id: str) -> dict[str, Any]:
        """返回 success, reply, error?"""
        ...


class DefaultMeetingService:
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

    def cancel_booking(self, booking_id: str) -> dict[str, Any]:
        if not (booking_id or "").strip():
            return {"success": False, "reply": "未指定要取消的会议。", "error": "MISSING_BOOKING_ID"}
        bid = (booking_id or "").strip()
        booking = self._store.get(bid)
        if not booking:
            return {"success": False, "reply": "未找到该预定，可能已取消或不存在。", "error": "NOT_FOUND"}
        try:
            if getattr(booking, "reminder_job_id", None):
                self._scheduler.cancel_reminder(booking.reminder_job_id)
            self._store.remove(bid)
            return {"success": True, "reply": f"已取消会议「{booking.title}」。", "error": None}
        except Exception as e:
            logger.exception("cancel_booking 失败: %s", e)
            return {"success": False, "reply": "取消失败，请稍后重试。", "error": str(e)}
