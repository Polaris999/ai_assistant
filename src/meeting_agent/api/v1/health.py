"""健康与就绪探针。"""
from fastapi import APIRouter, Request

from meeting_agent import __version__

router = APIRouter()


def _agent_ready(request: Request) -> str:
    """'ok' 可用，'placeholder' 占位未就绪。"""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        return "placeholder"
    if getattr(agent, "_scheduler", None) is not None:
        return "ok"
    return "placeholder"


@router.get("/health", summary="健康检查")
async def health(request: Request) -> dict:
    agent_status = _agent_ready(request)
    return {
        "status": "ok",
        "version": __version__,
        "checks": {
            "config": "ok",
            "agent": agent_status,
        },
    }
