# LLM 交互流程规范

本文档定义**与 LLM 交互的标准流程**，当前由 **LangGraph Agent**（create_react_agent + 技能转 LangChain Tool）遵循，阶段 1 意图短路在 agent/llm_flow.py 统一实现。

---

## 1. 目标与原则

- **单一规范**：用户输入到最终回复的整条链路拆成固定阶段，每阶段职责清晰、可测试、可观测。
- **意图优先**：能由规则确定的意图（如问候、关键词查会议室）在**调用 LLM 之前**处理完毕，不交给 LLM，减少误判与成本。
- **LLM 职责边界**：仅用于「规则难以覆盖」的部分：选工具/意图 + 槽位填充、复杂解析；且调用前必有超时、重试与结构化输出约定。
- **解析失败有回退**：LLM 输出无法解析时，按规则回退到确定工具或安全默认（如 `reply_only`），不直接报错。

---

## 2. 标准阶段定义

整体流水线如下，**每个请求严格按顺序经过各阶段**；若某阶段已产生最终回复则提前结束，不再进入后续阶段。

```
用户输入
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 1：输入校验与意图短路（Pre-LLM）                              │
│ 职责：空输入校验；规则可识别的意图直接返回，不调 LLM。              │
└─────────────────────────────────────────────────────────────────┘
    │ 若已返回 → 结束
    ▼ 否则进入阶段 2
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 2：LLM 调用（仅当需要意图/槽位时）                            │
│ 职责：构造 system + user prompt，带超时与重试调用 LLM，得到文本。   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 3：解析与回退（Parse & Fallback）                            │
│ 职责：按约定格式解析 LLM 输出；失败时按规则回退到确定 tool/行为。   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 4：参数校验与执行（Validate & Execute）                      │
│ 职责：业务规则校验（代码内）；通过后再调技能/后端。                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 5：响应封装（Response）                                      │
│ 职责：统一结构 reply/booking/error；错误时抛 AppException。        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 各阶段规范详解

### 3.1 阶段 1：输入校验与意图短路（Pre-LLM）

| 项 | 规范 |
|----|------|
| **输入** | 原始 `user_input`（已 trim）。 |
| **必做** | 空输入 → 直接返回固定提示（如「请说出或输入您要预定的会议信息。」），不调 LLM。 |
| **意图短路** | 使用**统一意图模块**（如 `agent/intent.py`）做规则识别：若为 `CHITCHAT`（问候/闲聊）或可选的 `QUERY_ROOMS`（纯关键词查会议室），**直接返回对应回复**，不调用 LLM、不进入技能。 |
| **输出** | 若本阶段产生回复：返回 `{ reply, booking, error }` 并结束；否则交给阶段 2。 |
| **原则** | 「能规则判定的就不交给 LLM」——避免问候被误判为订会、减少 404/503 与成本。 |

**实现落点**：

- **统一入口**：`agent/llm_flow.py` 的 `run_pre_llm_stage(user_input, rag_context=None)`。空输入、CHITCHAT、QUERY_ROOMS（仅当传入 rag_context）在此直接返回 `(result_dict, stage_name)`，调用方若得到非 None 则直接返回并结束。
- 意图定义与识别：`agent/intent.py`（`UserIntent`、`detect_intent`、`reply_for_chitchat`、`reply_for_query_rooms`），由 `llm_flow.run_pre_llm_stage` 内部调用。
- 当前入口：`agent/langgraph_runner.py` 的 `invoke()` 开头调用 `run_pre_llm_stage(user_input)`，无 rag_context 故仅短路空输入与 CHITCHAT。

**扩展**：新增「可短路意图」时，在 `intent.py` 增加枚举与规则，并在 `run_pre_llm_stage` 中统一使用。

---

### 3.2 阶段 2：LLM 调用

| 项 | 规范 |
|----|------|
| **触发条件** | 阶段 1 未产生最终回复，需要 LLM 做「意图选择 + 槽位填充」或「复杂解析」。 |
| **输入** | 当前用户输入、可选会话历史、当前时间等；system prompt 来自配置/模板，不硬编码。 |
| **必做** | 调用前设置**超时**与**重试次数**（来自配置）；调用失败或超时 → 转为明确错误信息或回退文案，不裸抛异常到用户。 |
| **输出** | LLM 返回的**原始文本**；结构化解析属于阶段 3。 |
| **可观测** | 打 span（如 `llm.invoke`）、记录耗时；不记录完整 prompt/回复到日志（可截断或脱敏）。 |

**实现落点**：

- 当前：LangGraph Agent 使用 LangChain `ChatOpenAI`（vLLM/OpenAI 端点），由 `core/llm/factory.py` 与 `langchain_adapter.py` 提供；超时由 LangChain request_timeout 控制，异常在 Runner 内捕获并转为 AppException（LLM_ERROR）。
- 抽象：`core/llm/base.py`（`BaseLLM`）；Dify 仍用 `DifyLLMAdapter`。

**原则**：LLM 调用具备超时与错误处理；prompt 模板集中在 `config/prompts/` 或配置指定路径。

---

### 3.3 阶段 3：解析与回退（Parse & Fallback）

| 项 | 规范 |
|----|------|
| **输入** | LLM 原始输出文本 + 当前用户输入（用于回退判断）。 |
| **必做** | 按**约定格式**（如 JSON `tool` + `arguments`）解析；若解析失败，**必须**走回退逻辑，不得直接以「解析失败」对用户报错。 |
| **回退规则** | 按业务约定：例如「若含查会议室关键词 → 回退为 query_meeting_rooms」；「若含订会+时间关键词 → 回退为 book_meeting 并推断时间」；其余 → 回退为 `reply_only` 并带引导文案。 |
| **输出** | 确定的 `tool`（或等价意图）+ `arguments`（或等价的解析结果）；供阶段 4 执行。 |
| **可观测** | 解析失败时打 warning 并记录短片段（如前 200 字符）；回退时打 info 标明回退原因（如「按关键词回退为 query_meeting_rooms」）。 |

**实现落点**：

- 当前（LangGraph）：模型返回结构化 `tool_calls`，无文本解析；回退由模型或工具执行结果决定。

**原则**：回退规则集中、可枚举；新增回退场景时在文档与代码注释中说明，避免散落多处 if。

---

### 3.4 阶段 4：参数校验与执行（Validate & Execute）

| 项 | 规范 |
|----|------|
| **输入** | 阶段 3 得到的 tool（或意图）+ arguments（或结构化 intent）。 |
| **必做** | **先做业务规则校验**（最多提前 N 天、单次时长上限、必填字段等），校验在**代码内**完成，不依赖 LLM；不通过则返回明确错误码与文案，不调用后端。 |
| **执行** | 校验通过后，再调用技能执行层（如 `execute_tool` → skill.execute() 或 HTTP）；技能内部不再重复做同一套规则校验，由本阶段统一保证。 |
| **错误** | 执行失败（含后端 4xx/5xx）→ 映射为稳定错误码（如 RUNTIME_ERROR、CONFIG_ERROR），并带可读 reply。 |

**实现落点**：

- 工具执行入口：`agent/tools.py` 的 `execute_tool()`；技能层：`agent/skills/manager.py`（SkillManager.execute_tool）及各 Skill 的 execute。
- 会议规则校验：技能 execute 内（或 HTTP 后端）做规则校验；本地「最多提前天数」等见 `config/settings`（如 `meeting_max_days_ahead`）。

**原则**：与架构文档 §6.4「校验先于执行」一致；新增技能时在 execute 前增加对应校验并统一错误码。

---

### 3.5 阶段 5：响应封装（Response）

| 项 | 规范 |
|----|------|
| **成功** | 返回至少 `reply`；可含 `booking`、`conversation_id` 等；`error` 为 None 或不带。 |
| **失败** | 在 Agent 内部抛 `AppException`，带 code、message、details（含 reply、error、conversation_id）；由 API 层统一映射为 HTTP 状态与 body。 |
| **一致性** | 所有 Agent 实现均返回同一结构的 dict；对外 API 的 code/msg/data 结构不因 Agent 类型变化。 |

**实现落点**：

- 协议：`agent/protocol.py`（`InvokeResult`、`AgentRunner.invoke`）。
- API：`api/response.py`、`app.py` 的 exception_handler；`api/services/chat_service.py` 使用 `result.get("reply")` 等写入会话并返回 data。

---

## 4. 与现有实现的对应关系

| 阶段 | 当前落点（LangGraph） |
|------|----------------------|
| 1 意图短路 | `langgraph_runner.invoke` 开头：`run_pre_llm_stage(user_input)`，CHITCHAT/空输入则 return |
| 2 LLM | `create_react_agent` 内：LangChain ChatModel（tool_calls 原生支持） |
| 3 解析与回退 | 模型输出 tool_calls，无文本解析；工具执行结果作为 observation 继续推理 |
| 4 校验与执行 | `execute_tool` → SkillManager / skills.execute()（会议为 HTTP） |
| 5 响应 | return result 或抛 AppException |

---

## 5. 新增/修改功能时的自检清单

- [ ] **阶段 1**：新意图若可由规则识别，是否已加入 `intent.py` 并在两处 Agent 的阶段 1 中处理？
- [ ] **阶段 2**：LLM 调用是否使用 LangChain ChatModel 并配置超时？
- [ ] **阶段 3**：工具调用失败或异常是否有明确处理与回退（LangGraph 中为 observation 反馈）？
- [ ] **阶段 4**：新技能是否在 execute 前做规则校验并统一错误码？
- [ ] **阶段 5**：是否通过 `AppException` 与统一 body 返回错误，且未在业务代码中到处写 503/200 分支？

遵循本规范可避免「到处打补丁」：新需求对号入座到某一阶段，在规范落点处扩展，而不是在 invoke 中间随意加 if。

---

## 6. 参考

- 架构文档意图与流水线：`docs/ARCHITECTURE.md` §6（意图理解与路由）、§6.4（标准处理流程）。
- 技能与执行层：`docs/ARCHITECTURE.md` §6.3.1、§4.5。
