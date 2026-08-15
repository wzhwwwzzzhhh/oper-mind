# P8 审计导出 —— 审计活动留档与外部核验 · Design

> 状态：已确认
> 更新：2026-08-14
> 用户已确认（2026-08-14）：§6 决策 1–5 全部拍板。
> 关联：`docs/prd/audit/P8-audit-export.md`（已确认 PRD，issue #79）、
> `docs/prd/audit/P8-audit-activity-log.md`（#62，检索已交付）、
> `docs/design/audit/P8审计操作记录Design.md`（已确认架构方案，本 Design 复用其领域模型与脱敏纪律）、
> `docs/产品定义.md` §4（安全治理层审计）、`docs/开发规范.md` §4/§5（脱敏与留痕纪律）、
> `docs/接口清单.md` 第五部分（审计行"导出/报表（另行排期）"）

## 1. 目标与范围

一句话目标：在既有 `GET /audit/activities` 安全摘要检索之上，新增 `GET /audit/export`——运维可按**同一套过滤条件**把审计活动全量（受条数上限约束）导出为可下载文件（CSV / Markdown），内容与审计页看到的**同一资源投影**一致，供季度合规核验与留档备查；无新增持久化、无迁移、无凭据。

### 做什么
- 新增 `GET /audit/export`：与 `GET /audit/activities` 相同的过滤参数（from/to、service_id、action_type、result）+ 格式参数 `format=csv|md`，返回 `Content-Disposition` 附件下载。
- 导出内容与列表资源**同构**（`AuditActivityData` 全字段投影，与 `AuditActivityResource` 一致），沿用既有脱敏纪律；对文本字段做敏感字面量**兜底脱敏**。
- 导出文件含**元信息块**（导出时间、过滤条件、条数、快照标注），无匹配记录返回"0 条"空文件（不抛错），超上限返回明确错误（不产半截文件）。
- 前端审计操作记录页新增"导出"按钮，携带当前过滤条件触发下载；导出中/空结果/超限/失败诚实提示。

### 明确不做（对齐 PRD）
- 不做报表/图表/统计汇总（只做明细导出；聚合报表另行排期）。
- 不做定时导出 / 邮件发送 / 归档订阅。
- 不导出原始事件、Trace 内部事件、CoT/Prompt、原始工具输出、原始异常、凭据/DSN/`sk-`。
- 不新增持久化、不迁移（复用 runs / action_events 既有表，只读快照）。
- 不改变 `GET /audit/activities` 契约与行为。
- 不做身份/权限模型（`产品定义.md` §7 未决）。
- 不做分片导出 / 后台任务 / 异步生成（单次上限内同步流式返回）。

## 2. 设计决策

### D1 · 接口契约：`GET /api/v1/audit/export`

| Query 参数 | 类型 | 说明 |
|---|---|---|
| `from` / `to` | datetime | 时间窗（可选）；`from > to` → 422（与列表一致） |
| `service_id` | str ≤64 | 服务过滤（可选）；未知 service_id → 空导出，不抛错 |
| `action_type` | 11 值枚举 | 审计类型过滤（可选） |
| `result` | 10 值枚举 | 结果过滤（可选） |
| `format` | `csv` \| `md`，默认 `csv` | 导出格式 |

