# Agent 模式与业界命名

本文档说明业界对 Agent 模式的常见命名、本项目与之的对应关系，以及「是否要全部实现」的建议。

---

## 1. 业界常见命名

常见分类大致如下：

| 业界常用名 | 英文 | 含义 | 典型流程 |
|------------|------|------|----------|
| **Function Calling / Tool Use** | Function Calling, Tool Use | LLM 将用户意图映射为「调用哪个函数 + 参数」，一次或多次调用 | 单轮：用户输入 → LLM 输出 tool + arguments → 执行 → 返回。也可多轮但每轮仍是「选一个 tool」。 |
| **ReAct** | Reason + Act | 推理与行动交替的循环 | **Thought → Action → Observation → Thought → …** 直到任务结束；每步可调用工具，根据观察结果再决定下一步。 |
| **Plan-and-Execute** | Plan-and-Execute | 先规划再执行 | **先** 用 LLM 生成步骤列表（计划），**再** 按序执行每一步；执行过程中一般不再重新规划。 |
| **Reflexion** | Reflexion | 在 ReAct 基础上加自我反思与记忆 | 在 Thought-Action-Observation 后增加自我评估，把「错误/经验」写入记忆，用于后续改进。 |

因此：

- 业界常用 **Function Calling**、**Tool Use**、**ReAct** 等；本项目主实现为 **LangGraph ReAct**。
- 若强调「每轮只选一个工具、单次执行」，可称为 **单轮 Tool Use / 单轮 Function Calling**，或 **Single-turn tool-calling agent**。

---

## 2. 本项目与业界模式的对应

| 本项目实现 | 对应业界模式 | 说明 |
|------------|--------------|------|
| **LangGraph Runner**（`langgraph_runner.py`） | **ReAct**（create_react_agent） | 意图短路 → 多轮「模型 → 选工具执行 → 观察 → 再模型」直到结束；工具为技能转 LangChain StructuredTool。 |
| 未实现 | **Plan-and-Execute** | 先规划步骤再执行，可按需用 LangGraph 图实现。 |
| 未实现 | **Reflexion** | 在 ReAct 上增加自我评估与记忆。 |

命名建议（对外/文档）：主 Agent 称为 **LangGraph ReAct Agent** 或 **基于 LangGraph 的对话 Agent**。

---

## 3. 几种模式是否都要实现？

**不必全部实现**，按产品需求选即可：

| 模式 | 适用场景 | 是否建议实现 |
|------|----------|--------------|
| **ReAct（当前 LangGraph）** | 多轮选工具、观察结果再决策；封闭业务、预定义技能（订会、查会议室、取消） | ✅ 已实现。 |
| **Plan-and-Execute（当前 Planning Agent）** | 需要「先 A 再 B」的固定多步（如先加载技能再订会） | ✅ 已实现；适合明确多步、不需根据中间结果改计划的场景。 |
| **ReAct** | 开放域、多步推理、需根据**中间结果**动态决定下一步（如边查边订、多次澄清） | ⚠️ 按需：若产品有「多轮探索、根据工具返回再决策」的需求再做；实现成本与 token 成本都更高。 |
| **Reflexion** | 需要 Agent 从错误中学习、自我改进 | ⚠️ 一般可延后：依赖长期记忆与评估逻辑，复杂度高，多数业务先不做。 |

结论：

- **当前已覆盖**：单轮 Tool Use + Plan-and-Execute，已能支撑「订会、查会议室、多步规划」等常见需求。
- **不必为了「凑齐所有模式」而实现 ReAct/Reflexion**；等有明确需求（如「多轮探索式订会」「根据会议室查询结果再决定订哪间」）再考虑 ReAct 或混合模式。

---

## 4. 与标准对齐的用词约定（已落地）

- **README / 对外文档**：采用「**LangGraph ReAct Agent**」或「基于 LangGraph 的对话 Agent」。
- **配置项 `agent_type`**：保留 `tool` / `planning`；注释中写明对应关系：`tool` = 单轮 Tool Use / Function Calling，`planning` = Plan-and-Execute。
- **代码与架构**：模块/类 docstring 与架构文档中统一标注标准名，如「业界：单轮 Tool Use / Function Calling」「业界：Plan-and-Execute」。

---

*与 `docs/LLM_INTERACTION_FLOW.md`、`docs/ARCHITECTURE_EXTENSIBILITY.md` 配套使用。*
