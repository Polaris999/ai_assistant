"""命令行入口：文本/语音预定会议。"""
import argparse
import logging
import sys
from pathlib import Path

import requests

from ai_assistant.api.agent_bootstrap import create_agent_or_placeholder
from ai_assistant.config import settings
from ai_assistant.voice.stt import speech_to_text

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def check_vllm() -> bool:
    """验证 vLLM 配置是否可达（发一次最小 chat 请求）。"""
    base_url = (getattr(settings, "vllm_base_url", None) or "").strip().rstrip("/")
    if not base_url:
        print("未配置 VLLM_BASE_URL")
        return False
    url = base_url + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = (getattr(settings, "vllm_api_key", None) or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    model = (getattr(settings, "vllm_chat_model", None) or "").strip() or "default"
    timeout = int(getattr(settings, "vllm_timeout", 0) or 10)
    timeout = min(timeout, 15)
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
            print(f"vLLM 服务可达，但模型名 '{model}' 不存在。请设置 VLLM_CHAT_MODEL 为服务端实际模型名（如 /v1/models 所列）")
            return False
        print(f"vLLM 返回 {r.status_code}: {(r.text or '')[:300]}")
        return False
    except requests.RequestException as e:
        print(f"vLLM 连接失败: {e}")
        return False


def check_vector_store() -> bool:
    """验证当前配置的向量库是否可达/可用（Chroma 检查目录，Qdrant/Weaviate 请求健康接口）。"""
    t = (getattr(settings, "vector_store_type", None) or "chroma").strip().lower()
    timeout = 10

    if t == "chroma":
        persist = (getattr(settings, "chroma_persist_dir", None) or "./data/chroma_db").strip()
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
        url = (getattr(settings, "qdrant_url", None) or "").strip().rstrip("/")
        if not url:
            print("Qdrant 需配置 QDRANT_URL（例如 http://localhost:6333）")
            return False
        health_url = url + "/healthz"
        headers = {}
        api_key = (getattr(settings, "qdrant_api_key", None) or "").strip()
        if api_key:
            headers["api-key"] = api_key
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
        url = (getattr(settings, "weaviate_url", None) or "").strip().rstrip("/")
        if not url:
            print("Weaviate 需配置 WEAVIATE_URL（例如 http://localhost:8080）")
            return False
        ready_url = url + "/v1/.well-known/ready"
        headers = {}
        api_key = (getattr(settings, "weaviate_api_key", None) or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
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


def _list_openai_compat_models(base_url: str, headers: dict, timeout: int) -> list[str]:
    """尝试从 OpenAI 兼容服务获取 /models，返回模型 id 列表（失败返回空）。"""
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


def check_embedding() -> bool:
    """验证当前配置的 Embedding 服务是否可达/可用（发一次最小 /v1/embeddings 请求）。"""
    t = (getattr(settings, "embedding_type", None) or "api").strip().lower()
    timeout = 15
    headers = {"Content-Type": "application/json"}

    if t == "api":
        base_url = (getattr(settings, "embedding_base_url", None) or "").strip().rstrip("/")
        if not base_url:
            print("EMBEDDING_TYPE=api 时需配置 EMBEDDING_BASE_URL（例如 http://<host>:<port>/v1）")
            return False
        api_key = (getattr(settings, "embedding_api_key", None) or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        model = (getattr(settings, "embedding_model", None) or "").strip() or "default"
        url = base_url + "/embeddings"
    elif t == "openai":
        api_key = (getattr(settings, "openai_api_key", None) or "").strip()
        if not api_key:
            print("EMBEDDING_TYPE=openai 时需配置 OPENAI_API_KEY")
            return False
        headers["Authorization"] = f"Bearer {api_key}"
        model = (getattr(settings, "openai_embedding_model", None) or "text-embedding-3-small")
        base_url = (
            getattr(settings, "openai_embedding_base_url", None)
            or getattr(settings, "openai_base_url", None)
            or "https://api.openai.com/v1"
        )
        base_url = (base_url or "").strip().rstrip("/")
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
        if r.status_code == 404 and ("does not exist" in body or "not exist" in body or "NotFound" in body):
            print(f"Embedding 服务可达，但模型名 '{model}' 不存在。请设置 EMBEDDING_MODEL / OPENAI_EMBEDDING_MODEL 为服务端实际模型名。")
            # 尝试列出可用模型（仅对 api/兼容服务更有意义）
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


def main() -> None:
    parser = argparse.ArgumentParser(description="会议预定 Agent（LangChain+LangGraph+Dify+RAG）")
    parser.add_argument("--check-vllm", action="store_true", help="验证 vLLM 配置是否可达")
    parser.add_argument("--check-embedding", action="store_true", help="验证 Embedding 配置是否可达/可用")
    parser.add_argument("--check-vector-store", action="store_true", help="验证当前配置的向量库是否可达/可用")
    parser.add_argument("--text", type=str, help="直接传入文本，例如：明天下午3点开项目会")
    parser.add_argument("--voice", type=str, help="语音文件路径（如 .wav），将先转文字再预定")
    parser.add_argument("--no-whisper", action="store_true", help="语音文件时使用本地识别而非 Whisper")
    args = parser.parse_args()

    if args.check_vllm:
        ok = check_vllm()
        sys.exit(0 if ok else 1)
    if args.check_embedding:
        ok = check_embedding()
        sys.exit(0 if ok else 1)
    if args.check_vector_store:
        ok = check_vector_store()
        sys.exit(0 if ok else 1)

    if args.text:
        user_input = args.text
    elif args.voice:
        try:
            user_input = speech_to_text(args.voice, use_whisper=not args.no_whisper)
        except FileNotFoundError as e:
            logger.error("%s", e)
            sys.exit(1)
        if not user_input.strip():
            logger.error("语音识别结果为空")
            sys.exit(1)
        logger.info("语音识别结果: %s", user_input)
    else:
        print("请输入会议信息（或提供 --text / --voice），例如：明天下午3点开项目会，1小时，会议室A")
        user_input = input("> ").strip()
        if not user_input:
            sys.exit(0)

    agent = create_agent_or_placeholder()
    result = agent.invoke(user_input)
    print(result.get("reply", "未得到回复"))
    if result.get("error"):
        logger.warning("error: %s", result["error"])
    booking = result.get("booking")
    if booking is not None:
        bid = booking.get("id") if isinstance(booking, dict) else getattr(booking, "id", None)
        if bid:
            print("会议ID:", bid)


if __name__ == "__main__":
    main()
