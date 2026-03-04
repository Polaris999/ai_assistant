"""Tools：聚合各能力 schema，解析 LLM 输出的 tool + arguments 并分发执行。"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ai_assistant.agent.capabilities.meeting import TOOL_REPLY_ONLY

logger = logging.getLogger(__name__)
TOOL_REPLY_ONLY_NAME = TOOL_REPLY_ONLY


def get_tools_schema_for_prompt(capabilities: list[Any]) -> str:
    intro = """
你只能输出一个 JSON 对象，且仅此 JSON，不要 markdown 或多余文字。根据用户意图选择 exactly 一个 tool，并填写 arguments。
"""
    fragments = [c.schema_fragment() for c in capabilities]
    tool_lists = [c.tool_names() for c in capabilities]
    all_tools = set()
    for s in tool_lists:
        all_tools |= s
    tool_list_str = "|".join(sorted(all_tools))
    return intro + "\n".join(fragments) + f"\n输出格式：{{\"tool\": \"{tool_list_str}\", \"arguments\": {{...}}}}"


def get_all_tool_names(capabilities: list[Any]) -> set[str]:
    out = set()
    for c in capabilities:
        out |= c.tool_names()
    return out


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    capabilities: list[Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    for cap in capabilities:
        if tool_name in cap.tool_names():
            return cap.execute(tool_name, arguments or {}, context)
    return {"reply": "暂不支持该操作。", "booking": None, "error": "UNKNOWN_TOOL"}


def parse_llm_tool_output(text: str, valid_tools: set[str]) -> tuple[Optional[str], dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None, {}
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if l.strip() and not l.strip().startswith("```"))
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        tool = (data.get("tool") or "").strip().lower()
        args = data.get("arguments")
        if not isinstance(args, dict):
            args = {}
        if tool in valid_tools:
            return tool, args
    except json.JSONDecodeError:
        pass
    return None, {}
