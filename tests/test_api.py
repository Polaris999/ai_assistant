"""API 集成测试（FastAPI TestClient）。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """使用根目录 app 创建 TestClient。"""
    from app import app
    return TestClient(app)


def test_health(client: TestClient):
    """GET /api/v1/health 返回 200。"""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_book_missing_form(client: TestClient):
    """POST /api/v1/book 缺少 text：422 为参数校验，400 可能为依赖（如未配置 Agent）失败。"""
    r = client.post("/api/v1/book")
    assert r.status_code in (400, 422)


def test_book_with_text(client: TestClient):
    """POST /api/v1/book 带 text：200 为正常或业务错误文案；400 为未配置 API Key 等。"""
    r = client.post("/api/v1/book", data={"text": "明天下午3点开项目会，1小时"})
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert isinstance(r.text, str) and len(r.text) > 0
    else:
        assert "code" in r.json() or len(r.text) > 0
