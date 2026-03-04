# config/settings.py
"""应用配置，支持按 profile 加载 .env 与环境变量。"""
import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

# 项目根目录（src/ai_assistant/config -> 根）
_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Profile：由环境变量 APP_PROFILE 或 ENV 指定，未设时默认 dev（先读环境变量，不依赖 .env）
_PROFILE = (os.environ.get("APP_PROFILE") or os.environ.get("ENV") or "dev").strip().lower()
if _PROFILE not in ("dev", "test", "prod"):
    _PROFILE = "dev"

_env_profile = _ROOT / f".env.{_PROFILE}"
_env_common = _ROOT / ".env"
# 先 profile 再 .env，后者覆盖；不存在的文件 pydantic 会忽略
_env_files = [str(_env_profile), str(_env_common)]

try:
    from dotenv import load_dotenv
    if _env_profile.exists():
        load_dotenv(_env_profile, encoding="utf-8")
    if _env_common.exists():
        load_dotenv(_env_common, encoding="utf-8")
except Exception as e:
    _logger.warning("加载 .env 失败（将仅用环境变量）: %s", e)

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM/Embeddings/向量库按 type 切换，见字段注释。"""
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM（llm_type: vllm | openai | dify）---
    llm_type: str = "vllm"
    reply_llm_type: str = ""  # 空=不润色；可填 vllm/openai/dify 用另一套 LLM
    # vLLM（llm_type=vllm 时必填 VLLM_BASE_URL）
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_chat_model: str = ""
    vllm_api_key: str = ""
    vllm_timeout: int = 120
    # OpenAI（llm_type=openai 时必填 OPENAI_API_KEY）
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    # Dify（llm_type=dify 时必填 DIFY_API_KEY）
    dify_api_key: str = ""
    dify_base_url: str = "https://api.dify.ai/v1"
    dify_chat_app_type: str = "chat-messages"

    # --- Embeddings（embedding_type: openai | api，单独 embedding 服务）---
    embedding_type: str = "api"
    # openai：用 OPENAI_*；单独向量端点填 openai_embedding_base_url（空则用 openai_base_url）
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_base_url: str = ""
    # api：自建服务，必填 EMBEDDING_BASE_URL（OpenAI 兼容 /v1/embeddings）
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_request_timeout: int = 60  # Embedding 请求超时（秒），避免远程不可达时无限挂起

    # --- 向量库（vector_store_type: chroma | qdrant | weaviate）---
    vector_store_type: str = "chroma"
    chroma_persist_dir: str = "./data/chroma_db"  # 相对路径时相对于进程 CWD，生产建议用绝对路径
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""
    weaviate_text_key: str = "content"
    vector_store_warmup_timeout_seconds: int = 45  # 启动时向量库预热超时（秒），超时则首请求按需连接

    # --- API 限制 ---
    api_chat_text_max_length: int = 2000  # 对话输入最大字符数
    api_voice_max_bytes: int = 10 * 1024 * 1024  # 语音上传最大字节数（默认 10MB）

    # --- 其他 ---
    local_whisper_model: str = "base"  # 语音转文字本地模型（faster-whisper）
    default_remind_minutes: int = 15
    log_level: str = "INFO"
    prompt_parse_intent_path: str = ""  # 空=包内默认
    prompt_reply_polish_path: str = ""
    langchain_tracing_enabled: bool = False
    langchain_project: str = "ai-assistant"
    use_tool_agent: bool = True  # True=Agent+Tools 调用 IMeetingService；False=原 LangGraph 图

    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


def get_profile() -> str:
    """当前配置 profile（dev/test/prod），由 APP_PROFILE 或 ENV 决定。"""
    return _PROFILE


settings = Settings()
