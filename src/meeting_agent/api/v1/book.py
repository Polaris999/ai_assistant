"""会议预定 API：文本/语音提交，返回 JSON。"""
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from meeting_agent.api.deps import get_agent
from meeting_agent.config import settings
from meeting_agent.core.exceptions import ValidationError
from meeting_agent.voice.stt import speech_to_text

logger = logging.getLogger(__name__)
router = APIRouter()

AGENT_ERROR_CODES_503 = {"RUNTIME_ERROR", "CONFIG_ERROR"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def _book_response(request: Request, result: dict) -> JSONResponse:
    reply = result.get("reply", "处理失败")
    booking = result.get("booking")
    error = result.get("error")
    body = {
        "reply": reply,
        "booking": booking,
        "error": error,
        "request_id": _request_id(request),
    }
    if error and error in AGENT_ERROR_CODES_503:
        return JSONResponse(content=body, status_code=503)
    return JSONResponse(content=body, status_code=200)


@router.post("/book", summary="文本预定会议")
async def book_by_text(
    request: Request,
    text: str = Form(..., description="会议描述"),
    agent=Depends(get_agent),
) -> JSONResponse:
    max_len = getattr(settings, "api_book_text_max_length", 2000)
    if len(text) > max_len:
        raise ValidationError(
            f"会议描述不得超过 {max_len} 个字符，当前 {len(text)} 字",
            details={"max_length": max_len, "actual_length": len(text)},
        )
    result = agent.invoke(text.strip(), request_id=_request_id(request))
    return _book_response(request, result)


@router.post("/book/voice", summary="语音预定会议")
async def book_by_voice(
    request: Request,
    audio: UploadFile = File(..., description="音频文件"),
    agent=Depends(get_agent),
) -> JSONResponse:
    content = await audio.read()
    max_bytes = getattr(settings, "api_voice_max_bytes", 10 * 1024 * 1024)
    if len(content) > max_bytes:
        raise ValidationError(
            f"音频文件不得超过 {max_bytes // (1024 * 1024)}MB，当前约 {len(content) // (1024 * 1024)}MB",
            details={"max_bytes": max_bytes, "actual_bytes": len(content)},
        )
    try:
        user_input = speech_to_text(content, use_whisper=True)
    except Exception as e:
        logger.exception("语音识别失败: %s", e)
        raise ValidationError("语音识别失败，请重试或使用 POST /api/v1/book 提交文本。", details={"cause": str(e)})
    if not user_input.strip():
        raise ValidationError("未识别到有效内容，请重试。")
    result = agent.invoke(user_input.strip(), request_id=_request_id(request))
    return _book_response(request, result)
