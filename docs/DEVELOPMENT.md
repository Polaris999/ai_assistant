# 开发手册

本文档面向开发：框架复用与扩展、开发测试、代码规范。

---

## 1. 框架复用与新增 Agent

### 1.1 可复用框架层

| 模块 | 说明 |
|------|------|
| `ai_assistant.agent` | Agent 协议：`AgentRunner`、`InvokeResult`、`is_agent_ready()`、`run_agent_warmup()`（实现于 agent/protocol.py） |
| `ai_assistant.api.response` | 统一响应：`code` / `msg` / `data`，`success()`、`json_response()` |
| `ai_assistant.api.middleware` | RequestID、安全头、请求日志 |
| `ai_assistant.api.agent_bootstrap` | `create_agent_or_placeholder(agent_factory=...)` |
| `ai_assistant.core` | exceptions、llm、embeddings、vectorstore、callbacks、helper |
| `ai_assistant.config` | Settings、校验、Prompt 加载 |

**统一入口**：`from ai_assistant.framework import ...` 可一次导入上述大部分符号（含中间件、InvokeResult、run_agent_warmup）。

### 1.2 Agent 协议约定（AgentRunner）

- **invoke(user_input, user_id, request_id)**：返回至少 `reply`、`error` 的 dict；可含 `booking`、`intent` 等。类型可参考 `InvokeResult`。
- **_scheduler**：无则 None。非 None 时用于 lifespan 关闭时 `shutdown(wait=True)` 与就绪判断。
- **可选 is_ready() -> bool**：若实现，`is_agent_ready(agent)` 优先调用它。
- **可选 warmup()**：若实现，lifespan 会带超时调用；未实现时框架会尝试 `_rag.init_default_knowledge()`（兼容会议 Agent）。也可直接使用 `run_agent_warmup(agent, timeout_seconds)`。

实现类或工厂函数交给 `create_agent_or_placeholder(agent_factory=...)` 即可接入现有 API 与生命周期。

### 1.3 新增一个 Agent 的步骤

1. **实现 AgentRunner**：新建模块（如 `ai_assistant.agent.xxx_agent`），实现 `invoke()` 与 `_scheduler`（可选 `is_ready()`、`warmup()`）；内部 `from ai_assistant.framework import get_llm, get_embeddings, ...`。
2. **配置**：在现有 Settings 上扩展或新建该 Agent 的配置；校验可复用 `config.validation` 思路。
3. **注册**：在 app lifespan 中 `app.state.agent = create_agent_or_placeholder(agent_factory=create_xxx_agent_graph)`。
4. **API**：新路由继续使用 `api.response` 的 `success()`、`json_response()`；异常抛出 AppException/ValidationError，由 app 全局 handler 统一成 code/msg/data。
5. **可选**：RAG 复用 `get_vector_store`、`get_embeddings`；健康检查沿用 `/health`，`is_agent_ready(app.state.agent)` 已抽象。

---

## 2. 开发与测试

- **环境与 profile**：按 `APP_PROFILE` 或 `ENV` 加载对应配置（dev/test/prod），未设时默认 **dev**。加载顺序：`.env.{profile}` → `.env`（后者覆盖）。例如 `APP_PROFILE=prod` 时加载 `.env.prod` 再 `.env`。本地密钥或覆盖写在 `.env` 即可。
- **安装开发依赖**：`pip install -e ".[dev]"`（含 pytest、httpx、ruff）。
- **运行测试**：项目根目录执行 `pytest tests/ -v`。
- **代码检查**：`ruff check src tests`。
- **命令行**：安装后 `ai-assistant`，或 `python -m ai_assistant.main`（需 `PYTHONPATH=src` 或已安装）。
- **API**：根目录 `uvicorn app:app --reload`。
- **自检**：`ai-assistant --check-vector-store`、`ai-assistant --check-embedding` 检查向量库与 Embedding 可达性。

### 2.1 开发检查（CI/本地）

提交前或在 CI 中建议执行（需先 `pip install -e ".[dev]"`）：

```bash
ruff check src tests
pytest tests/ -v --tb=short
```

两者均通过后再提交，可减少风格与回归问题。

---

## 3. 代码规范

- **命名**：模块/函数 snake_case，类 PascalCase，内部实现 `_` 前缀。
- **类型注解**：函数参数与返回值、TypedDict 字段带类型；`Optional` 统一。
- **异常**：使用 `core.exceptions` 的 AppException 体系；API 层不吞异常，由全局 handler 统一处理并带 request_id。
- **导入**：标准库 → 第三方 → 本地（ai_assistant）；isort/ruff 已配置。
- **注释**：模块首行 docstring；公开类与关键函数有 docstring；复杂逻辑处简短行内注释。
- **分层**：agent 不依赖 api；api 依赖 agent/config/core；core 不依赖 agent/api/services，保证依赖单向、可测。

---

## 4. 会议 Agent 专用模块（参考）

| 模块 | 说明 |
|------|------|
| `agent.tool_agent` | **默认** Tool Agent：LLM 选 tool（query_meeting_rooms/book_meeting/reply_only），执行走 IMeetingService |
| `agent.tools` | Tool 定义与执行，调用 IMeetingService |
| `agent.intent` | 规则意图（LangGraph 模式用）；意图与路由设计见 [技术架构 §6](ARCHITECTURE.md#6-意图理解与路由设计选型与落地) |
| `ai_assistant.agent.meeting_agent` | LangGraph 图（USE_TOOL_AGENT=false 时使用） |
| `services.meeting_service` | **IMeetingService** 协议与默认实现；生产可替换为 HTTP 调业务后端 |
| `models.meeting` | MeetingIntent、MeetingBooking |
| `rag.meeting_rag` | 会议知识 RAG、默认知识 |
| `services` | MeetingStore、ReminderScheduler |
| `api.controllers.chat` | POST /chat、/chat/voice（统一对话入口） |
| `agent.capabilities` | 能力层：meeting（会议预定）、ops 占位（运维工单）；各能力提供 schema_fragment、tool_names、execute |

### 4.1 能力扩展（如运维工单）

- 在 `agent/capabilities/` 下新增模块（如 `ops.py`），实现与 `MeetingCapability` 同构的接口：`schema_fragment()`、`tool_names()`、`execute(tool_name, arguments, context)`；可选 `warmup()`、`get_scheduler()`。
- 会话上下文：`context["get_session_value"](key)` 可读本会话键值；成功创建工单后由 API 层调用 `store.set_session_value(cid, "last_ticket_id", id)`，供「查刚建的工单」等联想。
- 在 `capabilities/__init__.py` 的 `get_default_capabilities()` 中注册新能力实例即可，Tool Agent 会自动合并工具说明并分发执行。

更细的协议说明与框架评论见 [技术架构](ARCHITECTURE.md)。

---

## 5. 后续改进（可选）

- **超时与重试**：LLM/Embedding 从 settings 统一超时，对可重试错误（网络、429）有限次重试。
- **检索策略**：RAG 配置 semantic/keyword/hybrid，在向量库支持时扩展。
- **胶水层单测**：为各 factory 写单测（Mock settings/HTTP），覆盖 ConfigError、占位返回格式。
- **本地联调**：文档或 docker-compose 说明「启动 vLLM + Embedding + 本应用」及 curl 示例。
- **CLI**：`ai-assistant --check-config` 调用配置校验便于脚本检查。
