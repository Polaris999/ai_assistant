"""Agent 图与节点测试（Mock LLM/Store/Scheduler，不依赖真实 API）。"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# 保证 src 在 path 中（conftest 已加，此处防御性导入）
import sys
from pathlib import Path
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from meeting_agent.agent.meeting_agent import create_meeting_agent_graph
from meeting_agent.services.meeting_store import MeetingStore
from meeting_agent.services.reminder_scheduler import ReminderScheduler


class MockLLM:
    """返回固定 JSON 的 LLM，用于解析意图节点单测。"""
    name = "mock"

    def invoke(self, prompt: str, *, system: str = None, temperature: float = 0, **kwargs) -> str:
        start = datetime.now() + timedelta(days=1)
        # 单行 JSON，避免拼接产生多余字符导致 json.loads "Extra data"
        return (
            '{"title": "项目会", "start_time": "' + start.isoformat() + '", '
            '"duration_minutes": 60, "room": null, "participants": [], "remind_minutes_before": 15}'
        )


class MockRAG:
    """不依赖 Chroma/Embeddings 的 RAG，仅返回固定上下文供测试。"""
    def init_default_knowledge(self) -> None:
        pass

    def retrieve_context(self, query: str, k: int = 4) -> str:
        return "（无额外知识）"


@pytest.fixture
def store():
    return MeetingStore()


@pytest.fixture
def scheduler():
    return ReminderScheduler()


@pytest.fixture
def agent(store, scheduler):
    return create_meeting_agent_graph(
        llm=MockLLM(),
        reply_llm=None,
        meeting_store=store,
        reminder_scheduler=scheduler,
        meeting_rag=MockRAG(),
    )


def test_agent_invoke_returns_reply_and_booking(agent, store):
    """图执行后应返回 reply，且当解析成功时产生 booking。"""
    result = agent.invoke("明天下午3点开项目会，1小时")
    assert "reply" in result
    assert isinstance(result["reply"], str)
    assert len(result["reply"]) > 0
    # 使用 MockLLM 会解析出 intent 并走 create_booking
    assert result.get("booking") is not None
    assert result.get("error") is None
    booking = result["booking"]
    assert booking.title == "项目会"
    assert booking.duration_minutes == 60


def test_agent_empty_input_returns_friendly_reply(agent):
    """空输入应得到友好提示而非异常。"""
    result = agent.invoke("")
    assert "reply" in result
    assert result.get("booking") is None
    assert "请" in result["reply"] or "输入" in result["reply"].lower()
