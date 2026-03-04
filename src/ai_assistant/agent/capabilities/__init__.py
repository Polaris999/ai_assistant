# 能力层：会议预定、后续可扩展运维工单等
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from ai_assistant.agent.capabilities.meeting import MeetingCapability

if TYPE_CHECKING:
    from ai_assistant.services.meeting_service import IMeetingService

__all__ = ["MeetingCapability", "get_default_capabilities"]


def get_default_capabilities(
    meeting_service: "IMeetingService | None" = None,
) -> List[Any]:
    """
    返回当前启用的能力列表；后续可在此注册运维工单等能力。
    若传入 meeting_service 则使用（便于测试或组合根注入），否则创建 DefaultMeetingService()。
    """
    if meeting_service is None:
        from ai_assistant.services.meeting_service import DefaultMeetingService
        meeting_service = DefaultMeetingService()
    return [MeetingCapability(meeting_service)]
