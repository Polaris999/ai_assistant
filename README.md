# 会议预定 Agent

通过**语音或文本**输入创建会议预定，在会议开始前 **N 分钟**触发提醒。基于 LangChain + LangGraph + RAG，LLM/Embeddings/向量库按配置切换。

## 技术栈

- **LangChain / LangGraph**：有状态 Agent 工作流（RAG → 解析意图 → 创建会议 → 安排提醒 → 回复润色）
- **胶水层**：LLM（vllm / openai / dify）、Embeddings（openai / api）、向量库（chroma / qdrant / weaviate）
- **RAG**：会议知识库 + 默认会议室/规则
- **APScheduler**：定时提醒

## 快速开始

```bash
# 按 profile 加载：未设时用 dev，加载 .env.dev 再 .env（.env 覆盖）
# 设 APP_PROFILE=prod 则加载 .env.prod 再 .env。密钥与覆盖写在 .env 或环境变量
# 可选：cp .env.example .env 并编辑

pip install -e .
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- **API**：`POST /api/v1/book`（表单 `text=会议描述`）、`POST /api/v1/book/voice`、`GET /api/v1/health`
- **命令行**：`meeting-agent --text "明天下午3点开项目会，1小时，会议室A"` 或 `meeting-agent --voice path/to.wav`

响应格式统一为 `code` / `msg` / `data` / `request_id`，`code === 0` 表示成功。

---

## 文档导航

| 类型 | 文档 | 说明 |
|------|------|------|
| **开发手册** | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 框架复用、新增 Agent、开发与测试、代码规范 |
| **技术架构** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层架构、核心流程、Agent 图、框架设计与评论 |
| **安装部署** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 环境与依赖服务、本地/生产部署、K8s、vLLM Embedding |

---

## 项目结构（概要）

```
1agent/
├── src/meeting_agent/     # 主包
│   ├── agent_base.py     # Agent 协议（AgentRunner、run_agent_warmup）
│   ├── framework/        # 可复用框架聚合
│   ├── agent/            # LangGraph 图（会议 Agent）
│   ├── api/              # 路由、响应、中间件、agent_bootstrap
│   ├── core/             # LLM、Embeddings、向量库、异常、callbacks
│   ├── config/           # 配置、Prompt 加载
│   ├── rag/              # RAG
│   ├── models/           # MeetingIntent、MeetingBooking
│   ├── services/         # MeetingStore、ReminderScheduler
│   └── voice/            # 语音转文字
├── app.py                # FastAPI 入口
├── docs/                 # 开发手册、技术架构、安装部署
└── tests/
```

---

## 常见问题

- **WinError 1114 / c10.dll**：若仅用 vLLM + 单独 Embedding（不跑本地模型），可 `pip uninstall torch -y` 后启动。
- **向量库/Embedding 不可达**：使用 `meeting-agent --check-vector-store`、`meeting-agent --check-embedding` 自检；详见 [安装部署](docs/DEPLOYMENT.md)。

更多使用说明、扩展方式与部署细节见上述三类文档。
