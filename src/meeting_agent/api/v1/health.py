from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health() -> dict:
    return {"status": "ok"}
