# 技术架构

本文档说明系统目标、分层架构、核心流程与框架设计。

---

## 1. 系统概述

- **目标**：作为统一对话助手，通过文本或语音输入完成多种任务；当前内置会议相关能力（查会议室/预定/取消），后续可扩展运维工单等能力。
- **输入**：自然语言或语音文件。
- **输出**：统一 `code/msg/data/request_id`；`data` 内含 `reply`、可选业务结果（如 `booking`）与 `conversation_id`。
- **能力边界**：每轮由 LLM 选择一个 tool 并填参，执行层按「能力」分发；会话内可用 session 键值（如 `last_booking_id`）做上下文联想；能力可插拔扩展。

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
| services | IMeetingService、MeetingStore、ReminderScheduler、meeting_rules（规则来源） |
| agent | AgentRunner 协议（protocol.py）、Tool Agent、能力层（capabilities：Protocol + BaseCapability）、tools 聚合；能力依赖由组合根注入 |
| api | 路由（controllers）、response、middleware、agent_bootstrap（组合根）；**应用层** api/services（如 ChatService）做对话用例编排，Controller 仅做参数校验与 HTTP，与 Dify 等「Controller 薄 + Service 编排」一致 |

---

## 3. 核心流程

### 3.1 会议预定主流程（默认：Tool Agent）

1. 用户输入文本或上传语音；语音经 STT 转文字。
2. **Tool Agent**：LLM 根据 system prompt 与用户输入输出 `tool` + `arguments`（意图与参数一步到位）。
3. **校验**：能力层在 `execute` 内做规则校验（如最多提前 N 天、单次时长上限），不通过则直接返回错误，不调后端。
4. **执行**：`execute_tool` 分发到对应 capability；订会时调用 IMeetingService.book_meeting（内部用 MeetingStore + ReminderScheduler 或 HTTP 调业务后端）。
5. 返回 `reply`、`booking`、`error`，由 API 层封装为 code/msg/data。

（当 `USE_TOOL_AGENT=false` 时走 LangGraph 图：rag → parse_intent → create_booking → reply_polish，见 §6.3。）

### 3.2 LangGraph 图结构（USE_TOOL_AGENT=false 时）

```
  START → [rag] → [parse_intent] ── 条件边 ──→ [create_booking] → [reply_polish] → END
```

- 状态：`MeetingAgentState`；依赖由组合根注入。

### 3.3 HTTP 请求链路

1. 请求 → RequestID → SecurityHeaders → RequestLogging。
2. 路由 → `get_agent(request)` 从 `app.state.agent` 取 Agent。
3. **多轮会话**：若请求带 `conversation_id` 则从会话存储取最近 N 轮历史，否则新建会话；`agent.invoke(text, request_id=..., conversation_id=..., history=...)`；执行后将本轮 user/assistant 写入会话存储。
4. 响应（data 中含 `conversation_id` 供下一轮携带）；异常由 app 全局 handler 统一为 code/msg/data + request_id。

### 3.4 多轮会话与澄清

- **会话**：`conversation_id` 由客户端首轮不传（服务端生成并返回）或客户端生成；同一会话内保留最近若干轮 user/assistant 历史（默认 20 条，见 `core/conversation.py`）。
- **存储**：默认进程内 `ConversationStore`，生产可替换为 Redis 等；仅用于多轮上下文，不落库业务数据。
- **澄清**：Tool Agent 的 system 提示中约定「若信息不足先用 reply_only 追问」；LLM 看到历史 + 当前输入后可输出追问，下一轮用户补充后再选 `book_meeting`。

### 3.5 知识库 CRUD 与多库

