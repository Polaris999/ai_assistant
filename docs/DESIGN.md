# 会议预定 Agent — 概要设计说明

## 1. 系统概述

### 1.1 目标与能力

本系统是一个**会议预定 Agent**，支持用户通过**文本或语音**描述会议需求，由 Agent 解析意图、结合会议知识库（RAG）生成结构化预定信息，完成预定创建并在会议开始前 **N 分钟**触发提醒。

- **输入**：自然语言（如「明天下午 3 点开项目会，1 小时，会议室 A，提前 15 分钟提醒」）或语音文件。
- **输出**：预定结果文案；可选返回预定记录与提醒任务标识。
- **能力边界**：单轮意图解析 + 预定创建 + 定时提醒；不包含多轮对话、取消/改签等（可扩展）。

### 1.2 用户场景

- **Web/API**：前端或第三方调用 `POST /api/v1/book`（文本）、`POST /api/v1/book/voice`（语音），获取预定结果。
- **命令行**：`meeting-agent --text "..."`、`meeting-agent --voice path/to.wav` 或交互式输入。

---

## 2. 架构概览

### 2.1 分层结构

```
┌─────────────────────────────────────────────────────────────────┐
│  接入层 (api/)          │ 路由、中间件、依赖注入、异常处理        │
├─────────────────────────────────────────────────────────────────┤
│  Agent 层 (agent/)      │ LangGraph 图、状态定义、节点实现        │
├─────────────────────────────────────────────────────────────────┤
│ 服务/领域 (services/,   │ 预定存储、提醒调度、RAG、领域模型       │
│  rag/, models/)         │                                        │
├─────────────────────────────────────────────────────────────────┤
│ 胶水层 (core/)          │ LLM/Embeddings 抽象与适配器、异常、回调 │
├─────────────────────────────────────────────────────────────────┤
│ 配置与支撑 (config/,    │ 配置、Prompt 加载、外部客户端、语音     │
│  clients/, voice/)      │                                        │
└─────────────────────────────────────────────────────────────────┘
```

- **依赖方向**：自上而下；Agent 不依赖 API，API 依赖 Agent；Core 不依赖 Agent/API，便于单测与替换实现。

### 2.2 模块职责

| 模块 | 路径 | 职责 |
|------|------|------|
| 配置 | `config/` | 环境变量与 `.env`、pydantic-settings；Prompt 模板加载与缓存 |
| 胶水层 | `core/` | LLM/Embeddings 抽象（BaseLLM/BaseEmbeddings）与 openai/vllm/dify 适配器；统一异常（AppException）；可观测回调（AgentLoggingCallbackHandler） |
| 外部客户端 | `clients/` | Dify API 客户端（chat-messages/completion-messages） |
| 领域模型 | `models/` | MeetingIntent、MeetingBooking（Pydantic） |
| RAG | `rag/` | 向量库（chroma/qdrant/weaviate）、默认会议知识、检索上下文 |
| 应用服务 | `services/` | MeetingStore（预定 CRUD）、ReminderScheduler（APScheduler 定时提醒） |
| Agent | `agent/` | MeetingAgentState、LangGraph 图定义与节点、AgentRunner.invoke |
| API | `api/` | FastAPI 路由（v1/book、v1/health）、依赖注入（get_agent、get_settings）、中间件（RequestID、安全头、请求日志） |
| 语音 | `voice/` | 语音转文字（Whisper / SpeechRecognition） |

---

## 3. 核心流程

### 3.1 会议预定主流程

1. 用户输入文本或上传语音；语音经 `voice.stt` 转文字。
2. **RAG**：根据用户输入检索会议知识库，得到 `rag_context`。
3. **解析意图**：LLM 根据 Prompt 模板 + 当前时间 + 默认提醒分钟数 + `rag_context` + 用户输入，输出 JSON；反序列化为 `MeetingIntent`。
4. **创建预定**：`MeetingStore.create_booking` 生成 `MeetingBooking`；`ReminderScheduler.schedule_reminder` 在「开始时间 − 提醒分钟」触发回调。
5. **回复润色**（可选）：使用 `reply_llm` 对结果文案做简短润色。
6. 返回 `reply`（及可选 `booking`、`error`）给调用方。

### 3.2 Agent 图结构（LangGraph）

```
  START
    │
    ▼
  [rag]  ── 检索会议知识，写入 state.rag_context
    │
    ▼
  [parse_intent]  ── LLM 解析 JSON → state.intent / state.error
    │
    ├── 有条件边 _route_after_parse
    │       ├── intent 且无 error → [create_booking]
    │       └── 否则 → END
    │
  [create_booking]  ── Store + Scheduler，写入 state.booking / state.reply
    │
    ▼
  [reply_polish]  ── 可选 reply_llm 润色 state.reply
    │
    ▼
   END
```

