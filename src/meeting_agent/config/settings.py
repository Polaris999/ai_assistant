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
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_type: str = "vllm"
    reply_llm_type: str = ""
    embedding_type: str = "local"
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    # 本地 Whisper 模型（语音转文字私有化时使用，需安装 faster-whisper）
    local_whisper_model: str = "base"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_base_url: str = ""

    # 自建 Embedding 服务（embedding_type=api 时使用，无需 OPENAI_*）
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""

    # vLLM
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_chat_model: str = ""
    vllm_api_key: str = ""
    vllm_timeout: int = 120

    dify_api_key: str = ""
    dify_base_url: str = "https://api.dify.ai/v1"
    dify_chat_app_type: str = "chat-messages"

    # 向量库: chroma | qdrant | weaviate
    vector_store_type: str = "chroma"
    chroma_persist_dir: str = "./data/chroma_db"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""
    weaviate_text_key: str = "content"  # Weaviate 中存文本的字段名
    default_remind_minutes: int = 15
    log_level: str = "INFO"

    # Prompt 模板：空则使用包内默认；否则为绝对路径或相对项目根的路径
    prompt_parse_intent_path: str = ""
    prompt_reply_polish_path: str = ""

    # 可观测：LangSmith 由 LANGCHAIN_API_KEY 控制，此处仅开关与项目名
    langchain_tracing_enabled: bool = False
    langchain_project: str = "meeting-agent"

    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


settings = Settings()
