#!/usr/bin/env python3
"""FastAPI 入口。"""
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from meeting_agent.api.v1 import router as v1_router
from meeting_agent.config import settings
from meeting_agent.core.exceptions import AppException

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="会议预定 Agent",
    description="LangChain+LangGraph+Dify+RAG，模型胶水层支持 OpenAI/Dify 等",
    version="1.0.0",
)


@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    status = 422 if exc.code == "VALIDATION_ERROR" else 400
    if exc.code == "NOT_FOUND":
        status = 404
    return JSONResponse(status_code=status, content=exc.to_dict())


app.include_router(v1_router)

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/static/book_example.html")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
