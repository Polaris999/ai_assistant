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

会议 Agent 依赖 **LLM**、**Embedding**、**RAG 向量库** 三类能力，按所选配置决定要自建哪些服务。

| 能力 | 选项 | 是否需自建 |
|------|------|------------|
| **LLM** | vllm / openai / dify | vllm 需自建；openai/dify 仅配密钥与地址 |
| **Embedding** | api / openai | api 需自建（如 vLLM embedding）；openai 仅配密钥 |
| **向量库** | chroma / qdrant / weaviate | chroma 内嵌无需单独部署；qdrant/weaviate 各需 1 个服务 |

**典型组合**：

- **全自建（vllm + api + chroma）**：部署 2 个服务 —— ① LLM（vLLM chat） ② Embedding（vLLM embedding 或其它 `/v1/embeddings`）；向量库用 Chroma 内嵌。
- **全用 OpenAI**：不部署任何服务，只配 `OPENAI_API_KEY`，向量库用 Chroma。
- **混合**：例如 vllm + openai + chroma，只需部署 1 个 LLM 服务。

详细表格与 `.env` 示例见 [DEPLOY_SERVICES.md](DEPLOY_SERVICES.md)。

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

---

## 5. 详细子文档

| 文档 | 内容 |
|------|------|
| [DEPLOY_SERVICES.md](DEPLOY_SERVICES.md) | 三类依赖的选项、配置项、典型组合与最小自建方案 |
| [K8S_DEPLOY.md](K8S_DEPLOY.md) | Kubernetes 部署：vLLM（LLM）、Embedding、Qdrant/Weaviate、ai-assistant 的 Helm/Deployment 与配置 |
| [VLLM_EMBEDDING_DOCKER.md](VLLM_EMBEDDING_DOCKER.md) | 使用 vLLM Docker 部署 Embedding 模型（/v1/embeddings），含 GPU/CPU、ModelScope、故障排查 |

部署自建服务时，先确定「需要部署哪些服务」→ 按 [DEPLOY_SERVICES.md](DEPLOY_SERVICES.md) 配好 `.env`；若用 K8s 或 vLLM Docker 部署 Embedding，再查阅对应子文档。
