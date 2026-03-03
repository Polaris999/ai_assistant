"""会议预定 API：文本提交与语音上传（转写后预定）。"""
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse

from meeting_agent.api.deps import get_agent
from meeting_agent.voice.stt import speech_to_text

logger = logging.getLogger(__name__)
router = APIRouter()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


@router.post(
    "/book",
    response_class=PlainTextResponse,
    summary="文本预定会议",
    description="提交会议描述（如：明天下午3点开项目会，1小时），返回预定结果文案。",
)
async def book_by_text(
    request: Request,
    text: str = Form(..., description="会议描述"),
    agent=Depends(get_agent),
) -> str:
    result = agent.invoke(text, request_id=_request_id(request))
    return result.get("reply", "处理失败")


@router.post(
    "/book/voice",
    response_class=PlainTextResponse,
    summary="语音预定会议",
    description="上传音频文件，先转写再预定会议。",
)
async def book_by_voice(
    request: Request,
    audio: UploadFile = File(..., description="音频文件"),
    agent=Depends(get_agent),
) -> str:
    content = await audio.read()
    try:
        user_input = speech_to_text(content, use_whisper=True)
    except Exception as e:
        logger.exception("语音识别失败: %s", e)
        return "语音识别失败，请重试或使用 POST /api/v1/book 提交文本。"
    if not user_input.strip():
        return "未识别到有效内容，请重试。"
    result = agent.invoke(user_input, request_id=_request_id(request))
    return result.get("reply", "处理失败")
