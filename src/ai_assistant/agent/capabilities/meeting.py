"""会议能力：查会议室、订会、取消。依赖 IMeetingService；规则见 ARCHITECTURE §6.4。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Optional

DEFAULT_MAX_DAYS_AHEAD = 7
DEFAULT_MAX_DURATION_MINUTES = 240

from ai_assistant.agent.capabilities.base import BaseCapability
from ai_assistant.services.meeting_rules import IMeetingRulesProvider, MeetingBookingRules
from ai_assistant.services.meeting_service import IMeetingService

TOOL_REPLY_ONLY = "reply_only"
TOOL_QUERY_ROOMS = "query_meeting_rooms"
TOOL_BOOK_MEETING = "book_meeting"
TOOL_CANCEL_MEETING = "cancel_meeting"


def _schema_fragment() -> str:
    return '''
可选 tool：
1. reply_only - 用户只是打招呼、问你是谁、闲聊，或无法解析为预定/查会议室/取消时使用。
   arguments: { "reply": "给用户的回复文案" }

2. query_meeting_rooms - 用户想了解有哪些会议室、预约规则、可用会议室等信息时使用。
   arguments: {}  或 { "query": "可选，用户原话或关键词" }

3. book_meeting - 用户明确要预定会议时使用。必须能从用户输入中解析出会议主题、开始时间、时长。
   arguments: {
     "title": "会议主题，字符串",
     "start_time": "开始时间，ISO 格式如 2026-03-05T14:00:00",
     "duration_minutes": 60,
     "room": "会议室名，可选，无则 null",
     "participants": ["可选参与者列表"],
     "remind_minutes_before": 15
   }

4. cancel_meeting - 用户表示要「取消」会议时必须用此 tool。包括：取消刚定的、取消刚才的、取消上一笔、不订了、取消预约 等。
   不填 booking_id 表示取消本会话中「上一笔」预定（系统会自动联想）。
   arguments: {}  或 { "booking_id": "可选，若用户明确说了预定 id 再填" }
'''


class MeetingCapability(BaseCapability):
    """会议预定：查会议室、订会、取消。规则来自 rules_provider 或 settings。"""

    def __init__(
        self,
        service: IMeetingService,
        *,
        rules_provider: Optional[IMeetingRulesProvider] = None,
        max_days_ahead: Optional[int] = None,
        max_duration_minutes: Optional[int] = None,
    ) -> None:
        self._service = service
        self._rules_provider = rules_provider
        if rules_provider is None:
            try:
                from ai_assistant.config.meeting_rules_config import meeting_rules_config
                self._max_days_ahead = max_days_ahead if max_days_ahead is not None else meeting_rules_config.meeting_max_days_ahead
                self._max_duration_minutes = max_duration_minutes if max_duration_minutes is not None else meeting_rules_config.meeting_max_duration_minutes
            except Exception:
                self._max_days_ahead = max_days_ahead if max_days_ahead is not None else DEFAULT_MAX_DAYS_AHEAD
                self._max_duration_minutes = max_duration_minutes if max_duration_minutes is not None else DEFAULT_MAX_DURATION_MINUTES
        else:
            self._max_days_ahead = self._max_duration_minutes = 0

    def schema_fragment(self) -> str:
        return _schema_fragment()

    def tool_names(self) -> set[str]:
        return {TOOL_REPLY_ONLY, TOOL_QUERY_ROOMS, TOOL_BOOK_MEETING, TOOL_CANCEL_MEETING}

    def _get_rules(self) -> MeetingBookingRules:
        if self._rules_provider is not None:
            return self._rules_provider.get_booking_rules()
        return MeetingBookingRules(
            max_days_ahead=self._max_days_ahead,
            max_duration_minutes=self._max_duration_minutes,
        )

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        current_time: datetime = context.get("current_time") or datetime.now()
        get_session_value: Optional[Callable[[str], Any]] = context.get("get_session_value")

        if tool_name == TOOL_REPLY_ONLY:
            reply = (arguments.get("reply") or "").strip() or "需要帮您预定会议吗？请直接说会议时间、主题和时长。"
            return {"reply": reply, "booking": None, "error": None}

        if tool_name == TOOL_QUERY_ROOMS:
            query = (arguments.get("query") or "").strip()
            text = self._service.query_meeting_rooms(query)
            reply = f"根据当前信息：\n{text}\n\n如需预定，请说明会议主题、开始时间和时长。"
            # 用户问「某天有哪些空闲」时提示：当前仅有会议室介绍与规则，无档期接口
            if any(k in (query or "") for k in ("空闲", "可用", "明天", "哪天", "有没有空")):
                reply += "\n\n说明：当前仅提供会议室介绍与预约规则，具体某日的空闲时段需对接预约系统或联系管理员。"
            return {"reply": reply, "booking": None, "error": None}

        if tool_name == TOOL_BOOK_MEETING:
            title = (arguments.get("title") or "").strip() or "未命名会议"
            start_time_str = arguments.get("start_time")
            if not start_time_str:
                return {"reply": "未解析到会议开始时间，请说明具体日期和时间。", "booking": None, "error": "PARSE_ERROR"}
            try:
                if isinstance(start_time_str, str):
                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00").strip())
                else:
                    return {"reply": "会议时间格式有误。", "booking": None, "error": "PARSE_ERROR"}
            except ValueError:
                return {"reply": "无法解析会议时间，请说明具体日期和时间。", "booking": None, "error": "PARSE_ERROR"}
            rules = self._get_rules()
            now = current_time if isinstance(current_time, datetime) else datetime.now()
            limit_date = (now + timedelta(days=rules.max_days_ahead)).date()
            start_date = start_time.date() if hasattr(start_time, "date") else start_time
            if start_date > limit_date:
                return {
                    "reply": f"预约规则：最多只能提前 {rules.max_days_ahead} 天预约，您选择的日期超出范围，请选择 {rules.max_days_ahead} 天内的日期。",
                    "booking": None,
                    "error": "EXCEED_MAX_DAYS_AHEAD",
                }
            duration_minutes = int(arguments.get("duration_minutes") or 60)
            if duration_minutes <= 0 or duration_minutes > rules.max_duration_minutes:
                return {
                    "reply": f"预约规则：单次会议时长需在 1～{rules.max_duration_minutes // 60} 小时内，请调整时长。",
                    "booking": None,
                    "error": "EXCEED_MAX_DURATION",
                }
            room = arguments.get("room") or None
            if isinstance(room, str) and not room.strip():
                room = None
            participants = arguments.get("participants")
            if isinstance(participants, list):
                participants = [str(p) for p in participants]
            else:
                participants = None
            remind_minutes_before = int(arguments.get("remind_minutes_before") or 15)

            result = self._service.book_meeting(
                title=title,
                start_time=start_time,
                duration_minutes=duration_minutes,
                room=room,
                participants=participants,
                remind_minutes_before=remind_minutes_before,
            )
            if result.get("success") and result.get("booking"):
                b = result["booking"]
                reply = (
                    f"已为您预定会议：{b.get('title', title)}，"
                    f"开始时间 {start_time.strftime('%Y-%m-%d %H:%M')}，"
                    f"时长 {duration_minutes} 分钟。将在开始前 {remind_minutes_before} 分钟提醒您。"
                )
                return {"reply": reply, "booking": b, "error": None}
            return {
                "reply": result.get("error") or "预定失败，请稍后重试。",
                "booking": None,
                "error": result.get("error") or "BOOK_ERROR",
            }

        if tool_name == TOOL_CANCEL_MEETING:
            booking_id = (arguments.get("booking_id") or "").strip() if arguments else ""
            if not booking_id and get_session_value:
                booking_id = (get_session_value("last_booking_id") or "").strip()
            if not booking_id:
                return {
                    "reply": "未找到要取消的会议。请在本会话中先预定一场会议，或说明要取消的会议编号。",
                    "booking": None,
                    "error": "MISSING_BOOKING_ID",
                }
            result = self._service.cancel_booking(booking_id)
            if result.get("success"):
                return {"reply": result.get("reply", "已取消。"), "booking": None, "error": None}
            return {
                "reply": result.get("reply") or "取消失败。",
                "booking": None,
                "error": result.get("error") or "CANCEL_ERROR",
            }

        return {"reply": "暂不支持该操作。", "booking": None, "error": "UNKNOWN_TOOL"}

    def warmup(self) -> None:
        rag = getattr(self._service, "_rag", None)
        if rag is not None and hasattr(rag, "init_default_knowledge"):
            rag.init_default_knowledge()

    def get_scheduler(self) -> Any:
        return getattr(self._service, "scheduler", None)
