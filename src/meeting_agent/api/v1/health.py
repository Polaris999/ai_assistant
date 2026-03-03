"""健康与版本探针，供负载均衡/就绪检查。"""
from fastapi import APIRouter

from meeting_agent import __version__

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health() -> dict:
    """存活探针：返回状态与版本，可用于负载均衡/就绪判断。"""
    return {
        "status": "ok",
        "version": __version__,
        "checks": {"config": "ok"},
    }
