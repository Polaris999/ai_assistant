# 可改进项

基于当前代码与使用场景整理的改进建议，按优先级与工作量分类。

---

## 一、体验与健壮性（优先）

### 1. 健康检查区分「存活」与「就绪」 ✅ 已实现

- **实现**：`GET /api/v1/health` 增加 `checks.agent: "ok" | "placeholder"`（占位时 `_scheduler` 为 None），便于就绪探针。

### 2. API 返回结构化错误与状态码 ✅ 已实现

- **实现**：`/api/v1/book`、`/api/v1/book/voice` 改为 JSON 响应 `{ "reply", "booking", "error", "request_id" }`；成功 200，Agent 未就绪（RUNTIME_ERROR/CONFIG_ERROR）503，参数校验失败 422。

### 3. 配置校验（可选启动时校验） ✅ 已实现

- **实现**：`config/validation.py` 提供 `validate_settings()`（仅检查必填项，不发起请求），lifespan 启动时调用，不通过则打 WARNING，不阻塞启动；另有 `validate_settings_or_raise()` 可供 CLI 使用。

---

## 二、接口与抽象（参考 Dify）

### 4. Embedding 基类增加可选异步接口 ✅ 已实现

- **实现**：`BaseEmbeddings` 增加 `aembed_documents`、`aembed_query`，默认委托同步方法，子类可覆盖。

### 5. 检索策略可配置（语义 / 关键词 / 混合）

- **现状**：RAG 仅做语义检索（向量相似度）。
- **建议**：参考 Dify 的 `RetrievalMethod` 枚举，增加配置项（如 `RAG_RETRIEVAL_METHOD=semantic_search|keyword_search|hybrid_search`），在 `MeetingRAG` 中按策略调用不同检索路径（若向量库支持）；当前 Chroma 可先只支持 semantic，为后续扩展留口子。

### 6. LLM/Embedding 调用超时与重试

- **现状**：vLLM 适配器有 timeout 配置，OpenAI/Embedding 多为库默认，无统一重试。
- **建议**：在 `BaseLLM`/适配器层统一超时参数（如从 settings 读取），对可重试错误（网络、429）做有限次数重试并记录日志，避免单次超时或限流导致整请求失败。

---

## 三、安全与运维

### 7. 请求体大小与频率限制 ✅ 已满足

- **已实现**：`api_book_text_max_length`（默认 2000）、`api_voice_max_bytes`（默认 10MB），超限返回 422。限流由网关负责，应用层不实现。

### 8. 敏感配置不落日志 ✅ 已实现

- **实现**：`core/helper.py` 提供 `mask_secret()`；Agent 创建失败时若异常信息过长（>500 字）则日志中脱敏，接口仍返回完整错误给调用方。

### 9. 依赖版本与安全

- **现状**：`requirements.txt` / `pyproject.toml` 使用最低版本约束（如 `>=0.3.0`），未固定上限。
- **建议**：定期 `pip audit` 或 Dependabot；对关键依赖可加上限（如 `langchain-core>=0.3,<0.4`）减少破坏性升级，并在 CI 中跑测试。

---

## 四、测试与可维护性

### 10. 胶水层单测与 Mock

- **现状**：有 `test_models`、`test_api`、`test_meeting_agent`，对 `get_llm`/`get_embeddings`/`get_vector_store` 的边界与失败路径覆盖不足。
- **建议**：为各 factory 写单测（Mock settings 与 HTTP），覆盖 `ConfigError`、不支持的 type、缺失配置等；对占位 Agent 的 invoke 返回格式做断言。

### 11. 集成测试与真实后端

- **现状**：无文档说明如何用本地 vLLM/Chroma 跑一次完整流程。
- **建议**：在 `docs/` 或 README 中增加「本地联调」小节：启动 vLLM + Embedding 服务 + 本应用，用 curl 调用 `/api/v1/book`，验证 RAG → 解析 → 预定 → 回复；可选 docker-compose 一键起依赖服务。

### 12. 文档与类型

- **现状**：部分函数缺 docstring 或类型注解，OpenAPI 描述较简略。
- **建议**：为 core 层（factory、adapter）补充简短 docstring 与返回类型；FastAPI 的 summary/description 可补充请求示例与错误响应示例，便于生成清晰 API 文档。

---

## 五、小结（按优先级）

| 优先级 | 项 | 说明 |
|--------|----|------|
| 高 | 健康检查就绪状态 | 便于部署与探针 |
| 高 | API 返回 JSON/状态码 | 便于前端与调用方 |
| 中 | 配置校验（含可选连通性） | 启动即可发现问题 |
| 中 | 超时与重试 | 提升稳定性 |
| 中 | 请求大小与限流 | 安全与防滥用 |
| 低 | Embedding 异步接口 | 高并发优化 |
| 低 | 检索策略可配置 | 扩展 RAG 能力 |
| 低 | 胶水层单测与集成文档 | 可维护性与联调 |

---

## 六、还可改进（未做）

| 项 | 说明 |
|----|------|
| **超时与重试** | LLM/Embedding 统一超时（settings），可重试错误（网络/429）有限次重试 |
| ~~限流~~ | 由网关做，应用层不考虑 |
| **依赖版本上限** | 关键依赖加版本上限（如 `langchain-core>=0.3,<0.4`），CI 跑 `pip audit` |
| **检索策略** | RAG 配置 semantic/keyword/hybrid，向量库支持时再实现 |
| **胶水层单测** | factory 单测（Mock settings/HTTP），覆盖 ConfigError、占位返回格式 |
| **本地联调文档** | README 或 docs 写「启动 vLLM+Embedding+本应用 + curl 示例」或 docker-compose |
| **CLI --check-config** | `meeting-agent --check-config` 调用 `validate_settings_or_raise()` 便于脚本检查 |
| **根路径 / 兜底** | `GET /` 重定向到 `/static/book_example.html`，若 static 不存在可改为 404 或简单 JSON 欢迎页 |

以上按需实施即可。
