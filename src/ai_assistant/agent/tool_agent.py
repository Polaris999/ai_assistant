"""
Tool 型 Agent：LLM 选择 tool 并填参，由多能力（会议、后续运维工单等）分发执行。
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

from ai_assistant.agent.capabilities import get_default_capabilities
from ai_assistant.agent.capabilities.meeting import TOOL_BOOK_MEETING, TOOL_QUERY_ROOMS, TOOL_REPLY_ONLY
from ai_assistant.agent.tools import (
    execute_tool,
    get_all_tool_names,
    get_tools_schema_for_prompt,
    parse_llm_tool_output,
)
from ai_assistant.agent.protocol import AgentRunner as AgentRunnerProtocol
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.core.exceptions import AppException, ConfigError
from ai_assistant.core.serialization import to_json_serializable
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.factory import get_llm

logger = logging.getLogger(__name__)


@contextmanager
def _noop_span():
    yield None


def _get_tracer():
    try:
        from ai_assistant.core.observability import get_tracer as _gt
        return _gt()
    except Exception:
        return None


def _span_ctx(tracer: Any, name: str):
    if tracer is None:
        return _noop_span()
    return tracer.start_as_current_span(name)


# 解析失败时 LLM 原始输出在日志中保留的最大长度（便于排查，避免过长）
_LLM_OUTPUT_LOG_MAX_LEN = 800


def _log_chat_request(
    request_id: Optional[str],
    tool: str,
    duration_ms: float,
    error: Optional[str],
    parse_fallback: bool,
    llm_output_snippet: Optional[str] = None,
) -> None:
    """单条结构化日志；parse_fallback 时可带 llm_output_snippet 便于排查。"""
    payload = {
        "event": "chat_request",
        "request_id": request_id or "",
        "tool": tool,
        "duration_ms": round(duration_ms, 2),
        "error": error,
        "parse_fallback": parse_fallback,
    }
    if llm_output_snippet is not None:
        payload["llm_output_snippet"] = llm_output_snippet
    logger.info("observability %s", json.dumps(payload, ensure_ascii=False))


def _get_max_days_ahead() -> int:
    """从会议规则配置读取「最多提前天数」，供 system 与回退文案使用；失败时默认 7。"""
    try:
        from ai_assistant.config.meeting_rules_config import meeting_rules_config
        return meeting_rules_config.meeting_max_days_ahead
    except Exception:
        return 7


def _build_system_prompt(capabilities: list[Any]) -> str:
    from ai_assistant.config.prompt_loader import get_tool_agent_system_intro
    max_days = _get_max_days_ahead()
    intro = get_tool_agent_system_intro(max_days=max_days)
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
    """解析失败时用于回退：若像「查会议室」则走 query_meeting_rooms。关键词覆盖「查/有哪些/列表」等常见说法，避免误走 reply_only。"""
    if not (user_input or "").strip():
        return False
    s = (user_input or "").strip()
    if "会议室" not in s:
        return False
    keywords = ("查", "有哪些", "多少", "介绍", "看", "列表", "预约规则", "怎么约")
    return any(k in s for k in keywords) or len(s) <= 12


def _looks_like_book_meeting_with_time(user_input: str) -> bool:
    """解析失败时用于回退：若同时包含「订/预约」与「时间」类词则走 book_meeting，由 _infer_start_time_from_relative 推断 start_time。"""
    if not (user_input or "").strip():
        return False
    s = (user_input or "").strip()
    book_keywords = ("定", "订", "预约", "预定", "订会", "定会", "订会议室", "定会议室")
    time_keywords = ("天后", "天之后", "明天", "后天", "下周", "号", "日", "点", "上午", "下午", "早上", "晚上")
    return any(b in s for b in book_keywords) and any(t in s for t in time_keywords)


def _infer_start_time_from_relative(user_input: str, now: datetime) -> Tuple[Optional[datetime], bool]:
    """从「N天后」「明天」「后天」等推断 start_time。默认 14:00 以便未说具体钟点时仍有合理时间。返回 (datetime, True) 或 (None, False)。"""
    s = (user_input or "").strip()
    m = re.search(r"(\d+)\s*天\s*后", s)
    if m:
        n = int(m.group(1))
        d = (now + timedelta(days=n)).replace(hour=14, minute=0, second=0, microsecond=0)
        return d, True
    if "明天" in s:
        d = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        return d, True
    if "后天" in s:
        d = (now + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
        return d, True
    return None, False


class ToolAgentRunner:
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
        **kwargs: Any,
    ) -> dict[str, Any]:
        user_input = (user_input or "").strip()
        if not user_input:
            _log_chat_request(request_id, "", 0, None, False)
            return {"reply": "请说出或输入您要预定的会议信息。", "booking": None, "error": None}
        now = datetime.now()
        prompt = _build_user_prompt(user_input, now, history=history)
        t0 = time.perf_counter()
        parse_fallback = False
        tracer = _get_tracer()
        with _span_ctx(tracer, "tool_agent.invoke") as agent_span:
            if agent_span and hasattr(agent_span, "set_attribute") and request_id:
                agent_span.set_attribute("request_id", request_id)
            timeout_sec = 120
            try:
                from ai_assistant.config import settings
                timeout_sec = getattr(settings, "llm_request_timeout_seconds", 120) or 120
                with _span_ctx(tracer, "llm.invoke"):
                    with ThreadPoolExecutor(max_workers=1) as ex:
                        text = ex.submit(
                            lambda: self._llm.invoke(prompt, system=self._system_prompt, temperature=0)
                        ).result(timeout=timeout_sec)
            except FuturesTimeoutError:
                logger.warning("Tool Agent LLM 调用超时: %ss", timeout_sec)
                _log_chat_request(request_id, "", (time.perf_counter() - t0) * 1000, "LLM_ERROR", False)
                raise AppException(
                    "success",
                    code="LLM_ERROR",
                    details={
                        "reply": "服务响应超时，请稍后重试。",
                        "booking": None,
                        "error": "LLM_ERROR",
                        "conversation_id": conversation_id or "",
                    },
                )
            except Exception as e:
                logger.warning("Tool Agent LLM 调用失败: %s", e)
                _log_chat_request(request_id, "", (time.perf_counter() - t0) * 1000, "LLM_ERROR", False)
                raise AppException(
                    "success",
                    code="LLM_ERROR",
                    details={
                        "reply": "服务暂时不可用，请稍后重试。",
                        "booking": None,
                        "error": "LLM_ERROR",
                        "conversation_id": conversation_id or "",
                    },
                )
            logger.debug("tool_agent llm %.0fms", (time.perf_counter() - t0) * 1000)

            llm_output_snippet = None
            tool_name, arguments = parse_llm_tool_output(text, self._valid_tools)
            if tool_name is None:
                parse_fallback = True
                raw_snippet = (text or "").strip()[: _LLM_OUTPUT_LOG_MAX_LEN]
                if len((text or "").strip()) > _LLM_OUTPUT_LOG_MAX_LEN:
                    raw_snippet += "..."
                llm_output_snippet = raw_snippet
                logger.warning(
                    "Tool Agent 解析失败，LLM 原始输出（供排查）: request_id=%s snippet=%s",
                    request_id or "-",
                    raw_snippet,
                )
                if _looks_like_query_rooms(user_input):
                    tool_name = TOOL_QUERY_ROOMS
                    arguments = {"query": user_input}
                    logger.info("Tool Agent 解析失败，按关键词回退为 query_meeting_rooms")
                elif _looks_like_book_meeting_with_time(user_input):
                    start_time, ok = _infer_start_time_from_relative(user_input, now)
                    if ok and start_time:
                        tool_name = TOOL_BOOK_MEETING
                        arguments = {
                            "title": "未命名会议",
                            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "duration_minutes": 60,
                        }
                        logger.info("Tool Agent 解析失败，按「订会+时间」回退为 book_meeting")
                    else:
                        tool_name = TOOL_REPLY_ONLY
                        max_days = _get_max_days_ahead()
                        arguments = {"reply": f"请说明具体日期和时间，例如「明天下午3点」或「8天后上午10点」；预约规则为最多提前 {max_days} 天。"}
                else:
                    logger.warning("Tool Agent 解析 LLM 输出失败，回退为 reply_only")
                    tool_name = TOOL_REPLY_ONLY
                    arguments = {"reply": "抱歉，我没理解您的意思。需要预定会议请说明主题、开始时间和时长；想查会议室可直接问「有哪些会议室」。"}

            store = get_conversation_store()
            get_session_value = None
            if conversation_id:
                get_session_value = lambda k, cid=conversation_id: store.get_session_value(cid, k)
            context = {"current_time": now, "get_session_value": get_session_value}

            with _span_ctx(tracer, "execute_tool") as tool_span:
                if tool_span and hasattr(tool_span, "set_attribute"):
                    tool_span.set_attribute("tool", tool_name)
                result = execute_tool(tool_name, arguments, self._capabilities, context)
        duration_ms = (time.perf_counter() - t0) * 1000
        _log_chat_request(
            request_id, tool_name, duration_ms, result.get("error"), parse_fallback, llm_output_snippet
        )
        err = result.get("error")
        if err is not None:
            code = err if err in ("RUNTIME_ERROR", "CONFIG_ERROR") else "BUSINESS_ERROR"
            raise AppException(
                "success",
                code=code,
                details={
                    "reply": result.get("reply", "处理失败"),
                    "booking": to_json_serializable(result.get("booking")),
                    "error": err,
                    "conversation_id": conversation_id or "",
                },
            )
        return result


def create_tool_agent(
    llm: Optional[BaseLLM] = None,
    capabilities: Optional[list[Any]] = None,
) -> AgentRunnerProtocol:
    caps = capabilities if capabilities is not None else get_default_capabilities()
    if llm is None:
        try:
            llm = get_llm()
        except ConfigError as e:
            logger.warning("LLM 未配置，Tool Agent 不可用: %s", e)
            from ai_assistant.agent.meeting_agent import _UnreadyAgentRunner
            return _UnreadyAgentRunner(str(e))
    return ToolAgentRunner(llm, caps)
