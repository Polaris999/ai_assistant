# 技术架构

本文档说明系统目标、分层架构、核心流程与框架设计。

---

## 1. 系统概述

- **目标**：通过文本或语音描述会议需求，由 Agent 解析意图、结合 RAG 生成预定信息，完成预定并在开始前 N 分钟提醒。
- **输入**：自然语言或语音文件。
- **输出**：预定结果（统一 code/msg/data）；可选返回预定记录与提醒标识。
- **能力边界**：单轮意图解析 + 预定创建 + 定时提醒；多轮对话、取消/改签可扩展。

---

## 2. 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  接入层 (api/)          │ 路由、中间件、依赖注入、统一响应与异常   │
├─────────────────────────────────────────────────────────────────┤
│  Agent 层 (agent/)      │ LangGraph 图、状态定义、节点实现        │
├─────────────────────────────────────────────────────────────────┤
│ 服务/领域 (services/,   │ 预定存储、提醒调度、RAG、领域模型       │
│  rag/, models/)         │                                        │
├─────────────────────────────────────────────────────────────────┤
│ 胶水层 (core/)          │ LLM/Embeddings/向量库、异常、回调       │
├─────────────────────────────────────────────────────────────────┤
│ 配置与支撑 (config/,     │ 配置、Prompt 加载、语音                │
│  clients/, voice/)      │                                        │
└─────────────────────────────────────────────────────────────────┘
```

- **依赖方向**：自上而下；Agent 不依赖 API，API 依赖 Agent；Core 不依赖 Agent/API。

### 模块职责（简要）

| 模块 | 职责 |
|------|------|
| config | 环境变量与 .env、pydantic-settings；Prompt 模板加载与缓存 |
| core | LLM/Embeddings 抽象与 vllm/openai/dify 适配器；向量库工厂；统一异常；可观测回调；会话历史（conversation） |
| models | MeetingIntent、MeetingBooking |
| rag | 向量库封装、默认会议知识、检索上下文 |
| services | IMeetingService、MeetingStore、ReminderScheduler |
| agent | Tool Agent（默认）、能力层（capabilities/meeting、占位 ops）、tools 聚合、AgentRunner.invoke |
| api | 路由（v1/chat、v1/chat/voice、v1/health）、response、middleware、agent_bootstrap |

---

## 3. 核心流程

### 3.1 会议预定主流程

1. 用户输入文本或上传语音；语音经 STT 转文字。
2. **RAG**：根据用户输入检索会议知识库 → `rag_context`。
3. **解析意图**：LLM 根据模板 + 时间 + rag_context + 用户输入输出 JSON → `MeetingIntent`。
4. **创建预定**：MeetingStore 创建预定；ReminderScheduler 在「开始时间 − 提醒分钟」调度提醒。
5. **回复润色**（可选）：reply_llm 润色结果文案。
6. 返回 `reply`、`booking`、`error`（由 API 层封装为 code/msg/data）。

### 3.2 Agent 图结构（LangGraph）

```
  START → [rag] → [parse_intent] ── 条件边 ──→ [create_booking] → [reply_polish] → END
                                    (intent 且无 error)              否则 → END