- **按库名分集合**：不采用「单集合 + metadata 分类」，而是**每个业务独立 collection**（与 [Langchain-Chatchat 多知识库](https://github.com/chatchat-space/Langchain-Chatchat/blob/master/libs/chatchat-server/chatchat/server/api_server/kb_routes.py) 一致）。会议用 `meeting_knowledge`，运维工单用 `ops_ticket_knowledge`，检索/清空互不影响；新增业务时在 `rag/meeting_rag.py` 的 `ALLOWED_KB_NAMES` 增加名称即可。
- **启动**：仅会议库有默认知识，由 Agent warmup 调用 `init_default_knowledge()` 写入；运维工单库无默认数据，需通过 API 或后续能力录入。
- **接口**（所有 CRUD 支持 query 参数 `kb`，默认 `meeting`，前缀 `/api/v1`）：
  - `GET /api/v1/knowledge/bases` — 已登记知识库列表（如 meeting、ops_ticket）
  - `GET /api/v1/knowledge?kb=` — 统计指定 kb 的 chunk 数量
  - `GET /api/v1/knowledge/search?q=&kb=` — 检索预览
  - `POST /api/v1/knowledge?kb=` — 追加文档
  - `DELETE /api/v1/knowledge?kb=` — 清空指定 kb（Chroma 支持）
- **鉴权**：应用内不实现鉴权，建议由网关将上述接口限制为管理端或授权调用。

---

## 4. 框架设计要点

### 4.1 模型胶水层

- **LLM**：`BaseLLM` + factory 按 `LLM_TYPE` 返回 vllm / openai / dify。
- **Embeddings**：`BaseEmbeddings` + factory 按 `EMBEDDING_TYPE` 返回 openai / api。
- **向量库**：`get_vector_store` 按 `VECTOR_STORE_TYPE` 返回 Chroma/Qdrant/Weaviate，进程内同配置缓存连接。

### 4.2 配置与 Prompt

- 配置：pydantic-settings，从 .env 与环境变量加载。
- Prompt：默认 `config/prompts/`，可通过以下环境变量覆盖：
  - `PROMPT_PARSE_INTENT_PATH`：解析意图模板
  - `PROMPT_REPLY_POLISH_PATH`：回复润色模板
  - `PROMPT_TOOL_AGENT_SYSTEM_PATH`：Tool Agent 的 system 提示（规则说明）

### 4.3 可观测

- **当前已有**：请求级 request_id、请求结束日志（method、path、status、duration_ms、request_id）；chat 层（req_id、cid、text_len、elapsed_ms）；Tool Agent（invoke 总耗时、tool 名、解析失败回退时打 INFO）。
- **可选 LangSmith**：配置 `LANGCHAIN_TRACING_ENABLED`、`LANGCHAIN_API_KEY` 后仅对 LangChain/LangGraph 路径自动上报；Tool Agent 使用自定义 BaseLLM，不会自动进 LangSmith，需手动 trace 或包成 Runnable。

**可观测最佳实践（分层、优先顺序）**：

| 层级 | 做法 | 说明 |
|------|------|------|
| **1. 基础（必选）** | 结构化日志 + 全链路 request_id + 关键耗时与错误码 | 与业界一致：每条请求可关联、可检索、可算成功率/延迟；当前已有 request_id 与部分耗时，可补「单条 JSON 日志」含 request_id、tool、duration_ms、error、parse_fallback。 |
| **2. 链路（推荐）** | OpenTelemetry 或现有 APM 打 span | 请求 → agent.invoke → llm / execute_tool 形成父子 span，便于看瓶颈与故障点；与语言/框架无关，后端可接 Jaeger/Datadog 等。 |
| **3. LLM 专项（按需）** | LangSmith / 同类产品 | 用于 prompt 与补全查看、评估、回放；在 1、2 做好后再加，作为补充而非替代。 |

结论：**更符合最佳实践的是「先 1 再 2，再按需 3」**；不推荐跳过 1、2 只上 LangSmith。

**当前实现**：
- **Layer 1**：每次 chat 请求结束时 Tool Agent 打一条 JSON 日志（`observability {"event":"chat_request","request_id":...,"tool":...,"duration_ms":...,"error":...,"parse_fallback":...}`），便于采集与检索；request_id 贯穿中间件与 chat。
- **Layer 2**：可选 OpenTelemetry（`pip install -e '.[otel]'` 后配置 `OTEL_EXPORTER_OTLP_ENDPOINT`），启动时 `init_otel()` 初始化；中间件为每个请求建 `http.request` span，Tool Agent 内建 `tool_agent.invoke`、`llm.invoke`、`execute_tool` 父子 span，可接 Jaeger/Datadog 等。

### 4.4 组合根与生命周期

- **组合根**：`create_agent_or_placeholder()`（在 api/agent_bootstrap）根据配置创建 Tool Agent 或 LangGraph Agent；Tool Agent 通过 `get_default_capabilities(meeting_service=...)` 获取能力列表，未传则内部创建 DefaultMeetingService，便于测试注入 Mock。命令行 `ai-assistant --text/--voice` 与 Web 共用该创建逻辑。
- **启动**：创建 Agent、执行 `run_agent_warmup(agent)`（优先 agent.warmup()，否则 _rag.init_default_knowledge）。
- **关闭**：从 agent 取 _scheduler，若有则 `shutdown(wait=True)`。

### 4.5 Agent 与能力协议

- **AgentRunner**：定义于 `agent/protocol.py`，对外统一从 `ai_assistant.agent` 导入；`agent_base.py` 仅作兼容 re-export。
- **Capability**：Protocol 仅要求 `schema_fragment`、`tool_names`、`execute`；可选方法 `warmup`、`get_scheduler` 由 `BaseCapability` 提供默认实现，子类按需重写。

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

### 6.4 标准处理流程（意图 → 参数 → 校验 → 执行 → 响应）

业内通用：NLU/意图与实体 → 槽位填充 → **校验（代码内，通过后才调后端）** → 执行 → 响应。参考：Rasa [Dialogue Management](https://rasa.com/docs/learn/concepts/dialogue-management)、[Slot Validation](https://rasa.com/docs/rasa/next/slot-validation-actions/)；Microsoft [Add NLU to your bot](https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-howto-v4-luis)。

**本项目等价流水线**：

```
用户输入
    ↓
① 意图识别（选 tool）     ← 对应 NLU / Intent
    ↓
② 参数抽取（arguments）   ← 对应 Slot Filling / Entity → slots
    ↓
③ 参数/规则校验           ← 对应 Slot Validation（代码内，不通过不执行）
    ↓
④ 分支执行（按 tool）     ← 对应 Action / Backend Call
    ↓
⑤ 响应                    ← 对应 Response
```

| 环节 | 职责 | 本项目当前落点 | 建议 |
|------|------|----------------|------|
| **① 意图识别** | 判断用户要「查/订/取消/闲聊」 | LLM 一次输出 `tool` + `arguments`（意图与参数同步） | Prompt 中明确：说了相对时间就推断 start_time 并走 book_meeting，避免误走 reply_only |
| **② 参数抽取** | 从自然语言中解析出 start_time、title、duration 等 | 同上，LLM 填 arguments | 相对时间（如「8天后」）须在 prompt 中要求推断为 ISO 时间 |
| **③ 参数/规则校验** | 格式 + **业务规则**（如最多提前 7 天、单次不超过 4 小时） | 能力层 `execute()` 内：解析后先做规则校验，再调 service | **规则必须在代码中校验**，与业内「Validation 在 Action 前」一致；新增规则在 capability execute 前增加校验并返回明确 error |
| **④ 分支执行** | 按 tool 调用对应能力或后端 | `execute_tool()` → capability.execute() → IMeetingService | 保持「校验通过才调后端」 |
| **⑤ 响应** | 统一结构、错误码与文案 | API 层 code/msg/data；能力层 reply/booking/error | 校验失败时 error 码固定（如 EXCEED_MAX_DAYS_AHEAD） |

**原则**：校验在代码、先于执行；硬性规则在 capability execute 内、调 service 前校验；新能力按同一流水线实现。

### 6.5 业内最佳实践自检清单

| 检查项 | 业内建议 | 本项目状态 |
|--------|----------|------------|
| **流水线** | NLU → Slot Filling → Validation → Action → Response | ✅ LLM 出 tool+arguments，execute 内先校验再调 service |
| **规则在代码** | 业务规则在代码中校验，不依赖 LLM/RAG | ✅ capability 内校验，规则来自 rules_provider 或 settings |
| **校验先于执行** | 通过后才调后端 | ✅ 不通过即 return，不调 `_service.book_meeting` |
| **固定错误码** | 校验失败返回稳定错误码 | ✅ EXCEED_MAX_DAYS_AHEAD、EXCEED_MAX_DURATION、PARSE_ERROR、MISSING_BOOKING_ID |
| **API 响应统一** | code/msg/data/request_id；业务与系统错误区分 | ✅ response 统一 body；chat 层 error 入 data，503 区分 |
| **请求可观测** | request_id、请求结束日志 | ✅ middleware 注入 request_id、打日志 |
| **解析失败回退** | 关键词回退 | ✅ `_looks_like_query_rooms` → query_meeting_rooms，否则 reply_only |
| **规则覆盖完整** | 与对外宣称一致 | ✅ 时长、提前天数在 capability 内校验，数值来自配置或后台 |
| **规则可配置** | 改配置或由后台提供 | ✅ 本地 settings；或 MEETING_RULES_API_URL（§6.6） |
| **规则校验单测** | 关键规则有单测 | ✅ `test_tool_agent_and_capabilities` 中 EXCEED_MAX_DAYS_AHEAD、EXCEED_MAX_DURATION |

新增能力时按 §6.4 与上表自检。

### 6.6 规则来源：本地 vs 业务后台

**IMeetingRulesProvider**（`services/meeting_rules.py`）：本地 `SettingsMeetingRulesProvider`；后台 `BackendMeetingRulesProvider`（内存缓存）。规则相关配置与系统配置分离：`config/meeting_rules_config.py`（环境变量 MEETING_*），系统配置仍在 `config/settings.py`。

---

## 7. 入口与扩展约束

| 入口 | 说明 |
|------|------|
| app.py | FastAPI 入口，`uvicorn app:app` |
| ai_assistant.main | 命令行 `ai-assistant --text/--voice` |

- **扩展**：新 LLM/Embedding 在 core 增加适配器并在 factory 分支；新 Agent 实现 AgentRunner（见 agent/protocol.py）并注册 agent_factory；新能力实现 Capability（继承 BaseCapability 可选），在 `get_default_capabilities` 中注册；查/订逻辑实现 IMeetingService 并通过 `get_default_capabilities(meeting_service=...)` 注入。
- **约束**：默认预定与提醒为进程内，重启丢失；多实例需替换为持久化与分布式调度或对接业务接口。

---

## 8. 后续可优化方向（可选）

| 方向 | 说明 |
|------|------|
| **测试** | 为 BackendMeetingRulesProvider 增加单测（Mock requests）；为「8 天后 / 超 4 小时」E2E 或 API 层补一条回归用例。 |
| **规则与 RAG 一致** | 若规则改由后台下发，RAG 默认知识里的「7 天」「4 小时」可改为从规则接口或配置生成，避免文案与校验不一致。 |
| **可观测** | 规则拉取失败、校验失败（EXCEED_*）可打 metrics 或单独日志，便于监控与排障。 |
| **安全** | 知识库 CRUD、后台规则接口等建议由网关做鉴权；敏感配置（API Key）不落日志。 |
| **性能** | 高并发时会话存储、向量检索、LLM 调用可做限流与超时；规则缓存已做，可按需调 MEETING_RULES_CACHE_SECONDS。 |
