# 会议预定 Agent 示例（LangChain + LangGraph + RAG）

通过**语音或文本**输入创建会议预定，并在会议开始前 **X 分钟**触发提醒。

## 技术栈

- **LangChain / LangGraph**：有状态 Agent 工作流（RAG → 解析意图 → 创建会议 → 安排提醒 → 回复润色）
- **Core 胶水层**：LLM（vllm / openai / dify）、Embeddings（local / openai）、向量库（chroma / qdrant / weaviate）按配置切换
- **RAG**：会议知识库，Embedding 与向量库由胶水层注入
- **APScheduler**：定时在“开始前 X 分钟”触发提醒

**Agent 开发范式**：显式状态（`MeetingAgentState` TypedDict）、单职责节点、图内依赖注入（LLM/Store/Scheduler/RAG），生命周期与 FastAPI `app.state` 一致；详见 `docs/AGENT_REVIEW.md`。

**Prompt 配置化**：解析意图/回复润色模板默认来自 `config/prompts/`，可通过 `PROMPT_PARSE_INTENT_PATH`、`PROMPT_REPLY_POLISH_PATH` 覆盖（绝对路径或相对项目根）。  
**可观测**：请求级日志回调（节点/LLM 打点，带 `request_id`）；可选开启 LangSmith（`LANGCHAIN_TRACING_ENABLED=true` 且配置 `LANGCHAIN_API_KEY`）。

## 项目结构（src layout + 最佳实践）

**源码集中在 `src/meeting_agent/`**，符合 Python 社区常见的 [src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)：测试与安装时不会误用仓库根目录的代码，依赖更清晰。

```
1agent/
├── src/
│   └── meeting_agent/          # 主包（所有业务代码）
│       ├── config/             # 配置
│       ├── core/               # 胶水层（exceptions, llm, embeddings）
│       ├── clients/            # 外部服务客户端
│       ├── rag/                # RAG
│       ├── models/             # 领域模型
│       ├── services/           # 应用服务
│       ├── agent/              # LangGraph 图
│       ├── api/                # HTTP 层（deps, v1, middleware）
│       ├── voice/              # 语音转文字
│       └── main.py             # 命令行入口逻辑
├── tests/                      # 单元/集成测试
│   ├── conftest.py             # pytest 与 path
│   └── test_models.py
├── static/                     # 前端示例页
├── app.py                      # FastAPI 入口（uvicorn app:app）
├── pyproject.toml              # 包元数据、构建、可选 pytest
├── requirements.txt           # 依赖列表（可与 pyproject 二选一）
├── .env.example
├── .gitignore
├── README.md
└── docs/                    # 设计与管理文档
    ├── DESIGN.md            # 概要设计说明（架构、流程、模块职责）
    └── AGENT_REVIEW.md      # 框架与技术范式审查、代码规范
```

### 文档索引

| 文档 | 说明 |
|------|------|
| [docs/DESIGN.md](docs/DESIGN.md) | **概要设计**：系统目标、分层架构、核心流程（预定、Agent 图、HTTP）、关键设计（胶水层、配置、可观测、生命周期）、目录与入口、扩展与约束 |
| [docs/AGENT_REVIEW.md](docs/AGENT_REVIEW.md) | **框架与规范**：项目结构、技术选型、Agent 范式、代码风格与注释规范、业内做法、后续优化建议 |
| [docs/PRIVATE_DEPLOYMENT.md](docs/PRIVATE_DEPLOYMENT.md) | 私有化部署：LLM/Embeddings/向量库/语音配置与可选依赖 |

## 环境准备

1. 复制环境变量并填写密钥：

```bash
cp .env.example .env
# 编辑 .env：至少配置一种 LLM（OPENAI_API_KEY / VLLM_BASE_URL / DIFY_API_KEY）
```

2. 安装依赖（二选一）：

```bash
# 方式一：可编辑安装（推荐，便于开发）
pip install -e .

# 方式二：仅安装依赖
pip install -r requirements.txt
```

若出现 `ModuleNotFoundError: No module named 'langgraph'`，请先单独安装：

```bash
pip install langgraph
```

（依赖解析可能需 1～3 分钟，请等待完成。若仍失败，可新建虚拟环境后执行 `pip install -r requirements.txt`。）

