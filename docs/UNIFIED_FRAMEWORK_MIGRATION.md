# 统一框架迁移：当前状态与规范

项目已统一到 **LangChain + LangGraph + Skills + RAG**，自研 Agent/LLM 轮子已移除。本文记录当前实现与可选后续优化。

---

## 1. 当前实现总览

| 区域 | 实现方式 |
|------|----------|
| **Agent 执行** | **LangGraph** `create_react_agent`（`langgraph_runner.py`），唯一入口 |
| **工具** | 技能 → `langgraph_tools.skills_to_langchain_tools` → LangChain `StructuredTool`，执行仍走 `Skill.execute` |
| **LLM** | vLLM/OpenAI 使用 **LangChain ChatOpenAI**（`factory.py` + `langchain_adapter.py`）；Dify 使用 `DifyLLMAdapter` |
| **意图短路** | `intent.py` + `llm_flow.run_pre_llm_stage`（业务规则，保留） |
| **RAG/向量/Embeddings** | 已用 LangChain 生态 |
| **会话** | 自研 `ConversationStore`（可选后续迁 LangChain MessageHistory，P2） |
| **Prompt 模板** | `prompt_loader.py`（可选自定义 system 等，主 Agent 不依赖） |

---

## 2. 已完成的统一改造

### 2.1 LangGraph Runner（唯一 Agent）

- **位置**：`src/ai_assistant/agent/langgraph_runner.py`
- **行为**：`create_react_agent` + 技能转 LangChain Tool；`llm_type=openai` / `vllm` 均通过 `ChatOpenAI` 调用；实现 `AgentRunner` 协议。
- **配置**：由 `agent_bootstrap` 创建，无 `agent_type` 分支。

### 2.2 技能 → LangChain Tool

- **位置**：`src/ai_assistant/agent/langgraph_tools.py`
- **行为**：技能生成 `StructuredTool` 列表；invoke 经 contextvar 取 context，调用 `SkillManager.execute_tool`。

### 2.3 LLM 统一

- **位置**：`core/llm/factory.py`、`core/llm/langchain_adapter.py`
- **行为**：vLLM/OpenAI 返回 `LangChainChatModelAdapter(ChatOpenAI(...))`；自研 `vllm_adapter`/`openai_adapter`/`retry` 已删除。

---

## 3. 可选后续优化（P2）

- **会话存储**：可对接 LangChain `BaseChatMessageHistory`，接口略不同，可包一层。
- **Prompt**：`PromptTemplate.from_file` 为可选；当前模板化已够用。
- **可观测**：LangSmith 与 LangGraph 天然对接，按需开启。

---

## 4. 配置

Agent 固定为 LangGraph，无 `AGENT_TYPE` 或其它类型切换；自研 tool/planning 已移除兼容。

---

## 5. 后续可选（P2）

- **会话**：用 LangChain `RedisChatMessageHistory` 等实现与现有 `ConversationStore` 同接口的封装，或逐步改为直接使用 LangChain 类型。
- **Prompt**：部分提示从 `prompt_loader` 迁到 `PromptTemplate.from_file`，便于与 LangChain 模板复用。
- **Dify**：继续使用自研适配器；若 Dify 提供 LangChain 集成再考虑替换。

*与 `docs/AGENT_FRAMEWORKS.md`、`docs/TOOLS_AND_LANGCHAIN.md` 配套使用。*
