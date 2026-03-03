"""Agent 创建：成功返回图实例，OSError/ValueError 时返回占位（接口返回原始错误信息）。"""
import logging

logger = logging.getLogger(__name__)


def _placeholder(reason: str):
    """创建失败时占位；_scheduler=None 供 lifespan shutdown 判断。"""
    class _Placeholder:
        _scheduler = None

        def invoke(self, user_input: str, user_id: str = "default", request_id: str | None = None):
            return {"reply": reason, "booking": None, "error": "RUNTIME_ERROR"}

    return _Placeholder()


def create_agent_or_placeholder():
    """创建会议 Agent；OSError/ValueError 时返回占位，其它异常抛出。"""
    try:
        from meeting_agent.agent.meeting_agent import create_meeting_agent_graph
        return create_meeting_agent_graph()
    except (OSError, ValueError) as e:
        logger.warning("Agent 创建失败: %s", e)
        return _placeholder(str(e))
