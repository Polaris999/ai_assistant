from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from ai_assistant.agent.capabilities.meeting import (
    MeetingCapability,
    DEFAULT_MAX_DAYS_AHEAD,
    DEFAULT_MAX_DURATION_MINUTES,
)
from ai_assistant.agent.tool_agent import ToolAgentRunner
from ai_assistant.core.llm.base import BaseLLM


class _FakeLLM(BaseLLM):
    def __init__(self, output: str):
        self._output = output

    def invoke(self, prompt: str, *, system: Optional[str] = None, temperature: float = 0, **kwargs: Any) -> str:
        return self._output


class _StubMeetingService:
    def __init__(self) -> None:
        self.query_called_with: list[str] = []
        self.cancel_called_with: list[str] = []

    def query_meeting_rooms(self, query: str = "") -> str:
        self.query_called_with.append(query)
        return "ROOMS_OK"

    def book_meeting(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"success": False, "booking": None, "error": "NOT_IMPLEMENTED"}

    def cancel_booking(self, booking_id: str) -> dict[str, Any]:
        self.cancel_called_with.append(booking_id)
        return {"success": True, "reply": f"cancelled:{booking_id}", "error": None}


def test_tool_agent_fallback_to_query_rooms_when_parse_fails():
    service = _StubMeetingService()
    caps = [MeetingCapability(service)]  # type: ignore[arg-type]
    runner = ToolAgentRunner(_FakeLLM("not a json"), caps)

    result = runner.invoke("查询会议室")
    assert result.get("error") is None
    assert result.get("booking") is None
    assert "ROOMS_OK" in (result.get("reply") or "")
    assert service.query_called_with == ["查询会议室"]


def test_tool_agent_query_rooms_when_llm_returns_valid_json():
    service = _StubMeetingService()
    caps = [MeetingCapability(service)]  # type: ignore[arg-type]
    runner = ToolAgentRunner(_FakeLLM('{"tool":"query_meeting_rooms","arguments":{}}'), caps)

    result = runner.invoke("有哪些会议室")
    assert result.get("error") is None
    assert result.get("booking") is None
    assert "ROOMS_OK" in (result.get("reply") or "")
    assert service.query_called_with == [""]


def test_meeting_capability_cancel_uses_last_booking_id_from_session():
    service = _StubMeetingService()
    cap = MeetingCapability(service)  # type: ignore[arg-type]

    ctx = {"get_session_value": lambda k: "id123"}
    result = cap.execute("cancel_meeting", {}, ctx)
    assert result.get("error") is None
    assert result.get("booking") is None
    assert "cancelled:id123" in (result.get("reply") or "")
    assert service.cancel_called_with == ["id123"]


def test_meeting_capability_book_exceed_max_days_ahead_returns_rule_error():
    """业内实践：规则在代码中校验，超过配置天数不调后端，返回固定错误码。"""
    service = _StubMeetingService()
    cap = MeetingCapability(service, max_days_ahead=7, max_duration_minutes=240)  # type: ignore[arg-type]
    now = datetime.now()
    beyond = now + timedelta(days=DEFAULT_MAX_DAYS_AHEAD + 1)
    start_time_str = beyond.strftime("%Y-%m-%dT14:00:00")
    ctx = {"current_time": now}

    result = cap.execute(
        "book_meeting",
        {"title": "测试", "start_time": start_time_str, "duration_minutes": 60},
        ctx,
    )
    assert result.get("error") == "EXCEED_MAX_DAYS_AHEAD"
    assert result.get("booking") is None
    assert "7" in (result.get("reply") or "")


def test_meeting_capability_book_exceed_max_duration_returns_rule_error():
    """业内实践：单次会议时长由配置限制，在 execute 内校验。"""
    service = _StubMeetingService()
    cap = MeetingCapability(service, max_days_ahead=7, max_duration_minutes=240)  # type: ignore[arg-type]
    now = datetime.now()
    start_time_str = (now + timedelta(days=1)).strftime("%Y-%m-%dT14:00:00")
    ctx = {"current_time": now}

    result = cap.execute(
        "book_meeting",
        {"title": "测试", "start_time": start_time_str, "duration_minutes": DEFAULT_MAX_DURATION_MINUTES + 60},
        ctx,
    )
    assert result.get("error") == "EXCEED_MAX_DURATION"
    assert result.get("booking") is None
    assert "4" in (result.get("reply") or "") or "240" in (result.get("reply") or "")

