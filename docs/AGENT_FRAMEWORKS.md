# Agent 框架选型与当前实现

项目已**统一到 LangChain + LangGraph**，Agent 仅保留 **LangGraph create_react_agent**（`langgraph_runner.py`），技能通过 `langgraph_tools.py` 转为 LangChain StructuredTool，LLM 使用 LangChain ChatOpenAI（vllm/openai 端点）。下文保留框架对照，供扩展参考。

---

## 1. 当前实现

| 能力 | 实现方式 |
|------|----------|
| **Agent 主流程** | `langgraph_runner.py`：LangGraph `create_react_agent` + 技能转 LangChain Tool；意图短路在 `llm_flow.run_pre_llm_stage` |
| **工具与执行** | 技能 `tools.json` → `skills_to_langchain_tools` → 执行仍走 `Skill.execute`（含 HTTP 后端） |
| **LLM** | vllm/openai 使用 LangChain `ChatOpenAI`；dify 使用专用 `DifyLLMAdapter` |

---

## 2. 可支撑同类能力的成熟框架

以下框架都能做「工具调用」和/或「规划-执行」类 Agent，且生态成熟、文档齐全。

### 2.1 LangGraph（LangChain 生态）

- **能力**：图编排、Tool Calling Agent、**Plan-and-Execute** 官方教程与示例。
- **做法**：用 `StateGraph` 定义节点（如 planner、executor），工具用 `@tool` 或 LangChain Tool 绑定到 LLM，按图流转。
- **适合**：希望用「图」表达多步、有条件分支、或将来做 ReAct；且能接受把技能改成 `@tool` 或适配成 LangChain Tool 时。
- **文档**：[LangGraph Plan-and-Execute](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/)、[Tool Calling Agent](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/)。

### 2.2 LangChain（不含 LangGraph）

- **能力**：`bind_tools` + LCEL 做单轮/多轮 Tool Use；`create_react_agent` 做 ReAct。
- **做法**：LLM 绑定 tools → 解析 tool_calls → 执行 → 再调 LLM（若多轮）。没有「图」，是链式调用。
- **适合**：想用 LangChain 的模型封装与 Tool 抽象，但不需要图、不需要 Plan-and-Execute 的复杂编排时。

### 2.3 CrewAI

- **能力**：多 Agent 协作、角色与任务、工具定义、顺序/并行/层级执行。
- **做法**：定义 Agent（role、goal、tools）+ Task + Crew，由框架调度执行。
- **适合**：多角色协作（如「研究员 + 写手 + 审核」）、任务拆解与委派；对「单 Agent + 单轮/规划执行」略重。

### 2.4 Microsoft AutoGen

- **能力**：多 Agent 对话、代码执行、工具调用、GroupChat。
- **做法**：Agent 之间通过对话推进，可注册 tool、代码执行等。
- **适合**：对话式协作、代码助手；复杂分支与长流程不如 LangGraph 直观。

### 2.5 Microsoft Semantic Kernel

- **能力**：Plugin（函数即工具）、Planner（多步规划）、与 Azure/Office 集成。
- **做法**：用 Plugin 暴露能力，用 Planner 生成并执行计划。
- **适合**：微软技术栈、企业集成；Python 有支持但生态以 .NET 为主。

### 2.6 其他

- **LlamaIndex**：Query Engine、Agent 与 Tool 支持，偏检索与问答场景。
- **Dify**：低代码工作流，内置 Agent 节点与工具，适合快速搭界面与流程，代码可控性低于自研。
- **Instructor**：仅做「结构化输出」（如 Pydantic），可把「tool + arguments」当结构化结果拉取，执行层自己写，最轻量。

---

## 3. 对比小结（与当前需求相关）

| 框架 | 单轮 Tool Use | Plan-and-Execute | 与当前技能模型（tools.json + HTTP）的适配成本 |
|------|----------------|------------------|-----------------------------------------------|
| **LangGraph** | ✅ 支持 | ✅ 官方模式 | 中：需把技能转成 `@tool` 或 LangChain Tool，或写一层适配器把现有 execute_tool 包成 Tool。 |
| **LangChain（LCEL）** | ✅ bind_tools | 需自己写「先规划再执行」的链 | 中：同上，工具层要适配。 |
| **CrewAI** | ✅ Agent + tools | ✅ 通过 Task 顺序执行 | 中高：概念是「多 Agent + Task」，和当前单 Agent + 技能门面不完全一致。 |
| **AutoGen** | ✅ 可注册 function | 通过多轮对话间接实现 | 中：对话模型与当前「单轮/规划」的请求-响应模型不同。 |
| **Semantic Kernel** | ✅ Plugin | ✅ Planner | 中：Plugin 与现有 Skill 可对应，但要迁到 SK 的规划与调用约定。 |
| **自研（当前）** | ✅ | ✅ | 无：已按技能 + HTTP 设计，完全可控。 |

---

## 4. 何时考虑用框架、何时继续自研

**适合继续自研（或仅用 LangChain 做 RAG/向量/LLM 适配）的情况：**

