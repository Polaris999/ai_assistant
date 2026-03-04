"""领域模型与配置的简单单元测试。"""
from datetime import datetime

import pytest

from ai_assistant.models.meeting import MeetingBooking, MeetingIntent


def test_meeting_intent():
    intent = MeetingIntent(
        title="周会",
        start_time=datetime(2025, 3, 3, 14, 0),
        duration_minutes=60,
        room="A",
        remind_minutes_before=15,
    )
    assert intent.title == "周会"
    assert intent.duration_minutes == 60
    assert intent.room == "A"


def test_meeting_booking():
    booking = MeetingBooking(
        id="test-id",
        title="周会",
        start_time=datetime(2025, 3, 3, 14, 0),
        duration_minutes=60,
    )
    assert booking.id == "test-id"
    assert booking.remind_minutes_before == 15
