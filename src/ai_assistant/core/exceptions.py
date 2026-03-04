"""应用异常：code/message/details，可序列化为 API 响应。"""
from typing import Any, Optional


class AppException(Exception):
    """异常基类。"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigError(AppException):
    """配置缺失或非法。"""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="CONFIG_ERROR", details=details)


class ValidationError(AppException):
    """参数校验失败。"""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class LLMError(AppException):
    """LLM 调用失败。"""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class NotFoundError(AppException):
    """资源不存在。"""

    def __init__(self, message: str = "资源不存在", details: Optional[dict[str, Any]] = None):
        super().__init__(message, code="NOT_FOUND", details=details)
