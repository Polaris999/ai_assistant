"""能力协议：各能力实现 schema_fragment、tool_names、execute；可选 warmup、get_scheduler。"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Capability(Protocol):
    """单种能力的协议。"""

    def schema_fragment(self) -> str:
        """供 LLM 的工具说明文本（不含通用头尾）。"""
        ...

    def tool_names(self) -> set[str]:
        """该能力处理的 tool 名称集合。"""
        ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行该能力下的某个 tool。返回 reply, booking?, error?。"""
        ...

    def warmup(self) -> None:
        """可选：预热。"""
        ...

    def get_scheduler(self) -> Any:
        """可选：供 lifespan 关闭的调度器，无则返回 None。"""
        ...
