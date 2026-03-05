"""LangGraph 会议预定 Agent：RAG → 解析意图 → 创建预定 → 回复润色，状态与节点显式定义。"""
import json
import logging
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from langgraph.graph import END, START, StateGraph

from ai_assistant.agent.protocol import AgentRunner as AgentRunnerProtocol
from ai_assistant.agent.intent import (
    UserIntent,
    detect_intent,
    reply_for_chitchat,
    reply_for_query_rooms,
)
from ai_assistant.agent.state import MeetingAgentState
from ai_assistant.config import settings
from ai_assistant.config.prompt_loader import get_parse_intent_template, get_reply_polish_template
from ai_assistant.core.exceptions import AppException, ConfigError
from ai_assistant.core.serialization import to_json_serializable
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.factory import get_llm
from ai_assistant.core.llm.retry import invoke_with_retry
from ai_assistant.models.meeting import MeetingIntent
from ai_assistant.rag.meeting_rag import MeetingRAG
from ai_assistant.services.meeting_store import MeetingStore
from ai_assistant.services.reminder_scheduler import ReminderScheduler

logger = logging.getLogger(__name__)


def _parse_intent_node(state: MeetingAgentState) -> dict[str, Any]:
    """RAG 后解析用户输入为会议意图（JSON），写入 state.intent 或 state.error/reply。先按意图路由：闲聊/查会议室直接回复，其余走 LLM 解析会议。"""
    user_input = (state.get("user_input") or "").strip()
    if not user_input:
        return {"intent": None, "error": "用户输入为空", "reply": "请说出或输入您要预定的会议信息。"}

    intent = detect_intent(user_input)
    rag_context = state.get("rag_context") or ""

    if intent == UserIntent.CHITCHAT:
        return {"intent": None, "error": None, "reply": reply_for_chitchat(user_input)}
    if intent == UserIntent.QUERY_ROOMS:
        return {"intent": None, "error": None, "reply": reply_for_query_rooms(rag_context)}

    now = datetime.now()
    default_minutes = getattr(settings, "default_remind_minutes", 15)
    llm: Optional[BaseLLM] = state.get("_llm")
    if not llm:
        return {"intent": None, "error": "未注入 LLM", "reply": "服务暂不可用。"}

    prompt = get_parse_intent_template().format(
        current_time=now.isoformat(),
        default_remind_minutes=default_minutes,
        rag_context=rag_context or "（无额外知识）",
        user_input=user_input,
    )
    system = "你只输出一个合法的 JSON 对象，不要 markdown 或多余解释。"

    text = ""
    try:
        t0 = time.perf_counter()
        timeout_sec = getattr(settings, "llm_request_timeout_seconds", 120) or 120
        retry_count = getattr(settings, "llm_retry_count", 0) or 0
        text = invoke_with_retry(
            llm,
            prompt,
            system=system,
            temperature=0,
            timeout_sec=timeout_sec,
            retry_count=retry_count,
        )
        logger.debug("parse_intent llm %.0fms", (time.perf_counter() - t0) * 1000)
        text = (text or "").strip()
        if not text:
            raise ValueError("LLM 返回为空，无法解析会议意图")
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(line for line in lines if line.strip() and not line.strip().startswith("```"))
            text = text.strip()
        # 若仍非合法 JSON，尝试从文本中抽取首段 {...}
        data = None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(text[start : end + 1])
        if data is None:
            logger.warning("parse_intent 非 JSON，原始: %.200s", (text or "")[:200])
            raise ValueError("LLM 返回内容不是合法 JSON，无法解析会议意图")
        start_time_str = data.get("start_time")
        if isinstance(start_time_str, str):
            s = start_time_str.replace("Z", "+00:00").strip()
            try:
                data["start_time"] = datetime.fromisoformat(s)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        data["start_time"] = datetime.strptime(s[:19], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"无法解析时间: {start_time_str}")
        intent = MeetingIntent(
            title=data.get("title", "未命名会议"),
            start_time=data["start_time"],
            duration_minutes=int(data.get("duration_minutes", 60)),
            room=data.get("room"),
            participants=data.get("participants") or [],
            remind_minutes_before=int(data.get("remind_minutes_before", default_minutes)),
        )
        return {"intent": intent, "error": None}
    except FuturesTimeoutError:
        logger.warning("parse_intent LLM 调用超时")
        return {
            "intent": None,
            "error": "LLM_ERROR",
            "reply": "服务响应超时，请稍后重试。",
        }
    except Exception as e:
        logger.warning("解析意图失败: %s", e)
        logger.debug("parse_intent 原始返回: %.300s", (text or "")[:300], exc_info=True)
        return {
            "intent": None,
            "error": "PARSE_ERROR",
            "reply": "抱歉，我没理解您的会议安排，请说明会议主题、开始时间和时长。",
        }


