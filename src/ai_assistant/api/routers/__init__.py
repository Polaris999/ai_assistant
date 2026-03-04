"""按领域拆分的 API 路由，统一前缀 /api/v1。"""
from fastapi import APIRouter

from ai_assistant.api.routers import chat, health, knowledge

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(chat.router, tags=["对话"])
api_v1_router.include_router(health.router, tags=["健康检查"])
api_v1_router.include_router(knowledge.router, tags=["知识库"])

__all__ = ["api_v1_router"]
