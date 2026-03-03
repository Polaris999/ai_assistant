# config/prompt_loader.py
"""从配置或默认文件加载 Prompt 模板，支持按环境覆盖。"""
import logging
from pathlib import Path
from typing import Optional

from langchain_core.prompts import PromptTemplate

from meeting_agent.config import settings

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# 项目根目录（prompts -> config -> meeting_agent -> src -> 根）
_ROOT = _PROMPTS_DIR.parent.parent.parent.parent
_parse_intent_cache: Optional[PromptTemplate] = None
_reply_polish_cache: Optional[PromptTemplate] = None


def _load_template(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _resolve_path(path_conf: str) -> Path:
    p = Path(path_conf)
    return p if p.is_absolute() else _ROOT / path_conf


def get_parse_intent_template() -> PromptTemplate:
    """解析意图用 Prompt 模板：优先使用 PROMPT_PARSE_INTENT_PATH，否则使用包内默认。"""
    global _parse_intent_cache
    if _parse_intent_cache is not None:
        return _parse_intent_cache
    path_conf = getattr(settings, "prompt_parse_intent_path", "").strip()
    try:
        path = _resolve_path(path_conf) if path_conf else _PROMPTS_DIR / "parse_intent.txt"
        if path_conf and not path.exists():
            logger.warning("自定义 parse_intent 路径不存在 %s，使用默认", path)
            path = _PROMPTS_DIR / "parse_intent.txt"
        content = _load_template(path)
    except Exception as e:
        logger.warning("加载 parse_intent 模板失败，使用默认: %s", e)
        content = _load_template(_PROMPTS_DIR / "parse_intent.txt")
    _parse_intent_cache = PromptTemplate.from_template(content)
    return _parse_intent_cache


def get_reply_polish_template() -> PromptTemplate:
    """回复润色用 Prompt 模板：优先使用 PROMPT_REPLY_POLISH_PATH，否则使用包内默认。"""
    global _reply_polish_cache
    if _reply_polish_cache is not None:
        return _reply_polish_cache
    path_conf = getattr(settings, "prompt_reply_polish_path", "").strip()
    try:
        path = _resolve_path(path_conf) if path_conf else _PROMPTS_DIR / "reply_polish.txt"
        if path_conf and not path.exists():
            logger.warning("自定义 reply_polish 路径不存在 %s，使用默认", path)
            path = _PROMPTS_DIR / "reply_polish.txt"
        content = _load_template(path)
    except Exception as e:
        logger.warning("加载 reply_polish 模板失败，使用默认: %s", e)
        content = _load_template(_PROMPTS_DIR / "reply_polish.txt")
    _reply_polish_cache = PromptTemplate.from_template(content)
    return _reply_polish_cache
