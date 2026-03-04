"""Agent 创建：支持注入 factory，成功返回 Runner，失败返回占位（符合 AgentRunner 协议）。"""
import logging
from typing import Any, Callable, Optional

from ai_assistant.agent.protocol import AgentRunner
from ai_assistant.core.exceptions import ConfigError
from ai_assistant.core.helper import mask_secret

logger = logging.getLogger(__name__)

_LOG_EXC_MAX_LEN = 500


def _placeholder(reason: str) -> AgentRunner:
    """占位 Agent，_scheduler=None 供 shutdown 判断。"""

    class _Placeholder:
        _scheduler = None

        def invoke(
            self, user_input: str, user_id: str = "default", request_id: Optional[str] = None, **kwargs: Any
        ) -> dict[str, Any]:
            return {"reply": reason, "booking": None, "error": "RUNTIME_ERROR"}

    return _Placeholder()  # type: ignore[return-value]


def create_agent_or_placeholder(
    agent_factory: Optional[Callable[[], AgentRunner]] = None,
) -> AgentRunner:
    """
    创建 Agent；失败时返回占位 Runner。
    未传 agent_factory 时：USE_TOOL_AGENT=true 使用 Tool Agent（查/订走 IMeetingService），否则使用原 LangGraph 图。
    """
    from ai_assistant.config import settings
    factory = agent_factory
    if factory is None:
        if getattr(settings, "use_tool_agent", True):
            from ai_assistant.agent.tool_agent import create_tool_agent
            def _factory() -> AgentRunner:
                return create_tool_agent()
            factory = _factory
        else:
            from ai_assistant.agent.meeting_agent import create_meeting_agent_graph
            factory = create_meeting_agent_graph
    try:
        return factory()
    except (OSError, ValueError, ImportError, ConfigError) as e:
        msg = str(e)
        log_msg = msg if len(msg) <= _LOG_EXC_MAX_LEN else mask_secret(msg, visible=80)
        logger.warning("Agent 创建失败: %s", log_msg)
        return _placeholder(msg)
