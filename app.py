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

from meeting_agent import __version__
from meeting_agent.api.deps import get_agent
from meeting_agent.api.middleware import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from meeting_agent.api.v1 import router as v1_router
from meeting_agent.config import settings
from meeting_agent.core.exceptions import AppException

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """可观测、配置校验（仅打日志）、创建 Agent；失败则占位。"""
    if getattr(settings, "langchain_tracing_enabled", False):
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if getattr(settings, "langchain_project", ""):
            os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("LangSmith 追踪已开启，项目名: %s", getattr(settings, "langchain_project", "meeting-agent"))
    from meeting_agent.config.validation import validate_settings
    errs = validate_settings()
    if errs:
        logger.warning("配置校验未通过: %s", errs)
    from meeting_agent.api.agent_bootstrap import create_agent_or_placeholder
    app.state.agent = create_agent_or_placeholder()
    yield
    agent = getattr(app.state, "agent", None)
    if agent is not None:
        scheduler = getattr(agent, "_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=True)
                logger.info("ReminderScheduler 已关闭")
            except Exception as e:
                logger.exception("Scheduler 关闭异常: %s", e)


app = FastAPI(
    title="会议预定 Agent",
    description="LangChain+LangGraph+RAG，LLM/Embeddings/向量库按配置切换（vllm、openai、dify、api、chroma、qdrant、weaviate）",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(v1_router)


def _error_body(exc: AppException, request_id: str = "") -> dict:
    body = exc.to_dict()
    if request_id:
        body["request_id"] = request_id
    return body


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    status = 422 if exc.code == "VALIDATION_ERROR" else 400
    if exc.code == "NOT_FOUND":
        status = 404
    return JSONResponse(
        status_code=status,
        content=_error_body(exc, request_id),
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    logger.exception("unhandled exception request_id=%s: %s", request_id, exc)
    body = {
        "code": "INTERNAL_ERROR",
        "message": "Internal server error",
        "details": {},
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(
        status_code=500,
        content=body,
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
    )


_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/static/book_example.html")


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
