"""
LangGraph Agent Runner：使用 create_react_agent + 技能转 LangChain Tool，实现 AgentRunner 协议。

当前唯一 Agent 实现，由 agent_bootstrap 创建。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ai_assistant.agent.langgraph_tools import reset_langgraph_context, set_langgraph_context, skills_to_langchain_tools
from ai_assistant.agent.llm_flow import run_pre_llm_stage
from ai_assistant.agent.skills.manager import SkillManager
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.core.exceptions import AppException, ConfigError
from ai_assistant.core.serialization import to_json_serializable

logger = logging.getLogger(__name__)


def _get_langchain_chat_model() -> Any:
    """根据配置返回 LangChain ChatModel（OpenAI 或 vLLM 兼容端点）。"""
    from ai_assistant.config import settings
    llm_type = (getattr(settings, "llm_type", None) or "vllm").strip().lower()
    if llm_type == "openai":
        from langchain_openai import ChatOpenAI
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise ConfigError("LLM_TYPE=openai 时需配置 OPENAI_API_KEY")
        base_url = (getattr(settings, "openai_base_url", None) or "").strip() or None
        model = getattr(settings, "openai_chat_model", "gpt-4o-mini")
        timeout = int(getattr(settings, "llm_request_timeout_seconds", 0) or 120)
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            request_timeout=timeout,
        )
    if llm_type == "vllm":
        from langchain_openai import ChatOpenAI
        base_url = (getattr(settings, "vllm_base_url", None) or "").strip()
        if not base_url:
            raise ConfigError("LLM_TYPE=vllm 时需配置 VLLM_BASE_URL")
        model = (getattr(settings, "vllm_chat_model", None) or "").strip() or "default"
        api_key = (getattr(settings, "vllm_api_key", None) or "").strip() or "no-key"
        timeout = int(getattr(settings, "llm_request_timeout_seconds", 0) or 120)
        return ChatOpenAI(
            model=model,
            base_url=base_url.rstrip("/"),
            api_key=api_key if api_key != "no-key" else None,
            temperature=0,
            request_timeout=timeout,
        )
    raise ConfigError(f"LangGraph 当前仅支持 llm_type=openai 或 vllm，当前: {llm_type}")


class LangGraphRunner:
    """基于 LangGraph create_react_agent 的 Runner，实现 AgentRunner 协议。"""

    _scheduler = None

    def __init__(
        self,
        manager: Optional[SkillManager] = None,
        *,
        model: Any = None,
    ) -> None:
        self._manager = manager or SkillManager()
        self._model = model if model is not None else _get_langchain_chat_model()
        skills = self._manager.get_skills()
        self._tools = skills_to_langchain_tools(
            skills,
            include_load_skill=self._manager.use_skill_catalog_only(),
            execute_tool_fn=self._manager.execute_tool,
        )
        try:
            from langgraph.prebuilt import create_react_agent
            self._agent = create_react_agent(self._model, self._tools)
        except ImportError as e:
            raise ConfigError("LangGraph 路径需要 langgraph，请安装: pip install langgraph") from e

    def warmup(self) -> None:
        for skill in self._manager.get_skills():
            if getattr(skill, "warmup", None):
                skill.warmup()

    def invoke(
        self,
        user_input: str,
        user_id: str = "default",
        request_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        user_input = (user_input or "").strip()

        # 阶段 1：与自研一致，意图短路
        pre_result, _ = run_pre_llm_stage(user_input, rag_context=None)
        if pre_result is not None:
            return pre_result

        store = get_conversation_store()
        cid = conversation_id or ""
        now = datetime.now()
        get_session_value = None
        if cid:
            get_session_value = lambda k, cid=cid: store.get_session_value(cid, k)
        from ai_assistant.config import settings
        skill_timeout = getattr(settings, "skill_http_timeout_seconds", 30) or 30
        context = {
            "current_time": now,
            "get_session_value": get_session_value,
            "_skill_http_timeout": skill_timeout,
            "_last_tool_result": None,
        }
        token = set_langgraph_context(context)
        try:
            from langchain_core.messages import AIMessage, HumanMessage
            messages = []
            if history:
                for m in history:
                    role = (m.get("role") or "").strip() or "user"
                    content = (m.get("content") or "").strip()
                    if role == "user":
                        messages.append(HumanMessage(content=content))
                    else:
                        messages.append(AIMessage(content=content))
            messages.append(HumanMessage(content=user_input))
            config = {}
            if request_id:
                config["metadata"] = {"request_id": request_id}
            result = self._agent.invoke({"messages": messages}, config=config)
            last = (result.get("messages") or [])[-1] if result else None
            content = getattr(last, "content", None) or (last if isinstance(last, str) else "") or ""
            reply = content.strip() if content else "处理完成。"
            last_tool = context.get("_last_tool_result")
            if last_tool and isinstance(last_tool, dict):
                if last_tool.get("error"):
                    code = last_tool.get("error") if last_tool.get("error") in ("RUNTIME_ERROR", "CONFIG_ERROR") else "BUSINESS_ERROR"
                    raise AppException(
                        "success",
                        code=code,
                        details={
                            "reply": last_tool.get("reply", reply),
                            "booking": to_json_serializable(last_tool.get("booking")),
                            "error": last_tool.get("error"),
                            "conversation_id": cid,
                        },
                    )
                reply = last_tool.get("reply") or reply
            booking = to_json_serializable(last_tool.get("booking") if last_tool else None)
            return {"reply": reply, "booking": booking, "error": None}
        finally:
            reset_langgraph_context(token)


def create_langgraph_agent(manager: Optional[SkillManager] = None) -> Any:
    """创建 LangGraph Runner；失败时抛 ConfigError 或返回占位。"""
    try:
        return LangGraphRunner(manager=manager)
    except ConfigError:
        raise
    except Exception as e:
        logger.warning("LangGraph Agent 创建失败: %s", e)
        from ai_assistant.agent.protocol import create_placeholder_runner
        return create_placeholder_runner(str(e))
