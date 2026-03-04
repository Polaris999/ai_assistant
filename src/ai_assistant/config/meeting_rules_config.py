"""会议预约业务配置，与系统配置（settings）分离，便于按业务/环境单独维护。"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PROFILE = (os.environ.get("APP_PROFILE") or os.environ.get("ENV") or "dev").strip().lower()
if _PROFILE not in ("dev", "test", "prod"):
    _PROFILE = "dev"
_env_profile = _ROOT / f".env.{_PROFILE}"
_env_common = _ROOT / ".env"
_env_files = [str(_env_profile), str(_env_common)]


class MeetingRulesConfig(BaseSettings):
    """仅会议预约规则相关，环境变量 MEETING_*。"""
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )
    meeting_max_days_ahead: int = 7
    meeting_max_duration_minutes: int = 240
    meeting_rules_api_url: str = ""
    meeting_rules_cache_seconds: int = 300


meeting_rules_config = MeetingRulesConfig()
