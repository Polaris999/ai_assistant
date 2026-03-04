"""对话 API：统一入口，支持闲聊、订会、取消、查会议室等；文本/语音；多轮会话。"""
import logging
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ai_assistant.api.deps import get_agent
from ai_assistant.core.conversation import get_conversation_store
from ai_assistant.api.response import (
    CODE_BUSINESS_ERROR,
    CODE_SERVICE_UNAVAILABLE,
    CODE_SUCCESS,
    json_response,
)
from ai_assistant.config import settings
from ai_assistant.core.exceptions import ValidationError
from ai_assistant.voice.stt import speech_to_text

logger = logging.getLogger(__name__)
router = APIRouter()

AGENT_ERROR_CODES_503 = {"RUNTIME_ERROR", "CONFIG_ERROR"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def _booking_to_json_serializable(booking: Optional[Any]) -> Any:
    if booking is None:
        return None
    if hasattr(booking, "model_dump"):
        return booking.model_dump(mode="json")
    if hasattr(booking, "dict"):
        return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in booking.dict().items()}
    return booking


def _chat_response(request: Request, result: dict[str, Any], conversation_id: Optional[str] = None) -> JSONResponse:
    reply = result.get("reply", "处理失败")
    booking = result.get("booking")
    error = result.get("error")
    req_id = _request_id(request)
    data_payload: dict[str, Any] = {"reply": reply, "booking": _booking_to_json_serializable(booking)}
    if error is not None:
        data_payload["error"] = error
    if conversation_id:
        data_payload["conversation_id"] = conversation_id
    if error and error in AGENT_ERROR_CODES_503:
        return json_response(CODE_SERVICE_UNAVAILABLE, "服务暂不可用", data_payload, req_id, status_code=503)
    # 无错误即视为成功（查会议室、闲聊、订会成功等均 code 0；有 error 时为业务错误 code 1）
    if error is None:
        return json_response(CODE_SUCCESS, "success", data_payload, req_id)
    return json_response(CODE_BUSINESS_ERROR, "success", data_payload, req_id)


async def _handle_text(request: Request, text: str, conversation_id: Optional[str], agent: Any) -> JSONResponse:
    if len(text) > settings.api_chat_text_max_length:
        raise ValidationError(
            f"输入不得超过 {settings.api_chat_text_max_length} 个字符，当前 {len(text)} 字",
            details={"max_length": settings.api_chat_text_max_length, "actual_length": len(text)},
        )
    req_id = _request_id(request)
    store = get_conversation_store()
    cid = store.get_or_create_id(conversation_id)
    history = store.get_recent(cid)
    t0 = time.perf_counter()
    result = agent.invoke(text.strip(), request_id=req_id, conversation_id=cid, history=history)
    elapsed = (time.perf_counter() - t0) * 1000
    store.append(cid, "user", text)
    store.append(cid, "assistant", result.get("reply") or "")
    if result.get("booking") and result["booking"].get("id"):
        store.set_last_booking_id(cid, result["booking"]["id"])
    logger.info("chat req_id=%s cid=%s text_len=%s elapsed_ms=%.0f", req_id, cid[:8], len(text), elapsed)
    return _chat_response(request, result, conversation_id=cid)


async def _handle_voice(request: Request, audio: UploadFile, conversation_id: Optional[str], agent: Any) -> JSONResponse:
    content = await audio.read()
    if len(content) > settings.api_voice_max_bytes:
        raise ValidationError(
            f"音频文件不得超过 {settings.api_voice_max_bytes // (1024 * 1024)}MB",
            details={"max_bytes": settings.api_voice_max_bytes, "actual_bytes": len(content)},
        )
    try:
        user_input = speech_to_text(content, use_whisper=True)
    except Exception as e:
        logger.exception("语音识别失败: %s", e)
        raise ValidationError("语音识别失败，请重试或使用 POST /api/chat 提交文本。", details={"cause": str(e)})
    if not user_input.strip():
        raise ValidationError("未识别到有效内容，请重试。")
    return await _handle_text(request, user_input.strip(), conversation_id, agent)


@router.post("/chat", summary="对话（文本）", description="统一对话入口：闲聊、订会、取消、查会议室等；支持多轮 conversation_id。")
async def chat_by_text(
    request: Request,
    text: str = Form(..., description="用户输入内容"),
    conversation_id: Optional[str] = Form(None, description="会话 id，不传则新建"),
    agent=Depends(get_agent),
) -> JSONResponse:
    return await _handle_text(request, text, conversation_id, agent)


@router.post("/chat/voice", summary="对话（语音）", description="语音输入，识别后按对话处理；支持多轮 conversation_id。")
async def chat_by_voice(
    request: Request,
    audio: UploadFile = File(..., description="音频文件"),
    conversation_id: Optional[str] = Form(None, description="会话 id，不传则新建"),
    agent=Depends(get_agent),
) -> JSONResponse:
    return await _handle_voice(request, audio, conversation_id, agent)
