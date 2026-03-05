"""技能协议与基类：业内常用格式为 Skill Manifest + Tools Schema（OpenAI/JSON Schema 兼容）。"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

# 业内常见：技能清单（id/name/description）+ 工具列表（name/description/parameters）
SkillManifest = dict[str, Any]  # 至少含 id, name, description
ToolSchema = dict[str, Any]    # 至少含 name, description, parameters (JSON Schema)


def format_tools_schema_for_prompt(tools_schema: list[ToolSchema]) -> str:
    """将结构化 tool schema（OpenAI/JSON Schema 风格）格式化为供 LLM 阅读的文本片段。"""
    lines = []
    for i, t in enumerate(tools_schema, 1):
        name = t.get("name") or "unknown"
        desc = (t.get("description") or "").strip()
        params = t.get("parameters") or {}
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        parts = [f"{i}. {name} - {desc}"]
        if props:
            args_pairs = []
            for k, v in props.items():
                pdesc = (v.get("description") or "").strip() or str(v.get("type", ""))
                req = "必填" if k in required else "可选"
                args_pairs.append(f'"{k}": {pdesc}（{req}）')
            parts.append("   arguments: { " + ", ".join(args_pairs) + " }")
        else:
            parts.append("   arguments: {} 或 { \"query\": \"可选\" } 等")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


@runtime_checkable
class Skill(Protocol):
    """
    单技能协议，与业内（OpenAI Function Calling、Dify、Bot Framework 等）对齐：
    - 技能清单（manifest）：id、name、description
    - 工具列表（tools schema）：每项含 name、description、parameters（JSON Schema）
    """

    def get_skill_manifest(self) -> SkillManifest:
        """返回技能清单：id, name, description（可选 version、endpoint 等）。"""
        ...

    def get_tools_schema(self) -> list[ToolSchema]:
        """返回该技能下的工具定义列表，每项为 OpenAI 风格：name, description, parameters。"""
        ...

    def schema_fragment(self) -> str:
        """供 LLM 的工具说明文本（可由 get_tools_schema() 经 format_tools_schema_for_prompt 生成）。"""
        ...

    def tool_names(self) -> set[str]:
        """该技能暴露的 tool 名称集合。"""
        ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行该技能下的某个 tool。返回 reply, booking?, error?。"""
        ...


class BaseSkill:
    """
    技能基类：提供基于 get_tools_schema() 的默认 schema_fragment/tool_names；
    子类实现 get_skill_manifest、get_tools_schema、execute 即可。
    """

    def get_skill_manifest(self) -> SkillManifest:
        """默认返回空清单，子类应覆盖。"""
        return {"id": "", "name": "", "description": ""}

    def get_tools_schema(self) -> list[ToolSchema]:
        """默认返回空列表，子类应覆盖。"""
        return []

    def schema_fragment(self) -> str:
        """由 get_tools_schema() 生成 prompt 用文本。"""
        return format_tools_schema_for_prompt(self.get_tools_schema())

    def tool_names(self) -> set[str]:
        """从 get_tools_schema() 提取 name 集合。"""
        return {str(t["name"]) for t in self.get_tools_schema() if t.get("name")}

    def warmup(self) -> None:
        """可选：启动时预热。"""
        pass

    def get_scheduler(self) -> Any:
        """可选：供 lifespan 关闭的调度器。"""
        return None
