"""LLM 胶水层抽象：统一 invoke 接口，由 openai / vllm / dify 等适配器实现。"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseLLM(ABC):
    """LLM 抽象基类，仅约定 invoke 与 name，便于多后端切换。"""

    @abstractmethod
    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        """输入 prompt（及可选 system、temperature），返回模型生成文本。"""
        pass

    @property
    def name(self) -> str:
        """适配器名称，用于日志等。"""
        return self.__class__.__name__
