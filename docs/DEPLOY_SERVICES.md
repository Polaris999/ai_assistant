# 部署需要哪些服务

会议预定 Agent 依赖三类外部能力，按你选的配置决定**要部署哪些**、**用云还是自建**。

---

## 1. LLM 服务（必选，三选一）

用于解析用户输入为会议意图、可选做回复润色。

| 方式 | 需要部署/配置 | 配置项 |
|------|----------------|--------|
| **vllm**（默认） | 自建 vLLM 服务，挂载你的 chat 模型 | `LLM_TYPE=vllm`，`VLLM_BASE_URL=http://<主机>:<端口>/v1` |
| **openai** | 无需自建，用 OpenAI 或兼容 API | `LLM_TYPE=openai`，`OPENAI_API_KEY=...`，可选 `OPENAI_BASE_URL` |
| **dify** | 使用 Dify 应用 | `LLM_TYPE=dify`，`DIFY_API_KEY=...`，`DIFY_BASE_URL=...` |

- 选 **vllm**：需要部署 **1 个 LLM 服务**（vLLM 提供 OpenAI 兼容的 `/v1/chat/completions`）。
- 选 **openai/dify**：不用自己部署 LLM，只配密钥/地址即可。

---

## 2. Embedding 服务（必选，二选一）

用于 RAG：把会议知识、用户问题向量化并检索。当前默认 **api**（单独 embedding 服务）。

| 方式 | 需要部署/配置 | 配置项 |
|------|----------------|--------|
| **api**（默认） | 自建 **1 个 Embedding 服务**，提供 OpenAI 兼容的 `/v1/embeddings` | `EMBEDDING_TYPE=api`，`EMBEDDING_BASE_URL=http://<主机>:<端口>/v1` |
| **openai** | 无需自建 | `EMBEDDING_TYPE=openai`，`OPENAI_API_KEY=...` |

- 选 **api**：需要部署 **1 个 Embedding 服务**（如用 vLLM 的 embedding 接口、或其它实现 `/v1/embeddings` 的服务）。**用 vLLM Docker 部署 Embedding 模型**见 [VLLM_EMBEDDING_DOCKER.md](VLLM_EMBEDDING_DOCKER.md)。
- 选 **openai**：不部署，只配 `OPENAI_API_KEY`。

---

## 3. RAG 向量库（必选，三选一）

存会议知识向量，做相似检索。默认 **chroma**（内嵌，无需单独进程）。

| 方式 | 需要部署 | 配置项 |
|------|----------|--------|
| **chroma**（默认） | **不需要单独部署**，应用内嵌 Chroma，数据落盘 | `VECTOR_STORE_TYPE=chroma`，`CHROMA_PERSIST_DIR=./data/chroma_db` |
| **qdrant** | 部署 1 个 Qdrant 服务 | `VECTOR_STORE_TYPE=qdrant`，`QDRANT_URL=http://<主机>:6333` |
| **weaviate** | 部署 1 个 Weaviate 服务 | `VECTOR_STORE_TYPE=weaviate`，`WEAVIATE_URL=http://<主机>:8080` |

- 选 **chroma**：**不部署**，只配目录即可。
- 选 **qdrant/weaviate**：需要各部署 **1 个** 对应服务。

---

## 汇总：按典型组合你要部署什么

| 组合 | LLM | Embedding | 向量库 | 需要部署的服务 |
|------|-----|-----------|--------|----------------|
| 全自建（vllm + api + chroma） | vllm | api | chroma | **2 个**：① LLM（vLLM chat） ② Embedding（vLLM embedding 或其它 /v1/embeddings） |
| 全自建 + 独立向量库 | vllm | api | qdrant/weaviate | **3 个**：① LLM ② Embedding ③ Qdrant 或 Weaviate |
| 用 OpenAI | openai | openai | chroma | **0 个**（只配 `OPENAI_API_KEY`，向量库用内嵌 Chroma） |
| 混合 | vllm | openai | chroma | **1 个**：仅 LLM（vLLM） |

---

## 最小自建方案（vllm + api + chroma）

1. **部署 LLM**：起一个 vLLM，暴露 OpenAI 兼容的 chat 接口（如 `http://<host>:8000/v1`）。
2. **部署 Embedding**：起一个提供 `/v1/embeddings` 的服务（可与 vLLM 同机不同端口，或同一 vLLM 实例同时提供 chat + embeddings）。
3. **向量库**：不部署，用默认 Chroma，在应用里写 `CHROMA_PERSIST_DIR=./data/chroma_db`。

`.env` 示例：

```bash
LLM_TYPE=vllm
VLLM_BASE_URL=http://<LLM 主机>:8000/v1

EMBEDDING_TYPE=api
EMBEDDING_BASE_URL=http://<Embedding 主机>:端口/v1

VECTOR_STORE_TYPE=chroma
CHROMA_PERSIST_DIR=./data/chroma_db
```

这样你需要部署的只有：**LLM 模型服务** 和 **Embedding 模型服务**；RAG 数据库用 Chroma 内嵌，无需单独部署。

**K8s 部署**：若在 Kubernetes 上自建上述服务，见 [K8S_DEPLOY.md](K8S_DEPLOY.md)（vLLM/Embedding/向量库 Helm 或 Deployment 示例、meeting-agent 配置与 Service 发现）。

**自检命令**：配置好后可用 CLI 验证连通性，失败时退出码为 1。
- `meeting-agent --check-vllm`：验证 vLLM 是否可达。
- `meeting-agent --check-embedding`：验证 Embedding 是否可达/可用（请求 `/v1/embeddings`，若模型名不匹配会提示可用模型）。
- `meeting-agent --check-vector-store`：验证当前向量库是否可用（Chroma 检查目录可写，Qdrant 请求 `/healthz`，Weaviate 请求 `/v1/.well-known/ready`）。
