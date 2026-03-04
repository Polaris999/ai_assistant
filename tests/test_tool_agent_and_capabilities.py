from __future__ import annotations

from typing import Any, Optional

from ai_assistant.agent.capabilities.meeting import MeetingCapability
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

