"""
运维工单能力（占位）：后续可在此实现「发现一处问题，自动创建运维工单」等。
实现后需在 capabilities/__init__.py 的 get_default_capabilities() 中注册。
"""
from __future__ import annotations

from typing import Any


# 占位：后续可定义 TOOL_CREATE_OPS_TICKET 等，实现 schema_fragment、tool_names、execute；
# 会话上下文可用 set_session_value(cid, "last_ticket_id", ticket_id) 供「查询刚建的工单」等联想。
