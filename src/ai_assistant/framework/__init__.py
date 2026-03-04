"""
可复用框架层：新 Agent 可直接 from ai_assistant.framework import ... 使用。

包含：
- Agent 抽象：AgentRunner、InvokeResult、is_agent_ready、run_agent_warmup
- 响应：body、success、json_response、CODE_*
- 异常：AppException、ValidationError、ConfigError、LLMError、NotFoundError
- 中间件：REQUEST_ID_HEADER、RequestIDMiddleware、SecurityHeadersMiddleware、RequestLoggingMiddleware
- LLM：BaseLLM、get_llm
- Embeddings：BaseEmbeddings、get_embeddings
- 向量库：get_vector_store、VectorStoreWrapper
- 可观测：AgentLoggingCallbackHandler
- 工具：mask_secret
"""
from ai_assistant.agent_base import AgentRunner, InvokeResult, is_agent_ready, run_agent_warmup
from ai_assistant.api.response import (
    CODE_BUSINESS_ERROR,
    CODE_INTERNAL_ERROR,
    CODE_NOT_FOUND,
    CODE_SERVICE_UNAVAILABLE,
    CODE_SUCCESS,
    CODE_VALIDATION_ERROR,
    app_exception_to_code_status,
    body,
    json_response,
    success,
)
from ai_assistant.core.callbacks import AgentLoggingCallbackHandler
from ai_assistant.core.embeddings.base import BaseEmbeddings
from ai_assistant.core.embeddings.factory import get_embeddings
from ai_assistant.core.exceptions import (
    AppException,
    ConfigError,
    LLMError,
    NotFoundError,
    ValidationError,
)
from ai_assistant.core.helper import mask_secret
from ai_assistant.core.llm.base import BaseLLM
from ai_assistant.core.llm.factory import get_llm
from ai_assistant.api.middleware import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from ai_assistant.core.vectorstore.factory import VectorStoreWrapper, get_vector_store

__all__ = [
    "AgentRunner",
    "InvokeResult",
    "run_agent_warmup",
    "REQUEST_ID_HEADER",
    "RequestIDMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
    "AgentLoggingCallbackHandler",
    "AppException",
    "BaseEmbeddings",
    "BaseLLM",
    "ConfigError",
    "LLMError",
    "NotFoundError",
    "ValidationError",
    "CODE_SUCCESS",
    "CODE_BUSINESS_ERROR",
    "CODE_VALIDATION_ERROR",
    "CODE_NOT_FOUND",
    "CODE_INTERNAL_ERROR",
    "CODE_SERVICE_UNAVAILABLE",
    "app_exception_to_code_status",
    "body",
    "get_embeddings",
    "get_llm",
    "get_vector_store",
    "is_agent_ready",
    "json_response",
    "mask_secret",
    "success",
    "VectorStoreWrapper",
]
