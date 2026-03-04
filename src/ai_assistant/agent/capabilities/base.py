"""能力协议与基类：Protocol 定义必须实现；BaseCapability 提供可选方法默认实现。"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Capability(Protocol):
    """单种能力的协议：必须实现 schema_fragment、tool_names、execute。"""

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


class BaseCapability:
    """
    能力基类：提供可选方法默认实现，子类只需实现 schema_fragment、tool_names、execute。
    需要预热或调度器时重写 warmup()、get_scheduler()。
    """

    def warmup(self) -> None:
        """可选：启动时预热（如加载知识库）。默认空实现。"""
        pass

    def get_scheduler(self) -> Any:
        """可选：供 lifespan 关闭的调度器，无则返回 None。"""
        return None
