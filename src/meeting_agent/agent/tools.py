"""
Agent 可调用的 Tools：查询会议室、预定会议。执行时调用 IMeetingService，由业务服务接口实现。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from meeting_agent.services.meeting_service import IMeetingService

logger = logging.getLogger(__name__)

# Tool 名称，与 LLM 输出及执行分支一致
TOOL_QUERY_ROOMS = "query_meeting_rooms"
TOOL_BOOK_MEETING = "book_meeting"
TOOL_REPLY_ONLY = "reply_only"


def get_tools_schema_for_prompt() -> str:
    """返回供 LLM 使用的工具说明（拼进 system/user prompt），便于模型输出合规的 tool + arguments。"""
    return '''
你只能输出一个 JSON 对象，且仅此 JSON，不要 markdown 或多余文字。根据用户意图选择 exactly 一个 tool，并填写 arguments。

可选 tool：
1. reply_only - 用户只是打招呼、问你是谁、闲聊，或无法解析为预定/查会议室时使用。
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

输出格式：{"tool": "reply_only|query_meeting_rooms|book_meeting", "arguments": {...}}
'''


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    service: IMeetingService,
    current_time: datetime,
) -> dict[str, Any]:
    """
    执行指定 tool，返回统一结构：reply (str), booking (dict|None), error (str|None)。
    """
    if tool_name == TOOL_REPLY_ONLY:
        reply = (arguments.get("reply") or "").strip() or "需要帮您预定会议吗？请直接说会议时间、主题和时长。"
        return {"reply": reply, "booking": None, "error": None}

    if tool_name == TOOL_QUERY_ROOMS:
        query = (arguments.get("query") or "").strip()
        text = service.query_meeting_rooms(query)
        reply = f"根据当前信息：\n{text}\n\n如需预定，请说明会议主题、开始时间和时长。"
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
        duration_minutes = int(arguments.get("duration_minutes") or 60)
        room = arguments.get("room") or None
        if isinstance(room, str) and not room.strip():
            room = None
        participants = arguments.get("participants")
        if isinstance(participants, list):
            participants = [str(p) for p in participants]
        else:
            participants = None
        remind_minutes_before = int(arguments.get("remind_minutes_before") or 15)

        result = service.book_meeting(
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

    return {"reply": "暂不支持该操作。", "booking": None, "error": "UNKNOWN_TOOL"}


def parse_llm_tool_output(text: str) -> tuple[Optional[str], dict[str, Any]]:
    """从 LLM 输出中解析 tool 与 arguments。返回 (tool_name, arguments)，解析失败返回 (None, {})。"""
    text = (text or "").strip()
    if not text:
        return None, {}
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if l.strip() and not l.strip().startswith("```"))
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        tool = (data.get("tool") or "").strip().lower()
        args = data.get("arguments")
        if not isinstance(args, dict):
            args = {}
        if tool in (TOOL_REPLY_ONLY, TOOL_QUERY_ROOMS, TOOL_BOOK_MEETING):
            return tool, args
    except json.JSONDecodeError:
        pass
    return None, {}
