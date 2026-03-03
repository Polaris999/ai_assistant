# config/settings.py
"""应用配置，支持 .env 与环境变量。"""
from pathlib import Path

# 项目根目录（src/meeting_agent/config -> 根）
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", encoding="utf-8")
except Exception:
    pass

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM/Embeddings/向量库按 type 切换，见字段注释。"""
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
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

    # --- 向量库（vector_store_type: chroma | qdrant | weaviate）---
    vector_store_type: str = "chroma"
    chroma_persist_dir: str = "./data/chroma_db"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""
    weaviate_text_key: str = "content"

    # --- API 限制 ---
    api_book_text_max_length: int = 2000  # 文本预定会议描述最大字符数
    api_voice_max_bytes: int = 10 * 1024 * 1024  # 语音上传最大字节数（默认 10MB）

    # --- 其他 ---
    local_whisper_model: str = "base"  # 语音转文字本地模型（faster-whisper）
    default_remind_minutes: int = 15
    log_level: str = "INFO"
    prompt_parse_intent_path: str = ""  # 空=包内默认
    prompt_reply_polish_path: str = ""
    langchain_tracing_enabled: bool = False
    langchain_project: str = "meeting-agent"

    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


settings = Settings()
