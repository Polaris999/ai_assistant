# clients/dify_client.py
import logging
from typing import Any, Optional

import requests

from meeting_agent.config import settings

logger = logging.getLogger(__name__)


class DifyClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        app_type: Optional[str] = None,
    ):
        self.api_key = api_key or settings.dify_api_key
        self.base_url = (base_url or settings.dify_base_url).rstrip("/")
        self.app_type = app_type or settings.dify_chat_app_type

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat-messages"

    def _completion_url(self) -> str:
        return f"{self.base_url}/completion-messages"

    def invoke(
        self,
        query: str,
        user_id: str = "default",
        conversation_id: Optional[str] = None,
        response_mode: str = "blocking",
        **inputs: Any,
    ) -> dict[str, Any]:
        if self.app_type == "chat-messages":
            url = self._chat_url()
            body = {"inputs": {"query": query, **inputs}, "response_mode": response_mode, "user": user_id}
            if conversation_id:
                body["conversation_id"] = conversation_id
        else:
            url = self._completion_url()
            body = {"inputs": {"query": query, **inputs}, "response_mode": response_mode, "user": user_id}
        resp = requests.post(url, headers=self._headers(), json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def chat(
        self,
        query: str,
        user_id: str = "default",
        conversation_id: Optional[str] = None,
        **inputs: Any,
    ) -> str:
        data = self.invoke(query=query, user_id=user_id, conversation_id=conversation_id, response_mode="blocking", **inputs)
        if "answer" in data:
            return data["answer"] or ""
        if "message" in data and isinstance(data["message"], dict):
            return (data["message"].get("answer") or data["message"].get("message") or "") or ""
        return str(data)
