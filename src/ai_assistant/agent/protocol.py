"""
Agent 运行器协议与工具函数：所有 Agent 实现统一接口，便于 API、lifespan 与扩展。

- 实现 invoke() 成功时返回至少 reply（可含 booking 等）；有 error 时在内部抛 AppException，不返回 error 字段。
- API 层直接调用 agent.invoke()，无需再判断 result.get("error")。
- 可选：实现 is_ready()、warmup()；lifespan 会带超时调用 warmup，关闭时 shutdown _scheduler。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Optional, Protocol, TypedDict, runtime_checkable

logger = logging.getLogger(__name__)


class InvokeResult(TypedDict):
    """invoke() 最少应包含的字段；可含额外业务字段如 booking、intent。"""
    reply: str
    error: Optional[str]


@runtime_checkable
class AgentRunner(Protocol):
    """Agent 运行器协议：对接 API 与 lifespan 的统一入口。"""

    def invoke(
        self,
        user_input: str,
        user_id: str = "default",
        request_id: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行一轮对话/任务；成功返回含 reply（可含 booking 等）的 dict，失败在内部抛 AppException。"""
        ...

    @property
    def _scheduler(self) -> Any:
        """用于 lifespan 关闭时 shutdown(wait=True)；无则设为 None。"""
        ...


def is_agent_ready(agent: Optional[Any]) -> bool:
    """
    判断 Agent 是否就绪（非占位）。
    若实现类提供 is_ready() 则优先调用；否则以 _scheduler is not None 视为就绪。
    """
    if agent is None:
        return False
    is_ready_fn = getattr(agent, "is_ready", None)
    if callable(is_ready_fn):
        return bool(is_ready_fn())
    return getattr(agent, "_scheduler", None) is not None


def run_agent_warmup(agent: Any, timeout_seconds: int = 45) -> tuple[bool, Optional[str]]:
    """
    执行 Agent 启动预热：若存在可调用的 warmup() 则调用；否则若存在 _rag.init_default_knowledge 则调用。
    在子线程中执行并带超时。返回 (成功与否, 错误信息)。
    """
    if agent is None:
        return True, None
    warmup_fn = getattr(agent, "warmup", None)
    if not callable(warmup_fn):
        rag = getattr(agent, "_rag", None)
        warmup_fn = getattr(rag, "init_default_knowledge", None) if rag else None
    if not callable(warmup_fn):
        return True, None
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(warmup_fn).result(timeout=timeout_seconds)
        return True, None
    except FuturesTimeoutError:
        return False, f"预热超时 {timeout_seconds}s"
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Agent warmup 失败: %s", e)
        return False, str(e)
    except Exception as e:
        logger.exception("Agent warmup 未预期异常")
        return False, str(e)
