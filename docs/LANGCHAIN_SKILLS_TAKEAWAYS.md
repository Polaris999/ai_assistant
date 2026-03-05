# 《LangChain 版 Claude Skills 实战详解》可借鉴要点

本文档基于《LangChain版"Claude Skills"实战详解：为智能体赋予动态工具调度与复杂上下文治理能力》提炼可落地到本项目的优点，并与当前实现对比。

---

## 1. 文档核心思想摘要

### 1.1 问题与思路

- **问题**：复杂任务时若把所有规则、流程塞进 system prompt，会导致提示词过长、上下文成本高、模型易抓不住重点并产生幻觉。
- **思路**：将复杂任务拆成若干**技能（Skill）**，每项技能包含「针对某一类任务的完整执行说明」。System prompt 中**只列出技能名称与一句话描述**；仅在模型判断请求涉及某技能时，**通过工具按需加载**该技能的完整内容（Progressive Disclosure / 渐进式披露）。

### 1.2 Skill 的定位

- Skill 不仅描述「工具怎么用」，更描述「**在什么业务语境下、按什么顺序、在什么约束下**使用工具」——即对工具的「调度说明书」。
- 典型内容：任务目标、业务约束、使用工具的原则、正确示例。

### 1.3 实现形态（文档中的做法）

| 组件 | 作用 |
|------|------|
| **Skill 结构** | `name`、`description`（进 system prompt）、`content`（按需加载） |
| **load_skill 工具** | 输入 `skill_name`，返回「已加载技能：xxx」+ 对应 `content`，供模型在需要时调用 |
| **SkillMiddleware** | 每次模型调用前，把「可用技能目录」（仅 name + description）追加到 system prompt |
| **AgentState.skills_loaded**（进阶） | 记录已加载技能；业务工具（如 write_sql_query）在执行前检查 `vertical in skills_loaded`，未加载则拒绝并提示先 load_skill |

### 1.4 存储与发现（文档中的变体）

- **存储**：内存字典 / 文件系统（如 Claude Code）/ 远程（S3、DB、API）。
- **发现**：system 中列举 / 扫目录 / 注册中心 / 工具动态返回可用列表。
- **加载策略**：一次性加载整份 content / 分页 / 按搜索加载 / 分层（先概览再子模块）。

### 1.5 规模经验

- 小型（&lt;1K tokens）：可放进 system prompt，可配合 prompt caching。
- 中型（1K–10K tokens）：适合按需加载（文档典型场景）。
- 大型（&gt;10K tokens 或占窗口 5%–10%+）：必须分页/搜索/分层，否则严重挤占上下文。

---

## 2. 与当前项目的对比

| 维度 | 文档做法 | 本项目现状 |
|------|----------|------------|
| **Skill 结构** | name / description / content 分离 | ✅ 已有：SKILL.md frontmatter 的 name、description + body 作为 content |
| **注入 system 的内容** | 仅「技能目录」（name + description） | ❌ 当前是**全文**：`format_skill_docs_for_prompt` 拼入 `name + description + content` |
| **按需加载** | 通过 `load_skill(skill_name)` 工具加载 content | ⚠️ `load_skill_by_name` 已实现，但**未暴露为 Agent 的 tool**（config/skill_loader.py 注释中已提到可选） |
| **中间件** | Middleware 在每次模型调用前注入技能目录 | ❌ 无类似中间件；目前是在构造 system 时一次性拼好 |
| **状态约束** | AgentState.skills_loaded，业务工具校验「先 load 再执行」 | ❌ 无；未强制「先加载技能再使用该领域工具」 |
| **发现** | 可从 system 列举 / 文件 / 注册中心 | ✅ 与 skill_docs 发现 + ENABLED_SKILLS 一致 |

结论：**本项目已具备「按名称加载单技能」的能力和清晰的 Skill 文档结构，但尚未做「仅目录进 prompt + load_skill 工具 + 可选状态约束」的渐进式披露与上下文治理。**

---

## 3. 可借鉴的落地建议

### 3.1 渐进式披露（优先）

- **目标**：减少 system prompt 长度与噪音，在「合适的时间提供恰当信息」。
- **做法**  
  1. **技能目录与全文分离**  
     - 新增 `format_skill_catalog_for_prompt(skill_docs)`：只输出「技能名 + 一句话描述」列表（可带一句说明：需要详情时请使用 `load_skill` 工具）。  
     - 保留现有 `format_skill_docs_for_prompt`，用于「兼容模式」或调试时全文注入。  
  2. **将 load_skill 暴露为 Tool**  
     - 在 tools 层增加 `load_skill`：参数 `skill_name`，内部调用 `load_skill_by_name(skill_name)`，返回「已加载技能：{name}\n\n{content}」或未找到时的提示。  
     - 将该工具注册到 Agent 可用工具列表，并在 system 中说明：「当需要某类任务的详细说明、业务规则或示例时，请先调用 load_skill(skill_name)」。  
  3. **System 构建切换**  
     - 通过配置（如 `USE_SKILL_CATALOG_ONLY=true`）选择：  
       - `true`：system 中只拼 `format_skill_catalog_for_prompt` + 上述使用说明，不拼完整 content；  
       - `false`：保持当前「全文注入」行为，便于小规模或兼容旧行为。

