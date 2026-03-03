"""Agent 创建：成功返回图，OSError/ValueError 时返回占位。"""
import logging

from meeting_agent.core.helper import mask_secret

logger = logging.getLogger(__name__)

_LOG_EXC_MAX_LEN = 500


def _placeholder(reason: str):
    """占位 Agent，_scheduler=None 供 shutdown 判断。"""
    class _Placeholder:
        _scheduler = None

        def invoke(self, user_input: str, user_id: str = "default", request_id: str | None = None):
            return {"reply": reason, "booking": None, "error": "RUNTIME_ERROR"}

    return _Placeholder()


def create_agent_or_placeholder():
    """创建 Agent，OSError/ValueError 时返回占位。"""
    try:
        from meeting_agent.agent.meeting_agent import create_meeting_agent_graph
        return create_meeting_agent_graph()
    except (OSError, ValueError) as e:
        msg = str(e)
        log_msg = msg if len(msg) <= _LOG_EXC_MAX_LEN else mask_secret(msg, visible=80)
        logger.warning("Agent 创建失败: %s", log_msg)
        return _placeholder(msg)
