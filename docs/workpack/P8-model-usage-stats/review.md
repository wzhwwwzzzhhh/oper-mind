# 代码审查：P8-model-usage-stats

总体：PASS（无 P0/P1）

> 审查方式：独立子代理因会话环境 tooling_blocked 连续失败；经用户同意由主 agent 以审查视角直接审查（非独立审查，如实标注）。审查输入：plan.md、PRD、Design、完整 git diff。

发现：
- [P2] routes.py `get_model_usage` 中 `getattr(services, "model_usage_service", None)` 可简化为直接属性访问（V1Services 为 frozen dataclass 且字段已声明 Optional）；不阻塞，风格问题。
- [P3] application/model_usage.py 的 `stats()` 仅 catch `SQLAlchemyError`（对齐 `model_params.py` 先例）；若 reader 抛非存储异常会上抛为 500——与既有降级纪律一致，已注释说明。

核对项（全部通过）：
- 与 plan/PRD 映射：AC1–AC10 全覆盖；无越界文件、无过度实现。
- 分层合规：domain 三个 Protocol 端口（UsageRecorder / ModelUsageReader / PriceOverridesReader）；application 仅依赖 domain（ruff TID251 全绿）；infrastructure 实现在 dependencies.py 装配；跨层 TypedDict/Pydantic。
- 安全边界：无凭据路径；`model_usage_records` 表无内容字段；响应仅聚合计数与单价；错误走 ApiV1Error 包络；诚实空态与降级（应用库不可用 → 空统计）。
- 迁移：revision `20260813_13_p8_model_usage`、down_revision 钉死 `20260812_12_p8_run_rerun`；upgrade/downgrade 对称；约束与索引合理。
- 测试：采集（真实落库/usage 字段映射/mock 不采集/失败不阻断）、接口（聚合/时间窗/单价/空态/脱敏/422）、前端（展示/筛选/失败态）均覆盖。

AC 证据表：
- AC1: PASS（`test_真实调用后usage落库`、`test_recorder真实落库与聚合查询`）
- AC2: PASS（`test_按模型聚合返回token与估算花费`）
- AC3: PASS（`test_时间窗过滤只返回窗口内`、`test_from晚于to返回422`、`test_窗口跨度超过366天返回422`）
- AC4: PASS（`test_配置单价后按配置估算`、`test_未列出模型回退通用默认并标注unset`、响应 `estimate: true`）
- AC5: PASS（`test_mock调用不采集`、`test_mock模式统计为空态`）
- AC6: PASS（`test_无记录返回空态`，HTTP 200 + items=[]）
- AC7: PASS（`test_响应不含凭据与调用内容`；表结构无内容字段）
- AC8: PASS（`test_采集失败不影响调用`）
- AC9: PASS（前端 `展示用量统计聚合与估算标注`、`切换时间窗筛选后仍展示统计`、`用量统计读取失败时诚实提示`）
- AC10: PASS（后端全量 504 passed / 2 skipped；前端 typecheck + ModelSettingsPage 17 tests + build 通过）

结论：PASS（无 P0/P1，允许进入提交与交付）。
