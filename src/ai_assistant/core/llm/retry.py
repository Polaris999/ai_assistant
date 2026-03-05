"""LLM 调用重试：超时与网络类异常时指数退避重试。"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import TYPE_CHECKING, Optional

from ai_assistant.core.exceptions import LLMError

if TYPE_CHECKING:
    from ai_assistant.core.llm.base import BaseLLM

logger = logging.getLogger(__name__)


def invoke_with_retry(
    llm: "BaseLLM",
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0,
    timeout_sec: int = 120,
    retry_count: int = 0,
) -> str:
    """
    带超时与重试的 LLM 调用。仅对超时、LLMError、OSError 及通用 Exception 重试并指数退避。
    retry_count=0 表示不重试，仅调用一次。
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max(0, retry_count) + 1):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(
                    lambda: llm.invoke(prompt, system=system, temperature=temperature),
                ).result(timeout=timeout_sec)
        except (FuturesTimeoutError, LLMError, OSError) as e:
            last_exc = e
            if attempt < max(0, retry_count):
                delay = min(2 ** attempt, 10)
                logger.warning("LLM 调用失败（第 %s 次），%ss 后重试: %s", attempt + 1, delay, e)
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            last_exc = e
            if attempt < max(0, retry_count):
                delay = min(2 ** attempt, 10)
                logger.warning("LLM 调用异常（第 %s 次），%ss 后重试: %s", attempt + 1, delay, e)
                time.sleep(delay)
            else:
                raise
    assert last_exc is not None
    raise last_exc
