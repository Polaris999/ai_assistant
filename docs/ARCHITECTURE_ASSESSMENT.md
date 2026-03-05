# 现有架构评估与重构建议

本文档基于项目规范与当前实现评估架构。**当前 Agent 已统一为 LangChain + LangGraph**（`langgraph_runner.py`）；以下部分表述若涉及「tool_agent」为历史实现。

---

## 1. 与最佳实践的符合度

### 1.1 项目规范逐条对照

| 规范要求 | 现状 | 符合度 |
|----------|------|--------|
| **分层明确**：控制层 / 工具层 / 记忆层 / 知识层 / 基础设施层分离 | API → Agent → Skills/Tools；Core（LLM、conversation）不依赖 Agent；config 负责配置与 prompt 加载 | ✅ 符合 |
| **模块化**：agent/main 负责编排，非具体实现 | `langgraph_runner.py` 编排；具体执行在 `langgraph_tools`、`tools.execute_tool`、`skills/*`、`llm_flow` | ✅ 符合 |
| **配置分离**：模型参数、密钥、Prompt 从代码分离 | `config/settings.py` + `.env`；`config/prompts/*.txt` + `prompt_loader`；无硬编码密钥 | ✅ 符合 |
| **工具单一职责、Docstring、错误处理、依赖注入** | 工具由技能提供 schema/execute；GenericSkill 从 context 取超时；异常转 reply+error | ✅ 符合 |
| **Prompt 模板化、变量清晰** | `config/prompts/` 下模板，占位符明确 | ✅ 符合 |
| **记忆接口抽象、上下文管理** | `ConversationStore` 统一接口；`conversation_history_max_chars` 控制长度 | ✅ 符合 |
| **主循环健壮、解析验证与回退** | 五阶段流程、超时/重试、解析失败回退到 reply_only/query_rooms/book_meeting | ✅ 符合 |
| **日志与 request_id、异常体系、配置化开关** | 结构化日志、request_id 贯穿；AppException 体系；功能由配置控制 | ✅ 符合 |

结论：**现有架构与项目规范高度一致，无需为「符合规范」而做大规模重构。**

---

## 2. 当前架构的强项与已完成的优化

- **单一 Agent 流程**：五阶段（意图短路 → LLM → 解析回退 → 执行 → 响应）文档化且落地，便于测试与排错。
- **技能层与执行解耦**：`skill_docs` 发现、SkillManager 门面、GenericSkill HTTP 执行、注册表扩展，与 Anthropic/skillkit 思路对齐；已支持渐进式披露（目录 + load_skill）。
- **协议与入口统一**：`AgentRunner` 协议、`create_agent_or_placeholder`、lifespan warmup/shutdown，扩展新 Agent 类型时只需新 Runner 实现协议。
- **审查报告中的高优先级项**：README 更新、GenericSkill 超时配置、protocol warmup 清理、request_id 日志、invoke 内配置集中读取、共享线程池等均已实施。

---

## 3. 仍可改进的点（非必须重构）

以下属于**渐进式改进**，可在日常迭代中完成，不必单独做「重构版本」。

| 项 | 说明 | 建议 |
|----|------|------|
| **配置注入方式** | Runner 内配置读取若分散在流程中 | 可选：在 invoke 开头集中读取或轻量 `AgentConfig`，便于单测注入与可读性 |
| **技能 content 缓存** | `load_skill_by_name` 无缓存，同一会话多次 load_skill 会重复读文件 | 见 `SKILLKIT_COMPARISON.md`：按技能 ID + mtime 做 content 缓存，成本低、收益明确 |
| **扩展点文档** | 如何新增一种 Agent、如何新增技能源，目前散落在 README 与各模块注释 | 在 `docs/` 增加「扩展指南」：新增 Agent 类型、新增技能、多源发现等步骤说明，减少误用与重复造轮子 |

---

## 4. 是否建议「重构」

### 4.1 不建议做的重构

- **推倒重来**：当前分层与流程清晰，推倒重来成本高、收益不明确。
- **为迎合某一框架而大改**：当前已统一 LangGraph，无需再为「像 LangGraph」而改。
- **过早抽象「多 Agent 基类」**：目前仅 LangGraph Runner 一种；若未来有 RAG Agent、Planning Agent，可新增独立 Runner 实现同一协议即可（YAGNI）。
- **合并或拆分目录的纯结构调整**：如把 `config/skill_loader` 迁到 `agent/skills` 仅为了「技能相关放一起」。当前「config=加载与解析，agent/skills=门面与执行」职责清晰，无必要为迁而迁。

### 4.2 可考虑的小范围重构（按需）

仅在以下情况成立时再考虑，且控制范围与风险：

| 场景 | 可选做法 | 范围 |
|------|----------|------|
| 希望所有 Agent 共用「配置 + 超时 + 重试」等运行时参数 | 引入轻量 `AgentRuntimeConfig`（或 `AgentConfig`）dataclass，由工厂从 settings 构建并传入 Runner | 仅限 config 注入路径，不改变协议与阶段划分 |
| 未来要支持 Plan-and-Execute 等 | 可新增 LangGraph 图或独立 Runner，实现同一 `AgentRunner` 协议；API 层通过配置或路由选择 Runner | 增量新模块，与现有 LangGraph Runner 并存 |
| 技能来源要支持多目录/插件 | 在 `skill_loader` 或 SkillManager 中支持 `skill_sources: list[Path]`，按序发现并去重；见 `SKILLKIT_COMPARISON.md` | 扩展发现逻辑，不改变执行与 Agent 流程 |

---

## 5. 总结与建议

- **现有架构符合最佳实践**，与项目规范及审查结论一致；**无需为合规而做大规模重构**。
- **开发阶段更推荐**：继续按「渐进式改进」推进（配置可读性、技能 content 缓存、扩展点文档），必要时再做上述**小范围、有明确目标的重构**。
- **何时再评估重构**：当出现以下情况时可重新评估：① 需要第二种 Agent 形态（如多步、规划）；② 技能发现/加载逻辑明显膨胀（如多源、权限、版本）；③ 单轮流程无法满足产品需求（如必须多轮 tool 链）。在此之前，保持当前架构并持续小步优化即可。

---

*与 `AGENT_CODE_REVIEW_REPORT.md`、`LLM_INTERACTION_FLOW.md`、`SKILLKIT_COMPARISON.md` 配套使用。*
