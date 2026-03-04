"""全局统一响应格式：code, msg, data, request_id。"""
from typing import Any, Optional

from fastapi.responses import JSONResponse

# 业务码：与 HTTP 语义一致，便于前端统一判断
CODE_SUCCESS = 0
CODE_BUSINESS_ERROR = 1
CODE_VALIDATION_ERROR = 400
CODE_NOT_FOUND = 404
CODE_INTERNAL_ERROR = 500
CODE_SERVICE_UNAVAILABLE = 503

# AppException.code (string) -> (body code, http status)；新增异常子类时需在此登记
APP_EXCEPTION_MAP = {
    "VALIDATION_ERROR": (CODE_VALIDATION_ERROR, 422),
    "NOT_FOUND": (CODE_NOT_FOUND, 404),
    "CONFIG_ERROR": (CODE_SERVICE_UNAVAILABLE, 503),
    "RUNTIME_ERROR": (CODE_SERVICE_UNAVAILABLE, 503),
    "LLM_ERROR": (CODE_INTERNAL_ERROR, 500),
    "BUSINESS_ERROR": (CODE_BUSINESS_ERROR, 200),
    "SERVICE_UNAVAILABLE": (CODE_SERVICE_UNAVAILABLE, 503),
}


def body(
    code: int,
    msg: str,
    data: Any = None,
    request_id: str = "",
) -> dict:
    """构造统一响应体。"""
    out = {"code": code, "msg": msg, "data": data}
    if request_id:
        out["request_id"] = request_id
    return out


def json_response(
    code: int,
    msg: str,
    data: Any = None,
    request_id: str = "",
    status_code: Optional[int] = None,
) -> JSONResponse:
    """返回统一格式的 JSONResponse。未传 status_code 时：code 为 0 或 1 时用 HTTP 200，其余用 code 作为 HTTP 状态码。"""
    if status_code is None:
        status_code = 200 if code in (CODE_SUCCESS, CODE_BUSINESS_ERROR) else code
    return JSONResponse(
        status_code=status_code,
        content=body(code, msg, data, request_id),
    )


def success(data: Any = None, request_id: str = "", status_code: int = 200) -> JSONResponse:
    """成功响应。API 层仅包装 success，错误由抛异常 + 全局处理器返回。"""
    return json_response(CODE_SUCCESS, "success", data, request_id, status_code=status_code)


def app_exception_to_code_status(exc_code: str) -> tuple[int, int]:
    """AppException.code -> (body code, http status)。未知 code 按服务端错误返回 500。"""
    return APP_EXCEPTION_MAP.get(
        exc_code,
        (CODE_INTERNAL_ERROR, 500),
    )
