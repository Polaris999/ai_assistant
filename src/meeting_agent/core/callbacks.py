# core/callbacks.py
"""Agent 可观测：结构化日志回调，便于与 request_id 关联、与 LangSmith 互补。"""
import logging
import time
from typing import Any, Optional

from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class AgentLoggingCallbackHandler(BaseCallbackHandler):
    """对图节点与 LLM 调用打点并写结构化日志，支持 request_id 关联。"""

    def __init__(self, request_id: Optional[str] = None) -> None:
        self.request_id = request_id or ""
        self._run_start: Optional[float] = None
        self._llm_start: Optional[float] = None

    def _extra(self) -> dict:
        extra: dict = {}
        if self.request_id:
            extra["request_id"] = self.request_id
        return extra

    def on_chain_start(self, serialized: dict, inputs: dict, **kwargs: Any) -> None:
        name = serialized.get("name", serialized.get("id", ["unknown"])[-1] if isinstance(serialized.get("id"), list) else "chain")
        self._run_start = time.perf_counter()
        logger.info(
            "agent.node_start node=%s",
            name,
            extra={**self._extra(), "agent_node": name},
        )

    def on_chain_end(self, outputs: dict, **kwargs: Any) -> None:
        duration_ms = (time.perf_counter() - self._run_start) * 1000 if self._run_start else 0
        logger.info(
            "agent.node_end duration_ms=%.0f",
            duration_ms,
            extra={**self._extra(), "duration_ms": round(duration_ms)},
        )

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs: Any) -> None:
        self._llm_start = time.perf_counter()
        logger.info(
            "agent.llm_start",
            extra=self._extra(),
        )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        duration_ms = (time.perf_counter() - self._llm_start) * 1000 if self._llm_start else 0
        logger.info(
            "agent.llm_end duration_ms=%.0f",
            duration_ms,
            extra={**self._extra(), "duration_ms": round(duration_ms)},
        )

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        pass

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        pass
