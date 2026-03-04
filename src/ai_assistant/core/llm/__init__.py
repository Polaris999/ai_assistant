# OpenAI 适配器在 factory 内按需 import
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.factory import get_llm
from ai_assistant.core.llm.dify_adapter import DifyLLMAdapter

__all__ = ["BaseLLM", "get_llm", "DifyLLMAdapter"]
