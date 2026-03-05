"""
技能注册表：业内统一做法——技能 ID 与执行器工厂绑定，配合 skill_docs 发现实现「文档驱动 + 执行注册」。

- 来源：skill_docs/*/SKILL.md 决定「有哪些技能」（get_skill_ids_from_docs）
- 配置：ENABLED_SKILLS 可选过滤启用列表
- 执行：本注册表 skill_id -> factory，按 ID 实例化 Skill
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# skill_id -> 无参工厂，返回 Skill 实例
_REGISTRY: dict[str, Callable[[], Any]] = {}


def register(skill_id: str, factory: Callable[[], Any]) -> None:
    """注册技能：skill_id 与工厂函数绑定。factory() 返回实现 Skill 协议的对象。"""
    if not skill_id or not callable(factory):
        raise ValueError("skill_id 非空且 factory 必须可调用")
    _REGISTRY[skill_id] = factory
    logger.debug("技能已注册: %s", skill_id)


def create(skill_id: str) -> Any:
    """按 ID 创建技能实例；未注册返回 None。"""
    f = _REGISTRY.get(skill_id)
    if f is None:
        return None
    return f()


def create_all(skill_ids: list[str]) -> list[Any]:
    """按 ID 列表依次创建，跳过未注册的 ID。"""
    out = []
    for sid in skill_ids:
        s = create(sid)
        if s is not None:
            out.append(s)
        else:
            logger.warning("技能未注册，已跳过: %s", sid)
    return out


def registered_ids() -> set[str]:
    """已注册的技能 ID 集合。"""
    return set(_REGISTRY.keys())
