"""API 依赖：settings、Agent。"""
from functools import lru_cache
from typing import Any

from fastapi import Request

from ai_assistant.config import settings
from ai_assistant.config.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return settings


def get_agent(request: Request) -> Any:
    """从 app.state 取 Agent，未设置时懒创建占位。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is not None:
        return agent
    from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
    request.app.state.agent = create_agent_or_placeholder()
    return request.app.state.agent
