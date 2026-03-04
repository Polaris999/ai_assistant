# 能力层：会议预定、后续可扩展运维工单等
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from ai_assistant.agent.capabilities.meeting import MeetingCapability

if TYPE_CHECKING:
    from ai_assistant.services.meeting_service import IMeetingService
    from ai_assistant.services.meeting_rules import IMeetingRulesProvider

__all__ = ["MeetingCapability", "get_default_capabilities"]


def get_default_capabilities(
    meeting_service: "IMeetingService | None" = None,
    rules_provider: "IMeetingRulesProvider | None" = None,
) -> List[Any]:
    """返回能力列表。不传 meeting_service 则创建默认；不传 rules_provider 则按 MEETING_RULES_API_URL 选后台或 settings。"""
    if meeting_service is None:
        from ai_assistant.services.meeting_service import DefaultMeetingService
        meeting_service = DefaultMeetingService()
    if rules_provider is None:
        try:
            from ai_assistant.config.meeting_rules_config import meeting_rules_config
            if (meeting_rules_config.meeting_rules_api_url or "").strip():
                from ai_assistant.services.meeting_rules import BackendMeetingRulesProvider
                rules_provider = BackendMeetingRulesProvider(
                    meeting_rules_config.meeting_rules_api_url.strip(),
                    cache_seconds=meeting_rules_config.meeting_rules_cache_seconds,
                )
            else:
                from ai_assistant.services.meeting_rules import SettingsMeetingRulesProvider
                rules_provider = SettingsMeetingRulesProvider()
        except Exception:
            from ai_assistant.services.meeting_rules import SettingsMeetingRulesProvider
            rules_provider = SettingsMeetingRulesProvider()
    return [MeetingCapability(meeting_service, rules_provider=rules_provider)]
