"""对话应用服务：编排会话、历史、Agent 调用与回写；直接调用 agent.invoke()，有 error 时由 agent 内部抛异常。"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ai_assistant.api.services.chat_result_handlers import get_chat_result_handlers
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.core.serialization import to_json_serializable

logger = logging.getLogger(__name__)


class ChatService:
    """对话用例：一次文本请求的编排（会话取/建、历史、invoke、回写）。直接调用 agent.invoke()，出错由 agent 抛异常。"""

    def handle_text(
        self,
        text: str,
        conversation_id: Optional[str],
        request_id: str,
        agent: Any,
    ) -> dict[str, Any]:
        """处理单轮文本对话。成功返回 reply、booking、conversation_id；agent 有 error 时在内部抛异常。"""
        text = (text or "").strip()
        store = get_conversation_store()
        cid = store.get_or_create_id(conversation_id)
        history = store.get_recent(cid)
        t0 = time.perf_counter()
        result = agent.invoke(
            text,
            request_id=request_id,
            conversation_id=cid,
            history=history,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        store.append(cid, "user", text)
        store.append(cid, "assistant", result.get("reply") or "")
        for handler in get_chat_result_handlers():
            handler.after_chat_result(cid, result)
        logger.info("chat req_id=%s cid=%s text_len=%s elapsed_ms=%.0f", request_id, cid[:8], len(text), elapsed_ms)
        return {
            "reply": result.get("reply", "处理失败"),
            "booking": to_json_serializable(result.get("booking")),
            "conversation_id": cid,
        }
