# skillkit 与本项目技能加载/管理对比与可借鉴点

参考仓库：[maxvaega/skillkit](https://github.com/maxvaega/skillkit)（为 Agent 提供 Skills 发现、加载与执行的 Python 库，兼容 Anthropic SKILL.md、支持渐进式披露与 LangChain。）

---

## 1. skillkit 能力摘要（与加载/管理相关）

| 能力 | 说明 |
|------|------|
| **SKILL.md 兼容** | 与现有 Anthropic/社区 SKILL.md 格式兼容，可直接复用既有技能包 |
| **多源发现** | 从项目目录、Anthropic 配置、插件、自定义目录发现技能，**按优先级解决重名冲突** |
| **YAML frontmatter** | 解析并做**校验**（必填字段等） |
| **渐进式披露** | 三层：先仅元数据 → 再完整说明 → 最后按需引用附件；**约 80% 内存节省**、Level 2 内容缓存 |
| **内容缓存（v0.4）** | **LRU 内容缓存** + **mtime 自动失效**；缓存命中 &lt;1ms，支持 `get_cache_stats()`、`clear_cache()` |
| **嵌套目录** | 支持多级目录发现（最多约 5 层） |
| **脚本执行** | 技能目录内可带 Python/Shell/JS 等脚本，由库统一执行与安全控制（路径、超时等） |
| **API 形态** | `SkillManager()` → `discover()` → `list_skills()` / `invoke_skill(name, input)`；LangChain 集成：`create_langchain_tools(manager)` |

---

## 2. 与当前项目对比

| 维度 | skillkit | 本项目 |
|------|----------|--------|
| **发现范围** | 多源 + 优先级合并 | 单源 `skill_docs/` + `ENABLED_SKILLS` 过滤 |
| **目录结构** | 支持嵌套（多级） | 仅一层：`skill_docs/<id>/SKILL.md` |
| **元数据解析** | YAML 解析 + 校验 | 简单行匹配（name/description/executor），无校验 |
| **全文缓存** | `load_all` 有进程内缓存，**修改需重启** | 同：`_all_skill_docs_cache`，默认目录缓存 |
| **按需加载 content** | 有；且对「单技能 content」做 **LRU + mtime 失效** | 有 `load_skill_by_name` + `load_skill` 工具，**无 content 级缓存**，每次从文件/全表扫描 |
| **渐进式披露** | 元数据优先 + 按需拉 content + 附件 | 已实现：目录模式 + `load_skill` 工具 |
| **执行方式** | 技能内脚本 或 自然语言 invoke | 工具调用（tool + arguments） + 部分技能 HTTP executor |
| **Manager API** | discover / list_skills / invoke_skill | get_skill_docs_for_prompt / get_skills / execute_tool / execute_load_skill |

结论：**发现与缓存**上可向 skillkit 借鉴（多源/嵌套、content 缓存 + mtime）；**执行模型**保持现有「工具 + 参数 + HTTP 执行器」即可，不必引入脚本执行除非有明确需求。

---

## 3. 可借鉴点与落地建议

### 3.1 按需加载的 content 缓存（高价值）

- **现状**：`load_skill_by_name()` 每次通过目录遍历 + `load_skill_doc()` 读文件，同一会话内多次 `load_skill(meeting)` 会重复 I/O。
- **借鉴**：skillkit 的 LRU content 缓存 + 按文件 mtime 失效。
- **建议**：
  - 在 `skill_loader` 中为「单技能文档」增加可选缓存：key 为 `(skill_id 或 name, skill_docs_root)`，value 为 `{mtime, doc}`；若当前 `SKILL.md` 的 mtime 与缓存一致则直接返回缓存，否则重新加载并更新缓存。
  - 可配置：如 `skill_content_cache_size=0` 表示关闭，&gt;0 表示最多保留 N 个技能的 content 缓存；或简单用 dict + 单技能 mtime，不做 LRU（技能数通常不多）。
  - 这样在**目录模式 + 多轮对话**下，重复加载同一技能不会反复读盘，且修改 SKILL.md 后下次加载会自动生效。

### 3.2 多源发现与优先级（中长期）

- **现状**：仅从 `skill_docs`（及可选的 `skill_docs_root`）发现；启用列表由 `ENABLED_SKILLS` 控制。
- **借鉴**：skillkit 支持多个来源（项目、配置、插件、自定义路径）并按优先级合并，重名时先到先得或显式优先级。
- **建议**：
  - 若未来需要「内置技能 + 插件技能 + 用户目录」，可引入 `skill_sources: list[Path]` 或类似配置，按顺序扫描并合并；重名时以第一个为准（或约定 later source 覆盖），并在文档中写清优先级规则。
  - 当前单源若已满足需求，可仅保留在文档中说明「与 skillkit 多源设计的差异」，待有需求再实现。

### 3.3 Frontmatter 校验（低优先级）

- **现状**：`_parse_frontmatter` 仅做行匹配，缺少 `name`/`description` 时用目录名或空串兜底，无明确校验与报错。
- **借鉴**：skillkit 对 YAML 做校验，必填字段缺失会报错。
- **建议**：
  - 在 `load_skill_doc()` 内增加可选校验：若 `name` 为空且无 `id` 则打 warning 或返回 None；若需严格兼容 Anthropic 规范，可要求 `name` 与 `description` 必填并在解析失败时记录清晰错误，便于排查错误 SKILL.md。

### 3.4 嵌套目录发现（按需）

- **现状**：只发现 `skill_docs` 下**一层**子目录（每个子目录一个技能）。
- **借鉴**：skillkit 支持最多 5 层嵌套，技能 ID 可用路径表示（如 `a/b/c`）。
- **建议**：
  - 若希望支持 `skill_docs/team-a/meeting/SKILL.md` 这类结构，可将发现逻辑改为递归遍历，技能 ID 取相对路径（如 `team-a/meeting`），与现有 `id`/目录名 的约定兼容即可。
  - 若当前扁平结构已够用，可暂不实现，仅在文档中注明「当前仅一层」。

### 3.5 不采纳或延后

- **脚本执行**：skillkit 支持在技能目录内执行 Python/Shell 等脚本。本项目当前以「工具 + HTTP 执行器」为主，若未规划「技能内嵌脚本」能力，可不引入，以降低复杂度和安全面。
- **直接依赖 skillkit**：技能**发现/加载**应与具体 Agent、会议等业务解耦（见 `ARCHITECTURE_EXTENSIBILITY.md`）。解耦后，若在 **Skill Catalog 层** 用 skillkit 实现发现/加载，仅替换该层即可，不涉及 Tool 执行与会议业务；当前因 SkillManager 将发现/加载与 Tool 执行混在一起，直接替换成本较高。建议先完成「Catalog 与 Tool 执行分离」，再视需要引入 skillkit 作为 Catalog 实现。

---

## 4. 总结

| 借鉴项 | 优先级 | 说明 |
|--------|--------|------|
| **按需加载 content 缓存（mtime 失效）** | 高 | 减少重复 I/O、与渐进式披露配合好；实现成本低 |
| **多源发现与优先级** | 中/长期 | 有「多目录/插件」需求时再做 |
| **Frontmatter 校验** | 低 | 提升可观测性与排错体验 |
| **嵌套目录** | 按需 | 有分层组织需求时再支持 |
| **脚本执行 / 引入 skillkit 库** | 不采纳或延后 | 与当前架构与安全策略不符或收益有限 |

当前项目在「渐进式披露 + load_skill 工具 + Manager 门面」上已与 skillkit 的设计思路对齐；**最值得马上落地的**是在 `load_skill_by_name`（及 `execute_load_skill`）路径上增加**按技能 ID 的 content 缓存，并按 SKILL.md 的 mtime 失效**，这样在不改 API、不增加依赖的前提下即可获得明显的加载与内存收益。
