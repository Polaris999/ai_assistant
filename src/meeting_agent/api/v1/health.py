"""健康与就绪探针。"""
from fastapi import APIRouter, Request

from meeting_agent import __version__
from meeting_agent.agent_base import is_agent_ready
from meeting_agent.api.response import success

router = APIRouter()


def _agent_ready(request: Request) -> str:
    """'ok' 可用，'placeholder' 占位未就绪。"""
    agent = getattr(request.app.state, "agent", None)
    return "ok" if is_agent_ready(agent) else "placeholder"


@router.get("/health", summary="健康检查")
async def health(request: Request):
    """统一 code/msg/data 格式；data 含 status、version、checks。"""
    agent_status = _agent_ready(request)
    request_id = getattr(request.state, "request_id", "") or ""
    return success(
        data={
            "status": "ok",
            "version": __version__,
            "checks": {"config": "ok", "agent": agent_status},
        },
        request_id=request_id,
    )
