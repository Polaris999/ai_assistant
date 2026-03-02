from fastapi import APIRouter

from meeting_agent.api.v1 import book, health

router = APIRouter(prefix="/api/v1", tags=["v1"])
router.include_router(book.router)
router.include_router(health.router)
