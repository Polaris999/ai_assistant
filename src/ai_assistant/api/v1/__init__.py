"""v1 路由聚合：/api/v1/chat、/api/v1/chat/voice、/api/v1/health。"""
from fastapi import APIRouter

from ai_assistant.api.v1 import chat, health

router = APIRouter(prefix="/api/v1", tags=["v1"])
router.include_router(chat.router)
router.include_router(health.router)
