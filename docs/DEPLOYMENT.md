# 安装部署

本文档说明环境准备、依赖服务、本地与生产运行方式，并链接到 K8s、vLLM Embedding 等详细子文档。

---

## 1. 环境准备

### 1.1 依赖

- **Python**：3.10+（建议 3.11）。
- **可选**：若使用语音接口，需安装 ffmpeg（系统或 PATH 可用）。

### 1.2 配置与 profile

应用按 **profile** 加载配置：环境变量 `APP_PROFILE` 或 `ENV` 取值为 `dev`（默认）、`test`、`prod` 时，依次加载 `.env.{profile}`、`.env`（后者覆盖）。未设时默认 `dev`。

```bash
# 开发：不设或 APP_PROFILE=dev，加载 .env.dev 再 .env
# 生产：APP_PROFILE=prod，加载 .env.prod 再 .env
export APP_PROFILE=prod
cp .env.example .env
# 编辑 .env：至少配置 LLM、Embedding、向量库（见下方「需要部署哪些服务」）
```

- 配置项说明见 `.env.example` 内注释。
- 生产环境建议用环境变量或密钥管理注入，避免把 `.env` 打进镜像。

### 1.3 安装

```bash
pip install -e .
# 开发与测试：pip install -e ".[dev]"
```

---

## 2. 需要部署哪些服务

会议 Agent 依赖 **LLM**、**Embedding**、**RAG 向量库** 三类能力，按所选配置决定要自建哪些服务、用云还是自建。

### 2.1 LLM 服务（必选，三选一）

用于解析用户输入为会议意图、可选做回复润色。

| 方式 | 需要部署/配置 | 配置项 |
|------|----------------|--------|
| **vllm**（默认） | 自建 vLLM 服务，挂载 chat 模型 | `LLM_TYPE=vllm`，`VLLM_BASE_URL=http://<主机>:<端口>/v1` |
| **openai** | 无需自建，用 OpenAI 或兼容 API | `LLM_TYPE=openai`，`OPENAI_API_KEY=...`，可选 `OPENAI_BASE_URL` |
| **dify** | 使用 Dify 应用 | `LLM_TYPE=dify`，`DIFY_API_KEY=...`，`DIFY_BASE_URL=...` |

- 选 **vllm**：需部署 **1 个 LLM 服务**（vLLM 提供 OpenAI 兼容的 `/v1/chat/completions`）。
- 选 **openai/dify**：不用自建 LLM，只配密钥/地址即可。

### 2.2 Embedding 服务（必选，二选一）

用于 RAG：把会议知识、用户问题向量化并检索。默认 **api**（单独 embedding 服务）。

| 方式 | 需要部署/配置 | 配置项 |
|------|----------------|--------|
| **api**（默认） | 自建 **1 个 Embedding 服务**，提供 OpenAI 兼容的 `/v1/embeddings` | `EMBEDDING_TYPE=api`，`EMBEDDING_BASE_URL=http://<主机>:<端口>/v1` |
| **openai** | 无需自建 | `EMBEDDING_TYPE=openai`，`OPENAI_API_KEY=...` |

- 选 **api**：需部署 **1 个 Embedding 服务**（如 vLLM 的 embedding 接口或其它实现 `/v1/embeddings` 的服务）。**用 vLLM Docker 部署 Embedding** 见下文 §5。
- 选 **openai**：不部署，只配 `OPENAI_API_KEY`。

### 2.3 RAG 向量库（必选，三选一）

存会议知识向量，做相似检索。默认 **chroma**（内嵌，无需单独进程）。

| 方式 | 需要部署 | 配置项 |
|------|----------|--------|
| **chroma**（默认） | **不需要单独部署**，应用内嵌 Chroma，数据落盘 | `VECTOR_STORE_TYPE=chroma`，`CHROMA_PERSIST_DIR=./data/chroma_db` |
| **qdrant** | 部署 1 个 Qdrant 服务 | `VECTOR_STORE_TYPE=qdrant`，`QDRANT_URL=http://<主机>:6333` |
| **weaviate** | 部署 1 个 Weaviate 服务 | `VECTOR_STORE_TYPE=weaviate`，`WEAVIATE_URL=http://<主机>:8080` |

