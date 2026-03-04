"""会议预定内存存储与创建：单进程内 Dict 存储，可替换为持久化实现。"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ai_assistant.models.meeting import MeetingBooking


class MeetingStore:
    """会议预定仓储：创建、按 ID 查询、列出即将开始的预定。"""

    def __init__(self) -> None:
        self._bookings: Dict[str, MeetingBooking] = {}

    def add(self, booking: MeetingBooking) -> MeetingBooking:
        self._bookings[booking.id] = booking
        return booking

    def get(self, booking_id: str) -> Optional[MeetingBooking]:
        return self._bookings.get(booking_id)

    def remove(self, booking_id: str) -> bool:
        """移除指定预定（如取消会议）；存在并移除返回 True。"""
        if booking_id in self._bookings:
            del self._bookings[booking_id]
            return True
        return False

    def list_upcoming(self, after: Optional[datetime] = None) -> List[MeetingBooking]:
        after = after or datetime.now()
        return [b for b in self._bookings.values() if b.start_time >= after]

    def create_booking(
        self,
        title: str,
        start_time: datetime,
        duration_minutes: int = 60,
        room: Optional[str] = None,
        participants: Optional[List[str]] = None,
        remind_minutes_before: int = 15,
        reminder_job_id: Optional[str] = None,
    ) -> MeetingBooking:
        booking = MeetingBooking(
            id=str(uuid.uuid4()),
            title=title,
            start_time=start_time,
            duration_minutes=duration_minutes,
            room=room,
            participants=participants or [],
            remind_minutes_before=remind_minutes_before,
            reminder_job_id=reminder_job_id,
        )
        return self.add(booking)
