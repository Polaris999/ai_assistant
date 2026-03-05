"""命令行自检：vLLM、向量库、Embedding 可达性。与 main 入口分离，便于维护与扩展。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_assistant.config.settings import Settings

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


def _get_settings() -> "Settings":
    from ai_assistant.config.settings import settings
    return settings


def _list_openai_compat_models(base_url: str, headers: dict, timeout: int) -> list[str]:
    """尝试从 OpenAI 兼容服务获取 /models，返回模型 id 列表（失败返回空）。"""
    if not requests:
        return []
    try:
        url = base_url.rstrip("/") + "/models"
        r = requests.get(url, headers=headers or None, timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json() or {}
        items = data.get("data") or []
        ids: list[str] = []
        for it in items:
            mid = (it or {}).get("id")
            if isinstance(mid, str) and mid.strip():
                ids.append(mid.strip())
        return ids
    except Exception:
        return []


def check_vllm(settings: Optional["Settings"] = None) -> bool:
    """验证 vLLM 配置是否可达（发一次最小 chat 请求）。不传 settings 时使用全局配置。"""
    if not requests:
        print("未安装 requests，无法执行 vLLM 自检")
        return False
    s = settings or _get_settings()
    base_url = (s.vllm_base_url or "").strip().rstrip("/")
    if not base_url:
        print("未配置 VLLM_BASE_URL")
        return False
    url = base_url + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = (s.vllm_api_key or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    model = (s.vllm_chat_model or "").strip() or "default"
    timeout = min(int(s.vllm_timeout or 10), 15)
    try:
        r = requests.post(
            url,
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 2},
            headers=headers,
            timeout=timeout,
        )
        if r.status_code == 200:
            print("vLLM 连接正常")
            return True
        if r.status_code == 404 and "does not exist" in (r.text or ""):
            print(
                f"vLLM 服务可达，但模型名 '{model}' 不存在。"
                "请设置 VLLM_CHAT_MODEL 为服务端实际模型名（如 /v1/models 所列）"
            )
            return False
        print(f"vLLM 返回 {r.status_code}: {(r.text or '')[:300]}")
        return False
    except requests.RequestException as e:
        print(f"vLLM 连接失败: {e}")
        return False


def check_vector_store(settings: Optional["Settings"] = None) -> bool:
    """验证当前配置的向量库是否可达/可用（Chroma 检查目录，Qdrant/Weaviate 请求健康接口）。不传 settings 时使用全局配置。"""
    if not requests:
        print("未安装 requests，无法执行向量库自检（Qdrant/Weaviate）")
    s = settings or _get_settings()
    t = (s.vector_store_type or "chroma").strip().lower()
    timeout = 10

    if t == "chroma":
        persist = (s.chroma_persist_dir or "./data/chroma_db").strip()
        if not persist:
            print("Chroma 需配置 CHROMA_PERSIST_DIR")
            return False
        try:
            p = Path(persist)
            p.mkdir(parents=True, exist_ok=True)
            if not p.is_dir():
                print(f"CHROMA_PERSIST_DIR 无法创建或不是目录: {persist}")
                return False
            print("Chroma 向量库目录可用:", p.resolve())
            return True
        except OSError as e:
            print(f"Chroma 目录不可用 ({persist}): {e}")
            return False

    if t == "qdrant":
        if not requests:
            print("Qdrant 自检需要 requests")
            return False
        url = (s.qdrant_url or "").strip().rstrip("/")
        if not url:
            print("Qdrant 需配置 QDRANT_URL（例如 http://localhost:6333）")
            return False
        health_url = url + "/healthz"
        headers = {}
        if (s.qdrant_api_key or "").strip():
            headers["api-key"] = s.qdrant_api_key.strip()
        try:
            r = requests.get(health_url, headers=headers or None, timeout=timeout)
            if r.status_code == 200:
                print("Qdrant 向量库连接正常")
                return True
            print(f"Qdrant 返回 {r.status_code}: {(r.text or '')[:200]}")
            return False
        except requests.RequestException as e:
            print(f"Qdrant 连接失败: {e}")
            return False

    if t == "weaviate":
        if not requests:
            print("Weaviate 自检需要 requests")
            return False
        url = (s.weaviate_url or "").strip().rstrip("/")
        if not url:
            print("Weaviate 需配置 WEAVIATE_URL（例如 http://localhost:8080）")
            return False
        ready_url = url + "/v1/.well-known/ready"
        headers = {}
        if (s.weaviate_api_key or "").strip():
            headers["Authorization"] = f"Bearer {s.weaviate_api_key.strip()}"
        try:
            r = requests.get(ready_url, headers=headers or None, timeout=timeout)
            if r.status_code == 200:
                print("Weaviate 向量库连接正常")
                return True
            print(f"Weaviate 返回 {r.status_code}: {(r.text or '')[:200]}")
            return False
        except requests.RequestException as e:
            print(f"Weaviate 连接失败: {e}")
            return False

    print(f"不支持的 vector_store_type: {t}，可选: chroma, qdrant, weaviate")
    return False


def check_embedding(settings: Optional["Settings"] = None) -> bool:
    """验证当前配置的 Embedding 服务是否可达/可用（发一次最小 /v1/embeddings 请求）。不传 settings 时使用全局配置。"""
    if not requests:
        print("未安装 requests，无法执行 Embedding 自检")
        return False
    s = settings or _get_settings()
    t = (s.embedding_type or "api").strip().lower()
    timeout = 15
    headers = {"Content-Type": "application/json"}

    if t == "api":
        base_url = (s.embedding_base_url or "").strip().rstrip("/")
        if not base_url:
            print("EMBEDDING_TYPE=api 时需配置 EMBEDDING_BASE_URL（例如 http://<host>:<port>/v1）")
            return False
        if (s.embedding_api_key or "").strip():
            headers["Authorization"] = f"Bearer {s.embedding_api_key.strip()}"
        model = (s.embedding_model or "").strip() or "default"
        url = base_url + "/embeddings"
    elif t == "openai":
        api_key = (s.openai_api_key or "").strip()
        if not api_key:
            print("EMBEDDING_TYPE=openai 时需配置 OPENAI_API_KEY")
            return False
        headers["Authorization"] = f"Bearer {api_key}"
        model = (s.openai_embedding_model or "text-embedding-3-small").strip()
        base_url = (
            (s.openai_embedding_base_url or s.openai_base_url or "https://api.openai.com/v1") or ""
        ).strip().rstrip("/")
        url = base_url + "/embeddings"
    else:
        print(f"不支持的 embedding_type: {t}，可选: openai, api")
        return False

    try:
        r = requests.post(
            url,
            json={"model": model, "input": ["ping"]},
            headers=headers,
            timeout=timeout,
        )
        if r.status_code == 200:
            data = r.json() or {}
            emb = (((data.get("data") or [None])[0]) or {}).get("embedding")
            dim = len(emb) if isinstance(emb, list) else None
            if dim:
                print(f"Embedding 连接正常（model={model}, dim={dim}）")
            else:
                print(f"Embedding 连接正常（model={model}）")
            return True

        body = (r.text or "")[:300]
        if r.status_code == 404 and (
            "does not exist" in body or "not exist" in body or "NotFound" in body
        ):
            print(
                "Embedding 服务可达，但模型名不存在。"
                "请设置 EMBEDDING_MODEL / OPENAI_EMBEDDING_MODEL 为服务端实际模型名。"
            )
            models = _list_openai_compat_models(base_url, headers, timeout=timeout)
            if models:
                preview = ", ".join(models[:10])
                more = "" if len(models) <= 10 else f" ...（共 {len(models)} 个）"
                print(f"服务端 /v1/models: {preview}{more}")
            return False

        print(f"Embedding 返回 {r.status_code}: {body}")
        return False
    except requests.RequestException as e:
        print(f"Embedding 连接失败: {e}")
        return False