- 状态：`MeetingAgentState`（TypedDict），含 `user_input`、`rag_context`、`intent`、`booking`、`reply`、`error` 及运行时注入的 `_llm`、`_store`、`_scheduler`、`_rag`、`_reply_llm`。

### 3.3 HTTP 请求链路（简要）

1. 请求进入 → **RequestID**（生成/透传 X-Request-ID）→ **SecurityHeaders** → **RequestLogging**。
2. 路由匹配 → 依赖 `get_agent(request)` 从 `app.state.agent` 取 Agent（未设置时懒创建）。
3. 调用 `agent.invoke(text, request_id=request.state.request_id)`；若传 `request_id`，则注入 `AgentLoggingCallbackHandler` 打点。
4. 响应返回；异常由 `app.exception_handler` 统一处理，响应体带 `request_id`。

---

## 4. 关键设计说明

### 4.1 模型胶水层（LLM / Embeddings）

- **目的**：统一多后端，业务只依赖 `BaseLLM.invoke()`，便于切换与测试。
- **LLM**：`core/llm/base.py` 定义 `BaseLLM`；`factory.get_llm(llm_type)` 按 `LLM_TYPE` 返回 vllm / openai / dify 适配器。
- **Embeddings**：`core/embeddings` 按 `EMBEDDING_TYPE` 返回 openai / api（单独 embedding 服务），供 RAG 使用。向量库由 `core/vectorstore/factory.get_vector_store` 按 `VECTOR_STORE_TYPE` 返回 chroma / qdrant / weaviate。

### 4.2 配置与 Prompt 配置化

- **配置**：`config/settings.py` 使用 pydantic-settings，从 `.env` 与环境变量加载；包含 LLM/Embeddings 类型与密钥、vLLM/Dify 端点、RAG 持久化目录、提醒默认分钟数、Prompt 路径、可观测开关等。
- **Prompt**：默认模板位于 `config/prompts/`（`parse_intent.txt`、`reply_polish.txt`）；可通过 `PROMPT_PARSE_INTENT_PATH`、`PROMPT_REPLY_POLISH_PATH` 覆盖（绝对路径或相对项目根）。由 `config/prompt_loader.py` 加载并进程内缓存。

### 4.3 可观测

- **请求级**：中间件为请求注入 `request_id`，并写请求结束日志（method、path、status、duration_ms、request_id）。
- **Agent 级**：调用 `agent.invoke(..., request_id=...)` 时注入 `AgentLoggingCallbackHandler`，对图节点与 LLM 调用打点（node_start/node_end、llm_start/llm_end、duration_ms），日志 `extra` 带 `request_id`。
- **LangSmith**：设置 `LANGCHAIN_TRACING_ENABLED=true` 与 `LANGCHAIN_API_KEY` 后，lifespan 中设置 `LANGCHAIN_TRACING_V2`、`LANGCHAIN_PROJECT`，可上报 LangSmith。

### 4.4 生命周期与依赖注入

- **FastAPI**：lifespan 启动时创建 `create_meeting_agent_graph()` 并写入 `app.state.agent`；关闭时从 `app.state.agent` 取 Scheduler 执行 `shutdown(wait=True)`。
- **get_agent(request)**：从 `request.app.state.agent` 读取；若未设置（如部分测试环境）则懒创建并写回 state。
- **Agent 图内**：LLM、Store、Scheduler、RAG 通过图构造参数或 state 注入，单测时可传入 Mock。

---

## 5. 目录与入口

| 入口 | 说明 |
|------|------|
| `app.py` | FastAPI 应用入口，挂载路由、中间件、静态资源、全局异常处理；`uvicorn app:app` 启动。 |
| `meeting_agent.main` | 命令行入口，`meeting-agent --text/--voice` 或交互式；内部同样调用 `create_meeting_agent_graph().invoke()`。 |
| 测试 | `tests/`：`test_api.py`（API 集成）、`test_meeting_agent.py`（Agent 图 Mock LLM/RAG）、`test_models.py`（领域模型）。 |

---

## 6. 扩展与约束

- **扩展**：新增 LLM 后端可在 `core/llm/` 增加适配器并在 `factory.get_llm` 中分支；新增 Embeddings 同理。Prompt 可通过配置文件或远程加载扩展。
- **约束**：当前预定存储为进程内 Dict，重启丢失；提醒为进程内 APScheduler，多实例需外部调度或共享存储。生产场景可替换 MeetingStore/ReminderScheduler 为持久化与分布式调度实现。

---

本文档与 `AGENT_REVIEW.md`（框架与范式审查）、`README.md`（使用与环境）互补，共同构成项目代码与设计文档。