- 过滤参数、枚举与校验语义**复用** `GET /audit/activities` 的同一枚举与领域映射（`AuditActivityType` / `AuditOutcome` / 窗口校验），并用测试断言"导出过滤结果与列表同条件一致"做等价保证（AC2"过滤语义与列表一致"）。
- 无 `cursor`/`limit` 参数：导出为全量快照，不分页。
- 响应：
  - `200` + `Content-Disposition: attachment; filename="audit-export-<UTC时间戳>.csv|md"`，媒体类型 `text/csv; charset=utf-8` 或 `text/markdown; charset=utf-8`。
  - 响应头 `X-Export-Count: <int>`：本次导出行数（0 条时前端据此诚实提示空结果）。
  - 响应头 `X-Request-Id`（必要）：由 `response_meta` / `apply_headers` 回显，前端 diagnostics（client.ts）依赖其校验协议（既有 `StreamingResponse` 先例 routes.py 1408–1418 同款带头）。
  - 错误走既有 `ApiV1Error` 协议体：`422 EXPORT_LIMIT_EXCEEDED`（超上限，message 建议收窄时间窗）；`422 VALIDATION_ERROR`（窗口不合法 / 枚举非法）。
  - **`EXPORT_LIMIT_EXCEEDED` 的错误映射约定**：该码**不加入** `routes.py` 的 `APPLICATION_ERROR_STATUS` 映射表（保持该表只收既有应用错误），超限由 `GET /audit/export` 路由**直接构造** `ApiV1Error(422, "EXPORT_LIMIT_EXCEEDED", ...)` 抛出（与列表路由直抛 `VALIDATION_ERROR` 同款先例），避免经 `raise_application_error` 落入 500；应用层 `AuditExportLimitExceededError` 仅作为服务层边界信号，路由捕获后转直抛。

### D2 · 导出内容：与列表同构的字段集 + 确定性排序

- **字段集**：与 `AuditActivityResource` **完全一致**（18 字段同投影）：`id` / `kind` / `type` / `occurred_at` / `service_id` / `session_id` / `session_title` / `outcome` / `summary` / `run_id` / `severity` / `confidence` / `proposal_status` / `verification_status` / `proposal_id` / `action_id` / `mode` / `approval_actor`。理由：AC1"内容与列表同构"，运维核验时可逐行对照审计页；不精简字段集（PRD 开放问题 Q3 推荐一致）。
- **排序**：`occurred_at desc, id desc`（与列表归并排序完全一致，AC8 确定性；PRD 开放问题 Q4 推荐一致）。
- **行构造**：复用领域模型 `AuditActivityData`（`backend/src/domain/audit.py`）与仓储查询路径，**不新增第二套投影**；run/action 专属字段为空时如实输出空值，`approval_actor` 仅 `approval_recorded` 项为"未记录"，其余为空（AC6，不伪造）。

### D3 · 条数上限与超限语义

- **上限**：单次导出 ≤ **5000 条**（PRD 开放问题 Q2 推荐值；一次导出约 5000 行 × 18 字段，内存与响应体量可控）。
- **实现**：仓储新增只读方法 `list_all_activities(max_items, filters...)`，两侧（runs / action_events）各取 `max_items + 1` 行，按 `(occurred_at desc, id desc)` 归并；归并后行数 > max_items ⟺ 超限（与既有分页 `has_more` 判定同一可证逻辑）。
- **超限行为**：不返回任何截断文件——直接 `422 EXPORT_LIMIT_EXCEEDED`，message 如实说明"结果超过单次导出上限 5000 条，请收窄时间窗或过滤条件后重试"（AC4）。**不做**"截断 + 文件内标注"方案（对留档核验不诚实，文件可能被误当作全量存档）。
- **性能**：单次查询（两侧各 ≤5001 行）替代列表分页循环，不逐页翻页；导出文本由生成器**流式写出**（`StreamingResponse` 逐块 yield），避免一次拼接大字符串。

### D4 · 兜底脱敏与元信息

- **兜底脱敏**：对导出文本字段 `session_title` / `summary` 复用 `src/core/tool_gateway.py` 的 `desensitize()`（`sk-` 密钥、`password=/token=/api_key=` 键值、`scheme://user:pass@host` 凭据段 → 占位符）做**最后一道防线**；结构化字段（id/枚举/时间/severity 等）本身是受控字面量，不做文本替换。兜底脱敏不改变列表接口（列表已由资源投影收敛）。
- **元信息块**（AC7，导出时间 / 过滤条件 / 条数 / 快照标注，如实呈现）：
  - CSV：文件前部为 `#` 注释行（`# 导出时间:`、`# 过滤条件:` 逐项列出实际使用的过滤值，未过滤项标注"无"、`# 条数:`、`# 说明: 只读快照，不含原始证据、工具输出与凭据`），空行后接表头 + 数据行。
  - Markdown：文件顶部 `## 导出元信息` 列表块（同四要素），其后 `## 活动记录` 表格。
  - 元信息中的过滤条件**如实序列化**（如 `from=2026-08-01T00:00:00Z` / `service_id=postgres-production` / 未过滤项 `无`），不写"全部"这类含糊值。
