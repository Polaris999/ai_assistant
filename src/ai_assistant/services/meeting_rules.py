"""会议预约规则来源：本地 settings 或业务后台 API（拉取并缓存）。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeetingBookingRules:
    max_days_ahead: int
    max_duration_minutes: int


@runtime_checkable
class IMeetingRulesProvider(Protocol):
    def get_booking_rules(self) -> MeetingBookingRules:
        ...


class SettingsMeetingRulesProvider:
    def get_booking_rules(self) -> MeetingBookingRules:
        try:
            from ai_assistant.config.meeting_rules_config import meeting_rules_config
            return MeetingBookingRules(
                max_days_ahead=meeting_rules_config.meeting_max_days_ahead,
                max_duration_minutes=meeting_rules_config.meeting_max_duration_minutes,
            )
        except Exception as e:
            logger.warning("从 settings 读取预约规则失败，使用默认: %s", e)
            return MeetingBookingRules(max_days_ahead=7, max_duration_minutes=240)


class BackendMeetingRulesProvider:
    """从业务后台 GET 接口拉取规则并内存缓存。API 返回 JSON：max_days_ahead, max_duration_minutes。"""

    def __init__(
        self,
        api_url: str,
        *,
        cache_seconds: int = 300,
        timeout_seconds: float = 5,
        fallback: Optional[MeetingBookingRules] = None,
    ) -> None:
        self._api_url = api_url.strip()
        self._cache_seconds = max(1, cache_seconds)
        self._timeout = timeout_seconds
        self._fallback = fallback or MeetingBookingRules(max_days_ahead=7, max_duration_minutes=240)
        self._cached: Optional[MeetingBookingRules] = None
        self._cached_at: float = 0.0

    def get_booking_rules(self) -> MeetingBookingRules:
        now = time.monotonic()
        if self._cached is not None and (now - self._cached_at) < self._cache_seconds:
            return self._cached
        try:
            import requests
            resp = requests.get(
                self._api_url,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            max_days = int(data.get("max_days_ahead", self._fallback.max_days_ahead))
            max_mins = int(data.get("max_duration_minutes", self._fallback.max_duration_minutes))
            if max_days < 1:
                max_days = self._fallback.max_days_ahead
            if max_mins < 1:
                max_mins = self._fallback.max_duration_minutes
            self._cached = MeetingBookingRules(max_days_ahead=max_days, max_duration_minutes=max_mins)
            self._cached_at = now
            return self._cached
        except Exception as e:
            logger.warning("从后台拉取预约规则失败，使用缓存或默认: %s", e)
            if self._cached is not None:
                return self._cached
            return self._fallback
