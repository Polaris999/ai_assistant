"""
通用序列化：将 Pydantic、datetime 等转为可被 JSON 编码的类型。
供 API 层、Service 层在返回给前端或写日志前统一使用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def to_json_serializable(obj: Any) -> Any:
    """
    将对象转为可 JSON 序列化的值。支持：
    - None → None
    - Pydantic v2 (.model_dump(mode="json")) → dict
    - Pydantic v1 (.dict()) → dict，datetime 转为 isoformat
    - dict / list → 递归处理
    - datetime → isoformat 字符串
    - 其他 → 原样返回
    """
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return {k: to_json_serializable(v) for k, v in obj.dict().items()}
    return _scalar_json(obj)


def _scalar_json(v: Any) -> Any:
    """单值：datetime → str，嵌套 dict/list 递归；其他原样。"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _scalar_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scalar_json(x) for x in v]
    return v