- 选 **chroma**：不部署，只配目录即可。
- 选 **qdrant/weaviate**：各需部署 **1 个** 对应服务。

### 2.4 汇总：按典型组合你要部署什么

| 组合 | LLM | Embedding | 向量库 | 需要部署的服务 |
|------|-----|-----------|--------|----------------|
| 全自建（vllm + api + chroma） | vllm | api | chroma | **2 个**：① LLM（vLLM chat） ② Embedding（vLLM embedding 或其它 /v1/embeddings） |
| 全自建 + 独立向量库 | vllm | api | qdrant/weaviate | **3 个**：① LLM ② Embedding ③ Qdrant 或 Weaviate |
| 用 OpenAI | openai | openai | chroma | **0 个**（只配 `OPENAI_API_KEY`，向量库用内嵌 Chroma） |
| 混合 | vllm | openai | chroma | **1 个**：仅 LLM（vLLM） |

### 2.5 最小自建方案（vllm + api + chroma）

1. **部署 LLM**：起一个 vLLM，暴露 OpenAI 兼容的 chat 接口（如 `http://<host>:8000/v1`）。
2. **部署 Embedding**：起一个提供 `/v1/embeddings` 的服务（可与 vLLM 同机不同端口，或同一 vLLM 实例同时提供 chat + embeddings）。
3. **向量库**：不部署，用默认 Chroma，在应用里设 `CHROMA_PERSIST_DIR=./data/chroma_db`。

`.env` 示例：

```bash
LLM_TYPE=vllm
VLLM_BASE_URL=http://<LLM 主机>:8000/v1

EMBEDDING_TYPE=api
EMBEDDING_BASE_URL=http://<Embedding 主机>:端口/v1

VECTOR_STORE_TYPE=chroma
CHROMA_PERSIST_DIR=./data/chroma_db
```

这样只需部署 **LLM 模型服务** 和 **Embedding 模型服务**；RAG 用 Chroma 内嵌，无需单独部署。

**K8s 部署**：若在 Kubernetes 上自建上述服务，见本文档 §6（Kubernetes 部署）。

---

## 3. 本地运行

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- **API**：`POST /api/v1/chat`、`POST /api/v1/chat/voice`、`GET /api/v1/health`。
- **命令行**：`ai-assistant --text "会议描述"` 或 `ai-assistant --voice path/to.wav`。

### 自检命令（可选）

配置好后可用 CLI 验证连通性，失败时退出码非 0：

| 命令 | 说明 |
|------|------|
| `ai-assistant --check-vllm` | 验证 vLLM（LLM）是否可达 |
| `ai-assistant --check-embedding` | 验证 Embedding 服务（/v1/embeddings） |
| `ai-assistant --check-vector-store` | 验证当前向量库（Chroma 目录可写，Qdrant/Weaviate 健康） |

---

## 4. 生产部署要点

- **请求 ID**：中间件为每个请求生成 `request_id`，响应头与日志携带，便于排查。
- **安全头**：中间件统一加安全相关响应头（如 X-Content-Type-Options 等）。
- **优雅关闭**：FastAPI lifespan 在关闭时对 Agent 的 `_scheduler` 执行 `shutdown(wait=True)`，避免任务丢失。
- **健康检查**：`GET /api/v1/health` 可做就绪探针；若实现 `is_ready(agent)`，会反映 Agent 与调度器状态。
- **全局异常**：未捕获异常由 app 全局 handler 统一为 `code` / `msg` / `data`，并带 `request_id`。

多实例时，当前预定与提醒为进程内存储与调度，重启会丢失；若需持久化与分布式提醒，需替换 MeetingStore 与 ReminderScheduler 实现。

---

## 4.1 生产就绪结论与前置条件

**结论**：在满足下表「必须满足」的前提下，可用于**内网/低风险场景**的生产部署（如内部工具、试点环境）。若面向公网或对数据持久化、多实例一致性有要求，需先完成「建议完成」项。

