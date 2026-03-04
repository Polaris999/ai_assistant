"""生产用中间件：请求 ID、安全头、请求日志、可选 OpenTelemetry span。"""
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)




class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或透传 X-Request-ID，并写入 request.state 与响应头。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加常用安全响应头。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求结束后打一条日志（method, path, status, duration_ms, request_id）；可选 OTel span 包裹整请求。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        try:
            from ai_assistant.core.observability import get_tracer
            tracer = get_tracer()
            with tracer.start_as_current_span("http.request") as span:
                if hasattr(span, "set_attribute"):
                    span.set_attribute("http.method", request.method)
                    span.set_attribute("http.target", request.url.path or "")
                    rid = getattr(request.state, "request_id", None)
                    if rid:
                        span.set_attribute("request_id", rid)
                response = await call_next(request)
        except Exception:
            response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        request_id = getattr(request.state, "request_id", "")
        logger.info(
            "req %s %s %s %.0fms %s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id or "-",
        )
        return response
