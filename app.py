#!/usr/bin/env python3
"""FastAPI 入口（生产向：请求 ID、安全头、lifespan、全局异常、可观测）。"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ai_assistant import __version__
from ai_assistant.api.deps import get_agent
from ai_assistant.api.middleware import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from ai_assistant.api.response import (
    body as response_body,
    app_exception_to_code_status,
    CODE_INTERNAL_ERROR,
)
from ai_assistant.api.v1 import router as v1_router
from ai_assistant.config import get_profile, settings
from ai_assistant.core.exceptions import AppException

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """可观测、配置校验（仅打日志）、创建 Agent；失败则占位。"""
    logger.info("配置 profile: %s", get_profile())
    if getattr(settings, "langchain_tracing_enabled", False):
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if getattr(settings, "langchain_project", ""):
            os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("LangSmith 追踪已开启，项目名: %s", getattr(settings, "langchain_project", "ai-assistant"))
    from ai_assistant.config.validation import validate_settings
    errs = validate_settings()
    if errs:
        logger.warning("配置校验未通过: %s", errs)
    from ai_assistant.agent_base import run_agent_warmup
    from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
    app.state.agent = create_agent_or_placeholder()
    timeout_s = getattr(settings, "vector_store_warmup_timeout_seconds", 45) or 45
    ok, err = run_agent_warmup(app.state.agent, timeout_seconds=timeout_s)
    if ok and err is None:
        logger.info("Agent 预热完成")
    elif err:
        logger.warning("Agent 预热: %s", err)
    yield
    agent = getattr(app.state, "agent", None)
    if agent is not None:
        scheduler = getattr(agent, "_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=True)
            except Exception as e:
                logger.warning("Scheduler 关闭异常: %s", e)


app = FastAPI(
    title="Assistant",
    description="统一对话助手，支持会议预定、查会议室、取消等；LangChain+LangGraph+RAG，LLM/Embeddings/向量库按配置切换（vllm、openai、dify、api、chroma、qdrant、weaviate）",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(v1_router)


def _response_headers(request_id: str):
    return {REQUEST_ID_HEADER: request_id} if request_id else None


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    code, status = app_exception_to_code_status(exc.code)
    return JSONResponse(
        status_code=status,
        content=response_body(code, exc.message, exc.details or None, request_id),
        headers=_response_headers(request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    logger.exception("unhandled exception request_id=%s: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content=response_body(CODE_INTERNAL_ERROR, "Internal server error", None, request_id),
        headers=_response_headers(request_id),
    )


_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/static/chat.html")


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
