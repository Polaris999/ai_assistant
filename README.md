# AI Assistant

统一对话助手：**语音或文本**输入，支持会议预定、查会议室、取消等；后续可扩展运维工单等技能。基于 **LangChain + LangGraph + Skills + RAG**，LLM/Embeddings/向量库按配置切换。

## 技术栈

- **Agent**：LangGraph `create_react_agent` + 技能转 LangChain Tool（意图短路 → ReAct → 技能执行）；详见 [LLM 交互流程规范](docs/LLM_INTERACTION_FLOW.md)。
- **技能层**：技能由 `skill_docs/` 发现，会议等通过 GenericSkill 调 HTTP 后端执行；订会/提醒由技能后端承担。
- **胶水层**：LLM（vllm / openai / dify）、Embeddings（openai / api）、向量库（chroma / qdrant / weaviate）。
- **RAG**：知识库 API（会议等默认知识、检索/追加/清空），供管理端或技能后端使用。

## 快速开始

```bash
# 按 profile 加载：未设时用 dev，加载 .env.dev 再 .env（.env 覆盖）
# 设 APP_PROFILE=prod 则加载 .env.prod 再 .env。密钥与覆盖写在 .env 或环境变量
# 可选：cp .env.example .env 并编辑

pip install -e .
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- **API**（统一前缀 `/api/v1`）：`POST /api/v1/chat`、`POST /api/v1/chat/voice`、`GET /api/v1/health`；知识库：`GET /api/v1/knowledge/bases`、`GET /api/v1/knowledge?kb=`、`GET /api/v1/knowledge/search?q=&kb=`、`POST /api/v1/knowledge?kb=`、`DELETE /api/v1/knowledge?kb=`，建议由网关限制为管理端
- **多轮会话**：首轮不传 `conversation_id`，响应 `data.conversation_id` 供下一轮携带；同会话内支持追问与补全（如先问「订个会」再补「明天下午3点」）。
- **命令行**：`ai-assistant --text "明天下午3点开项目会，1小时，会议室A"` 或 `ai-assistant --voice path/to.wav`

响应格式统一为 `code` / `msg` / `data` / `request_id`，`code === 0` 表示成功；`data.conversation_id` 用于多轮。

---

## 文档导航

| 类型 | 文档 | 说明 |
|------|------|------|
| **核心流程** | [docs/LLM_INTERACTION_FLOW.md](docs/LLM_INTERACTION_FLOW.md) | LLM 交互五阶段规范（意图短路 → LLM → 解析回退 → 执行 → 响应） |
| **Agent 模式与命名** | [docs/AGENT_MODES_AND_NAMING.md](docs/AGENT_MODES_AND_NAMING.md) | 业界命名（Function Calling / ReAct / Plan-and-Execute）、与项目对应、是否需全实现 |
| **自研与框架选型** | [docs/AGENT_FRAMEWORKS.md](docs/AGENT_FRAMEWORKS.md) | 现成框架（LangGraph、CrewAI 等）能否支撑、何时迁框架/何时继续自研 |
| **统一框架迁移** | [docs/UNIFIED_FRAMEWORK_MIGRATION.md](docs/UNIFIED_FRAMEWORK_MIGRATION.md) | 自造轮子审计、LangGraph 接入、AGENT_TYPE=langgraph 使用说明 |
| **工具与 LangChain** | [docs/TOOLS_AND_LANGCHAIN.md](docs/TOOLS_AND_LANGCHAIN.md) | 为何用技能+tools.json 而非 LangChain @tool、何时可引入 @tool |
| **代码审查与最佳实践** | [docs/CODE_REVIEW_ARCHITECT_REPORT.md](docs/CODE_REVIEW_ARCHITECT_REPORT.md) | 架构师视角的全面审查：分层、技术选型、逻辑质量、风格、文档与可操作改进建议 |
| **开发手册** | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 框架复用、新增 Agent、开发与测试、代码规范 |
| **技术架构** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层架构、核心流程、框架设计与评论 |
| **Skill 设计审核** | [docs/SKILL_DESIGN_REVIEW.md](docs/SKILL_DESIGN_REVIEW.md) | 技能封装/步骤/约束、少编码扩展、业内做法对照 |
| **安装部署** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 环境与依赖服务、本地/生产部署、K8s、vLLM Embedding |

---

## 项目结构（概要）

```
agent/
├── skill_docs/           # 技能文档（业内统一：每技能一文件夹 + SKILL.md），决定「有哪些技能」
│   └── meeting/          # 会议技能：SKILL.md（name、description、When/How to use、Guidelines）
├── src/ai_assistant/     # 主包
│   ├── agent/            # Agent 协议、LangGraph Runner、技能执行层（skills → LangChain Tool）
│   ├── config/           # 配置、Prompt 加载、skill_loader（发现 skill_docs）
│   ├── api/、core/、models/、rag/、services/、clients/、voice/
├── app.py                # FastAPI 入口
├── docs/                 # 开发手册、技术架构、安装部署
└── tests/
```

- **技能启用**：默认从 `skill_docs/` 发现全部有 SKILL.md 的技能；可选环境变量 `ENABLED_SKILLS=meeting,ops` 只启用指定 ID。
- **新技能两种方式**：① **仅 SKILL.md**：在 frontmatter 中写 `executor: { type: http, url: "https://..." }` 或 `url: ${ENV_VAR}`，由 GenericSkill 通过 HTTP 执行；② **SKILL.md + Python**：实现 Skill 并 `register(id, factory)`，见 [ARCHITECTURE §6.3.1](docs/ARCHITECTURE.md)。
- **会议仅 HTTP**：会议能力由 HTTP 后端提供，须配置 `MEETING_SKILL_URL` 后会议技能才加载；tool schema 见 `skill_docs/meeting/tools.json`，契约见 [docs/SKILL_HTTP_BACKEND.md](docs/SKILL_HTTP_BACKEND.md)。
- **skill-creator**：`ai-assistant create-skill <id> [--name NAME] [--description DESC] [--http-url URL] [--overwrite]` 生成 `skill_docs/<id>/SKILL.md` 模板，对齐 [Anthropic](https://github.com/anthropics/skills)/[LangChain](https://github.com/Lubu-Labs/langchain-agent-skills) 的 skill-creator 用法。

---

## 常见问题

- **WinError 1114 / c10.dll**：若仅用 vLLM + 单独 Embedding（不跑本地模型），可 `pip uninstall torch -y` 后启动。
- **向量库/Embedding 不可达**：使用 `ai-assistant --check-vector-store`、`ai-assistant --check-embedding` 自检；详见 [安装部署](docs/DEPLOYMENT.md)。

更多使用说明、扩展方式与部署细节见上述三类文档。
