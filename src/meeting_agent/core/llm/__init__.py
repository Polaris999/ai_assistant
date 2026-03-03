# OpenAI 适配器在 factory 内按需 import
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.factory import get_llm
from meeting_agent.core.llm.dify_adapter import DifyLLMAdapter

__all__ = ["BaseLLM", "get_llm", "DifyLLMAdapter"]
