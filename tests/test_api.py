"""API 集成测试（FastAPI TestClient）。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """使用根目录 app 创建 TestClient；不抛服务端异常以便断言 500 响应。"""
    from app import app
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient):
    """GET /api/v1/health 返回 200 及 status、version、checks（含 agent 就绪状态）。"""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
    checks = data.get("checks", {})
    assert checks.get("config") == "ok"
    assert checks.get("agent") in ("ok", "placeholder")


def test_book_missing_form(client: TestClient):
    """POST /api/v1/book 缺少 text：422。"""
    r = client.post("/api/v1/book")
    assert r.status_code == 422


def test_book_text_too_long(client: TestClient):
    """POST /api/v1/book 文本超长：422。"""
    r = client.post("/api/v1/book", data={"text": "x" * 3000})
    assert r.status_code == 422
    assert r.json().get("code") == "VALIDATION_ERROR"


def test_book_with_text(client: TestClient):
    """POST /api/v1/book 带 text：200/503 时 body 含 reply、error、request_id；500 为未捕获异常（如外部服务不可用）。"""
    r = client.post("/api/v1/book", data={"text": "明天下午3点开项目会，1小时"})
    assert r.status_code in (200, 503, 500)
    data = r.json()
    if r.status_code in (200, 503):
        assert "reply" in data and "error" in data and "request_id" in data
    else:
        assert "code" in data or "message" in data
