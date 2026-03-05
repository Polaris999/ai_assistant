"""
LangGraph 用：将现有技能（Skill）暴露为 LangChain StructuredTool，执行仍走 execute_tool/Skill.execute。

通过 contextvar 注入单次请求的 context（conversation_id、get_session_value 等），
LangGraph 调用 tool.invoke 时从 contextvar 取 context，无需改技能层。
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, List

from ai_assistant.agent.tools import execute_tool

logger = logging.getLogger(__name__)

# 当前请求的 context，由 LangGraphRunner.invoke 在入口设置、出口清除
_LANGGRAPH_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("langgraph_agent_context", default=None)


def set_langgraph_context(context: dict[str, Any] | None) -> Any:
    """设置当前请求的 context（供工具 invoke 时使用）。返回 token，finally 中应调用 reset_langgraph_context(token)。"""
    return _LANGGRAPH_CONTEXT.set(context)


def reset_langgraph_context(token: Any) -> None:
    """恢复 contextvar 到 set 之前的状态，传入 set_langgraph_context 的返回值。"""
    if token is None:
        return
    try:
        _LANGGRAPH_CONTEXT.reset(token)
    except Exception:
        pass


def get_langgraph_context() -> dict[str, Any] | None:
    """获取当前请求的 context。"""
    return _LANGGRAPH_CONTEXT.get(None)


def _tool_result_to_content(result: dict[str, Any]) -> str:
    """将 execute_tool 返回的 dict 转为供 LLM 阅读的字符串。"""
    reply = (result.get("reply") or "").strip()
    if result.get("error"):
        return f"错误: {result.get('error')}\n{reply}" if reply else f"错误: {result.get('error')}"
    return reply or json.dumps(result, ensure_ascii=False)


def skills_to_langchain_tools(
    skills: List[Any],
    include_load_skill: bool = False,
    execute_tool_fn: Any = None,
) -> List[Any]:
    """
    将技能列表转为 LangChain StructuredTool 列表，供 LangGraph bind_tools / create_react_agent 使用。

    execute_tool_fn 若提供则应为 (tool_name, arguments, context) -> dict；
    否则使用本模块的 execute_tool(skills=skills)。
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as e:
        raise ImportError("LangGraph 路径需要 langchain-core，请安装: pip install langchain-core") from e

    tools_schema: List[dict[str, Any]] = []
    for s in skills:
        for t in (s.get_tools_schema() if hasattr(s, "get_tools_schema") else []):
            if isinstance(t, dict) and t.get("name"):
                tools_schema.append(t)
    if include_load_skill:
        tools_schema.append({
            "name": "load_skill",
            "description": "将某技能的完整说明加载到上下文中。当需要某类任务的详细说明、业务规则或示例时使用。",
            "parameters": {
                "type": "object",
                "properties": {"skill_name": {"type": "string", "description": "要加载的技能名称，如 meeting"}},
                "required": [],
            },
        })

    def _invoke(tool_name: str, **kwargs: Any) -> str:
        ctx = get_langgraph_context() or {}
        if execute_tool_fn is not None:
            result = execute_tool_fn(tool_name, kwargs, ctx)
        else:
            result = execute_tool(tool_name, kwargs, skills, ctx)
        if isinstance(ctx, dict) and "_last_tool_result" in ctx:
            ctx["_last_tool_result"] = result
        return _tool_result_to_content(result)

    out: List[Any] = []
    for t in tools_schema:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        desc = (t.get("description") or "").strip() or name
        params = t.get("parameters") or {}
        # 为每个 tool 绑定 name 的闭包
        def _make_func(n: str):
            def _f(**kw: Any) -> str:
                return _invoke(n, **kw)
            return _f
        tool = StructuredTool.from_function(
            name=name,
            description=desc,
            func=_make_func(name),
            args_schema=None,  # 由 function 推断或后续用 schema 约束
        )
        # LangChain 部分版本支持直接传 coroutine；这里用同步
        out.append(tool)
    return out