这样在不改现有 Skill 文档格式的前提下，即可实现「目录常驻 + 按需加载 content」的渐进式披露。

### 3.2 技能内容的写作规范（与文档对齐）

- 在 SKILL.md 或内部规范中明确建议每项技能包含：  
  - **任务目标**（如：编写符合业务规则的会议预订请求）；  
  - **业务约束**（有效状态、必填字段、排除情况）；  
  - **使用工具的原则**（何时查 schema、何时不查、调用顺序）；  
  - **示例**（正确工具使用范式或示例回复）。  
这样 Skill 真正起到「工具调度说明书」的作用，而不只是工具参数说明。

### 3.3 可选：状态约束（先加载再执行）

- 若希望强制「先 load_skill 再使用该领域工具」：  
  - 在会话或请求级 state 中维护 `skills_loaded: list[str]`。  
  - `load_skill` 工具执行成功后，将对应 `skill_name` 加入 `skills_loaded`。  
  - 在 `execute_tool` 或具体技能执行前，根据工具与技能的归属关系检查：若该工具属于技能 A，则要求 `A in skills_loaded`，否则返回明确错误（如「请先使用 load_skill(\"xxx\") 加载该技能」）。  
- 实现时需约定「工具 ↔ 技能」的映射（当前已有技能与 tool 的归属，可复用）。

### 3.4 存储与发现（中长期）

- **当前**：内存 + 文件（skill_docs/*/SKILL.md），发现用目录扫描 + ENABLED_SKILLS，已足够。  
- **可借鉴**：若后续技能数量或体量增大，可考虑：  
  - 按技能大小选择策略：小技能仍可目录+按需或甚至全文；大技能强制分页/搜索/分层加载；  
  - 发现方式：除 system 列举外，可增加「工具返回当前可用技能列表」或从注册中心拉取，便于多团队/多环境。

### 3.5 与现有流程的兼容

- **LLM 交互流程**（见 `docs/LLM_INTERACTION_FLOW.md`）：  
  - 阶段 2 的 system 构建改为「目录 + load_skill 说明」即可，无需改阶段划分。  
  - 解析与回退（阶段 3）：若 LLM 选择 `load_skill`，则解析出 `tool=load_skill, skill_name=xxx`，执行后结果作为 Tool Message 进入上下文，不产出最终用户回复；下一轮或同轮继续时可再选业务工具。  
- **意图短路**：保持现有 Pre-LLM 短路逻辑不变；load_skill 仅在有 LLM 调用的会话中使用。

---

## 4. 总结

| 借鉴点 | 优先级 | 说明 |
|--------|--------|------|
| 仅技能目录进 system + load_skill 工具 | 高 | 直接降低上下文、提升稳定性，且项目已有 `load_skill_by_name`，改动面小 |
| 技能内容结构（目标/约束/原则/示例） | 中 | 文档与规范层面统一，提升「调度说明书」质量 |
| 状态约束 skills_loaded | 低/可选 | 对强合规或多领域 SQL 类场景有价值，可按需上 |
| 存储/发现/分页与分层 | 低/中长期 | 技能规模上来后再细化 |

整体上，文档中的 **Progressive Disclosure + 技能目录与 content 分离 + load_skill 工具** 与当前架构兼容度高，可作为下一步「上下文治理」与「动态工具调度」的优先落地方向；**状态约束**和**大技能分页/搜索**可按业务需要再迭代。

---

## 5. 已实现（本次优化）

- **仅技能目录进 system + load_skill 工具**：已实现。
  - 配置项 `USE_SKILL_CATALOG_ONLY`（默认 `false`）：为 `true` 时 system 只注入技能目录（name+description），并暴露 `load_skill` 工具；Agent 可先调用 `load_skill(skill_name)` 再选业务工具。
  - 实现位置：`config/settings.py`（`use_skill_catalog_only`）、`agent/skills/loader.py`（`format_catalog_for_prompt`）、`agent/tools.py`（`TOOL_LOAD_SKILL`、schema 与 `get_all_tool_names(include_load_skill)`）、`agent/skills/manager.py`（目录模式、`execute_load_skill`、`execute_tool` 内处理 load_skill）、`agent/langgraph_tools.py`（技能转 LangChain Tool 时含 load_skill）。
