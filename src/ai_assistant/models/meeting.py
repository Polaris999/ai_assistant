"""会议领域模型：意图（解析结果）与预定（持久化/调度用）。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MeetingIntent(BaseModel):
    """LLM 解析出的会议预定意图，含主题、时间、时长、会议室、参与者、提醒分钟数。"""
    title: str = Field(description="会议主题")
    start_time: datetime = Field(description="会议开始时间")
    duration_minutes: int = Field(default=60, ge=15, le=480, description="时长（分钟）")
    room: Optional[str] = Field(default=None, description="会议室")
    participants: List[str] = Field(default_factory=list, description="参与者列表")
    remind_minutes_before: int = Field(default=15, ge=0, le=1440, description="提前多少分钟提醒")


class MeetingBooking(BaseModel):
    """已创建的会议预定记录，含 reminder_job_id 等调度关联。"""
    id: str
    title: str
    start_time: datetime
    duration_minutes: int
    room: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    remind_minutes_before: int = 15
    reminder_job_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
