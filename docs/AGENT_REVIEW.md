# 会议预定 Agent：框架与技术范式审查

## 1. 项目结构（符合最佳实践）

- **src-layout**：业务代码在 `src/meeting_agent/`，根目录仅入口 `app.py`、测试 `tests/`、配置。
- **分层清晰**：
  - `agent/`：LangGraph 图与状态
  - `api/`：路由、依赖、中间件
  - `core/`：LLM/Embedding 抽象与异常
  - `config/`：配置
  - `models/`：领域模型
  - `rag/`：RAG
  - `services/`：存储与调度
  - `clients/`：外部 API（Dify）
  - `voice/`：语音

## 2. 技术选型（与 AI Agent 生态一致）

| 层次     | 选型                 | 说明 |
|----------|----------------------|------|
| Agent 编排 | LangGraph            | 显式状态图、节点/边、条件分支，符合 Agent 范式 |
| LLM 胶水层 | vllm / openai / dify | 配置切换 |
| LLM/提示  | LangChain + PromptTemplate | 模板统一用 langchain_core.prompts |
| RAG      | Chroma + langchain-chroma | 向量检索、与 LangChain 集成 |
| 配置     | pydantic-settings    | 类型安全、环境变量与 .env |
| Web      | FastAPI              | 异步、依赖注入、OpenAPI |

## 3. Agent 开发范式符合度

- **状态显式、类型明确**：`MeetingAgentState` 为 TypedDict，含业务字段与注入依赖（_llm、_store 等）。
- **图结构清晰**：`rag → parse_intent → 条件分支 → create_booking → reply_polish → END`，节点单一职责。
- **依赖注入**：LLM、Store、Scheduler、RAG 通过图构造或 state 注入，便于测试与替换。
- **未用 Tool 抽象**：当前为固定流程（RAG + 解析 + 预定 + 润色），未使用 LangChain Tool；若后续需要“模型选动作”可再引入。

## 4. 代码风格与规范

- **命名**：模块/函数 snake_case，类 PascalCase，内部实现 `_` 前缀。
- **类型注解**：函数参数与返回值、TypedDict 字段均带类型，统一使用 `Optional`。
- **异常**：`core.exceptions` 统一 AppException 体系，API 层全局处理并带 request_id。
- **导入**：标准库 → 第三方 → 本地（meeting_agent），isort/ruff 已配置。
- **注释与文档**：每个模块有首行 docstring 说明职责；公开类与关键函数/节点有 docstring；复杂逻辑处有简短行内注释。
- **分层**：agent 依赖 config/core/models/rag/services，不依赖 api；api 依赖 agent/config/core；core 不依赖 agent/api/services，保证依赖单向、可测。

## 5. 已做改进（与范式/风格对齐）

- Agent 生命周期：在 FastAPI lifespan 中创建 Agent 并放入 `app.state`，`get_agent` 从 `Request` 取，与应用同生命周期。
- 导入顺序：`meeting_agent` 包内导入按子包顺序统一。
- 节点与图 docstring：关键节点和图构造处补充简要说明，便于维护与测试。
- Agent 单测：`tests/test_meeting_agent.py` 使用 Mock LLM/RAG + 真实 Store/Scheduler 跑通整图，覆盖预定成功与空输入分支。
- **Prompt 配置化**：默认模板在 `config/prompts/`，通过 `PROMPT_PARSE_INTENT_PATH` / `PROMPT_REPLY_POLISH_PATH` 可覆盖（绝对路径或相对项目根），由 `config/prompt_loader.py` 加载并缓存。
- **可观测**：`core/callbacks.AgentLoggingCallbackHandler` 对图节点与 LLM 调用打点并写结构化日志（含 `request_id`）；API 调用 Agent 时传入 `request_id`，lifespan 中可开启 LangSmith（`LANGCHAIN_TRACING_ENABLED=true` + `LANGCHAIN_API_KEY`）。

## 6. 业内通用做法对齐

- **LLM 胶水层**：vllm / openai / dify 按配置切换；vllm 使用 `VLLM_BASE_URL`。
- **Embeddings / 向量库**：Embeddings 为 local / openai；向量库为 chroma / qdrant / weaviate，均按配置切换。

## 7. 建议后续优化（非必须）

- 可考虑接入 OpenTelemetry 与现有 tracing 打通。
