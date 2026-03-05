# 工具定义与 LangChain @tool 的差异

LangChain 提供 `@tool` 装饰器，把 Python 函数变成「Tool」对象。**本项目主路径**：技能通过 `langgraph_tools.skills_to_langchain_tools` 转为 LangChain `StructuredTool`，供 `create_react_agent` 使用；**未对每个工具使用 `@tool`**，原因与设计如下。

---

## 1. LangChain 的 @tool 在做什么

- 用 `@tool` 装饰一个 **Python 函数**，得到 `StructuredTool` 等对象。
- 工具名、描述、参数 schema 通常从 **函数名、docstring、参数类型** 推导或手写。
- 执行 = **直接调用该 Python 函数**（同进程）。
- 适合：工具逻辑在本进程内、且希望「一个函数一个工具」的写法。

---

## 2. 本项目的工具模型（技能 + 声明式 schema）

本项目的「工具」是 **按技能组织、声明式定义** 的：

| 维度 | 本项目 | LangChain @tool |
|------|--------|------------------|
| **定义方式** | 每个技能下 **tools.json**（或 Skill 的 `get_tools_schema()`） | Python 函数 + `@tool` 装饰器 |
| **Schema 来源** | JSON / 技能文档，与 OpenAI Function Calling 格式一致 | 函数签名 + docstring 推导 |
| **执行** | **Skill.execute(tool_name, arguments, context)** → 可能是 **HTTP 调用后端**（如会议）或注册的 Python 实现 | 直接调用被装饰的 Python 函数 |
| **粒度** | 以「技能」为单位聚合多工具（如 meeting 技能下有 book_meeting、query_meeting_rooms 等） | 通常「一个函数 = 一个工具」 |

因此：

- **会议等能力**：tool 定义在 `skill_docs/meeting/tools.json`，执行由 **GenericSkill** 把 `tool + arguments` POST 到会议后端，**没有对应的 Python 函数**，无法直接 `@tool` 装饰。
- **主路径**：`langgraph_tools.skills_to_langchain_tools` 根据技能的 `get_tools_schema()` 生成 **LangChain StructuredTool**，由 `create_react_agent` 的 `bind_tools` 使用；执行时通过 contextvar 调用 `SkillManager.execute_tool`，对内仍是 Skill。
- **可选文案**：`get_tools_schema_for_prompt(skills)` 用于拼可选 system 文案，非主 Agent 必经路径。

---

## 3. 为什么技能不直接写成 @tool（总结）

1. **执行不在本进程**：会议等由 HTTP 后端执行，没有「一个 Python 函数对应一个 tool」的映射。
2. **技能优先**：扩展方式是「加技能（SKILL.md + tools.json）」，与业内 Skill/Plugin 模型一致；工具形态由适配层转为 StructuredTool，无需每个技能手写 @tool。
3. **已统一框架**：主 Agent 为 LangGraph，工具通过技能 → StructuredTool 适配器接入，已使用 LangChain Tool 类型与 `bind_tools`。

---

## 4. 若将来要用 @tool（可选）

适合用 `@tool` 的场景：**纯本进程、无技能归属** 的小工具（如计算器、当前时间、或把 `load_skill` 也做成一个 @tool）。做法可以是：

- 用 `@tool` 定义若干 Python 工具，用 LangChain 的 `tool.invoke` 或 schema 转成我们的 `ToolSchema` 格式，在 `get_tools_schema_for_prompt` 里与技能 schema 合并；
- 在 `execute_tool` 中：若 `tool_name` 属于某「内置工具列表」，则转调对应 `@tool` 的 `invoke`，否则走现有技能分支。

这样会引入「技能工具」与「@tool 工具」两套来源，需要约定命名不冲突、文档说明清楚。当前需求下 **不必须**，等有明确「进程内小工具」需求再加即可。

---

*与 [Agent 模式与业界命名](AGENT_MODES_AND_NAMING.md)、[ARCHITECTURE](ARCHITECTURE.md) 配套。*