| 类别 | 必须满足（否则不建议上生产） | 建议完成 |
|------|------------------------------|----------|
| **数据与调度** | 接受「预定与提醒仅进程内、重启丢失」；或自行替换 `MeetingStore` / `ReminderScheduler` 为持久化与分布式实现 | 预定落库、提醒走消息队列或分布式调度 |
| **认证与权限** | 在网关/反向代理层做认证（API Key、JWT 等）；或仅部署在内网且不对外暴露 | 应用层增加 API Key / 鉴权中间件 |
| **限流** | 在网关或接入层做限流与防滥用 | 文档已约定由网关负责 |
| **配置与密钥** | 使用环境变量或密钥管理注入密钥，不把 `.env` 打进镜像；生产用 `APP_PROFILE=prod` | 敏感配置脱敏、定期轮换 |
| **可观测** | 保留 request_id、请求日志、全局异常；健康检查用于探针 | 接入统一日志与监控（如 ELK、Prometheus） |

当前应用**未实现**：HTTP API 认证、应用层限流、预定/提醒持久化与多实例共享。这些若由网关或外部系统保障，或业务接受其缺失，则可在上述前提下用于生产。

### 4.2 生产就绪评估摘要（再次核对）

| 维度 | 状态 | 说明 |
|------|------|------|
| **请求可观测** | ✅ | X-Request-ID、请求日志（method/path/status/duration）、全局异常带 request_id |
| **安全头** | ✅ | X-Content-Type-Options、X-Frame-Options、X-XSS-Protection |
| **健康与就绪** | ✅ | GET /api/v1/health，含 agent 状态，可做 K8s 就绪/存活探针 |
| **优雅关闭** | ✅ | lifespan 结束时 scheduler.shutdown(wait=True) |
| **配置与密钥** | ✅ | Profile（dev/test/prod）、.env + 环境变量、无硬编码密钥 |
| **会话存储** | ✅ | 可选 Redis，多实例共享会话；未配置则进程内 |
| **输入校验** | ✅ | 文本长度、语音大小、知识库 kb 白名单 |
| **API 文档** | ✅ | /docs、/redoc；生产可设 DOCS_ENABLED=false 关闭 |
| **CORS** | 可选 | 设 CORS_ORIGINS 后启用；否则由网关处理 |
| **认证/限流** | 网关 | 应用内不实现，由网关或内网隔离保障 |
| **多实例一致性** | 部分 | 会话可 Redis；预定/提醒仍进程内，需替换实现或接受单实例 |

**结论**：在「由网关做鉴权与限流、或仅内网」且「接受预定/提醒进程内或自替换」的前提下，**可以上生产**（内网/试点/低风险场景）。上线前建议：`APP_PROFILE=prod`、密钥走环境变量、生产环境关闭文档（`DOCS_ENABLED=false`）、多实例时配置 Redis 会话存储。

---

## 5. 用 vLLM Docker 部署 Embedding 模型

vLLM 官方镜像支持挂载 **embedding 模型**，对外提供 OpenAI 兼容的 `/v1/embeddings`，供 RAG 使用。与 vLLM LLM（Chat）同镜像 `vllm/vllm-openai:latest`，仅把模型换成 embedding 模型、端口与容器名区分即可。K8s 部署见本文档 §6（Kubernetes 部署）中的 Embedding 一节。

### 5.1 与 vLLM LLM（Chat）的对应关系

| 用途 | 镜像 | 端口示例 | 模型示例 | 接口 |
|------|------|----------|----------|------|
| **LLM（Chat）** | `vllm/vllm-openai:latest` | 8000 | `Qwen/Qwen2.5-7B-Instruct` | `/v1/chat/completions` |
| **Embedding**   | `vllm/vllm-openai:latest` | 8001 | `BAAI/bge-small-zh-v1.5`  | `/v1/embeddings` |

本地可同时跑两个容器：LLM 用 8000、Embedding 用 8001。

### 5.2 前置条件

- 已安装 Docker；如需 GPU，安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)。
- 足够内存/显存：小模型（如 bge-small）约 1～2GB。

### 5.3 一键运行 Embedding（GPU）

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model BAAI/bge-small-zh-v1.5
```

- **端口**：容器内 8000，映射主机 8001（避免与 vLLM chat 的 8000 冲突）。
- **模型**：可换成 `BAAI/bge-m3`、`BAAI/bge-large-zh-v1.5` 等（显存需更大）。
- **缓存**：`-v ~/.cache/huggingface:...` 挂载 Hugging Face 缓存，首次下载后下次启动复用。若报错 `unknown or invalid runtime name: nvidia`，见下文 §5.9 故障排查。

### 5.4 从 ModelScope（魔搭）下载

国内网络可改用 ModelScope 拉取，启动时加环境变量并挂载魔搭缓存：

```bash
docker run -d \
  --name vllm-embedding \
  --gpus all \
  -p 8001:8000 \
  -e VLLM_USE_MODELSCOPE=True \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/.cache/modelscope:/root/.cache/modelscope \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model BAAI/bge-small-zh-v1.5
