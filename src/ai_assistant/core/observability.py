"""可观测：OpenTelemetry 链路（可选）。未安装 otel 或未开启时为 no-op。"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)

_tracer: Any = None


class _NoopSpan:
    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, name: str, attributes: Optional[dict[str, Any]] = None):
        yield _NoopSpan()


def init_otel(service_name: Optional[str] = None, otlp_endpoint: Optional[str] = None) -> bool:
    """
    初始化 OpenTelemetry TracerProvider（需先 pip install -e '.[otel]'）。
    未传 otlp_endpoint 时读环境变量 OTEL_EXPORTER_OTLP_ENDPOINT；未配置或未安装则 get_tracer() 为 no-op。
    """
    import os
    global _tracer
    if _tracer is not None and not isinstance(_tracer, _NoopTracer):
        return True
    endpoint = (otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        logger.debug("OpenTelemetry 未安装，链路为 no-op。可选: pip install -e '.[otel]'")
        _tracer = _NoopTracer()
        return False
    if not endpoint:
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT 未配置，链路为 no-op")
        _tracer = _NoopTracer()
        return False
    try:
        name = service_name or os.environ.get("OTEL_SERVICE_NAME", "ai-assistant")
        resource = Resource.create({"service.name": name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("ai_assistant", "1.0.0")
        logger.info("OpenTelemetry 已启用，OTLP endpoint: %s", endpoint)
        return True
    except Exception as e:
        logger.warning("OpenTelemetry 初始化失败，链路为 no-op: %s", e)
        _tracer = _NoopTracer()
        return False


def get_tracer() -> Any:
    """返回 Tracer；未初始化或未安装 otel 时为 no-op（start_as_current_span 不做事）。"""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace
        _tracer = trace.get_tracer("ai_assistant", "1.0.0")
        return _tracer
    except ImportError:
        _tracer = _NoopTracer()
        return _tracer
