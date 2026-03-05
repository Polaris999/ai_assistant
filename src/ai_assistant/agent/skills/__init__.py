# 技能层：业内统一做法——skill_docs 发现 + 执行层（HTTP 或注册表）
from __future__ import annotations

from typing import Any, List

from ai_assistant.agent.skills.registry import create_all

__all__ = ["get_default_skills", "get_enabled_skill_ids"]


def get_enabled_skill_ids() -> List[str]:
    """
    返回当前启用的技能 ID 列表。
    若配置 ENABLED_SKILLS 则取其（逗号分隔）；否则从 skill_docs 发现全部有 SKILL.md 的子目录。
    """
    from ai_assistant.config import settings
    from ai_assistant.agent.skills.loader import get_skill_ids_from_docs
    raw = (getattr(settings, "enabled_skills", None) or "").strip()
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return get_skill_ids_from_docs()


def get_default_skills() -> List[Any]:
    """
    返回技能列表：按 get_enabled_skill_ids() 从注册表实例化。
    会议等技能由 skill_docs + executor.url 走 GenericSkill（HTTP），无进程内 MeetingSkill。
    """
    return create_all(get_enabled_skill_ids())
