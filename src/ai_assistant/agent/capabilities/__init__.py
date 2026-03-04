# 能力层：会议预定、后续可扩展运维工单等
from ai_assistant.agent.capabilities.meeting import MeetingCapability

__all__ = ["MeetingCapability", "get_default_capabilities"]


def get_default_capabilities():
    """返回当前启用的能力列表；后续可在此注册运维工单等能力。"""
    from ai_assistant.services.meeting_service import DefaultMeetingService
    return [MeetingCapability(DefaultMeetingService())]
