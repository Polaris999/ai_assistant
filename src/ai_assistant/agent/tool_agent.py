"""
Tool 型 Agent：LLM 选择 tool 并填参，由多能力（会议、后续运维工单等）分发执行。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from ai_assistant.agent.capabilities import get_default_capabilities
from ai_assistant.agent.capabilities.meeting import TOOL_QUERY_ROOMS, TOOL_REPLY_ONLY
from ai_assistant.agent.tools import (
    execute_tool,
    get_all_tool_names,
    get_tools_schema_for_prompt,
    parse_llm_tool_output,
)
from ai_assistant.agent.protocol import AgentRunner as AgentRunnerProtocol
from ai_assistant.config import settings
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.core.exceptions import ConfigError
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.factory import get_llm

logger = logging.getLogger(__name__)


def _build_system_prompt(capabilities: list[Any]) -> str:
    intro = """你是助手。根据用户输入（及最近对话上下文），选择 exactly 一个操作并用 JSON 输出。
- 若用户问「查询会议室」「有哪些会议室」「会议室有哪些」「查会议室」等，必须用 query_meeting_rooms，arguments 可为 {} 或 {"query": "用户原话"}，不要用 reply_only。
- 若用户要「订会」但信息不足（如只说「订个会」未说时间），用 reply_only 追问（例如「请说明会议主题、开始时间和时长」）。
- 若用户要「取消」会议（如：取消刚定的、取消刚才的、不订了、取消预约），必须用 cancel_meeting，arguments 可为 {}，系统会按本会话上一笔预定取消；不要用 reply_only 让用户再提供会议主题或时间。
"""
    return intro + get_tools_schema_for_prompt(capabilities)


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    lines = []
    for m in history:
        role = (m.get("role") or "").strip() or "user"
        content = (m.get("content") or "").strip()
        if role == "user":
            lines.append(f"用户：{content}")
        else:
            lines.append(f"助手：{content}")
    return "最近对话：\n" + "\n".join(lines) + "\n\n"


def _build_user_prompt(
    user_input: str,
    current_time: datetime,
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    prefix = _format_history(history) if history else ""
    return f"""{prefix}当前时间：{current_time.isoformat()}
当前用户输入：{user_input}

请输出一个 JSON 对象，包含 "tool" 和 "arguments"。"""


def _looks_like_query_rooms(user_input: str) -> bool:
    """用户输入是否明显在问「查会议室」类意图，用于解析失败时的关键词回退。"""
    if not (user_input or "").strip():
        return False
    s = (user_input or "").strip()
    if "会议室" not in s:
        return False
    # 含「会议室」且带查询意图关键词
    keywords = ("查", "有哪些", "多少", "介绍", "看", "列表", "预约规则", "怎么约")
    return any(k in s for k in keywords) or len(s) <= 12  # 短句如「查询会议室」也视为查会议室


class ToolAgentRunner:
    """基于多能力的 Agent：LLM 选 tool + 参数，按能力分发执行，返回 reply/booking/error。"""

    def __init__(self, llm: BaseLLM, capabilities: list[Any]):
        self._llm = llm
        self._capabilities = capabilities
        self._valid_tools = get_all_tool_names(capabilities)
        self._system_prompt = _build_system_prompt(capabilities)
        self._scheduler = None
        for cap in capabilities:
            if getattr(cap, "get_scheduler", None):
                s = cap.get_scheduler()
                if s is not None:
                    self._scheduler = s
                    break

    def warmup(self) -> None:
        for cap in self._capabilities:
            if getattr(cap, "warmup", None):
                cap.warmup()

    def invoke(
        self,
        user_input: str,
        user_id: str = "default",
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        user_input = (user_input or "").strip()
        if not user_input:
            return {"reply": "请说出或输入您要预定的会议信息。", "booking": None, "error": None}
        now = datetime.now()
        prompt = _build_user_prompt(user_input, now, history=history)
        t0 = time.perf_counter()
        try:
            text = self._llm.invoke(prompt, system=self._system_prompt, temperature=0)
        except Exception as e:
            logger.warning("Tool Agent LLM 调用失败: %s", e)
            return {"reply": "服务暂时不可用，请稍后重试。", "booking": None, "error": "LLM_ERROR"}
        logger.debug("tool_agent llm %.0fms", (time.perf_counter() - t0) * 1000)

        tool_name, arguments = parse_llm_tool_output(text, self._valid_tools)
        if tool_name is None:
            # 解析失败时按关键词回退：明显是「查会议室」则走 query_meeting_rooms，避免模型输出不规范时仍能响应
            if _looks_like_query_rooms(user_input):
                tool_name = TOOL_QUERY_ROOMS
                arguments = {"query": user_input}
                logger.info("Tool Agent 解析失败，按关键词回退为 query_meeting_rooms")
            else:
                logger.warning("Tool Agent 解析 LLM 输出失败，回退为 reply_only")
                tool_name = TOOL_REPLY_ONLY
                arguments = {"reply": "抱歉，我没理解您的意思。需要预定会议请说明主题、开始时间和时长；想查会议室可直接问「有哪些会议室」。"}

        store = get_conversation_store()
        get_session_value = None
        if conversation_id:
            get_session_value = lambda k, cid=conversation_id: store.get_session_value(cid, k)
        context = {"current_time": now, "get_session_value": get_session_value}

        result = execute_tool(tool_name, arguments, self._capabilities, context)
        logger.info("tool_agent invoke %.0fms tool=%s", (time.perf_counter() - t0) * 1000, tool_name)
        return result


def create_tool_agent(
    llm: Optional[BaseLLM] = None,
    capabilities: Optional[list[Any]] = None,
) -> AgentRunnerProtocol:
    """
    创建基于多能力的 Tool Agent。默认能力为会议预定；可注入 capabilities 扩展（如运维工单）。
    """
    caps = capabilities if capabilities is not None else get_default_capabilities()
    if llm is None:
        try:
            llm = get_llm()
        except ConfigError as e:
            logger.warning("LLM 未配置，Tool Agent 不可用: %s", e)
            from ai_assistant.agent.meeting_agent import _UnreadyAgentRunner
            return _UnreadyAgentRunner(str(e))
    return ToolAgentRunner(llm, caps)
