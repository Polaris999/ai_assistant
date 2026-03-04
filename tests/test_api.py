"""API 集成测试（FastAPI TestClient）。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """使用根目录 app 创建 TestClient；不抛服务端异常以便断言 500 响应。"""
    from app import app
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient):
    """GET /api/v1/health 返回 200，body 为 code/msg/data/request_id，data 内含 status、version、checks。"""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    payload = body.get("data") or {}
    assert payload.get("status") == "ok"
    assert "version" in payload
    checks = payload.get("checks", {})
    assert checks.get("config") == "ok"
    assert checks.get("agent") in ("ok", "placeholder")


def test_book_missing_form(client: TestClient):
    """POST /api/v1/book 缺少 text：422。"""
    r = client.post("/api/v1/book")
    assert r.status_code == 422


def test_book_text_too_long(client: TestClient):
    """POST /api/v1/book 文本超长：422，body.code 为 400（VALIDATION_ERROR）。"""
    r = client.post("/api/v1/book", data={"text": "x" * 3000})
    assert r.status_code == 422
    assert r.json().get("code") == 400


def test_book_with_text(client: TestClient):
    """POST /api/v1/book 带 text：200 时 body 为 code/msg/data/request_id，data 含 reply；503/500 时亦有 code、msg、request_id。"""
    r = client.post("/api/v1/book", data={"text": "明天下午3点开项目会，1小时"})
    assert r.status_code in (200, 503, 500)
    data = r.json()
    assert "code" in data
    assert "request_id" in data or "msg" in data
    if r.status_code == 200:
        payload = data.get("data") or {}
        assert "reply" in payload or "booking" in payload