- **空结果**：返回 `200` + 元信息块（条数 0）+ CSV 仅有表头无数据行 / MD 仅元信息块与空表格说明"无匹配记录"（AC3，不抛错）。

### D5 · 前端导出入口

- **位置**：审计操作记录页（`frontend/src/features/audit/AuditPage.tsx`）页头操作区，与"刷新"并列新增"导出"按钮。
- **行为**：
  - 点击时携带**当前已应用过滤条件**（service_id / action_type / result / applied_from / applied_to），请求 `format=csv`（首版仅 CSV 下载入口；Markdown 能力由 API 提供，前端入口后续如需再加）。
  - 导出中按钮置 disabled 显示"导出中…"；成功 → 浏览器下载文件，并按响应头 `X-Export-Count` 提示"已导出 N 条"（0 条 → "当前条件下没有可导出的审计记录"）。
  - 超限（`EXPORT_LIMIT_EXCEEDED`）→ 页内提示超限与收窄建议；失败 → 诚实错误提示 + 可重试。
- **实现**：`frontend/src/api/v1/client.ts` 新增下载函数 `export_audit_activities(query, options)`——基于既有 `request_json` 同款 fetch 封装（`X-Request-Id` / 错误协议解析），但响应按 blob/text 处理并解析 `Content-Disposition` 文件名与 `X-Export-Count`；非 2xx 时解析 JSON error 抛 `ApiClientError`（与既有错误展示路径一致）。`generated.ts` 由 `npm run generate:api` 生成（OpenAPI 新增 `format` 参数与 422 响应描述），禁止手改。

## 3. 文件改动面

### 后端（backend/）
- **修改** `src/domain/audit_repositories.py` —— `AuditActivityRepository` 端口 Protocol 新增 `list_all_activities(max_items, filters...)` 声明（服务层经端口类型安全调用，保持端口/DI 纪律）。
- **修改** `src/infrastructure/persistence/audit_repositories.py` —— 实现 `list_all_activities(max_items, filters...) -> tuple[list[AuditActivityData], bool]`（超限标志；复用既有 `_run_select` / `_action_select` / `_run_activity` / `_action_activity`）。
- **修改** `src/application/audit_service.py` —— 新增 `export_activities(max_items, filters...) -> ExportResult`（领域层 `AuditExportResult`：items + truncated）。
- **新增** `src/domain/audit_export.py`（或并入 `src/domain/audit.py`）—— `AuditExportFormat`（csv/md）、`AuditExportResult`（items、truncated、exported_at）；导出文本渲染器 `src/application/audit_export_renderer.py`（CSV / Markdown 渲染 + `desensitize` 兜底 + 元信息块，纯函数便于单测）。
- **修改** `src/application/errors.py` —— 新增 `AuditExportLimitExceededError`（服务层边界信号，对应 422 `EXPORT_LIMIT_EXCEEDED`，由路由捕获后直抛）。
- **修改** `src/api/v1/routes.py` —— 新增 `GET /audit/export` 路由（`format` 枚举校验、窗口校验、超限 → 路由直抛 `ApiV1Error(422, "EXPORT_LIMIT_EXCEEDED", ...)`、`StreamingResponse` + `X-Export-Count` / `X-Request-Id` 头）。
- **新增** `backend/tests/test_audit_export_api.py` —— 导出与列表同构/过滤一致、确定性（两次导出内容一致）、空结果 0 条元信息、超限 422 与错误码、CSV/MD 结构与脱敏兜底、敏感字面量不进文件、`X-Export-Count` 头。

