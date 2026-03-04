"""订会对话结果处理器：在 result 有 booking 时写入 last_booking_id。"""
from __future__ import annotations

from typing import Any

from ai_assistant.core.conversation import get_conversation_store


class BookingHandler:
    """订会域 ChatResultHandler：若 result 含有效 booking（含 id），则记入该会话 last_booking_id，供后续取消等使用。"""

    def after_chat_result(self, conversation_id: str, result: dict[str, Any]) -> None:
        booking = result.get("booking")
        if not booking or not booking.get("id"):
            return
        get_conversation_store().set_last_booking_id(conversation_id, booking["id"])
