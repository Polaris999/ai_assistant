"""
对话结果后置处理器：Agent 返回 result 后，由各业务自行判断并执行侧效应（如记录 last_booking_id）。
ChatService 只遍历调用，不感知具体业务；新增业务时在此注册新 handler 即可，无需改 ChatService。
协议采用结构子类型，各 Service 实现 after_chat_result 即可，无需显式继承。
"""
from __future__ import annotations

from typing import Any, Protocol


class ChatResultHandler(Protocol):
    """对话结果处理器：根据 result 内容决定是否执行本业务逻辑。"""

    def after_chat_result(self, conversation_id: str, result: dict[str, Any]) -> None:
        """在对话回合结束后调用；可检查 result 中的 booking、ticket 等并写入会话或做其他侧效应。"""
        ...


def get_chat_result_handlers() -> list[ChatResultHandler]:
    """返回所有已注册的对话结果处理器；新增业务时在此追加，无需修改 ChatService。"""
    from ai_assistant.api.services.booking_handler import BookingHandler

    return [
        BookingHandler(),
        # 后续例如: TicketHandler(), OrderHandler(), ...
    ]
