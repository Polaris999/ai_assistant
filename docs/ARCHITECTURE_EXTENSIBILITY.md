# 架构扩展性设计：技能层解耦与多 Agent

本文档明确两点：① **技能发现/加载与具体功能解耦**，不与某一 Agent 或会议业务绑定；② **多 Agent 下的扩展方式**，便于后续新增 RAG Agent、规划 Agent 等。

---

## 1. 当前问题

### 1.1 技能层与「具体功能」的耦合

需要区分的是：

- **技能发现与加载**（有哪些技能、加载 SKILL.md、格式化为目录/全文）应是**通用能力**，不依赖「当前是哪种 Agent」或「会议技能」。
- **与具体功能耦合的**是：谁在**使用**这些技能数据——当前 Agent 用它们生成「工具 schema」并 execute_tool；会议只是其中一个技能的**执行后端**（HTTP）。  
  因此，**不应耦合的是「发现/加载」与「某一类 Agent 或某一业务」**；执行、工具 schema 属于使用方一侧。

当前实现中：

- **已解耦**：`agent/skills/loader.py`（SkillLoader）只做发现、加载、格式化，无对某一 Agent 或会议的引用。
- **混在一起**：`SkillManager` 同时承担「发现/加载/格式化」与「工具 schema + execute_tool + execute_load_skill」。结果是：  
  - 其他 Agent（如只想要「技能目录/全文」做上下文的 RAG Agent）也要经过 SkillManager，会看到 get_tools_schema、execute_tool 等 Tool 专属概念。  
  - 若未来用 skillkit 做发现/加载，需要替换的是「发现/加载」实现，而不应动到「工具执行」逻辑；当前 SkillManager 把两者绑在一起，不利于替换或扩展。

### 1.2 多 Agent 需求

未来会有多种 Agent（如当前 LangGraph、RAG Agent、规划 Agent）。架构上应：

- 每种 Agent 只依赖自己需要的「技能相关能力」：当前 Agent 需要「工具 schema + 执行」；RAG Agent 可能只需要「技能文档内容」做检索或上下文。
- 技能发现/加载作为**共享基础层**，任何 Agent 都可使用，且不依赖具体 Agent 类型或业务（会议等）。

---

## 2. 目标架构：两层分离 + 多 Agent 扩展

### 2.1 技能层拆分

| 层次 | 职责 | 不包含 | 实现/接口 |
|------|------|--------|-----------|
| **技能发现与加载（Skill Catalog）** | 发现技能 ID、加载 SKILL.md、解析 frontmatter、格式化为「全文」或「目录」片段；可选多源、缓存 | 工具 schema、execute、load_skill 工具、任何 Agent 类型 | `config/skill_loader` + `SkillLoader`（或抽成 `SkillCatalog` 接口），仅暴露 discover、load、format_* |
| **技能执行（当前 Agent 用）** | 在「已启用的技能文档」之上：构建工具 schema、执行 load_skill / execute_tool | 发现逻辑、解析 SKILL.md、与会议等业务无关的「如何发现」 | `ToolSkillExecutor`、`SkillManager` 门面，依赖 Skill Catalog + registry + GenericSkill |

这样：

