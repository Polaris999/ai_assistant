"""LLM 抽象：invoke + name。"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseLLM(ABC):
    """LLM 基类，多后端切换。"""

    @abstractmethod
    def invoke(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__
