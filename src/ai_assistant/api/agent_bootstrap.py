"""Agent 创建：支持注入 factory，成功返回 Runner，失败返回占位（符合 AgentRunner 协议）。"""
import logging
from typing import Any, Callable, Optional

from ai_assistant.agent.protocol import AgentRunner
from ai_assistant.core.exceptions import ConfigError
from ai_assistant.core.helper import mask_secret

logger = logging.getLogger(__name__)

_LOG_EXC_MAX_LEN = 500


def create_agent_or_placeholder(
    agent_factory: Optional[Callable[[], AgentRunner]] = None,
) -> AgentRunner:
    """
    创建 Agent；失败时返回占位 Runner。
    未传 agent_factory 时固定使用 LangGraph（create_react_agent + 技能转 Tool）。
    """
    factory = agent_factory
    if factory is None:
        from ai_assistant.agent.langgraph_runner import create_langgraph_agent
        def _factory() -> AgentRunner:
            return create_langgraph_agent()
        factory = _factory
    try:
        return factory()
    except (OSError, ValueError, ImportError, ConfigError) as e:
        msg = str(e)
        log_msg = msg if len(msg) <= _LOG_EXC_MAX_LEN else mask_secret(msg, visible=80)
        logger.warning("Agent 创建失败: %s", log_msg)
        from ai_assistant.agent.protocol import create_placeholder_runner
        return create_placeholder_runner(msg)  # type: ignore[return-value]
