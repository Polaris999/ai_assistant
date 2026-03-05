"""
ToolSkillExecutor：技能层的「工具 schema + 执行」实现，与技能发现/加载解耦。

为 LangGraph Agent 提供技能实例与 execute_tool；可选 get_tools_schema_for_prompt 供自定义 system 文案。
依赖 Skill Catalog（SkillLoader）；会议等为 executor.url 型技能的 HTTP 后端。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ai_assistant.agent.skills.generic import GenericSkill
from ai_assistant.agent.skills.loader import SkillLoader
from ai_assistant.agent.skills.registry import create, registered_ids
from ai_assistant.agent.skills import get_enabled_skill_ids
from ai_assistant.agent.tools import TOOL_LOAD_SKILL, execute_tool as _execute_tool
from ai_assistant.agent.tools import get_tools_schema_for_prompt as _get_tools_schema_for_prompt

logger = logging.getLogger(__name__)


def _use_skill_catalog_only() -> bool:
    """是否仅注入技能目录（渐进式披露）。"""
    try:
        from ai_assistant.config import settings
        return getattr(settings, "use_skill_catalog_only", False)
    except Exception:
        return False


class ToolSkillExecutor:
    """
    技能执行器：在 Skill Catalog 之上，为 LangGraph Agent 提供技能实例、工具 schema 与执行。

    不包含发现/加载逻辑；构建 Skill 实例（GenericSkill 或注册表），对外 get_skills、get_tools_schema_for_prompt、execute_tool、execute_load_skill。
    """

    def __init__(self, catalog: SkillLoader) -> None:
        self._catalog = catalog
        self._skills_cache: Optional[list[Any]] = None

    def get_enabled_skill_ids(self) -> list[str]:
        """当前启用的技能 ID（来自配置或发现）。"""
        return get_enabled_skill_ids()

    def use_skill_catalog_only(self) -> bool:
        """是否仅注入技能目录（渐进式披露）。"""
        return _use_skill_catalog_only()

    def get_skills(self, *, force_refresh: bool = False) -> list[Any]:
        """
        返回当前启用的技能实例列表。
        若 doc 含 executor.url 则用 GenericSkill（HTTP）；否则用注册表。
        """
        if self._skills_cache is not None and not force_refresh:
            return self._skills_cache
        ids = self.get_enabled_skill_ids()
        reg = registered_ids()
        skills: list[Any] = []
        for sid in ids:
            doc = self._catalog.load_by_name(sid)
            if doc and (doc.get("executor") or {}).get("url"):
                skills.append(GenericSkill(doc))
                logger.debug("技能 %s 使用 HTTP 后端 (executor.url)", sid)
            elif sid in reg:
                inst = create(sid)
                if inst is not None:
                    skills.append(inst)
            else:
                logger.warning("技能 %s 未配置 executor.url 且未注册，已跳过", sid)
        self._skills_cache = skills
        return self._skills_cache

    def get_tools_schema_for_prompt(self) -> str:
        """聚合各技能的工具 schema；目录模式下包含 load_skill。"""
        skills = self.get_skills()
        return _get_tools_schema_for_prompt(skills, include_load_skill=self.use_skill_catalog_only())

    def execute_load_skill(self, skill_name: str) -> dict[str, Any]:
        """按需加载技能全文（渐进式披露）；返回 {reply, booking, error}。"""
        doc = self._catalog.load_by_name(skill_name)
        if doc:
            name = doc.get("name") or doc.get("id") or skill_name
            content = (doc.get("content") or "").strip()
            reply = f"已加载技能：{name}\n\n{content}"
            return {"reply": reply, "booking": None, "error": None}
        docs = self._catalog.load_all()
        available = ", ".join((d.get("name") or d.get("id") or "").strip() for d in docs if (d.get("id") or d.get("name")))
        reply = f"未找到技能「{skill_name}」。" + (f"可用技能包括：{available}" if available else "当前无可用技能。")
        return {"reply": reply, "booking": None, "error": None}

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """按 tool 名分发到对应技能执行；目录模式下 load_skill 由此处处理。"""
        if tool_name == TOOL_LOAD_SKILL and self.use_skill_catalog_only():
            skill_name = (arguments.get("skill_name") or arguments.get("skill_id") or "").strip()
            return self.execute_load_skill(skill_name)
        skills = self.get_skills()
        return _execute_tool(tool_name, arguments or {}, skills, context)
