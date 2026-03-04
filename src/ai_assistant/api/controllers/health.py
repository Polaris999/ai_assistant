"""健康与就绪探针。"""
from fastapi import APIRouter, Request

from ai_assistant import __version__
from ai_assistant.agent.protocol import is_agent_ready
from ai_assistant.api.response import success

router = APIRouter()


def _agent_ready(request: Request) -> str:
    agent = getattr(request.app.state, "agent", None)
    return "ok" if is_agent_ready(agent) else "placeholder"


@router.get("/health", summary="健康检查")
async def health(request: Request):
    agent_status = _agent_ready(request)
    request_id = getattr(request.state, "request_id", "") or ""
    return success(
        data={"status": "ok", "version": __version__, "checks": {"config": "ok", "agent": agent_status}},
        request_id=request_id,
    )
