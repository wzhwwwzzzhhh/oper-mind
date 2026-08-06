# P6-knowledge-retrieval · 工作包计划

## 基线与确认

- PRD：`docs/prd/knowledge/P6-knowledge-retrieval.md`（状态：已确认）
- Design：`docs/design/knowledge/P6知识检索Design.md`（状态：已获用户确认，2026-08-06）
- 分支：`feat/p6-knowledge-retrieval`（基于 `main`，2026-08-06）
- 隔离清单：工作区 `docs/prd/session/P6-cross-service-investigation.md` 为他人未跟踪文件，不纳入本工作包，不暂存、不提交。

## 范围

### 只做

- 新增 `search_knowledge` Tool（`backend/src/tools/knowledge_tools.py`）：受管目录内确定性关键词/标题检索，返回脱敏摘要（标题 + 相对文件名 + 最多 2 个命中片段，前后各 60 字符），相关度排序（标题命中优先、正文命中次数、文档名升序），limit 1–10 默认 5。覆盖 PRD AC1–AC6。
- 新增 `KnowledgeAgent`（`backend/src/agents/knowledge_agent.py`）：继承 `BaseAgent`，注册 `SearchKnowledgeTool`，系统提示词含只读边界与诚实空态要求；`bootstrap.build_coordinator` 装配并 `register_agent("knowledge", ...)`。覆盖 PRD AC7。
- 配置读取（`backend/src/config.py`）：新增 `KnowledgeSettings` 与 `load_knowledge_settings()`，`OPERMIND_KNOWLEDGE_DIR` 环境变量优先，YAML `knowledge.directory` 兜底，默认空 → 未配置；不打印、不落日志/Trace。
- 路由扩展（`backend/src/core/graph.py`）：LLM 路由 prompt target 枚举加 `knowledge`；关键词兜底新增 `_KNOWLEDGE_KW`（知识/文档/SOP/手册/howto/操作指引/检索），判定顺序在 log 之后；chain 顺序不变；parallel 自然包含新 Agent。
- 网关小改（`backend/src/core/tool_gateway.py`）：`_finish("ok", ...)` 的 detail 支持工具可选 `audit_summary()`（缺省中性文案，既有工具零影响）；`SearchKnowledgeTool` 提供 `audit_summary()` → `知识检索命中 N 篇：<标题列表>`。覆盖 PRD AC8。
- 新增测试：`backend/tests/test_knowledge_tool.py`、`backend/tests/test_knowledge_agent.py`；既有 `test_tool_gateway.py`、`test_diagnosis.py` 回归。覆盖 PRD AC9 与 DoD。
- 工作包文档：`docs/workpack/P6-knowledge-retrieval/{plan,review,evidence}.md`、`docs/workpack/README.md` 登记。

### 明确不做

- 不做向量库/Embedding/RAG/语义检索（后续阶段）。
- 不做文件管理/上传/编辑知识文档的前端或接口；不新增公开 API、数据库表或迁移。
- 不授予任意文件系统路径访问；只检索配置目录，路径逃逸拒绝，符号链接越界跳过。
- 不检索非 Markdown/二进制/隐藏/凭据文件（`.env`、`*.local.yaml`、`.key/.pem/.secret`、含 `sk-` 内容）。
- 不接入外部知识源；不发起任何网络访问。
- 不修改 `data/mock_db.py`、`data/scenarios.py` 与 S1–S4 评测路径。
- 不做知识写入/索引持久化；不缓存、不建索引。
- 不改前端功能（前端零改动，仅回归 typecheck/test/build）；不修改 `docs/prd/session/P6-cross-service-investigation.md`。

## 切片拆分

- [ ] S1：配置读取 + `SearchKnowledgeTool`（校验/检索/排序/脱敏/诚实空态/路径逃逸/凭据排除）+ 单测。覆盖 AC1–AC6。
- [ ] S2：`KnowledgeAgent` + bootstrap 装配 + graph 路由扩展 + 网关 `audit_summary()` 小改 + 集成/路由测试。覆盖 AC7、AC8。
- [ ] S3：全量回归（后端全量 pytest、前端 typecheck/test/build、`git diff --check`、敏感字面量门禁、S1–S4 关键词路由不变断言）。覆盖 AC9 与 DoD。

## 改动面（文件级）

### 后端新增

- `backend/src/tools/knowledge_tools.py`：`SearchKnowledgeTool`（含 `audit_summary()`）。
- `backend/src/agents/knowledge_agent.py`：`KnowledgeAgent`。
- `backend/tests/test_knowledge_tool.py`：未配置/空目录/匹配排序/无匹配/路径逃逸/凭据排除/脱敏/limit 测试。
- `backend/tests/test_knowledge_agent.py`：Agent 注册、网关准入、路由 direct/parallel、S1–S4 关键词路由不变回归。

### 后端修改

- `backend/src/config.py`：`KnowledgeSettings`、`load_knowledge_settings()`。
- `backend/src/core/bootstrap.py`：装配并注册 `knowledge` Agent。
- `backend/src/core/graph.py`：路由 prompt 枚举与 `_KNOWLEDGE_KW`/`_keyword_target` 兜底。
- `backend/src/core/tool_gateway.py`：`_finish` 支持工具可选 `audit_summary()`。

### 文档

- `docs/design/knowledge/P6知识检索Design.md`（已确认，随本工作包提交）。
- `docs/workpack/P6-knowledge-retrieval/plan.md`、`review.md`（dev-execute 回写）、`evidence.md`（dev-execute 回写）。
- `docs/workpack/README.md`：登记活跃工作包。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_tool.py tests/test_knowledge_agent.py -q`。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端回归：从 `frontend/` 执行 `npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；检查 diff 无 DSN、密码、`sk-`、原始异常；不暂存 `docs/prd/session/P6-cross-service-investigation.md` 与无关文件。
- 真实资源门禁：测试全部使用 `tmp_path` 确定性目录，不连接任何外部资源。

## 提交计划

- S1：`feat: 实现目录内 Markdown 确定性检索工具`
- S2：`feat: 接入 knowledge Agent 与路由`
- S3：`test: 知识检索回归与门禁收尾`

提交前只暂存本工作包实际修改的文件，不使用 `git add .`。
