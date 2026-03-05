"""
Skill Creator：脚手架生成 skill_docs/<id>/SKILL.md，对齐 [Anthropic skills](https://github.com/anthropics/skills) / [LangChain agent skills](https://github.com/Lubu-Labs/langchain-agent-skills) 的 skill-creator 用法。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from ai_assistant.config.skill_loader import SKILL_DOCS_DIR

logger = logging.getLogger(__name__)

# 合法 skill_id：小写字母、数字、连字符、下划线
SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _template_content(
    skill_id: str,
    name: str,
    description: str,
    http_url: Optional[str] = None,
) -> str:
    front = f"""---
name: {name}
description: {description}
"""
    if http_url and http_url.strip():
        front += f"""executor:
  type: http
  url: "{http_url.strip()}"
"""
    front += "---\n\n"
    body = f"""# {name}

请在此填写本技能的说明，供 LLM 判断何时选用与如何填参。与 [Anthropic Agent Skills](https://github.com/anthropics/skills) 规范一致。

## When to use this skill

- 用户意图 1
- 用户意图 2

## How to use this skill

1. 步骤一
2. 步骤二

## Guidelines

- 约束或注意点

## Keywords

触发本技能的关键词（逗号或换行）
"""
    return front + body


def create_skill(
    skill_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    http_url: Optional[str] = None,
    skill_docs_root: Optional[Path] = None,
    overwrite: bool = False,
) -> Path:
    """
    在 skill_docs 下创建新技能目录及 SKILL.md 模板。

    :param skill_id: 技能 ID，与目录名一致（小写字母、数字、连字符、下划线）。
    :param name: 显示名称，默认用 skill_id。
    :param description: 简短描述，默认占位文案。
    :param http_url: 若提供，在 frontmatter 中写入 executor.url，可作为无代码 HTTP 技能使用。
    :param skill_docs_root: 技能文档根目录，默认使用项目 skill_docs。
    :param overwrite: 若为 True 且 SKILL.md 已存在则覆盖；否则不覆盖。
    :return: 生成的 SKILL.md 路径。
    :raises ValueError: skill_id 格式不合法或目录已存在且未指定 overwrite。
    """
    skill_id = (skill_id or "").strip().lower()
    if not skill_id:
        raise ValueError("skill_id 不能为空")
    if not SKILL_ID_PATTERN.match(skill_id):
        raise ValueError(
            "skill_id 仅允许小写字母、数字、连字符、下划线，且不能以连字符/下划线开头"
        )
    root = Path(skill_docs_root) if skill_docs_root else SKILL_DOCS_DIR
    skill_dir = root / skill_id
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists() and not overwrite:
        raise ValueError(f"技能已存在: {skill_md}，使用 overwrite=True 可覆盖")
    name = (name or skill_id).strip() or skill_id
    description = (description or f"技能 {name} 的简短描述，供 LLM 判断何时使用。").strip()
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = _template_content(skill_id, name, description, http_url)
    skill_md.write_text(content, encoding="utf-8")
    logger.info("已创建技能: %s -> %s", skill_id, skill_md)
    return skill_md
