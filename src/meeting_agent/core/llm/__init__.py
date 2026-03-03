# 仅导出 base、factory、dify；OpenAI 适配器在 factory 中按需 import，避免未用 openai 时加载 torch/langchain
from meeting_agent.core.llm.base import BaseLLM
from meeting_agent.core.llm.factory import get_llm
from meeting_agent.core.llm.dify_adapter import DifyLLMAdapter

__all__ = ["BaseLLM", "get_llm", "DifyLLMAdapter"]