def _create_booking_node(state: MeetingAgentState) -> dict[str, Any]:
    """根据 intent 创建预定（MeetingStore）并调度提醒（ReminderScheduler），写入 state.booking/reply。"""
    intent = state.get("intent")
    if intent is None:
        return {"booking": None, "reply": state.get("reply", "无法创建会议。")}

    store: MeetingStore = state.get("_store")  # type: ignore
    scheduler: ReminderScheduler = state.get("_scheduler")  # type: ignore
    if not store or not scheduler:
        return {"booking": None, "error": "未注入 MeetingStore 或 ReminderScheduler", "reply": "服务暂不可用。"}

    try:
        reminder_at = intent.start_time - timedelta(minutes=intent.remind_minutes_before)
        if reminder_at <= datetime.now():
            reminder_at = datetime.now()
        booking = store.create_booking(
            title=intent.title,
            start_time=intent.start_time,
            duration_minutes=intent.duration_minutes,
            room=intent.room,
            participants=intent.participants,
            remind_minutes_before=intent.remind_minutes_before,
        )
        job_id = scheduler.schedule_reminder(
            run_at=reminder_at,
            booking_id=booking.id,
            title=booking.title,
            start_time=booking.start_time,
        )
        booking.reminder_job_id = job_id
        store.add(booking)
        reply = (
            f"已为您预定会议：{booking.title}，"
            f"开始时间 {booking.start_time.strftime('%Y-%m-%d %H:%M')}，"
            f"时长 {booking.duration_minutes} 分钟。"
            f"将在开始前 {booking.remind_minutes_before} 分钟提醒您。"
        )
        return {"booking": booking, "reply": reply, "error": None}
    except Exception as e:
        logger.exception("创建会议失败: %s", e)
        return {"booking": None, "error": "BOOK_ERROR", "reply": "创建会议失败，请稍后重试。"}


def _reply_node(state: MeetingAgentState) -> dict[str, Any]:
    """可选：用 reply_llm 对 state.reply 做简短润色后写回 state.reply。"""
    reply = state.get("reply") or ""
    if not reply:
        return {}
    reply_llm: Optional[BaseLLM] = state.get("_reply_llm")
    if not reply_llm:
        return {}
    try:
        prompt = get_reply_polish_template().format(reply=reply)
        t0 = time.perf_counter()
        out = reply_llm.invoke(prompt, temperature=0.3)
        logger.debug("reply_polish %.0fms", (time.perf_counter() - t0) * 1000)
        if out and out.strip():
            return {"reply": out.strip()}
    except Exception as e:
        logger.warning("回复润色失败: %s", e)
    return {}


def _route_after_parse(state: MeetingAgentState) -> Literal["create_booking", "end"]:
    """解析成功且有 intent 则走 create_booking，否则结束。"""
    if state.get("intent") is not None and state.get("error") is None:
        return "create_booking"
    return "end"


class _UnreadyAgentRunner:
    """LLM 未配置时返回的占位 Runner：invoke 直接返回友好提示，不跑图；_scheduler 为 None 供 lifespan 安全判断。"""

    _scheduler = None

    def __init__(self, config_message: str = ""):
        self._config_message = config_message or "LLM 未配置"

    def invoke(
        self, user_input: str, user_id: str = "default", request_id: Optional[str] = None, **kwargs: Any
    ) -> dict[str, Any]:
        reply = (
            "服务未就绪：请配置 LLM（如 OPENAI_API_KEY 或 VLLM_BASE_URL 或 DIFY_API_KEY）。"
            if not self._config_message.strip()
            else f"服务未就绪：{self._config_message}"
        )
        raise AppException(
            "success",
            code="CONFIG_ERROR",
            details={
                "reply": reply,
                "booking": None,
                "error": "CONFIG_ERROR",
                "conversation_id": kwargs.get("conversation_id") or "",
            },
        )


