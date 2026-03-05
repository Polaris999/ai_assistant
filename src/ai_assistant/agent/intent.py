"""
意图识别与路由：先判断用户意图，再决定后续处理（规则版，可扩展为 LLM 或 Tools）。

意图类型：
- chitchat：问候/闲聊，固定或模板回复
- query_rooms：查询会议室/预约信息，仅用 RAG 结果回复
- book_meeting：预定会议，走完整 RAG → 解析 → 创建预定流程
"""
from enum import Enum
from typing import Optional


class UserIntent(str, Enum):
    """用户意图枚举，用于路由分发。"""
    CHITCHAT = "chitchat"
    QUERY_ROOMS = "query_rooms"
    BOOK_MEETING = "book_meeting"


# 简短问候：精确匹配则视为闲聊
_CHITCHAT_PHRASES = {
    "你好", "您好", "hello", "hi", "在吗", "在", "嗨",
}

# 身份/介绍类：短句内包含则视为闲聊，避免被误解析为预定（如「你好，你是谁」）
_IDENTITY_KEYWORDS = ("你是谁", "你是什么", "who are you", "what are you", "介绍自己", "介绍下", "你能做什么")

# 会议室查询：输入包含任一关键词则视为查会议室/预约信息
_QUERY_ROOMS_KEYWORDS = ("会议室", "有哪些", "有什么", "列出", "列表", "可预约", "可用")

# 闲聊回复模板（按短语可扩展）
_CHITCHAT_REPLIES: dict[str, str] = {
    "你好": "你好！需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "您好": "您好！需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "hello": "你好！需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "hi": "你好！需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "在吗": "在的。需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "在": "在的。需要帮您预定会议吗？请直接说会议时间、主题和时长。",
    "嗨": "嗨！需要帮您预定会议吗？请直接说会议时间、主题和时长。",
}

DEFAULT_CHITCHAT_REPLY = "需要帮您预定会议吗？请直接说会议时间、主题和时长。"
IDENTITY_REPLY = "我是助手，可以帮您预定会议、查询会议室。需要预定请说会议时间、主题和时长。"


def detect_intent(user_input: str) -> UserIntent:
    """
    规则式意图识别（无 LLM）。
    先判闲聊，再判查会议室，其余一律视为预定会议，由后续节点解析。
    """
    s = (user_input or "").strip()
    if not s:
        return UserIntent.CHITCHAT

    # 短句精确匹配 → 闲聊
    if len(s) <= 20 and s.lower() in {p.lower() for p in _CHITCHAT_PHRASES}:
        return UserIntent.CHITCHAT

    # 短句以「你好/您好」或 hi/hello 开头（如「你好啊」「hi，你好啊」）→ 闲聊
    if len(s) <= 25:
        lower = s.lower()
        if s.startswith("你好") or s.startswith("您好"):
            return UserIntent.CHITCHAT
        if lower.startswith("hi") or lower.startswith("hello"):
            return UserIntent.CHITCHAT
        # 业内常见：按逗号/空格取首段，首段为问候即视为闲聊（如 "hi，你好啊" → 首段 "hi"）
        first_segment = s.split("，")[0].split(",")[0].strip()
        if first_segment:
            fl = first_segment.lower()
            if fl in {p.lower() for p in _CHITCHAT_PHRASES}:
                return UserIntent.CHITCHAT
            if first_segment.startswith("你好") or first_segment.startswith("您好"):
                return UserIntent.CHITCHAT

    # 短句内包含身份/介绍类（如「你好，你是谁」）→ 闲聊，避免误解析为预定
    if len(s) <= 50 and any(k in s for k in _IDENTITY_KEYWORDS):
        return UserIntent.CHITCHAT

    # 包含会议室/查询类关键词且不长 → 查会议室
    if len(s) <= 50 and any(k in s for k in _QUERY_ROOMS_KEYWORDS):
        return UserIntent.QUERY_ROOMS

    return UserIntent.BOOK_MEETING


def reply_for_chitchat(user_input: str) -> str:
    """闲聊意图的回复文案。身份/介绍类优先返回自我介绍，否则按短语匹配或默认。"""
    s = user_input.strip()
    if any(k in s for k in _IDENTITY_KEYWORDS):
        return IDENTITY_REPLY
    for key, reply in _CHITCHAT_REPLIES.items():
        if s.lower() == key.lower():
            return reply
    return DEFAULT_CHITCHAT_REPLY


def reply_for_query_rooms(rag_context: Optional[str]) -> str:
    """查会议室意图的回复文案（基于 RAG 上下文）。"""
    text = (rag_context or "").strip()
    if not text:
        return "当前暂无会议室信息。您可以直接说会议时间、主题和时长，我帮您预定。"
    return f"根据当前信息：\n{text}\n\n如需预定，请说明会议主题、开始时间和时长。"
