"""统一应用异常：便于 API 层映射为 HTTP 状态与 JSON body。"""
from typing import Any, Optional


class AppException(Exception):
    """业务/系统异常基类，含 code、message、details，可序列化为 API 响应。"""

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
    """配置缺失或非法（如未配置 API Key）。"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="CONFIG_ERROR", details=details)


class ValidationError(AppException):
    """请求参数校验失败。"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class LLMError(AppException):
    """LLM 调用失败或返回异常。"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class NotFoundError(AppException):
    """资源不存在。"""

    def __init__(self, message: str = "资源不存在", details: Optional[dict] = None):
        super().__init__(message, code="NOT_FOUND", details=details)
