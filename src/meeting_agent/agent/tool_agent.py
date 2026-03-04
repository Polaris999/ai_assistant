"""
Tool 型 Agent：LLM 选择 tool（query_meeting_rooms / book_meeting / reply_only）并填参，执行后返回。
查询会议室、预定会议由 IMeetingService 实现，可对接业务服务接口。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from meeting_agent.agent.tools import (
    execute_tool,
    get_tools_schema_for_prompt,
    parse_llm_tool_output,
    TOOL_REPLY_ONLY,
)
from meeting_agent.agent_base import AgentRunner as AgentRunnerProtocol
from meeting_agent.config import settings
from meeting_agent.core.exceptions import ConfigError
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.factory import get_llm
from meeting_agent.services.meeting_service import DefaultMeetingService, IMeetingService

logger = logging.getLogger(__name__)

TOOL_AGENT_SYSTEM = """你是会议预定助手。根据用户输入，选择 exactly 一个操作并用 JSON 输出。
""" + get_tools_schema_for_prompt()


def _build_user_prompt(user_input: str, current_time: datetime) -> str:
    return f"""当前时间：{current_time.isoformat()}
用户输入：{user_input}

请输出一个 JSON 对象，包含 "tool" 和 "arguments"。"""


class ToolAgentRunner:
    """基于 Tools 的 Agent：LLM 选 tool + 参数，执行 IMeetingService，返回 reply/booking/error。"""

    def __init__(
        self,
        llm: BaseLLM,
        service: IMeetingService,
        *,
        scheduler_for_shutdown: Any = None,
    ):
        self._llm = llm
        self._service = service
        self._scheduler = scheduler_for_shutdown

    def warmup(self) -> None:
        """预热：初始化 RAG 默认知识（当 service 为 DefaultMeetingService 时）。"""
        rag = getattr(self._service, "_rag", None)
        if rag is not None and hasattr(rag, "init_default_knowledge"):
            rag.init_default_knowledge()

    def invoke(
        self,
        user_input: str,
        user_id: str = "default",
        request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        user_input = (user_input or "").strip()
        if not user_input:
            return {
                "reply": "请说出或输入您要预定的会议信息。",
                "booking": None,
                "error": None,
            }
        now = datetime.now()
        prompt = _build_user_prompt(user_input, now)
        t0 = time.perf_counter()
        try:
            text = self._llm.invoke(prompt, system=TOOL_AGENT_SYSTEM, temperature=0)
        except Exception as e:
            logger.warning("Tool Agent LLM 调用失败: %s", e)
            return {
                "reply": "服务暂时不可用，请稍后重试。",
                "booking": None,
                "error": "LLM_ERROR",
            }
        logger.debug("tool_agent llm %.0fms", (time.perf_counter() - t0) * 1000)

        tool_name, arguments = parse_llm_tool_output(text)
        if tool_name is None:
            logger.warning("Tool Agent 解析 LLM 输出失败，回退为 reply_only")
            tool_name = TOOL_REPLY_ONLY
            arguments = {"reply": "抱歉，我没理解您的意思。需要预定会议请说明主题、开始时间和时长；想查会议室可直接问「有哪些会议室」。"}

        result = execute_tool(tool_name, arguments, self._service, now)
        logger.info("tool_agent invoke %.0fms tool=%s", (time.perf_counter() - t0) * 1000, tool_name)
        return result


def create_tool_agent(
    llm: Optional[BaseLLM] = None,
    service: Optional[IMeetingService] = None,
) -> AgentRunnerProtocol:
    """
    创建基于 Tools 的 Agent；查询/预定由 IMeetingService 实现，默认使用 DefaultMeetingService。
    生产可注入对接业务 HTTP 的 service 实现。
    """
    if service is None:
        service = DefaultMeetingService()
    if llm is None:
        try:
            llm = get_llm()
        except ConfigError as e:
            logger.warning("LLM 未配置，Tool Agent 不可用: %s", e)
            from meeting_agent.agent.meeting_agent import _UnreadyAgentRunner
            return _UnreadyAgentRunner(str(e))

    scheduler_for_shutdown = getattr(service, "scheduler", None) if isinstance(service, DefaultMeetingService) else None
    return ToolAgentRunner(llm, service, scheduler_for_shutdown=scheduler_for_shutdown)
