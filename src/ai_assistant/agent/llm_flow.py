"""
LLM 交互流程规范落点：阶段 1（输入校验与意图短路）统一实现，供 LangGraph Agent 复用。

详见 docs/LLM_INTERACTION_FLOW.md。新增可短路意图时在此模块与 intent.py 中扩展，避免在各 Agent 内零散打补丁。
"""
from __future__ import annotations

from typing import Optional, Tuple

from ai_assistant.agent.intent import (
    UserIntent,
    detect_intent,
    reply_for_chitchat,
    reply_for_query_rooms,
)


# 阶段 1 未短路时返回的空输入提示（与规范一致）
EMPTY_INPUT_REPLY = "请说出或输入您要预定的会议信息。"


def run_pre_llm_stage(
    user_input: str,
    rag_context: Optional[str] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    阶段 1：输入校验与意图短路（Pre-LLM）。

    若可直接回复则返回 (result_dict, stage_name)，调用方应直接返回并结束；
    否则返回 (None, None)，调用方进入阶段 2（LLM 调用）。

    - 空输入 → 固定提示，stage="empty"
    - CHITCHAT（问候/闲聊）→ reply_for_chitchat，stage="chitchat"
    - QUERY_ROOMS 且提供了 rag_context → reply_for_query_rooms(rag_context)，stage="query_rooms"
    - 其他（含 QUERY_ROOMS 但无 rag_context）→ (None, None)

    Returns:
        (result, stage_name): result 为 {"reply": str, "booking": None, "error": None}；stage_name 用于打日志。
    """
    s = (user_input or "").strip()

    if not s:
        return (
            {"reply": EMPTY_INPUT_REPLY, "booking": None, "error": None},
            "empty",
        )

    intent = detect_intent(user_input)

    if intent == UserIntent.CHITCHAT:
        return (
            {"reply": reply_for_chitchat(user_input), "booking": None, "error": None},
            "chitchat",
        )

    if intent == UserIntent.QUERY_ROOMS and rag_context is not None:
        return (
            {"reply": reply_for_query_rooms(rag_context), "booking": None, "error": None},
            "query_rooms",
        )

    return (None, None)
