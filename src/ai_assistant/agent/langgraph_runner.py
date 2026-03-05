"""
LangGraph Agent Runner：使用 create_react_agent + 技能转 LangChain Tool，实现 AgentRunner 协议。

当前唯一 Agent 实现，由 agent_bootstrap 创建。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ai_assistant.agent.intent import UserIntent, detect_intent
from ai_assistant.agent.langgraph_tools import reset_langgraph_context, set_langgraph_context, skills_to_langchain_tools
from ai_assistant.agent.llm_flow import run_pre_llm_stage
from ai_assistant.agent.skills.manager import SkillManager
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.core.exceptions import AppException, ConfigError, LLMError
from ai_assistant.core.llm.factory import get_chat_model_for_langgraph
from ai_assistant.core.serialization import to_json_serializable

logger = logging.getLogger(__name__)


def _truncate_history_by_chars(
    history: list[dict[str, str]],
    max_chars: int,
) -> list[dict[str, str]]:
    """当 max_chars>0 时从最旧消息起丢弃直到总字符数不超过 max_chars，保证保留最近消息。"""
    if not history or max_chars <= 0:
        return history
    total = sum(len((m.get("content") or "")) for m in history)
    out = list(history)
    while total > max_chars and len(out) > 1:
        total -= len((out[0].get("content") or ""))
        out.pop(0)
    return out


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
        self._model = model if model is not None else get_chat_model_for_langgraph()
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

    def is_ready(self) -> bool:
        """健康检查就绪：Runner 创建成功即可视为就绪。"""
        return True

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

        # 阶段 1：意图短路；QUERY_ROOMS 时先拉 RAG 上下文再短路，避免多一次 LLM
        rag_context: Optional[str] = None
        if detect_intent(user_input) == UserIntent.QUERY_ROOMS:
            try:
                from ai_assistant.rag.meeting_rag import get_default_meeting_rag
                rag = get_default_meeting_rag()
                rag_context = rag.retrieve_context(user_input, k=4)
            except Exception as e:
                logger.debug("QUERY_ROOMS RAG 检索失败，将走 LLM: %s", e)
                rag_context = None
        pre_result, _ = run_pre_llm_stage(user_input, rag_context=rag_context)
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
            "request_id": request_id or "",
        }
        token = set_langgraph_context(context)
        try:
            from langchain_core.messages import AIMessage, HumanMessage
            messages = []
            max_chars = int(getattr(settings, "conversation_history_max_chars", 0) or 0)
            if history:
                history = _truncate_history_by_chars(history, max_chars)
                for m in history:
                    role = (m.get("role") or "").strip() or "user"
                    content = (m.get("content") or "").strip()
                    if role == "user":
                        messages.append(HumanMessage(content=content))
                    else:
                        messages.append(AIMessage(content=content))
            messages.append(HumanMessage(content=user_input))
            from langchain_core.runnables import RunnableConfig
            config: RunnableConfig = {}
            if request_id:
                config["metadata"] = {"request_id": request_id, "conversation_id": cid}
            from ai_assistant.config import settings
            recursion_limit = int(getattr(settings, "agent_recursion_limit", 0) or 0)
            if recursion_limit > 0:
                config["recursion_limit"] = recursion_limit
            try:
                result = self._agent.invoke({"messages": messages}, config=config)
            except Exception as e:
                err_text = str(e)
                # vLLM OpenAI 兼容端点：未启用 tool calling 时会返回该错误
                if '"auto" tool choice requires --enable-auto-tool-choice' in err_text:
                    raise ConfigError(
                        "vLLM 未启用工具调用（tool choice=auto）。请用支持 tool calling 的方式启动 vLLM，或切换 LLM_TYPE=openai。",
                        details={
                            "hint": "为 vLLM OpenAI server 增加参数：--enable-auto-tool-choice --tool-call-parser hermes（或 mistral）",
                            "vllm_base_url": getattr(__import__("ai_assistant.config", fromlist=["settings"]).settings, "vllm_base_url", ""),
                            "request_id": request_id or "",
                            "conversation_id": cid,
                        },
                    ) from e
                logger.warning("LangGraph LLM 调用失败: %s", err_text)
                raise LLMError(
                    "LLM 调用失败",
                    details={
                        "error": err_text,
                        "request_id": request_id or "",
                        "conversation_id": cid,
                    },
                ) from e
            last = (result.get("messages") or [])[-1] if result else None
            content = getattr(last, "content", None) or (last if isinstance(last, str) else "") or ""
            reply = content.strip() if content else "处理完成。"
            # 模型有时输出英文兜底句，统一替换为中文
            if reply and ("need more steps" in reply.lower() or "sorry" in reply.lower() and "process" in reply.lower()):
                reply = "请补充会议主题、开始时间和时长，我来帮您预定。"
            last_tool = context.get("_last_tool_result")
            if last_tool and isinstance(last_tool, dict):
                if last_tool.get("error"):
                    err_code = str(last_tool.get("error") or "")
                    code = err_code if err_code in ("RUNTIME_ERROR", "CONFIG_ERROR") else "BUSINESS_ERROR"
                    err_reply = last_tool.get("reply", reply) or "技能执行失败"
                    # msg 用简短文案，详情仅放在 data.reply，避免重复
                    raise AppException(
                        "技能执行失败",
                        code=code,
                        details={
                            "reply": err_reply,
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
