"""健康与就绪探针。"""
from fastapi import APIRouter, Depends

from ai_assistant import __version__
from ai_assistant.agent.protocol import is_agent_ready
from ai_assistant.api.deps import get_agent, get_request_id
from ai_assistant.api.response import success

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health(
    agent=Depends(get_agent),
    request_id: str = Depends(get_request_id),
):
    agent_status = "ok" if is_agent_ready(agent) else "placeholder"
    return success(
        data={"status": "ok", "version": __version__, "checks": {"config": "ok", "agent": agent_status}},
        request_id=request_id,
    )