3. **胶水层**：LLM_TYPE 对应配置 OPENAI_API_KEY / VLLM_BASE_URL / DIFY_API_KEY；Embeddings 可选 local（`.[local]`）或 openai；向量库见 `VECTOR_STORE_TYPE`。  
4. **回复润色**：可选 `REPLY_LLM_TYPE`，不设则直接返回模板文案。

## 使用方式

### 命令行

安装后使用（推荐）：

```bash
pip install -e .
meeting-agent --text "明天下午3点开项目会，1小时，会议室A，提前15分钟提醒我"
meeting-agent --voice path/to/audio.wav
meeting-agent   # 交互式输入
```

或未安装时在项目根目录：

```bash
# Windows: set PYTHONPATH=src
# Linux/macOS: PYTHONPATH=src
python -m meeting_agent.main --text "明天下午3点开项目会，1小时，会议室A"
python -m meeting_agent.main --voice path/to/audio.wav
python -m meeting_agent.main
```

### HTTP 接口

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- `POST /api/v1/book`、`POST /api/v1/book/voice`、`GET /api/v1/health`
- 表单：`application/x-www-form-urlencoded`，字段 `text=会议描述`

## 流程说明

1. **输入**：语音文件 → STT（Whisper 或本地）→ 文本；或直接文本。
2. **RAG**：用当前用户输入在 Chroma 中检索会议知识（会议室、规则），得到 `rag_context`。
3. **解析意图**：胶水层 LLM 根据用户输入 + `rag_context` 输出结构化 `MeetingIntent`。
4. **创建会议**：写入会议存储，并用 APScheduler 在「开始时间 − X 分钟」触发提醒。
5. **回复**：若配置 `REPLY_LLM_TYPE`，用对应 LLM 润色；否则返回模板回复。

更细的流程与 Agent 图结构见 [docs/DESIGN.md](docs/DESIGN.md) 第 3 节。

提醒默认 **提前 15 分钟**，可在 `.env` 中设置 `DEFAULT_REMIND_MINUTES`，或在说法中明确“提前 X 分钟提醒”。

## 模型胶水层（扩展与私有化）

- **LLM**：实现 `meeting_agent.core.llm.base.BaseLLM`，在 `core.llm.factory.get_llm` 中按 `LLM_TYPE` 分支创建；已支持 openai / vllm / dify。
- **Embeddings**：实现 `BaseEmbeddings`，在 `get_embeddings` 中扩展；openai 适配器支持 `OPENAI_BASE_URL` / `OPENAI_EMBEDDING_BASE_URL`。
- **私有化**：见 [docs/PRIVATE_DEPLOYMENT.md](docs/PRIVATE_DEPLOYMENT.md)。

## 开发与测试

- **安装开发依赖**：`pip install -e ".[dev]"`（含 pytest、httpx、ruff）。
- **运行测试**：在项目根目录执行 `pytest tests/ -v`。
- **代码检查**：`ruff check src tests`。
- **命令行**：安装后执行 `meeting-agent`，或 `python -m meeting_agent.main`（需 `PYTHONPATH=src` 或已安装）。
- **API**：根目录执行 `uvicorn app:app --reload`。
- **CI**：`.github/workflows/ci.yml` 在 push/PR 时执行 ruff + pytest。

## 生产部署要点

- **请求 ID**：所有响应带 `X-Request-ID`（可透传或自动生成），异常响应 body 中含 `request_id` 便于排查。
- **安全头**：自动添加 `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`。
- **请求日志**：每条请求结束后打一条日志（method、path、status、duration_ms、request_id）。
- **优雅关闭**：lifespan 关闭时自动调用 `ReminderScheduler.shutdown()`，等待进行中任务结束。
- **健康检查**：`GET /api/v1/health` 返回 `status`、`version`、`checks`，可用于探针与版本查看。
- **全局异常**：未捕获异常统一返回 500 + `INTERNAL_ERROR`，仅记录服务端日志，不向客户端暴露堆栈。

## 扩展建议

- **会议存储**：将 `MeetingStore` 换为数据库持久化。
- **提醒方式**：在 `ReminderScheduler` 回调中接入邮件、企业微信、钉钉等。
- **新 LLM/Embedding**：按上述胶水层接口实现新 adapter 并注册到 factory。

## 还可改进的方向

- **配置**：多环境 `.env.dev` / `.env.prod`，或 pydantic `env_nested_delimiter`。
- **API 文档**：OpenAPI 补充示例、鉴权说明与错误响应 schema。
- **限流/鉴权**：按需加 rate limit、JWT 或 API Key 中间件。