def create_meeting_agent_graph(
    llm: Optional[BaseLLM] = None,
    reply_llm: Optional[BaseLLM] = None,
    meeting_store: Optional[MeetingStore] = None,
    reminder_scheduler: Optional[ReminderScheduler] = None,
    meeting_rag: Optional[MeetingRAG] = None,
) -> AgentRunnerProtocol:
    """构建 LangGraph 会议预定 Agent：rag → parse_intent → [create_booking → reply_polish] | end。"""
    store = meeting_store or MeetingStore()
    scheduler = reminder_scheduler or ReminderScheduler()
    rag = meeting_rag or MeetingRAG()
    if llm is None:
        try:
            llm = get_llm()
        except ConfigError as e:
            logger.warning("LLM 未配置，Agent 将返回就绪提示（不崩溃）: %s", e)
            return _UnreadyAgentRunner(str(e))
    if reply_llm is None:
        rt = getattr(settings, "reply_llm_type", "").strip()
        if rt:
            try:
                reply_llm = get_llm(rt)
            except Exception as e:
                logger.warning("回复润色 LLM 创建失败，将不润色: %s", e)
                reply_llm = None
        else:
            reply_llm = None

    def rag_node(state: MeetingAgentState) -> dict[str, Any]:
        user_input = state.get("user_input") or ""
        r = state.get("_rag") or rag
        t0 = time.perf_counter()
        context = r.retrieve_context(user_input, k=4)
        logger.debug("rag retrieve %.0fms", (time.perf_counter() - t0) * 1000)
        return {"rag_context": context}

    graph = StateGraph(MeetingAgentState)
    graph.add_node("rag", rag_node)
    graph.add_node("parse_intent", _parse_intent_node)
    graph.add_node("create_booking", _create_booking_node)
    graph.add_node("reply_polish", _reply_node)
    graph.add_edge(START, "rag")
    graph.add_edge("rag", "parse_intent")
    graph.add_conditional_edges("parse_intent", _route_after_parse, {"create_booking": "create_booking", "end": END})
    graph.add_edge("create_booking", "reply_polish")
    graph.add_edge("reply_polish", END)
    compiled = graph.compile()

    class AgentRunner:
        """封装编译后的图与依赖，对外仅暴露 invoke(user_input, request_id=...)。"""

        def __init__(self, g, st, sc, r, llm_instance, reply_llm_instance):
            self._graph = g
            self._store = st
            self._scheduler = sc
            self._rag = r
            self._llm = llm_instance
            self._reply_llm = reply_llm_instance

        def invoke(
            self, user_input: str, user_id: str = "default", request_id: Optional[str] = None, **kwargs: Any
        ) -> dict[str, Any]:
            t0 = time.perf_counter()
            initial: MeetingAgentState = {
                "user_input": user_input,
                "rag_context": "",
                "intent": None,
                "booking": None,
                "reply": "",
                "error": None,
                "messages": [],
                "_llm": self._llm,
                "_reply_llm": self._reply_llm,
                "_store": self._store,
                "_scheduler": self._scheduler,
                "_rag": self._rag,
            }
            config: dict = {}
            if request_id is not None:
                from ai_assistant.core.callbacks import AgentLoggingCallbackHandler
                config["callbacks"] = [AgentLoggingCallbackHandler(request_id=request_id)]
                config["metadata"] = {"request_id": request_id}
            result = self._graph.invoke(initial, config=config)
            logger.info("agent invoke %.0fms", (time.perf_counter() - t0) * 1000)
            err = result.get("error")
            # 空输入等软错误直接返回友好回复，与 Tool Agent 行为一致
            if err == "用户输入为空" and result.get("reply"):
                return {"reply": result["reply"], "booking": None}
            if err is not None:
                code = err if err in ("RUNTIME_ERROR", "CONFIG_ERROR") else "BUSINESS_ERROR"
                raise AppException(
                    "success",
                    code=code,
                    details={
                        "reply": result.get("reply", "处理失败"),
                        "booking": to_json_serializable(result.get("booking")),
                        "error": err,
                        "conversation_id": kwargs.get("conversation_id") or "",
                    },
                )
            return {
                "reply": result.get("reply", ""),
                "booking": result.get("booking"),
            }
    return AgentRunner(compiled, store, scheduler, rag, llm, reply_llm)
