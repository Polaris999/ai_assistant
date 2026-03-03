"""语音转文字：Whisper API / 本地 faster-whisper / Google SR。"""
import io
import logging
from pathlib import Path
from typing import Union

from meeting_agent.config import settings

logger = logging.getLogger(__name__)


def speech_to_text(
    audio_source: Union[str, Path, bytes],
    use_whisper: bool = True,
) -> str:
    """将音频文件或字节转为文本。优先：Whisper API（有 key）→ 本地 faster-whisper → Google SR。"""
    if use_whisper:
        if settings.openai_api_key:
            return _whisper_openai(audio_source)
        text = _whisper_local(audio_source)
        if text is not None:
            return text
    return _local_sr_transcribe(audio_source)


def _whisper_openai(audio_source: Union[str, Path, bytes]) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("未安装 openai，回退到本地识别")
        return _local_sr_transcribe(audio_source)

    client = OpenAI(api_key=settings.openai_api_key)
    if isinstance(audio_source, (str, Path)):
        path = Path(audio_source)
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")
        with open(path, "rb") as f:
            response = client.audio.transcriptions.create(model="whisper-1", file=f)
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            tmp.write(audio_source)
            tmp.flush()
            with open(tmp.name, "rb") as f:
                response = client.audio.transcriptions.create(model="whisper-1", file=f)
    return (response.text or "").strip()


def _whisper_local(audio_source: Union[str, Path, bytes]) -> str | None:
    """本地 Whisper（faster-whisper）；未安装时返回 None。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None

    model = WhisperModel(getattr(settings, "local_whisper_model", "base"), device="cpu", compute_type="int8")
    if isinstance(audio_source, bytes):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            tmp.write(audio_source)
            tmp.flush()
            segments, _ = model.transcribe(tmp.name, language="zh")
    else:
        path = Path(audio_source)
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")
        segments, _ = model.transcribe(str(path), language="zh")
    text = " ".join(s.text for s in segments).strip()
    return text or None


def _local_sr_transcribe(audio_source: Union[str, Path, bytes]) -> str:
    import speech_recognition as sr
    r = sr.Recognizer()
    if isinstance(audio_source, bytes):
        with sr.AudioFile(io.BytesIO(audio_source)) as source:
            audio = r.record(source)
    else:
        path = Path(audio_source)
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")
        with sr.AudioFile(str(path)) as source:
            audio = r.record(source)
    try:
        return r.recognize_google(audio, language="zh-CN")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        logger.warning("SpeechRecognition 请求失败: %s", e)
        return ""
