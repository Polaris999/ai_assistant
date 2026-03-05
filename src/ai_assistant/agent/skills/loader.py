"""
SkillLoader：Skill Catalog 实现，仅负责发现与加载，与具体 Agent、会议等业务解耦。

- 发现：skill_docs/*/SKILL.md，返回技能 ID 或文档列表。
- 加载：按目录或 name 加载 SKILL.md，解析 frontmatter（name、description、content、tools、executor）。
- 格式化：format_for_prompt（全文）、format_catalog_for_prompt（仅目录），供任意 Agent 使用。

不包含工具 schema、execute_tool、load_skill 等执行逻辑；执行由 ToolSkillExecutor 承担。
见 docs/ARCHITECTURE_EXTENSIBILITY.md。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# 委托给 config.skill_loader，agent 层统一从 skills.loader 引用
from ai_assistant.config.skill_loader import (
    SKILL_DOCS_DIR,
    format_skill_catalog_for_prompt,
    format_skill_docs_for_prompt,
    get_skill_ids_from_docs,
    load_all_skill_docs,
    load_skill_by_name,
    load_skill_doc,
)

__all__ = [
    "SKILL_DOCS_DIR",
    "SkillLoader",
    "load_all_skill_docs",
    "load_skill_doc",
    "load_skill_by_name",
    "get_skill_ids_from_docs",
    "format_skill_docs_for_prompt",
    "format_skill_catalog_for_prompt",
]


class SkillLoader:
    """
    技能文档加载器门面：发现 + 加载 + 格式化。

    用法与 skillkit 的 Discovery + 加载一致：指定根目录（默认 skill_docs），
    发现所有有 SKILL.md 的子目录，加载为 {id, name, description, content, tools?, executor?}。
    """

    def __init__(self, skill_docs_root: Optional[Path] = None) -> None:
        self._root = Path(skill_docs_root) if skill_docs_root else SKILL_DOCS_DIR

    def _docs_root_arg(self) -> Optional[Path]:
        """传 None 时 config.skill_loader 使用默认目录并走缓存。"""
        return None if self._root == SKILL_DOCS_DIR else self._root

    def discover_skill_ids(self) -> list[str]:
        """发现技能 ID 列表（有 SKILL.md 的子目录名）。"""
        return get_skill_ids_from_docs(self._docs_root_arg())

    def load_all(self) -> list[dict[str, Any]]:
        """加载全部技能文档。"""
        return load_all_skill_docs(self._docs_root_arg())

    def load_by_name(self, skill_name: str) -> Optional[dict[str, Any]]:
        """按名称加载单个技能文档。"""
        return load_skill_by_name(skill_name, self._docs_root_arg())

    def format_for_prompt(self, skill_docs: Optional[list[dict[str, Any]]] = None) -> str:
        """将技能文档格式化为可拼入 system prompt 的文本（全文）；不传则加载全部后格式化。"""
        docs = skill_docs if skill_docs is not None else self.load_all()
        return format_skill_docs_for_prompt(docs)

    def format_catalog_for_prompt(self, skill_docs: Optional[list[dict[str, Any]]] = None) -> str:
        """仅将技能目录（name+description）格式化为可拼入 system prompt 的文本，用于渐进式披露。"""
        docs = skill_docs if skill_docs is not None else self.load_all()
        return format_skill_catalog_for_prompt(docs)
