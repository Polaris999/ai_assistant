# AI Assistant

统一对话助手：**语音或文本**输入，支持会议预定、查会议室、取消等；后续可扩展运维工单等能力。基于 LangChain + LangGraph + RAG，LLM/Embeddings/向量库按配置切换。

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

- **API**：`POST /api/chat`、`POST /api/chat/voice`、`GET /api/health`；知识库按库名分（meeting / ops_ticket）：`GET /api/knowledge/bases`、`GET /api/knowledge?kb=`、`GET /api/knowledge/search?q=&kb=`、`POST /api/knowledge?kb=`、`DELETE /api/knowledge?kb=`，建议由网关限制为管理端
- **多轮会话**：首轮不传 `conversation_id`，响应 `data.conversation_id` 供下一轮携带；同会话内支持追问与补全（如先问「订个会」再补「明天下午3点」）。
- **命令行**：`ai-assistant --text "明天下午3点开项目会，1小时，会议室A"` 或 `ai-assistant --voice path/to.wav`

响应格式统一为 `code` / `msg` / `data` / `request_id`，`code === 0` 表示成功；`data.conversation_id` 用于多轮。

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
├── src/ai_assistant/     # 主包
│   ├── agent/            # Agent 协议（protocol.py）、Tool/LangGraph 实现、能力层（meeting、ops 占位）
│   ├── api/              # controllers（chat/health/knowledge）、deps、response、middleware、agent_bootstrap
│   ├── config/           # 配置、Prompt 加载、校验
│   ├── core/             # LLM、Embeddings、向量库、异常、callbacks、conversation（会话/Redis）
│   ├── framework/        # 可复用框架聚合导出
│   ├── models/           # MeetingIntent、MeetingBooking
│   ├── rag/              # RAG（按 kb 分库）
│   ├── services/         # IMeetingService、MeetingStore、ReminderScheduler
│   ├── clients/          # 外部客户端（如 Dify）
│   └── voice/            # 语音转文字
├── app.py                # FastAPI 入口
├── docs/                 # 开发手册、技术架构、安装部署
└── tests/
```

---

## 常见问题

- **WinError 1114 / c10.dll**：若仅用 vLLM + 单独 Embedding（不跑本地模型），可 `pip uninstall torch -y` 后启动。
- **向量库/Embedding 不可达**：使用 `ai-assistant --check-vector-store`、`ai-assistant --check-embedding` 自检；详见 [安装部署](docs/DEPLOYMENT.md)。

更多使用说明、扩展方式与部署细节见上述三类文档。
