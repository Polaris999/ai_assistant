"""
会话历史存储：按 conversation_id 保存最近 N 轮对话，供多轮澄清与上下文补全。
并维护每会话的通用上下文键值（如 last_booking_id、后续 last_ticket_id 等），供各能力联想。
业内做法：请求带 conversation_id（可选），响应带回；服务端按 id 取历史拼入 LLM 输入。
默认进程内存储；配置 REDIS_HOST 或 REDIS_URL 时使用 Redis 存储。
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

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
        """若未传或为空则生成新 id，否则返回去除首尾空白后的 id（不校验是否存在）。"""
        cid = (conversation_id or "").strip()
        return cid if cid else str(uuid.uuid4())

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


# Redis 实现：与 ConversationStore 同一接口，供生产多实例/持久化
_CONV_KEY_PREFIX = "ai_assistant:conv:"


class RedisConversationStore(ConversationStore):
    """基于 Redis 的会话存储：消息列表 + 会话上下文 Hash，支持 TTL。"""

    def __init__(
        self,
        redis_url: str,
        max_messages_per_conversation: int = DEFAULT_MAX_MESSAGES_PER_CONVERSATION,
        ttl_seconds: int = 86400,
    ):
        super().__init__(max_messages_per_conversation=max_messages_per_conversation)
        import redis
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds
        self._store = None  # 不再使用内存 store
        self._session_context = None  # 不再使用内存 context

    def _msgs_key(self, conversation_id: str) -> str:
        return f"{_CONV_KEY_PREFIX}{conversation_id}:msgs"

    def _ctx_key(self, conversation_id: str) -> str:
        return f"{_CONV_KEY_PREFIX}{conversation_id}:ctx"

    def _expire(self, conversation_id: str) -> None:
        self._client.expire(self._msgs_key(conversation_id), self._ttl)
        self._client.expire(self._ctx_key(conversation_id), self._ttl)

    def get_recent(self, conversation_id: str, limit: Optional[int] = None) -> list[MessageDict]:
        n = limit if limit is not None else self._max
        key = self._msgs_key(conversation_id)
        raw = self._client.lrange(key, -n, -1)  # 最后 n 条，保持从旧到新
        out = []
        for s in (raw or []):
            try:
                out.append(json.loads(s))
            except Exception:
                continue
        return out

    def append(self, conversation_id: str, role: str, content: str) -> None:
        key = self._msgs_key(conversation_id)
        msg = json.dumps({"role": role, "content": (content or "").strip()})
        self._client.rpush(key, msg)
        self._client.ltrim(key, -self._max, -1)
        self._expire(conversation_id)

    def clear(self, conversation_id: str) -> None:
        self._client.delete(self._msgs_key(conversation_id))
        self._client.delete(self._ctx_key(conversation_id))

    def set_session_value(self, conversation_id: str, key: str, value: Any) -> None:
        k = self._ctx_key(conversation_id)
        self._client.hset(k, key, json.dumps(value, default=str))
        self._expire(conversation_id)

    def get_session_value(self, conversation_id: str, key: str) -> Optional[Any]:
        """返回该会话下某上下文键的值，无则 None。若存的是非 JSON 字符串则记录 debug 并返回该字符串。"""
        raw = self._client.hget(self._ctx_key(conversation_id), key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Redis session value 非 JSON，key=%s: %s", key, e)
            return raw if isinstance(raw, str) else None

    def set_last_booking_id(self, conversation_id: str, booking_id: str) -> None:
        self.set_session_value(conversation_id, "last_booking_id", (booking_id or "").strip())

    def get_last_booking_id(self, conversation_id: str) -> Optional[str]:
        v = self.get_session_value(conversation_id, "last_booking_id")
        return str(v).strip() if v else None


# 全局单例，可被替换为 Redis 等实现
_conversation_store: Optional[ConversationStore] = None
_store_lock = threading.Lock()


def get_conversation_store() -> ConversationStore:
    global _conversation_store
    with _store_lock:
        if _conversation_store is None:
            from ai_assistant.config.settings import settings
            max_msgs = getattr(settings, "conversation_max_messages", None) or DEFAULT_MAX_MESSAGES_PER_CONVERSATION
            redis_url = settings.get_redis_url()
            if redis_url:
                _conversation_store = RedisConversationStore(
                    redis_url=redis_url,
                    max_messages_per_conversation=max_msgs,
                    ttl_seconds=settings.conversation_store_ttl_seconds,
                )
            else:
                _conversation_store = ConversationStore(max_messages_per_conversation=max_msgs)
        return _conversation_store
