"""
Skill 文档加载器：从 skill_docs/*/SKILL.md 加载技能说明；可选同目录 tools.json 定义多 tool schema；executor.url 支持 ${ENV_VAR} 占位符。

与以下规范对齐：
- [Anthropic Agent Skills](https://github.com/anthropics/skills)：每技能一文件夹 + SKILL.md（YAML name/description + Markdown）
- [LangChain Skills](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)：prompt-driven、可渐进披露（progressive disclosure）
- [agentskills.io](https://agentskills.io)：Agent Skills 标准

支持两种模式（由 USE_SKILL_CATALOG_ONLY 控制）：
- False（默认）：启动时 load_all_skill_docs() 注入全部技能全文到 system prompt。
- True：仅注入技能目录（name+description），通过 load_skill 工具按需加载 content（渐进式披露）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def resolve_executor_url(executor: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """若 executor.url 为 ${VAR} 则从环境变量替换；返回新 dict 或 None。"""
    if not executor or not isinstance(executor, dict):
        return executor
    url = (executor.get("url") or "").strip()
    if url.startswith("${") and url.endswith("}"):
        env_var = url[2:-1].strip()
        url = (os.environ.get(env_var) or "").strip()
        executor = {**executor, "url": url}
    return executor if (executor.get("url") or "").strip() else None

# 项目根目录（config -> ai_assistant -> src -> 根）
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILL_DOCS_DIR = _ROOT / "skill_docs"


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """
    解析 YAML frontmatter：name、description、可选 executor（type/url）用于无代码 HTTP 技能。
    避免依赖 PyYAML，仅做简单行匹配。
    """
    out: dict[str, Any] = {}
    in_executor = False
    executor: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*name\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            in_executor = False
            out["name"] = m.group(1).strip().strip("'\"")
            continue
        m = re.match(r"^\s*description\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            in_executor = False
            out["description"] = m.group(1).strip().strip("'\"")
            continue
        if re.match(r"^\s*executor\s*:\s*$", line, re.IGNORECASE):
            in_executor = True
            continue
        if in_executor:
            m = re.match(r"^\s+(?:type|url)\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                key = line.strip().split(":")[0].strip().lower()
                val = m.group(1).strip().strip("'\"")
                executor[key] = val
            elif line.strip() and not line.startswith(" "):
                in_executor = False
                if executor:
                    out["executor"] = executor
                    executor = {}
        continue
    if executor:
        out["executor"] = executor
    return out


def load_skill_doc(skill_dir: Path) -> Optional[dict[str, Any]]:
    """
    加载单个技能目录下的 SKILL.md，可选同目录 tools.json；返回 {id, name, description, content, executor?, tools?}。
    executor.url 支持 ${ENV_VAR}，可用 resolve_executor_url() 解析。
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    try:
        raw = skill_md.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取 SKILL.md 失败 %s: %s", skill_md, e)
        return None
    if "---" not in raw:
        return None
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    front = _parse_frontmatter(parts[1])
    body = parts[2].strip()
    name = (front.get("name") or skill_dir.name) if isinstance(front.get("name"), str) else skill_dir.name
    description = front.get("description") if isinstance(front.get("description"), str) else ""
    doc: dict[str, Any] = {"id": skill_dir.name, "name": name, "description": description, "content": body}
    if "executor" in front and isinstance(front["executor"], dict):
        resolved = resolve_executor_url(front["executor"])
        if resolved and (resolved.get("url") or "").strip():
            doc["executor"] = resolved
    tools_file = skill_dir / "tools.json"
    if tools_file.is_file():
        try:
            tools_data = json.loads(tools_file.read_text(encoding="utf-8"))
            if isinstance(tools_data, list) and tools_data:
                doc["tools"] = tools_data
            elif isinstance(tools_data, dict) and tools_data.get("tools"):
                doc["tools"] = tools_data["tools"]
        except Exception as e:
            logger.warning("读取 tools.json 失败 %s: %s", tools_file, e)
    return doc


# 进程内缓存：仅对默认目录（skill_docs_root=None）缓存，修改 SKILL.md 后需重启进程生效
_all_skill_docs_cache: Optional[list[dict[str, Any]]] = None


def load_all_skill_docs(skill_docs_root: Optional[Path] = None) -> list[dict[str, Any]]:
    """
    加载 skill_docs 下所有子目录中的 SKILL.md。
    返回 list[{name, description, content}]，按 name 排序。
    当 skill_docs_root 为 None 时使用进程内缓存，修改文件后需重启生效。
    """
    global _all_skill_docs_cache
    if skill_docs_root is None and _all_skill_docs_cache is not None:
        return _all_skill_docs_cache
    root = Path(skill_docs_root) if skill_docs_root else SKILL_DOCS_DIR
    if not root.is_dir():
        logger.debug("Skill 文档目录不存在: %s", root)
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        doc = load_skill_doc(d)
        if doc:
            out.append(doc)
    if skill_docs_root is None:
        _all_skill_docs_cache = out
    return out


def get_skill_ids_from_docs(skill_docs_root: Optional[Path] = None) -> list[str]:
    """
    从 skill_docs 目录发现技能 ID 列表（有 SKILL.md 的子目录名）。
    业内统一做法：以 skill_docs 为技能来源，与执行层注册表结合决定启用哪些技能。
    """
    docs = load_all_skill_docs(skill_docs_root=skill_docs_root)
    return [d["id"] for d in docs if d.get("id")]


def load_skill_by_name(skill_name: str, skill_docs_root: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """
    按名称加载单个技能文档（用于渐进披露：agent 通过 tool 按需加载）。
    skill_name 与文件夹名或 frontmatter name 匹配（忽略大小写、连字符/下划线）。
    """
    root = Path(skill_docs_root) if skill_docs_root else SKILL_DOCS_DIR
    if not root.is_dir():
        return None
    norm = skill_name.strip().lower().replace("_", "-")
    for d in root.iterdir():
        if not d.is_dir():
            continue
        doc = load_skill_doc(d)
        if not doc:
            continue
        doc_norm = (doc.get("name") or d.name).strip().lower().replace("_", "-")
        if doc_norm == norm:
            return doc
        if d.name.lower().replace("_", "-") == norm:
            return doc
    return None


def format_skill_docs_for_prompt(skill_docs: list[dict[str, Any]]) -> str:
    """将加载后的技能文档格式化为可拼入 system prompt 的文本（全文：name + description + content）。"""
    if not skill_docs:
        return ""
    blocks = []
    for s in skill_docs:
        name = s.get("name") or ""
        desc = (s.get("description") or "").strip()
        content = (s.get("content") or "").strip()
        if not name:
            continue
        blocks.append(f"## Skill: {name}\n{desc}\n\n{content}")
    return "\n\n---\n\n".join(blocks)


def format_skill_catalog_for_prompt(skill_docs: list[dict[str, Any]]) -> str:
    """
    仅将技能目录（name + description）格式化为可拼入 system prompt 的文本，用于渐进式披露。
    需要某技能详细说明时，由 Agent 调用 load_skill(skill_name) 按需加载 content。
    """
    if not skill_docs:
        return ""
    lines = ["## 可用技能（Available Skills）", ""]
    for s in skill_docs:
        name = s.get("name") or s.get("id") or ""
        desc = (s.get("description") or "").strip()
        if not name:
            continue
        lines.append(f"- **{name}**：{desc}")
    lines.append("")
    lines.append(
        "当你需要处理某一类具体请求的详细信息（业务规则、步骤、示例）时，"
        "请先使用 load_skill 工具加载对应技能的完整内容，再选择其他工具执行。"
    )
    return "\n".join(lines)
