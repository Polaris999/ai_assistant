from functools import lru_cache
from typing import Any, Optional

from meeting_agent.config import settings
from meeting_agent.config.settings import Settings
from meeting_agent.agent.meeting_agent import create_meeting_agent_graph

_agent_singleton: Any = None


@lru_cache
def get_settings() -> Settings:
    return settings


def get_agent():
    global _agent_singleton
    if _agent_singleton is None:
        _agent_singleton = create_meeting_agent_graph()
    return _agent_singleton


def get_scheduler() -> Optional[Any]:
    """返回当前 Agent 使用的 ReminderScheduler，用于 lifespan 优雅关闭。"""
    if _agent_singleton is None:
        return None
    return getattr(_agent_singleton, "_scheduler", None)
