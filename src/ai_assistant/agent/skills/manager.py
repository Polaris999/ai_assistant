"""
SkillManager：技能门面，组合「Skill Catalog（发现/加载）」与「技能执行器」。

- **Catalog**：发现、加载 SKILL.md，格式化为 prompt 片段（可选）。
- **执行**：由 ToolSkillExecutor 提供技能实例、execute_tool、execute_load_skill，供 LangGraph Agent（langgraph_tools）使用。

见 docs/ARCHITECTURE_EXTENSIBILITY.md。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ai_assistant.agent.skills.loader import SkillLoader
from ai_assistant.agent.skills.tool_executor import ToolSkillExecutor


class SkillManager:
    """
    技能门面：Catalog（发现/加载/格式化）+ 技能执行器。

    用法：LangGraph Runner 通过 langgraph_tools.skills_to_langchain_tools(manager.get_skills(), ..., execute_tool_fn=manager.execute_tool) 绑定工具；
    可选 system 文案：intro + manager.get_skill_docs_for_prompt() + manager.get_tools_schema_for_prompt()。
    """

    def __init__(self, skill_docs_root: Optional[Path] = None) -> None:
        self._catalog = SkillLoader(skill_docs_root=skill_docs_root)
        self._executor = ToolSkillExecutor(self._catalog)

    def get_enabled_skill_ids(self) -> list[str]:
        """当前启用的技能 ID（ENABLED_SKILLS 或从 skill_docs 发现）。"""
        return self._executor.get_enabled_skill_ids()

    def use_skill_catalog_only(self) -> bool:
        """是否仅注入技能目录（渐进式披露）；为 True 时需配合 load_skill 工具按需加载全文。"""
        return self._executor.use_skill_catalog_only()

    def get_skill_docs_for_prompt(self) -> str:
        """加载技能文档并格式化为可拼入 system prompt 的文本；目录模式下仅返回 name+description。"""
        if self.use_skill_catalog_only():
            return self._catalog.format_catalog_for_prompt()
        return self._catalog.format_for_prompt()

    def get_skills(self, *, force_refresh: bool = False) -> list[Any]:
        """返回当前启用的技能实例列表（Tool 执行用）。"""
        return self._executor.get_skills(force_refresh=force_refresh)

    def get_tools_schema_for_prompt(self) -> str:
        """聚合各技能的工具 schema，供 LLM 的 system prompt 使用。目录模式下包含 load_skill。"""
        return self._executor.get_tools_schema_for_prompt()

    def execute_load_skill(self, skill_name: str) -> dict[str, Any]:
        """按需加载技能全文（渐进式披露）；返回 {reply, booking, error}。"""
        return self._executor.execute_load_skill(skill_name)

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """按 tool 名分发到对应技能执行；目录模式下 load_skill 由此处处理。"""
        return self._executor.execute_tool(tool_name, arguments or {}, context)


def get_skill_manager(skill_docs_root: Optional[Path] = None) -> SkillManager:
    """获取单例 SkillManager（进程内复用，可选自定义 skill_docs 根目录）。"""
    if skill_docs_root is not None:
        return SkillManager(skill_docs_root=skill_docs_root)
    if not hasattr(get_skill_manager, "_instance"):
        get_skill_manager._instance = SkillManager()  # type: ignore[attr-defined]
    return get_skill_manager._instance  # type: ignore[attr-defined]
