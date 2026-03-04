"""API 集成测试（FastAPI TestClient）。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """使用根目录 app 创建 TestClient；不抛服务端异常以便断言 500 响应。"""
    from app import app
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient):
    """GET /api/health 返回 200，body 为 code/msg/data/request_id，data 内含 status、version、checks。"""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    payload = body.get("data") or {}
    assert payload.get("status") == "ok"
    assert "version" in payload
    checks = payload.get("checks", {})
    assert checks.get("config") == "ok"
    assert checks.get("agent") in ("ok", "placeholder")


def test_chat_missing_form(client: TestClient):
    """POST /api/chat 缺少 text：422。"""
    r = client.post("/api/chat")
    assert r.status_code == 422


def test_chat_text_too_long(client: TestClient):
    """POST /api/chat 文本超长：422，body.code 为 400（VALIDATION_ERROR）。"""
    r = client.post("/api/chat", data={"text": "x" * 3000})
    assert r.status_code == 422
    assert r.json().get("code") == 400


def test_chat_with_text(client: TestClient):
    """POST /api/chat 带 text：200 时 body 为 code/msg/data/request_id，data 含 reply、conversation_id。"""
    r = client.post("/api/chat", data={"text": "明天下午3点开项目会，1小时"})
    assert r.status_code in (200, 503, 500)
    data = r.json()
    assert "code" in data
    assert "request_id" in data or "msg" in data
    if r.status_code == 200:
        payload = data.get("data") or {}
        assert "reply" in payload or "booking" in payload
        assert "conversation_id" in payload


def test_chat_multiturn_conversation_id(client: TestClient):
    """多轮会话：首轮不传 conversation_id 响应带 conversation_id；第二轮传该 id 仍成功。"""
    r1 = client.post("/api/chat", data={"text": "你好"})
    assert r1.status_code == 200
    payload1 = r1.json().get("data") or {}
    cid = payload1.get("conversation_id")
    assert cid, "首轮响应应包含 conversation_id"
    r2 = client.post("/api/chat", data={"text": "有哪些会议室", "conversation_id": cid})
    assert r2.status_code == 200
    payload2 = r2.json().get("data") or {}
    assert payload2.get("conversation_id") == cid
    assert "reply" in payload2