```

宿主机预下载（可选）：`pip install modelscope` 后 `python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5')"`，再挂载 `~/.cache/modelscope`。已预下载时可用本地路径 `--model /root/.cache/modelscope/hub/models/Qwen/Qwen3-Embedding-8B` 启动，无需联网。

### 5.5 无 GPU 时能否用 CPU 跑？

**不能。** 官方镜像为 CUDA 构建，无 GPU 会报 `libcuda.so.1: cannot open shared object file`。可选：① 在有 GPU 的机器/云上起 vLLM，本机 `.env` 里 `EMBEDDING_BASE_URL` 指过去；② 或 `EMBEDDING_TYPE=openai` + `OPENAI_API_KEY` 用云端 Embedding。

### 5.6 验证服务

```bash
curl -X POST http://localhost:8001/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-small-zh-v1.5","input":"测试文本"}'
```

返回 JSON 且含 `data[0].embedding` 即正常。

### 5.7 应用配置

在 `.env` 中指向该 Embedding 服务：

```bash
EMBEDDING_TYPE=api
EMBEDDING_BASE_URL=http://localhost:8001/v1
# 若模型名与上面 --model 一致，可不填；否则用 EMBEDDING_MODEL 指定
```

### 5.8 常用 Embedding 模型与 Qwen3 示例

| 模型 | 说明 | 显存大致需求 |
|------|------|----------------|
| `BAAI/bge-small-zh-v1.5` | 中文小模型，推荐起步 | ~1GB |
| `BAAI/bge-base-zh-v1.5` / `bge-large-zh-v1.5` | 中文 base/large | ~2GB / ~4GB+ |
| `BAAI/bge-m3` | 多语言、长文本 | 更大 |
| `Qwen/Qwen3-Embedding-0.6B` | 0.6B、可与 7B LLM 同卡；需加 `--task embed` | ~1–2GB |
| `Qwen/Qwen3-Embedding-8B` | 8B、32K 上下文；需加 `--task embed` | ~18GB+ |

Qwen3 系列需显式 `--task embed`，例如：

```bash
docker run -d --name vllm-embedding --gpus all -p 8001:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen3-Embedding-8B --task embed
```

从魔搭拉取时加 `-e VLLM_USE_MODELSCOPE=True` 和 `-v ~/.cache/modelscope:/root/.cache/modelscope`。更多见 [vLLM 文档 - Pooling/Embedding 模型](https://docs.vllm.ai/en/latest/models/pooling_models/)。

### 5.9 故障排查

- **`Engine core initialization failed`**：看 `docker logs vllm-embedding 2>&1` 该行之前的根因（如 OOM、CUDA 错误）。可尝试加 `-e VLLM_USE_V1=0` 用旧引擎。
- **`unknown or invalid runtime name: nvidia`**：宿主机安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)，执行 `sudo nvidia-ctk runtime configure --runtime=docker`，重启 Docker 后再用 `--gpus all`。
- **`libcuda.so.1` / `Failed to infer device type`**：官方镜像不支持纯 CPU。在有 GPU 的机器上起容器，或改用远程 Embedding / `EMBEDDING_TYPE=openai`（见 §5.5）。
- **502 / 连接被拒**：确认容器在跑、端口已映射，且 `EMBEDDING_BASE_URL` 的 host 和端口正确（含 `/v1`）。
- **OOM**：换更小模型或增大显存。**模型下载慢**：挂载缓存后首次拉取，之后复用；可设 `HUGGING_FACE_HUB_TOKEN` 用私有模型。

---

## 6. Kubernetes 部署

在 K8s 上自建 vLLM（LLM）、Embedding 服务、RAG 向量库，并与本应用对接。