- 当前「单轮 Tool Use + Plan-and-Execute」已满足业务，且技能模型（SKILL.md + tools.json + HTTP）希望保持不动。
- 希望最小依赖、无图编排、无额外抽象，逻辑全在自家代码里便于排查和定制。
- 团队更熟悉当前代码库，短期没有 ReAct、多 Agent 协作、复杂分支等需求。

**适合引入/迁到框架的情况：**

- 明确要做 **ReAct**、**多 Agent 协作**、或**图状工作流**（多节点、条件分支、循环），希望用现成抽象和社区示例。
- 希望统一用 **LangChain Tool** 生态（如与 LangSmith、社区 tool 复用）或 **LangGraph** 的图与检查点。
- 愿意把「工具」从当前 `tools.json + Skill.execute」适配成框架的 Tool/Plugin 定义方式，并接受框架升级与依赖管理成本。

**折中方案：**

- **保留自研 Agent，仅用框架补一块**：例如 RAG/向量/LLM 继续用 LangChain（当前已是）；若将来做 ReAct，可单独用 LangGraph 做一个 ReAct Runner，与现有 `agent_type=tool|planning` 并列，由配置或路由选择。

---

## 5. 结论

- 当前 **唯一 Agent 为 LangGraph create_react_agent**，工具由技能转 LangChain StructuredTool。
- **有现成成熟框架可支撑同类能力**：LangGraph、LangChain、CrewAI、AutoGen、Semantic Kernel 等都能做 Tool Use 和/或 Plan-and-Execute，但都会引入「工具/技能」的适配与依赖。
- **是否上框架**取决于：是否要做 ReAct/多 Agent/图工作流、是否希望统一到某生态、以及是否愿意把现有技能层适配成框架的 Tool/Plugin。若当前需求已满足且希望保持简单可控，继续自研是合理选择；若未来要扩展复杂编排，可优先评估 **LangGraph** 作为「图 + Plan-and-Execute + Tool Calling」的一体方案。

---

## 6. 统一到 LangChain/LangSmith 生态：优先 LangGraph

若决定**统一到 LangChain/LangSmith 生态**，**优先选 LangGraph** 的原因与落地要点如下。

### 6.1 为什么优先 LangGraph

- **同一生态**：LangGraph 与 LangChain 同源，共用 `langchain_core`、Tool 抽象、LLM 封装；接入 LangSmith 后，图节点、LLM 调用、Tool 执行会**自动上 trace**，无需自建可观测。
- **三种模式一套图**：在同一个 StateGraph 里可以表达：
  - **单轮 Tool Use**：图仅「用户输入 → 调用 LLM（bind_tools）→ 执行 tool → 结束」；
  - **Plan-and-Execute**：官方提供 [Plan-and-Execute 教程](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/)（planner 节点 + executor 节点）；
  - **ReAct**：多轮「思考 → 选 tool → 执行 → 观察」用图上的循环边即可表达。
- **持久化与检查点**：LangGraph 支持 checkpointer，可做多轮会话状态、中断恢复，与当前 `conversation_id` + 会话存储可对齐。

### 6.2 统一后能获得什么

| 能力 | 说明 |
|------|------|
| **LangSmith 追踪** | 图节点、每次 LLM 调用、每次 Tool 调用自动成 span，与 request_id 关联后可排查单次请求全链路。 |
| **Tool 生态** | 工具用 `@tool` 或 `StructuredTool` 定义后，可与 LangChain 社区、文档、示例一致；现有技能可包一层适配器暴露为 LangChain Tool。 |
| **图可视化与调试** | 图结构可导出/可视化，便于评审与排查「卡在哪一步」。 |
| **模式扩展** | 后续加 ReAct、多 Agent、人工审批节点等，只需扩图，不必重写自研循环。 |

### 6.3 已落地实现

1. **工具层**：`langgraph_tools.skills_to_langchain_tools` 根据技能生成 `StructuredTool`，invoke 时调 `SkillManager.execute_tool`；`tools.json` + `Skill.execute` 不变。
2. **Agent**：`agent_bootstrap` 仅创建 LangGraph Runner，无 `agent_type`；实现 `AgentRunner` 协议。
3. **LLM**：vLLM/OpenAI 使用 LangChain `ChatOpenAI`，Dify 保留 `DifyLLMAdapter`。
4. **可观测**：配置 `LANGCHAIN_TRACING_ENABLED`、`LANGCHAIN_API_KEY` 后 LangGraph 调用自动上报 LangSmith。

### 6.4 自研轮子已移除

项目已**仅保留 LangGraph**；`tool_agent.py`、`planning.py`、自研 `retry`/`vllm_adapter`/`openai_adapter` 已删除，不再并存。

### 6.5 参考链接

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Plan-and-Execute 教程](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/)
- [Tool Calling Agent](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/)
- [LangSmith](https://smith.langchain.com/)：注册并获取 API Key 后，在环境变量中配置即可对 LangChain/LangGraph 调用做追踪。

*与 `docs/AGENT_MODES_AND_NAMING.md`、`docs/TOOLS_AND_LANGCHAIN.md` 配套使用。*
