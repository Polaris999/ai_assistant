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
    """从 app.state 获取 Agent（lifespan 中已创建，失败时为占位）。未设置时返回占位避免 500。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is not None:
        return agent
    # 未触发 lifespan 时（如部分测试）占位，避免 agent.invoke 报错
    from meeting_agent.api.agent_bootstrap import create_agent_or_placeholder
    request.app.state.agent = create_agent_or_placeholder()
    return request.app.state.agent
