"""
GenericSkill：仅凭 SKILL.md 中 executor.url 执行的「无代码」技能，与 [skillkit](https://github.com/maxvaega/skillkit) 的纯文档技能+执行器对齐。

当 frontmatter 含 executor.type=http 与 executor.url 时，执行时 POST 到该 URL，无需编写 Python Skill。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ai_assistant.agent.skills.base import BaseSkill, ToolSchema

logger = logging.getLogger(__name__)


class GenericSkill(BaseSkill):
    """
    由 SKILL.md 文档 + executor.url 驱动的技能；无 Python 实现时通过 HTTP 调用外部执行。
    """

    def __init__(self, doc: dict[str, Any]) -> None:
        self._doc = doc
        self._url = ((doc.get("executor") or {}).get("url") or "").strip()
        self._id = (doc.get("id") or doc.get("name") or "generic").strip()

    def get_skill_manifest(self) -> dict[str, Any]:
        return {
            "id": self._id,
            "name": self._doc.get("name") or self._id,
            "description": (self._doc.get("description") or "").strip(),
        }

    def get_tools_schema(self) -> list[ToolSchema]:
        """若 doc 含 tools（如 tools.json），返回多 tool schema；否则单 tool（技能 id 为名）。"""
        tools = self._doc.get("tools")
        if isinstance(tools, list) and tools:
            out: list[ToolSchema] = []
            for t in tools:
                if not isinstance(t, dict) or not t.get("name"):
                    continue
                out.append({
                    "name": str(t["name"]),
                    "description": (t.get("description") or "").strip() or "调用该工具",
                    "parameters": t.get("parameters") if isinstance(t.get("parameters"), dict) else {"type": "object", "properties": {}, "required": []},
                })
            if out:
                return out
        desc = (self._doc.get("description") or "调用该技能").strip()
        return [
            {
                "name": self._id,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "用户输入或参数"},
                        "arguments": {"type": "object", "description": "其他参数"},
                    },
                    "required": [],
                },
            }
        ]

    def _serialize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """可序列化 context 供 HTTP 请求（current_time → ISO 字符串，get_session_value → 常用键值）。"""
        out: dict[str, Any] = {}
        for k, v in context.items():
            if k == "get_session_value" and callable(v):
                try:
                    out["last_booking_id"] = v("last_booking_id")
                except Exception:
                    out["last_booking_id"] = None
                continue
            if k == "current_time" and hasattr(v, "isoformat"):
                out[k] = v.isoformat()
            elif k != "get_session_value":
                out[k] = v
        return out

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._url:
            return {"reply": "该技能未配置执行地址。", "booking": None, "error": "CONFIG_ERROR"}
        timeout = context.get("_skill_http_timeout")
        if timeout is None:
            try:
                from ai_assistant.config import settings
                timeout = getattr(settings, "skill_http_timeout_seconds", 30) or 30
            except Exception:
                timeout = 30
        payload = {
            "tool": tool_name,
            "arguments": arguments or {},
            "context": self._serialize_context(context),
        }
        last_error: Optional[Exception] = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                import requests
                resp = requests.post(self._url, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
                return {
                    "reply": data.get("reply", resp.text or "已执行"),
                    "booking": data.get("booking"),
                    "error": data.get("error"),
                }
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_attempts - 1:
                    logger.debug("GenericSkill HTTP 超时，重试 %s/%s: %s", attempt + 1, max_attempts, self._url)
                    continue
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < max_attempts - 1:
                    logger.debug("GenericSkill HTTP 连接失败，重试 %s/%s: %s", attempt + 1, max_attempts, self._url)
                    continue
            except Exception as e:
                last_error = e
                break
        logger.warning("GenericSkill HTTP 执行失败 %s: %s", self._url, last_error)
        return {
            "reply": f"技能执行失败：{last_error!s}" if last_error else "技能执行失败",
            "booking": None,
            "error": "RUNTIME_ERROR",
        }