### 6.1 整体架构

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     Kubernetes 集群                       │
  Ingress/网关       │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
  ───────────────►  │  │ meeting-    │  │ vllm-llm    │  │ vllm-embedding  │  │
                    │  │ agent       │──│ (chat)      │  │ (/v1/embeddings)│  │
                    │  │             │  └─────────────┘  └────────┬────────┘  │
                    │  │             │  ┌─────────────┐          │           │
                    │  │             │──│ qdrant       │◄─────────┘           │
                    │  └─────────────┘  │ (向量库)      │  (或 Weaviate)      │
                    └─────────────────────────────────────────────────────────┘
```

- **meeting-agent**：本应用，通过环境变量连上述服务。
- **vLLM（LLM）**：提供 `/v1/chat/completions`。
- **Embedding 服务**：提供 `/v1/embeddings`；可与 vLLM 同栈再起一个 vLLM 挂 embedding 模型。
- **向量库**：Qdrant / Weaviate，或用 Chroma 内嵌于本应用（无需单独部署）。

### 6.2 前置条件

- Kubernetes 集群（1.24+）；跑 vLLM 需 GPU 节点并安装 [NVIDIA Device Plugin](https://github.com/NVIDIA/k8s-device-plugin)。
- `kubectl`、`helm` 已安装；私有镜像需配置 imagePullSecrets。

### 6.3 部署 vLLM（LLM）

vLLM 提供 Helm Chart（以 [vLLM Helm 文档](https://docs.vllm.ai/deployment/frameworks/helm.html) 为准）：

```bash
helm repo add vllm https://vllm-project.github.io/vllm-helm
helm repo update
kubectl create namespace ai-serving
# 自定义 values：model.name、gpu.count、resources 等
helm upgrade --install vllm-llm vllm/vllm -n ai-serving -f vllm-llm-values.yaml
```

无 Helm 时可用 Deployment + Service：镜像 `vllm/vllm-openai:latest`，args `--model=Qwen/Qwen2.5-7B-Instruct`，端口 8000，资源 limits 含 `nvidia.com/gpu: "1"`。集群内访问示例：`http://vllm-llm.ai-serving.svc.cluster.local:8000/v1`。

### 6.4 部署 Embedding 服务

- **方式一**：再起一个 vLLM Deployment 挂 embedding 模型（如 `BAAI/bge-small-zh-v1.5`），与 LLM 分开；集群内示例：`http://vllm-embedding.ai-serving.svc.cluster.local:8000/v1`。
- **方式二**：自建提供 `/v1/embeddings` 的服务（如 FastAPI + sentence-transformers），本应用 `EMBEDDING_BASE_URL` 指向其 `/v1` 即可。

### 6.5 部署 RAG 向量库（可选）

- **Qdrant**：`helm repo add qdrant https://qdrant.github.io/qdrant-helm`，部署后集群内 `http://qdrant.vector-db.svc.cluster.local:6333`。
- **Weaviate**：见 [Weaviate K8s 文档](https://weaviate.io/developers/weaviate/installation/kubernetes)，一般 8080。
- **Chroma 内嵌**：不单独部署，本应用 `VECTOR_STORE_TYPE=chroma`，数据目录挂 PVC。

### 6.6 部署本应用（meeting-agent）

ConfigMap 示例：`LLM_TYPE=vllm`，`VLLM_BASE_URL=http://vllm-llm.ai-serving.svc.cluster.local:8000/v1`，`EMBEDDING_TYPE=api`，`EMBEDDING_BASE_URL=http://vllm-embedding.../v1`，`VECTOR_STORE_TYPE=qdrant`（或 chroma），`QDRANT_URL=...`。敏感项放 Secret。Deployment 用 `envFrom` 引用 ConfigMap/Secret；若用 Chroma，将 `CHROMA_PERSIST_DIR` 对应目录挂到 PVC。Service 暴露 8000，供 Ingress/网关转发。

### 6.7 服务发现与校验顺序

集群内通过 **Service 名.命名空间.svc.cluster.local:端口** 访问。建议顺序：① 向量库（若 Qdrant/Weaviate）→ ② vLLM LLM → ③ Embedding → ④ meeting-agent。健康检查 `GET /api/v1/health` 中 `checks.agent` 为 `ok` 即表示连上 LLM/Embedding 并完成初始化。
