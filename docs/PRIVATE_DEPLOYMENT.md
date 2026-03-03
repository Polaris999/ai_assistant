# 私有化 / 自托管部署说明

模型、向量库、语音均可通过配置使用自建或本地方案。

---

## 1. 能力与配置

| 能力 | 配置项 | 可选值 |
|------|--------|--------|
| LLM | `LLM_TYPE` | vllm / openai / dify |
| Embeddings | `EMBEDDING_TYPE` | openai / api（单独 embedding 服务） |
| 向量库 | `VECTOR_STORE_TYPE` | chroma / qdrant / weaviate |
| 语音 | 安装 faster-whisper，不配 `OPENAI_API_KEY` | 本地 Whisper / Google SR |

---

## 2. 各组件说明

### LLM
- vllm：`VLLM_BASE_URL`、可选 `VLLM_CHAT_MODEL`
- openai：`OPENAI_API_KEY`，可选 `OPENAI_BASE_URL` 指向自建
- dify：`DIFY_API_KEY`、`DIFY_BASE_URL`

### Embeddings（单独 embedding 服务）
- api（默认）：自建 embedding 服务，配置 `EMBEDDING_BASE_URL`（OpenAI 兼容 `/v1/embeddings`），可选 `EMBEDDING_API_KEY`、`EMBEDDING_MODEL`
- openai：`OPENAI_API_KEY`，可选 `OPENAI_BASE_URL` / `OPENAI_EMBEDDING_BASE_URL`

### 向量库
- chroma（默认）：`CHROMA_PERSIST_DIR`
- qdrant：`QDRANT_URL`，安装 `pip install -e ".[qdrant]"`
- weaviate：`WEAVIATE_URL`，安装 `pip install -e ".[weaviate]"`（Dify 默认向量库）

### 语音
- 安装 faster-whisper 且不配 `OPENAI_API_KEY` 时走本地 Whisper；否则可走 Whisper API 或回退 Google SR。可选 `LOCAL_WHISPER_MODEL=base`。

---

## 3. 配置示例

```bash
LLM_TYPE=vllm
VLLM_BASE_URL=http://your-host:8000/v1

EMBEDDING_TYPE=api
EMBEDDING_BASE_URL=http://your-embedding-service/v1

VECTOR_STORE_TYPE=chroma
CHROMA_PERSIST_DIR=./data/chroma_db
```

使用 openai 做 Embeddings 时：`pip install -e ".[openai]"`。

---

## 4. 可选依赖（pyproject.toml）

- `[openai]`：openai、langchain-openai（Embeddings 用 openai 或 api 时）
- `[qdrant]`：langchain-qdrant、qdrant-client
- `[weaviate]`：langchain-weaviate、weaviate-client

业务依赖胶水层抽象（BaseLLM、BaseEmbeddings、get_vector_store），切换方案仅改配置或实现新适配器。