- **发现/加载**与具体功能（某一 Agent、会议）解耦；可与 [skillkit](https://github.com/maxvaega/skillkit) 的 discovery/load 对齐接口。
- **执行**与「谁在用」绑定：当前 LangGraph Agent 使用 ToolSkillExecutor；其他 Agent 可不依赖它。

### 2.2 多 Agent 扩展方式

```
                    ┌─────────────────────────────────────┐
                    │  Agent 工厂 / 路由                    │
                    │  create_agent(type) 或按路由选 Runner │
                    └─────────────────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│ LangGraph Agent │        │ RAG Agent       │        │ Planning Agent  │
│ 依赖：          │        │ 依赖：          │        │ 依赖：          │
│ - Skill Catalog │        │ - Skill Catalog │        │ - Skill Catalog │
│   (目录/全文)   │        │   (可选：按需   │        │   (目录/全文)   │
│ - ToolSkillExec │        │    取 content)   │        │ - 规划/工具层    │
│   (schema+执行) │        │ - RAG/检索      │        │   (待定)         │
└─────────────────┘        └─────────────────┘        └─────────────────┘
         │                            │                            │
         └────────────────────────────┼────────────────────────────┘
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  Skill Catalog（仅发现/加载/格式化）  │
                    │  与 Agent 类型、会议等业务无耦合     │
                    └─────────────────────────────────────┘
```

- **Skill Catalog**：所有 Agent 共享；只提供「有哪些技能、技能全文/目录」。
- **当前 Agent**：在 Skill Catalog 之上使用 **ToolSkillExecutor**（工具 schema + execute_tool + execute_load_skill）。
- **RAG / 规划等**：仅使用 Skill Catalog，或再叠加自己的「执行/检索」层，不依赖 Tool 执行逻辑。

---

## 3. 重构方案（具体步骤）

### 3.1 抽象「Skill Catalog」接口（发现/加载不耦合具体功能）

- **保持** `config/skill_loader.py` 与 `agent/skills/loader.py`（SkillLoader）为**发现与加载**的实现；不在此处引用 tools、execute、Agent。
- **可选**：在 `agent/skills/` 下定义协议或抽象类，例如：

```python
# 概念接口（可选，用于类型与替换）
class SkillCatalogProtocol(Protocol):
    def discover_skill_ids(self) -> list[str]: ...
    def load_all(self) -> list[dict[str, Any]]: ...
    def load_by_name(self, skill_name: str) -> Optional[dict[str, Any]]: ...
    def format_for_prompt(self, skill_docs: Optional[list] = None) -> str: ...
    def format_catalog_for_prompt(self, skill_docs: Optional[list] = None) -> str: ...
```

- SkillLoader 实现该协议；未来若接入 skillkit，可写 `SkillkitCatalogAdapter(SkillCatalogProtocol)`，只换发现/加载，不碰执行。

### 3.2 抽出「Tool 型技能执行」为独立组件

- **新增** `agent/skills/tool_executor.py`（或类似命名），实现 **ToolSkillExecutor**（类名可再定）：
  - 依赖：**SkillCatalog 协议**（或直接依赖 SkillLoader）、`get_enabled_skill_ids`、registry、GenericSkill 构建逻辑。
  - 提供：`get_skill_instances()`、`get_tools_schema_for_prompt(include_load_skill: bool)`、`execute_tool(...)`、`execute_load_skill(skill_name)`。
  - 内部：从 catalog 按 enabled_skill_ids 加载 doc；根据 doc 是否有 executor.url 用 GenericSkill，否则用 registry；工具 schema 与 execute 与当前 SkillManager 中逻辑一致。
- **SkillManager** 的两种处理方式（二选一）：
  - **A（推荐）**：SkillManager 变为**薄门面**：持有一个 SkillCatalog + 一个 ToolSkillExecutor，对外方法委托给 catalog 与 executor；调用方（LangGraph Runner 经 langgraph_tools 使用 SkillManager）兼容现有 API。
  - **B**：LangGraph Runner 直接依赖 ToolSkillExecutor；SkillManager 作为默认门面保留。

这样，「发现/加载」与「Tool 执行」在代码上分离；发现/加载与具体功能解耦。

### 3.3 启用列表与配置

- `get_enabled_skill_ids()` 目前放在 `agent/skills/__init__.py`，依赖 settings 与 skill_docs 发现。建议：
  - 仍由「谁使用技能」决定启用列表：ToolSkillExecutor 构造时传入 enabled_ids，或从配置读取（与现在一致），但不把「发现实现」写死在 Tool 执行层里。
  - 发现实现只在 SkillLoader / SkillCatalog 中，ToolSkillExecutor 只消费「已发现的 doc + 启用列表」。

### 3.4 多 Agent 入口

- 在 `api/agent_bootstrap.py` 或新建 `agent/factory.py` 中：
  - 提供 `create_agent(agent_type: str)` 或根据配置/路由返回不同 Runner。
  - 当前：`create_langgraph_agent()` 使用 SkillManager（薄门面），经 `langgraph_tools.skills_to_langchain_tools` 绑定工具。
  - 未来 RAG Agent：仅注入 SkillCatalog（或 SkillLoader），用于获取技能目录/全文，不注入 ToolSkillExecutor。

---

## 4. 与 skillkit 的关系（修正说明）

- **之前表述**：「直接依赖 skillkit 会与 Agent、会议等业务耦合」——更准确的是：  
  **技能发现/加载逻辑本身不应与具体功能耦合**；当前 SkillManager 将「发现/加载」与「执行」组合为门面。
- **解耦后**：  
  - **发现/加载**：由 Skill Catalog 层统一负责，可与 skillkit 的 discover/load 对齐；在 Catalog 层替换或适配 skillkit 即可，不涉及 Agent 执行或会议业务。  
  - **执行**：由 ToolSkillExecutor（SkillManager 门面）负责，与 skillkit 是否接入无关。

因此，**技能发现/加载与具体功能解耦后，引入 skillkit 只影响 Catalog 层，不增加与某一 Agent、会议等的耦合**。

---

## 5. 实施优先级建议

| 步骤 | 内容 | 目的 | 状态 |
|------|------|------|------|
| 1 | 抽 ToolSkillExecutor，SkillManager 委托给 Catalog + ToolSkillExecutor | 分离「发现/加载」与「Tool 执行」，便于多 Agent 与后续替换 Catalog | ✅ 已做 |
| 2 | 明确 SkillLoader 为「Skill Catalog」唯一实现，文档声明其与 Agent/业务解耦 | 约定边界，避免后续在 Catalog 层写进 Tool/会议逻辑 | ✅ 已做 |
| 3 | Agent 工厂（agent_bootstrap）已统一创建 LangGraph Runner；预留 RAG/其他类型入口 | 为多 Agent 留扩展点 | 可选 |
| 4 | （可选）定义 SkillCatalogProtocol，SkillLoader 实现之；为日后 skillkit 适配留接口 | 便于替换或混用 skillkit | 待做 |

步骤 1、2 已完成：`agent/skills/tool_executor.py` 提供 ToolSkillExecutor，SkillManager 为薄门面；SkillLoader 模块注释约定为 Catalog、与业务解耦。

---

*与 `ARCHITECTURE_ASSESSMENT.md`、`SKILLKIT_COMPARISON.md` 配套使用。*
