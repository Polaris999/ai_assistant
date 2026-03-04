"""API 路由按 controller 聚合：对话、健康、知识库，统一前缀 /api。"""
from fastapi import APIRouter

from ai_assistant.api.controllers import chat, health, knowledge

router = APIRouter(prefix="/api")
router.include_router(chat.router, tags=["对话"])
router.include_router(health.router, tags=["健康检查"])
router.include_router(knowledge.router, tags=["知识库"])