```

- 状态：`MeetingAgentState`（user_input、rag_context、intent、booking、reply、error 及注入的 _llm、_store、_scheduler、_rag、_reply_llm）。
- 依赖注入：图构造时传入 Store、Scheduler、RAG、LLM，单测可 Mock。

### 3.3 HTTP 请求链路

1. 请求 → RequestID → SecurityHeaders → RequestLogging。
2. 路由 → `get_agent(request)` 从 `app.state.agent` 取 Agent。
3. **多轮会话**：若请求带 `conversation_id` 则从会话存储取最近 N 轮历史，否则新建会话；`agent.invoke(text, request_id=..., conversation_id=..., history=...)`；执行后将本轮 user/assistant 写入会话存储。
4. 响应（data 中含 `conversation_id` 供下一轮携带）；异常由 app 全局 handler 统一为 code/msg/data + request_id。

### 3.4 多轮会话与澄清

- **会话**：`conversation_id` 由客户端首轮不传（服务端生成并返回）或客户端生成；同一会话内保留最近若干轮 user/assistant 历史（默认 20 条，见 `core/conversation.py`）。
- **存储**：默认进程内 `ConversationStore`，生产可替换为 Redis 等；仅用于多轮上下文，不落库业务数据。
- **澄清**：Tool Agent 的 system 提示中约定「若信息不足先用 reply_only 追问」；LLM 看到历史 + 当前输入后可输出追问，下一轮用户补充后再选 `book_meeting`。

---

## 4. 框架设计要点

### 4.1 模型胶水层

- **LLM**：`BaseLLM` + factory 按 `LLM_TYPE` 返回 vllm / openai / dify。
- **Embeddings**：`BaseEmbeddings` + factory 按 `EMBEDDING_TYPE` 返回 openai / api。
- **向量库**：`get_vector_store` 按 `VECTOR_STORE_TYPE` 返回 Chroma/Qdrant/Weaviate，进程内同配置缓存连接。

### 4.2 配置与 Prompt

- 配置：pydantic-settings，从 .env 与环境变量加载。
- Prompt：默认 `config/prompts/`，可通过 `PROMPT_PARSE_INTENT_PATH`、`PROMPT_REPLY_POLISH_PATH` 覆盖。

### 4.3 可观测

- 请求级：request_id、请求结束日志（method、path、status、duration_ms、request_id）。
- Agent 级：AgentLoggingCallbackHandler 对节点与 LLM 打点（DEBUG 级别），extra 带 request_id。
- 可选：LangSmith（LANGCHAIN_TRACING_ENABLED、LANGCHAIN_API_KEY）。

### 4.4 生命周期

- 启动：创建 Agent（`create_agent_or_placeholder`）、执行 `run_agent_warmup(agent)`（优先 agent.warmup()，否则 _rag.init_default_knowledge）。
- 关闭：从 agent 取 _scheduler，若有则 `shutdown(wait=True)`。

---

## 5. 框架评论（摘要）

- **优点**：协议简单（invoke + _scheduler），响应/异常/LLM/Embeddings/向量库与业务解耦，工厂 + 协议 + agent_factory 便于扩展。
- **已做改进**：可选 `is_ready()`、统一 `run_agent_warmup()`、`InvokeResult` 类型、framework 聚合导出与中间件。
- **可维护性**：新增异常需在 `APP_EXCEPTION_MAP` 登记；向量库缓存按配置 key，不区分 embedding 实例。

（框架审核结论与已实施改进已合并到本文档。）

---

## 6. 意图理解与路由（设计选型与落地）

### 6.1 常见模式对比

| 模式 | 做法 | 适用场景 | 优点 | 缺点 |
|------|------|----------|------|------|
| **规则路由** | 关键词/短句匹配 → 固定分支 | 意图少、表述稳定 | 无额外 LLM、延迟低 | 泛化差 |
| **LLM 意图分类** | 先调 LLM 输出 intent 再分支 | 意图多、说法多样 | 泛化好 | 多一次 LLM 调用 |
| **Agent + Tools** | LLM 选「工具」并填参，按需调用 | 多能力、需组合（查+订+改） | 灵活，业内主流 | 依赖 prompt/结构化输出 |
| **Skills** | 能力模块化，由路由或 LLM 选择 | 团队分工、复用 | 边界清晰 | 与路由/Tools 结合使用 |

### 6.2 推荐流程（意图优先）

```
用户输入 → [意图识别] → [路由]
   chitchat      → 固定/模板回复
   query_rooms   → 仅 RAG（或业务接口）返回会议室信息
   book_meeting  → 解析参数后调用预定接口
```

- **意图识别**：可规则（关键词）或 LLM 输出 intent/结构化结果。
- **何时上 Tools**：可选动作多、参数由自然语言决定时，用 LLM 选 tool + 填参；**Skills** 为能力封装，可每个 skill 对应一个 tool。

### 6.3 本项目落地（默认：Agent + Tools）

- **默认**（`USE_TOOL_AGENT=true`）：**Tool Agent**。LLM 一次输出 `tool` + `arguments`，执行层调用 **IMeetingService** 后返回。
- **业务接口**：`IMeetingService`（`services/meeting_service.py`）提供 `query_meeting_rooms()`、`book_meeting(...)`；默认实现用 RAG + MeetingStore + ReminderScheduler，生产可替换为 HTTP 调业务后端。
- **Tools**：`reply_only`（闲聊）、`query_meeting_rooms`、`book_meeting`（见 `agent/tools.py`）；Agent 见 `agent/tool_agent.py`。
- **切换**：`USE_TOOL_AGENT=false` 时使用原 LangGraph 图（规则意图 `agent/intent.py` + 解析会议 JSON）。

---

## 7. 入口与扩展约束

| 入口 | 说明 |
|------|------|
| app.py | FastAPI 入口，`uvicorn app:app` |
| ai_assistant.main | 命令行 `ai-assistant --text/--voice` |

- **扩展**：新 LLM/Embedding 在 core 增加适配器并在 factory 分支；新 Agent 实现 AgentRunner 并注册 agent_factory；查/订逻辑实现 IMeetingService 并注入 Tool Agent。
- **约束**：默认预定与提醒为进程内，重启丢失；多实例需替换为持久化与分布式调度或对接业务接口。
