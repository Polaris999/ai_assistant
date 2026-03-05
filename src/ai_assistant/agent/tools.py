"""Tools：聚合各技能 schema 并分发执行；主流程由 LangGraph + LangChain Tool 驱动。

- 工具定义：技能声明式 schema（skill_docs/*/tools.json），执行走 Skill.execute（含 HTTP 后端）。
- Agent 主路径：langgraph_tools.skills_to_langchain_tools 将技能转为 LangChain StructuredTool，由 create_react_agent 调用。
- 本模块：get_tools_schema_for_prompt 供可选「拼 system 文案」；execute_tool 供技能层执行；详见 docs/ARCHITECTURE.md。
"""
from __future__ import annotations

import logging
from typing import Any

from ai_assistant.config.prompt_loader import get_prompt_tools_intro

logger = logging.getLogger(__name__)

# 会议技能 tool 名（与 skill_docs/meeting/tools.json 一致），用于解析回退与工具列表
TOOL_REPLY_ONLY = "reply_only"
TOOL_QUERY_ROOMS = "query_meeting_rooms"
TOOL_BOOK_MEETING = "book_meeting"
TOOL_CANCEL_MEETING = "cancel_meeting"
# 渐进式披露：按需加载技能全文，仅当 use_skill_catalog_only=True 时作为可选工具暴露
TOOL_LOAD_SKILL = "load_skill"

_LOAD_SKILL_SCHEMA_FRAGMENT = (
    "- load_skill: 将某技能的完整说明加载到上下文中。"
    "当需要某类任务的详细说明、业务规则或示例时使用。"
    "参数：skill_name（要加载的技能名称，如 meeting）。"
)


def get_tools_schema_for_prompt(
    skills: list[Any],
    include_load_skill: bool = False,
) -> str:
    intro = get_prompt_tools_intro()
    if not intro.endswith("\n"):
        intro += "\n"
    fragments = [s.schema_fragment() for s in skills]
    all_tools = set()
    for s in skills:
        all_tools |= s.tool_names()
    if include_load_skill:
        fragments.append(_LOAD_SKILL_SCHEMA_FRAGMENT)
        all_tools.add(TOOL_LOAD_SKILL)
    tool_list_str = "|".join(sorted(all_tools))
    return intro + "\n".join(fragments) + f"\n输出格式：{{\"tool\": \"{tool_list_str}\", \"arguments\": {{...}}}}"


def get_all_tool_names(skills: list[Any], include_load_skill: bool = False) -> set[str]:
    out = set()
    for s in skills:
        out |= s.tool_names()
    if include_load_skill:
        out.add(TOOL_LOAD_SKILL)
    return out


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    skills: list[Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """执行工具。load_skill 由 SkillManager.execute_tool 在内部处理，不进入本函数。"""
    for skill in skills:
        if tool_name in skill.tool_names():
            return skill.execute(tool_name, arguments or {}, context)
    return {"reply": "暂不支持该操作。", "booking": None, "error": "UNKNOWN_TOOL"}
