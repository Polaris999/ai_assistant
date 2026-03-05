"""应用配置，按 profile 加载 .env 与环境变量。"""
import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PROFILE = (os.environ.get("APP_PROFILE") or os.environ.get("ENV") or "dev").strip().lower()
if _PROFILE not in ("dev", "test", "prod"):
    _PROFILE = "dev"
_env_profile = _ROOT / f".env.{_PROFILE}"
_env_common = _ROOT / ".env"
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
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM（llm_type: vllm | openai | dify）---
    llm_type: str = "vllm"
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

    # --- API 限制与生产 ---
    api_chat_text_max_length: int = 2000  # 对话输入最大字符数
    api_voice_max_bytes: int = 10 * 1024 * 1024  # 语音上传最大字节数（默认 10MB）
    docs_enabled: bool = True  # 生产可设 DOCS_ENABLED=false 关闭 /docs、/redoc
    cors_origins: str = ""  # 逗号分隔的允许来源，空=不启用 CORS（由网关处理时可不设）

    # --- 其他 ---
    local_whisper_model: str = "base"  # 语音转文字本地模型（faster-whisper）
    log_level: str = "INFO"
    llm_request_timeout_seconds: int = 120  # LLM 单次调用超时（秒），超时后抛出 LLM_ERROR
    conversation_history_max_chars: int = 0  # 拼入 prompt 的会话历史最大字符数，0=不限制
    langchain_tracing_enabled: bool = False
    langchain_project: str = "ai-assistant"
    # 技能启用列表：逗号分隔的 skill_id（与 skill_docs 子目录名一致），空=按 skill_docs 发现全部
    enabled_skills: str = ""
    # 是否仅将技能目录注入 system prompt（渐进式披露）：True=仅 name+description，通过 load_skill 按需加载全文；False=注入全部技能全文
    use_skill_catalog_only: bool = False
    # 技能 HTTP 执行超时（秒），GenericSkill 调用 executor.url 时使用
    skill_http_timeout_seconds: int = 30
    # LangGraph ReAct 最大递归步数（防止工具反复失败导致同一请求内多次 tool 循环）
    agent_recursion_limit: int = 8
    # 会议预约规则：最多提前天数（技能校验与回退文案用）
    meeting_max_days_ahead: int = 7
    # Agent 固定为 LangGraph（create_react_agent + 技能 Tool），无其他类型切换

    # --- 会话存储（内存 | Redis）---
    # 若需用 Redis 存会话历史，配置 REDIS_HOST（或 REDIS_URL）；未配置则使用进程内内存
    redis_host: str = ""
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_url: str = ""  # 可选：直接写 redis://[:password@]host:port/db，优先于 host/port/password
    conversation_store_ttl_seconds: int = 86400  # Redis 会话 key 过期时间（秒），默认 24 小时
    conversation_max_messages: int = 20  # 每会话保留最近消息条数（user+assistant 合计），供多轮上下文

    def get_redis_url(self) -> str:
        """用于会话存储的 Redis 连接 URL；空串表示未配置，使用内存存储。"""
        if (self.redis_url or "").strip():
            return self.redis_url.strip()
        if not (self.redis_host or "").strip():
            return ""
        host = self.redis_host.strip()
        port = self.redis_port
        db = self.redis_db
        password = (self.redis_password or "").strip()
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        return f"redis://{host}:{port}/{db}"

    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


def get_profile() -> str:
    """当前配置 profile（dev/test/prod），由 APP_PROFILE 或 ENV 决定。"""
    return _PROFILE


settings = Settings()
