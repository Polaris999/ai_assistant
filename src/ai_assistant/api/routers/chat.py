"""对话路由：只返回 success；出错由 Service 抛异常 + 全局处理器统一返回。"""
import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from ai_assistant.api.deps import get_agent, get_request_id
from ai_assistant.api.response import success
from ai_assistant.api.services.chat_service import ChatService
from ai_assistant.config import settings
from ai_assistant.core.exceptions import ValidationError
from ai_assistant.voice.stt import speech_to_text

logger = logging.getLogger(__name__)
router = APIRouter()


async def _handle_text(
    request: Request,
    text: str,
    conversation_id: Optional[str],
    agent: Any,
    request_id: str,
) -> dict[str, Any]:
    if len(text) > settings.api_chat_text_max_length:
        raise ValidationError(
            f"输入不得超过 {settings.api_chat_text_max_length} 个字符，当前 {len(text)} 字",
            details={"max_length": settings.api_chat_text_max_length, "actual_length": len(text)},
        )
    return await asyncio.to_thread(
        ChatService().handle_text,
        text.strip(),
        conversation_id,
        request_id,
        agent,
    )


async def _handle_voice(
    request: Request,
    audio: UploadFile,
    conversation_id: Optional[str],
    agent: Any,
    request_id: str,
) -> dict[str, Any]:
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
        raise ValidationError("语音识别失败，请重试或使用 POST /api/v1/chat 提交文本。", details={"cause": str(e)})
    if not user_input.strip():
        raise ValidationError("未识别到有效内容，请重试。")
    return await _handle_text(request, user_input.strip(), conversation_id, agent, request_id)


@router.post("/chat", summary="对话（文本）", description="统一对话入口：闲聊、订会、取消、查会议室等；支持多轮 conversation_id。")
async def chat_by_text(
    request: Request,
    text: str = Form(..., description="用户输入内容"),
    conversation_id: Optional[str] = Form(None, description="会话 id，不传则新建"),
    agent=Depends(get_agent),
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    result = await _handle_text(request, text, conversation_id, agent, request_id)
    return success(result, request_id)


@router.post("/chat/voice", summary="对话（语音）", description="语音输入，识别后按对话处理；支持多轮 conversation_id。")
async def chat_by_voice(
    request: Request,
    audio: UploadFile = File(..., description="音频文件"),
    conversation_id: Optional[str] = Form(None, description="会话 id，不传则新建"),
    agent=Depends(get_agent),
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    result = await _handle_voice(request, audio, conversation_id, agent, request_id)
    return success(result, request_id)
