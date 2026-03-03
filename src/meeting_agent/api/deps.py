"""API 依赖注入：settings 单例、从 app.state 取 Agent。"""
from functools import lru_cache
from typing import Any

from fastapi import Request

from meeting_agent.config import settings
from meeting_agent.config.settings import Settings


@lru_cache
def get_settings() -> Settings:
    """返回全局配置单例（lru_cache 保证只读一份）。"""
    return settings


def get_agent(request: Request) -> Any:
    """从 app.state 获取 Agent（lifespan 中已设置）；测试环境下未触发 lifespan 时懒创建并写入 state。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        from meeting_agent.agent.meeting_agent import create_meeting_agent_graph
        request.app.state.agent = create_meeting_agent_graph()
        agent = request.app.state.agent
    return agent
