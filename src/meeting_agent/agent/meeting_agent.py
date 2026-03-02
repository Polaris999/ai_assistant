# agent/meeting_agent.py
import json
import logging
from datetime import datetime
from typing import Literal, Optional

from langgraph.graph import END, START, StateGraph
from langchain_core.prompts import PromptTemplate

from meeting_agent.config import settings
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.factory import get_llm
from meeting_agent.models.meeting import MeetingIntent
from meeting_agent.rag.meeting_rag import MeetingRAG
from meeting_agent.services.meeting_store import MeetingStore
from meeting_agent.services.reminder_scheduler import ReminderScheduler

from meeting_agent.agent.state import MeetingAgentState

logger = logging.getLogger(__name__)

PARSE_INTENT_PROMPT_TEMPLATE = PromptTemplate.from_template("""你是一个会议预定助手。根据用户输入和下面的会议知识，解析出会议预定信息。
若用户未明确说明日期/时间，使用“当前时间”作为参考（当前时间：{current_time}）。
若未说明提醒时间，使用默认提前 {default_remind_minutes} 分钟。

会议知识（仅供参考）：
{rag_context}

用户输入：{user_input}

请严格输出一个 JSON，且仅此 JSON，不要其他文字。字段说明：
- title: 会议主题（字符串）
- start_time: 会议开始时间，ISO 格式，如 2025-03-03T14:00:00
- duration_minutes: 时长（分钟），整数，默认 60
- room: 会议室名称，没有则 null
- participants: 参与者列表，没有则 []
- remind_minutes_before: 提前多少分钟提醒，整数，默认 {default_remind_minutes}
""")

REPLY_POLISH_PROMPT_TEMPLATE = PromptTemplate.from_template(
    "请用一句简短友好的中文确认以下会议预定结果，不要改变事实：{reply}"
)


def _parse_intent_node(state: MeetingAgentState) -> dict:
    user_input = (state.get("user_input") or "").strip()
    if not user_input:
        return {"intent": None, "error": "用户输入为空", "reply": "请说出或输入您要预定的会议信息。"}

    rag_context = state.get("rag_context") or ""
    now = datetime.now()
    default_minutes = getattr(settings, "default_remind_minutes", 15)
    llm: Optional[BaseLLM] = state.get("_llm")
    if not llm:
        return {"intent": None, "error": "未注入 LLM", "reply": "服务暂不可用。"}

    prompt = PARSE_INTENT_PROMPT_TEMPLATE.format(
        current_time=now.isoformat(),
        default_remind_minutes=default_minutes,
        rag_context=rag_context or "（无额外知识）",
        user_input=user_input,
    )
    system = "你只输出一个合法的 JSON 对象，不要 markdown 或多余解释。"

    try:
        text = llm.invoke(prompt, system=system, temperature=0)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if l.strip() and not l.strip().startswith("```"))
        data = json.loads(text)
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
    except Exception as e:
        logger.exception("解析会议意图失败: %s", e)
        return {
            "intent": None,
            "error": str(e),
            "reply": "抱歉，我没理解您的会议安排，请说明会议主题、开始时间和时长。",
        }


def _create_booking_node(state: MeetingAgentState) -> dict:
    intent = state.get("intent")
    if intent is None:
        return {"booking": None, "reply": state.get("reply", "无法创建会议。")}

    store: MeetingStore = state.get("_store")  # type: ignore
    scheduler: ReminderScheduler = state.get("_scheduler")  # type: ignore
    if not store or not scheduler:
        return {"booking": None, "error": "未注入 MeetingStore 或 ReminderScheduler", "reply": "服务暂不可用。"}

    try:
        from datetime import timedelta
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
        return {"booking": None, "error": str(e), "reply": "创建会议失败，请稍后重试。"}


def _reply_node(state: MeetingAgentState) -> dict:
    reply = state.get("reply") or ""
    if not reply:
        return {}
    reply_llm: Optional[BaseLLM] = state.get("_reply_llm")
    if not reply_llm:
        return {}
    try:
        prompt = REPLY_POLISH_PROMPT_TEMPLATE.format(reply=reply)
        out = reply_llm.invoke(prompt, temperature=0.3)
        if out and out.strip():
            return {"reply": out.strip()}
    except Exception as e:
        logger.warning("回复润色失败 (%s)，使用原回复: %s", reply_llm.name, e)
    return {}


def _route_after_parse(state: MeetingAgentState) -> Literal["create_booking", "end"]:
    if state.get("intent") is not None and state.get("error") is None:
        return "create_booking"
    return "end"


def create_meeting_agent_graph(
    llm: Optional[BaseLLM] = None,
    reply_llm: Optional[BaseLLM] = None,
    meeting_store: Optional[MeetingStore] = None,
    reminder_scheduler: Optional[ReminderScheduler] = None,
    meeting_rag: Optional[MeetingRAG] = None,
):
    store = meeting_store or MeetingStore()
    scheduler = reminder_scheduler or ReminderScheduler()
    rag = meeting_rag or MeetingRAG()
    if llm is None:
        llm = get_llm()
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

    def rag_node(state: MeetingAgentState) -> dict:
        user_input = state.get("user_input") or ""
        r = state.get("_rag") or rag
        context = r.retrieve_context(user_input, k=4)
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
        def __init__(self, g, st, sc, r, llm_instance, reply_llm_instance):
            self._graph = g
            self._store = st
            self._scheduler = sc
            self._rag = r
            self._llm = llm_instance
            self._reply_llm = reply_llm_instance

        def invoke(self, user_input: str, user_id: str = "default") -> dict:
            rag.init_default_knowledge()
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
            result = self._graph.invoke(initial)
            return {
                "reply": result.get("reply", ""),
                "booking": result.get("booking"),
                "error": result.get("error"),
            }
    return AgentRunner(compiled, store, scheduler, rag, llm, reply_llm)
