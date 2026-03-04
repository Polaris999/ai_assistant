"""会议预定 API：文本/语音提交，返回 JSON。"""
import logging
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from meeting_agent.api.deps import get_agent
from meeting_agent.api.response import (
    CODE_BUSINESS_ERROR,
    CODE_SERVICE_UNAVAILABLE,
    CODE_SUCCESS,
    json_response,
)
from meeting_agent.config import settings
from meeting_agent.core.exceptions import ValidationError
from meeting_agent.voice.stt import speech_to_text

logger = logging.getLogger(__name__)
router = APIRouter()

AGENT_ERROR_CODES_503 = {"RUNTIME_ERROR", "CONFIG_ERROR"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def _booking_to_json_serializable(booking: Optional[Any]) -> Any:
    """MeetingBooking -> JSON 可序列化 dict；None 返回 None。"""
    if booking is None:
        return None
    if hasattr(booking, "model_dump"):
        return booking.model_dump(mode="json")
    if hasattr(booking, "dict"):
        return {
            k: v.isoformat() if isinstance(v, datetime) else v
            for k, v in booking.dict().items()
        }
    return booking


def _book_response(request: Request, result: dict[str, Any]) -> JSONResponse:
    """统一 code/msg/data：msg 仅描述 code，业务结果（reply、booking）一律放在 data。"""
    reply = result.get("reply", "处理失败")
    booking = result.get("booking")
    error = result.get("error")
    req_id = _request_id(request)
    data_payload: dict[str, Any] = {"reply": reply, "booking": _booking_to_json_serializable(booking)}
    if error is not None:
        data_payload["error"] = error

    if error and error in AGENT_ERROR_CODES_503:
        return json_response(
            CODE_SERVICE_UNAVAILABLE,
            "服务暂不可用",
            data_payload,
            req_id,
            status_code=503,
        )
    if booking is not None:
        return json_response(
            CODE_SUCCESS,
            "success",
            data_payload,
            req_id,
        )
    return json_response(
        CODE_BUSINESS_ERROR,
        "success",
        data_payload,
        req_id,
    )


@router.post("/book", summary="文本预定会议")
async def book_by_text(
    request: Request,
    text: str = Form(..., description="会议描述"),
    agent=Depends(get_agent),
) -> JSONResponse:
    if len(text) > settings.api_book_text_max_length:
        raise ValidationError(
            f"会议描述不得超过 {settings.api_book_text_max_length} 个字符，当前 {len(text)} 字",
            details={"max_length": settings.api_book_text_max_length, "actual_length": len(text)},
        )
    req_id = _request_id(request)
    t0 = time.perf_counter()
    result = agent.invoke(text.strip(), request_id=req_id)
    logger.info("book req_id=%s text_len=%s elapsed_ms=%.0f", req_id, len(text), (time.perf_counter() - t0) * 1000)
    return _book_response(request, result)


@router.post("/book/voice", summary="语音预定会议")
async def book_by_voice(
    request: Request,
    audio: UploadFile = File(..., description="音频文件"),
    agent=Depends(get_agent),
) -> JSONResponse:
    content = await audio.read()
    if len(content) > settings.api_voice_max_bytes:
        raise ValidationError(
            f"音频文件不得超过 {settings.api_voice_max_bytes // (1024 * 1024)}MB，当前约 {len(content) // (1024 * 1024)}MB",
            details={"max_bytes": settings.api_voice_max_bytes, "actual_bytes": len(content)},
        )
    try:
        user_input = speech_to_text(content, use_whisper=True)
    except Exception as e:
        logger.exception("语音识别失败: %s", e)
        raise ValidationError("语音识别失败，请重试或使用 POST /api/v1/book 提交文本。", details={"cause": str(e)})
    if not user_input.strip():
        raise ValidationError("未识别到有效内容，请重试。")
    req_id = _request_id(request)
    t0 = time.perf_counter()
    result = agent.invoke(user_input.strip(), request_id=req_id)
    logger.info("book/voice req_id=%s elapsed_ms=%.0f", req_id, (time.perf_counter() - t0) * 1000)
    return _book_response(request, result)
