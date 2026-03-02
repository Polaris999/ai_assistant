# 会议预定 Agent 示例（LangChain + LangGraph + Dify + RAG）

通过**语音或文本**输入创建会议预定，并在会议开始前 **X 分钟**触发提醒。

## 技术栈

- **LangChain / LangGraph**：有状态 Agent 工作流（RAG → 解析意图 → 创建会议 → 安排提醒 → 回复润色）
- **Core 胶水层**：LLM / Embeddings 抽象与适配器，可切换 OpenAI、Dify 等，符合依赖倒置
- **RAG**：Chroma + 会议知识库，Embedding 由胶水层注入
- **APScheduler**：定时在“开始前 X 分钟”触发提醒

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
│       ├── api/                # HTTP 层（deps, v1, legacy）
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
└── README.md
```

## 环境准备

1. 复制环境变量并填写密钥：

```bash
cp .env.example .env
# 编辑 .env：至少配置 OPENAI_API_KEY（意图解析 + 可选 Whisper）
# 可选：DIFY_API_KEY、DIFY_BASE_URL（润色回复）
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

3. **模型胶水层**：`LLM_TYPE=openai` 时需配置 `OPENAI_API_KEY`；设为 `dify` 则用 `DIFY_API_KEY`。  
4. **回复润色**：可选 `REPLY_LLM_TYPE=dify`，用 Dify 润色最终回复；不设则直接返回模板文案。

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
3. **解析意图**：由胶水层 LLM（OpenAI 或 Dify）根据用户输入 + `rag_context` 输出结构化 `MeetingIntent`。
4. **创建会议**：写入会议存储，并用 APScheduler 在「开始时间 − X 分钟」触发提醒。
5. **回复**：若配置 `REPLY_LLM_TYPE`，用对应 LLM 润色；否则返回模板回复。

提醒默认 **提前 15 分钟**，可在 `.env` 中设置 `DEFAULT_REMIND_MINUTES`，或在说法中明确“提前 X 分钟提醒”。

## 模型胶水层（扩展新模型）

- **LLM**：实现 `meeting_agent.core.llm.base.BaseLLM`，在 `core.llm.factory.get_llm` 中按 `LLM_TYPE` 分支创建。
- **Embeddings**：实现 `meeting_agent.core.embeddings.base.BaseEmbeddings`，在 `get_embeddings` 中扩展。
- 业务代码只依赖抽象，便于测试与切换。

## 开发与测试

- **安装开发依赖**：`pip install -e ".[dev]"`（含 pytest、httpx、ruff）。
- **运行测试**：在项目根目录执行 `pytest tests/ -v`（会跑单元测试与 API 集成测试）。
- **代码检查**：`ruff check src tests`。
- **命令行**：安装后执行 `meeting-agent`，或 `python -m meeting_agent.main`（需 `PYTHONPATH=src` 或已安装）。
- **API**：根目录执行 `uvicorn app:app --reload`。
- **CI**：`.github/workflows/ci.yml` 在 push/PR 时执行 ruff + pytest（无需配置 API Key 即可通过）。

## 扩展建议

- **会议存储**：将 `MeetingStore` 换为数据库持久化。
- **提醒方式**：在 `ReminderScheduler` 回调中接入邮件、企业微信、钉钉等。
- **新 LLM/Embedding**：按上述胶水层接口实现新 adapter 并注册到 factory。

## 还可改进的方向

- **测试**：`pip install -e ".[dev]"` 后运行 `pytest`；为 API 增加 `TestClient` 集成测试。
- **代码质量**：在 `pyproject.toml` 中配置 `ruff` 或 `black`，可选 pre-commit。
- **CI**：GitHub Actions / GitLab CI 跑 pytest、lint，再构建镜像或发布。
- **配置**：多环境 `.env.dev` / `.env.prod`，或使用 pydantic 的 `env_nested_delimiter` 区分层级。
- **日志**：结构化日志（JSON）、request_id 与 trace 便于排查。
- **API 文档**：FastAPI 自带 OpenAPI；可补充示例与鉴权说明。
