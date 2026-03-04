"""
会话历史存储：按 conversation_id 保存最近 N 轮对话，供多轮澄清与上下文补全。
并维护每会话的通用上下文键值（如 last_booking_id、后续 last_ticket_id 等），供各能力联想。
业内做法：请求带 conversation_id（可选），响应带回；服务端按 id 取历史拼入 LLM 输入。
默认进程内存储，生产可替换为 Redis 等。
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

logger = None  # lazy init to avoid circular import

# 单条消息：role + content
MessageDict = dict[str, str]

# 每会话保留最近消息条数（user+assistant 合计）
DEFAULT_MAX_MESSAGES_PER_CONVERSATION = 20


class ConversationStore:
    """进程内会话历史：conversation_id -> [消息...]；及每会话的通用 session 键值（各能力共用）。"""

    def __init__(self, max_messages_per_conversation: int = DEFAULT_MAX_MESSAGES_PER_CONVERSATION):
        self._store: dict[str, list[MessageDict]] = {}
        self._session_context: dict[str, dict[str, Any]] = {}  # cid -> {key: value}
        self._lock = threading.Lock()
        self._max = max_messages_per_conversation

    def get_or_create_id(self, conversation_id: Optional[str] = None) -> str:
        """若未传则生成新 id，否则原样返回（不校验是否存在）。"""
        if conversation_id and (conversation_id or "").strip():
            return (conversation_id or "").strip()
        return str(uuid.uuid4())

    def get_recent(self, conversation_id: str, limit: Optional[int] = None) -> list[MessageDict]:
        """返回该会话最近 limit 条消息（从旧到新）；默认不超过配置的 max。"""
        n = limit if limit is not None else self._max
        with self._lock:
            messages = self._store.get(conversation_id) or []
            return messages[-n:] if len(messages) > n else messages

    def append(self, conversation_id: str, role: str, content: str) -> None:
        """追加一条消息；超过 max 时丢弃最旧的。"""
        with self._lock:
            if conversation_id not in self._store:
                self._store[conversation_id] = []
            self._store[conversation_id].append({"role": role, "content": (content or "").strip()})
            messages = self._store[conversation_id]
            if len(messages) > self._max:
                self._store[conversation_id] = messages[-self._max :]

    def clear(self, conversation_id: str) -> None:
        """清空该会话（可选能力，如用户说「重新开始」）。"""
        with self._lock:
            self._store.pop(conversation_id, None)
            self._session_context.pop(conversation_id, None)

    def set_session_value(self, conversation_id: str, key: str, value: Any) -> None:
        """设置该会话下某上下文键值，供各能力使用（如 last_booking_id、last_ticket_id）。"""
        with self._lock:
            if conversation_id not in self._session_context:
                self._session_context[conversation_id] = {}
            self._session_context[conversation_id][key] = value

    def get_session_value(self, conversation_id: str, key: str) -> Optional[Any]:
        """返回该会话下某上下文键的值，无则 None。"""
        with self._lock:
            return (self._session_context.get(conversation_id) or {}).get(key)

    def set_last_booking_id(self, conversation_id: str, booking_id: str) -> None:
        """记录该会话下最近一次成功预定的 booking_id（能力「会议」使用）。"""
        self.set_session_value(conversation_id, "last_booking_id", (booking_id or "").strip())

    def get_last_booking_id(self, conversation_id: str) -> Optional[str]:
        """返回该会话下最近一次预定的 booking_id，无则 None。"""
        v = self.get_session_value(conversation_id, "last_booking_id")
        return str(v).strip() if v else None


# 全局单例，可被替换为 Redis 等实现
_conversation_store: Optional[ConversationStore] = None
_store_lock = threading.Lock()


def get_conversation_store() -> ConversationStore:
    global _conversation_store
    with _store_lock:
        if _conversation_store is None:
            _conversation_store = ConversationStore()
        return _conversation_store
