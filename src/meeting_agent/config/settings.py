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

    llm_type: str = "openai"
    reply_llm_type: str = ""
    embedding_type: str = "openai"

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    dify_api_key: str = ""
    dify_base_url: str = "https://api.dify.ai/v1"
    dify_chat_app_type: str = "chat-messages"

    chroma_persist_dir: str = "./data/chroma_db"
    default_remind_minutes: int = 15
    log_level: str = "INFO"

    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


settings = Settings()
