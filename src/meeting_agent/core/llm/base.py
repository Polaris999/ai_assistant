# core/llm/base.py
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseLLM(ABC):
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
