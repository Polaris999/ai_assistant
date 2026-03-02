# core/exceptions.py
from typing import Any, Optional


class AppException(Exception):
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
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="CONFIG_ERROR", details=details)


class ValidationError(AppException):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class LLMError(AppException):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class NotFoundError(AppException):
    def __init__(self, message: str = "资源不存在", details: Optional[dict] = None):
        super().__init__(message, code="NOT_FOUND", details=details)
