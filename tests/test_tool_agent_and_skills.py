"""LangGraph Agent 与技能层（Skills）单测。会议仅走 HTTP，使用 GenericSkill + mock 后端。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun

from ai_assistant.agent.langgraph_runner import LangGraphRunner
from ai_assistant.agent.skills.generic import GenericSkill
from ai_assistant.agent.skills.manager import SkillManager


class _FakeChatModel(BaseChatModel):
    """测试用：按顺序返回预定义的 AIMessage，支持 tool_calls。"""
    responses: list[BaseMessage]

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools: list, **kwargs: object) -> "_FakeChatModel":
        """LangGraph create_react_agent 会 bind_tools，直接返回自身。"""
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        if not self.responses:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
        msg = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _meeting_skill_doc():
    """会议技能 doc（tools 从 skill_docs/meeting/tools.json 加载），executor.url 由测试 mock。"""
    tools_path = Path(__file__).resolve().parent.parent / "skill_docs" / "meeting" / "tools.json"
    tools = json.loads(tools_path.read_text(encoding="utf-8")) if tools_path.exists() else []
    return {
        "id": "meeting",
        "name": "会议预定",
        "description": "查会议室、订会、取消。",
        "tools": tools,
        "executor": {"type": "http", "url": "http://test-meeting/skill"},
    }


def _mock_manager_with_meeting_skill():
    """返回带会议技能（mock URL）的 SkillManager，用于单测。"""
    doc = _meeting_skill_doc()
    skill = GenericSkill(doc)
    manager = MagicMock(spec=SkillManager)
    manager.get_skills.return_value = [skill]
    manager.use_skill_catalog_only.return_value = False
    manager.execute_tool = lambda name, args, ctx: skill.execute(name, args or {}, ctx)
    return manager


def _fake_chat_model_tool_then_reply(tool_name: str, arguments: dict, final_reply: str = "ROOMS_OK"):
    """返回测试用 ChatModel：第一次返回 tool_calls，第二次返回最终回复。"""
    first = AIMessage(
        content="",
        tool_calls=[{"id": "tc-1", "name": tool_name, "args": arguments}],
    )
    second = AIMessage(content=final_reply)
    return _FakeChatModel(responses=[first, second])


def test_langgraph_chitchat_short_circuit_no_llm():
    """阶段 1：问候「你好」意图短路，不调用 LLM、不调用技能后端。"""
    manager = _mock_manager_with_meeting_skill()
    fake_model = MagicMock()
    runner = LangGraphRunner(manager=manager, model=fake_model)

    with patch("requests.post") as m:
        result = runner.invoke("你好")
    assert result.get("error") is None
    assert "你好" in (result.get("reply") or "")
    assert "预定" in (result.get("reply") or "")
    fake_model.invoke.assert_not_called()
    m.assert_not_called()


def test_langgraph_query_rooms_via_tool():
    """Agent 调用 query_meeting_rooms 工具时，请求转发到技能 HTTP 后端。"""
    manager = _mock_manager_with_meeting_skill()
    fake_model = _fake_chat_model_tool_then_reply("query_meeting_rooms", {"query": "有哪些会议室"})
    runner = LangGraphRunner(manager=manager, model=fake_model)

    with patch("requests.post") as m:
        m.return_value.status_code = 200
        m.return_value.content = b'{"reply":"ROOMS_OK","booking":null,"error":null}'
        m.return_value.json.return_value = {"reply": "ROOMS_OK", "booking": None, "error": None}
        m.return_value.raise_for_status = lambda: None

        result = runner.invoke("有哪些会议室")
    assert result.get("error") is None
    assert "ROOMS_OK" in (result.get("reply") or "")
    m.assert_called_once()
    call_json = m.call_args.kwargs.get("json") or m.call_args[1].get("json")
    assert call_json.get("tool") == "query_meeting_rooms"


def test_meeting_skill_cancel_uses_last_booking_id_from_session():
    """取消会议未填 booking_id 时，context 带 last_booking_id 供后端槽位联想。"""
    from datetime import datetime
    doc = _meeting_skill_doc()
    skill = GenericSkill(doc)
    ctx = {"get_session_value": lambda k: "id123", "current_time": datetime.now()}

    with patch("requests.post") as m:
        m.return_value.status_code = 200
        m.return_value.content = b'{"reply":"cancelled:id123","booking":null,"error":null}'
        m.return_value.json.return_value = {"reply": "cancelled:id123", "booking": None, "error": None}
        m.return_value.raise_for_status = lambda: None

        result = skill.execute("cancel_meeting", {}, ctx)
    assert result.get("error") is None
    assert "cancelled:id123" in (result.get("reply") or "")
    call_json = m.call_args.kwargs.get("json") or m.call_args[1].get("json")
    assert call_json.get("context", {}).get("last_booking_id") == "id123"


def test_meeting_skill_book_exceed_max_days_ahead_returns_rule_error():
    """后端返回 EXCEED_MAX_DAYS_AHEAD 时原样返回。"""
    from datetime import datetime, timedelta
    doc = _meeting_skill_doc()
    skill = GenericSkill(doc)
    now = datetime.now()
    ctx = {"current_time": now}
    args = {"title": "测试", "start_time": (now + timedelta(days=8)).strftime("%Y-%m-%dT14:00:00"), "duration_minutes": 60}

    with patch("requests.post") as m:
        m.return_value.status_code = 200
        m.return_value.json.return_value = {
            "reply": "最多提前 7 天预约。",
            "booking": None,
            "error": "EXCEED_MAX_DAYS_AHEAD",
        }
        m.return_value.raise_for_status = lambda: None

        result = skill.execute("book_meeting", args, ctx)
    assert result.get("error") == "EXCEED_MAX_DAYS_AHEAD"
    assert result.get("booking") is None
    assert "7" in (result.get("reply") or "")


def test_meeting_skill_book_exceed_max_duration_returns_rule_error():
    """后端返回 EXCEED_MAX_DURATION 时原样返回。"""
    from datetime import datetime, timedelta
    doc = _meeting_skill_doc()
    skill = GenericSkill(doc)
    now = datetime.now()
    ctx = {"current_time": now}
    args = {"title": "测试", "start_time": (now + timedelta(days=1)).strftime("%Y-%m-%dT14:00:00"), "duration_minutes": 300}

    with patch("requests.post") as m:
        m.return_value.status_code = 200
        m.return_value.json.return_value = {
            "reply": "单次会议时长不超过 240 分钟。",
            "booking": None,
            "error": "EXCEED_MAX_DURATION",
        }
        m.return_value.raise_for_status = lambda: None

        result = skill.execute("book_meeting", args, ctx)
    assert result.get("error") == "EXCEED_MAX_DURATION"
    assert result.get("booking") is None
