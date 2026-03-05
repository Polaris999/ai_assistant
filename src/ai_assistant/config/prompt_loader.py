# config/prompt_loader.py
"""Prompt 模板加载：从 config/prompts 或配置路径读取，进程内缓存。主 Agent 为 LangGraph，此处供可选 system 文案拼接（如 get_tools_schema_for_prompt）。"""
import logging
from pathlib import Path
from typing import Optional

from ai_assistant.config import settings

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_ROOT = _PROMPTS_DIR.parent.parent.parent.parent
_prompt_tools_intro_cache: Optional[str] = None


def _load_template(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _resolve_path(path_conf: str) -> Path:
    p = Path(path_conf)
    return p if p.is_absolute() else _ROOT / path_conf


def get_prompt_tools_intro() -> str:
    """可选工具说明头（用于 get_tools_schema_for_prompt 拼 system 文案）。默认包内 tool_agent_tools_intro.txt，进程内缓存。"""
    global _prompt_tools_intro_cache
    if _prompt_tools_intro_cache is not None:
        return _prompt_tools_intro_cache
    try:
        content = _load_template(_PROMPTS_DIR / "tool_agent_tools_intro.txt")
    except Exception as e:
        logger.warning("加载 tool_agent_tools_intro 失败，使用默认: %s", e)
        content = (
            "你只能输出一个 JSON 对象，且仅此 JSON；不要 <think>、不要 markdown、不要多余文字。"
            "根据用户意图选择 exactly 一个 tool，并填写 arguments。\n"
        )
    _prompt_tools_intro_cache = content
    return _prompt_tools_intro_cache