### 前端（frontend/）
- **修改** `src/api/v1/client.ts` —— `export_audit_activities` 下载函数（blob/text + 头解析）。
- **修改** `src/features/audit/AuditPage.tsx` —— "导出"按钮 + 导出中/成功/空/超限/失败提示。
- **修改** `src/features/audit/AuditPage.test.tsx` —— 导出按钮携带过滤条件、成功下载、空结果提示、超限/失败提示（MSW mock）。
- **修改** `src/test/handlers.ts` —— 导出接口 MSW handler（按 §8.1 追加式）。
- **修改** `src/api/v1/generated.ts` —— 由 `npm run generate:api` 重新生成（禁止手改）。

### 无功能改动部分
- 多 Agent 内核、审批执行链、Trace/SSE、`GET /audit/activities` 契约、服务中心、知识库、模型设置、会话工作台交互。

## 4. 可独立验收的改动单元（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **2 个独立可验收单元**：
- **U1 后端导出 API**：领域导出模型 + 仓储全量方法 + 应用服务 + 渲染器（CSV/MD）+ `/audit/export` 路由 + API 测试。验收语义：导出与列表同构（AC1）、过滤一致（AC2）、空态 0 条（AC3）、超限明确错误不产半截文件（AC4）、无敏感内容（AC5）、审批人"未记录"（AC6）、元信息四要素（AC7）、确定性（AC8）、回归（AC10）。
- **U2 前端导出入口**：client 下载函数 + AuditPage 导出按钮与状态提示 + 交互测试。验收语义：按钮携带当前过滤条件、成功下载、空/超限/失败诚实提示（AC9）、typecheck/test/build 通过（AC10）。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 导出与列表过滤语义漂移（两套组装） | 过滤复用同一枚举与领域映射（`AuditActivityType`/`AuditOutcome`/窗口校验），测试断言导出过滤结果与列表同条件一致 |
| 超限判定与既有分页 `has_more` 逻辑不一致 | 复用同一"每侧取 max+1，和 > max ⟺ 超限"可证判定；测试覆盖边界（恰 5000 / 5001 条） |
| summary 含换行/逗号破坏 CSV 结构 | Python `csv` 模块标准引用与转义；测试覆盖含逗号/换行/引号摘要 |
| 敏感字面量经文本字段漏进文件 | `desensitize()` 兜底 + 测试断言 `sk-`/`user:pass@` 不进文件 |
| 全量查询无裸时间索引 | 上限 5000 条约束查询规模；应用库数据量受产品使用规模约束（与既有检索同前提，PRD 禁迁移） |

- **回滚**：移除 `/audit/export` 路由注册 + 前端导出按钮即完全回退；无迁移、无凭据、无既有契约破坏（纯追加）。
- **门禁项清单**：新增公开 API（`GET /audit/export`，本 Design 覆盖）；无迁移、无凭据、无 Connector、无真实连接、无写能力（纯只读导出）。

## 6. 待用户确认的设计决策

1. **格式**：`format=csv|md` 双格式，默认 `csv`（PRD 开放问题 Q1 推荐组合）；前端首版入口仅下载 CSV，Markdown 能力由 API 提供后续按需加入口。备选：首版仅 CSV 单格式（实现更小）。
2. **条数上限**：单次导出 ≤ **5000 条**，超限返回 `422 EXPORT_LIMIT_EXCEEDED` + 收窄建议，**不产截断文件**（PRD 开放问题 Q2；"截断+标注"方案对留档核验不诚实，未采纳）。
3. **字段集**：与列表资源 `AuditActivityResource` **完全一致（18 字段同投影）**，不精简（PRD 开放问题 Q3 推荐一致）。
4. **排序**：`occurred_at desc, id desc`，与列表一致（PRD 开放问题 Q4 推荐一致）。
5. **兜底脱敏**：导出文本字段（`session_title`/`summary`）复用 `tool_gateway.desensitize()` 兜底（`sk-`/键值凭据/URL 凭据段 → 占位符）；结构化枚举字段不做文本替换。

> 用户确认后，将本文件顶部 `> 状态：草稿` 改为 `> 状态：已确认`，再放行到 dev-plan。
