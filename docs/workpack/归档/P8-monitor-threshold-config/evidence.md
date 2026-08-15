# P8-monitor-threshold-config · AC 证据表

> 关联 PRD：`docs/prd/service-center/P8-monitor-threshold-config.md`（issue #77）
> 关联 Design：`docs/design/service-center/P8监控阈值与关注项配置Design.md`（已确认，arch-review PASS）
> 分支：`feat/p8-monitor-threshold-config` · worktree：`D:/market-handsome/oper-mind-worktrees/p8-monitor-threshold-config`

## 验收标准证据

| AC | 验收标准 | 证据（代码/接口/测试） | 状态 |
|---|---|---|---|
| AC1 | GET 未配置服务返回内置默认并标注"默认" | `MonitorThresholdApplicationService.get()` 未配置 → `source=default` + `DEFAULT_MONITOR_THRESHOLDS`；`GET /api/v1/services/{id}/monitor/thresholds`；`test_未配置读取返回内置默认与default来源`、`test_GET未配置返回内置默认并标注default`；前端回显"内置默认"徽标 | ✅ |
| AC2 | PUT 保存合法配置返回视图且 GET 读回一致 | `save()` 单行 upsert（保存即生效）；`test_保存后读取返回一致配置与configured来源`、`test_PUT保存后GET读回一致`；前端保存后来源转"已配置" | ✅ |
| AC3 | PUT 非法配置（阈值<0/未知指标/窗口越界）→ 422 不落库 | schema `MonitorThresholdRequest`（extra=forbid + ge/le 约束，全量替换必填）；`test_非法配置在领域层被拒绝`、`test_PUT非法配置返回422且不落库`（负值/窗口 9999/未知字段/缺字段 4 例，GET 复核未落库） | ✅ |
| AC4 | 不存在服务 → 404 | 应用层 `SERVICE_NOT_FOUND` → 路由 404（复用既有安全错误语义）；`test_服务不存在抛出SERVICE_NOT_FOUND`、`test_不存在服务返回404`（GET+PUT） | ✅ |
| AC5 | 配置后 history/overview 异常计数按配置计算 | 后端 `_trend_summary` 读配置（窗口求和 ≥ 阈值，§2.3 契约）；`test_配置阈值后异常计数按配置计算`、`test_配置后概览异常计数按配置计算`（e2e）；前端趋势标记按同一契约复算（`is_anomalous_sample`）+ 测试 `配置阈值后运行趋势异常标记按配置复算` | ✅ |
| AC6 | 未配置时异常计数与配置前一致 | 默认常量（三项阈值 1/窗口 0/可用性变化 true）与旧 `_trend_summary` 逐点等价（含 Redis slowlog 分支、首样本不判、not_configured 排除）；`test_默认配置与现状异常判定等价`、`test_未配置服务概览行为与配置前一致`；既有 P5/P7 概览测试无需改动仍绿 | ✅ |
| AC7 | 配置持久化后重启读回一致 | 应用库表 `service_monitor_thresholds`（迁移 `20260815_13_p8_monitor_thresholds.py`，down_revision=20260812_12_p8_run_rerun）；`test_保存后读取返回一致配置与configured来源`（新会话读回）；迁移 upgrade/downgrade 全量测试通过 | ✅ |
| AC8 | 配置接口与响应无凭据/DSN/sk-/原始异常详情 | 白名单标量 schema（无表达式、无字符串输入）；`test_响应不含敏感内容`（GET+PUT 双响应扫描）；`test_配置行损坏回退内置默认`（防御性读取） | ✅ |
| AC9 | 前端详情页展示生效规则、编辑保存、失败/校验诚实提示 | `ThresholdConfigCard`（来源徽标/空态/加载态/422 错误气泡/保存成功提示/窗口与可用性开关/指标关注开关与阈值输入）；`ServiceDetailPage.test.tsx` 6 个交互测试（回显/已配置/编辑保存/422 提示/读取失败空态/趋势复算一致） | ✅ |
| AC10 | 回归全绿：monitor/service-center 相关 + 前端 typecheck/test/build | 后端全量 pytest 506 passed/2 skipped（含 `test_monitor_*`、`test_p2_schema`、`test_persistence_infrastructure`）；前端 `typecheck`/`build` 通过、ServiceDetailPage 10/10、MonitoringOverviewPage 7/7；全量前端失败集与基线一致（既有环境性时序 flakiness，非本包引入，见 review.md） | ✅ |

## 完成定义（DoD）核对

- [x] 全部 AC（AC1–AC10）通过（见上表）
- [x] 相关回归测试全绿：后端全量 506 passed / 2 skipped；前端受影响文件全绿
- [x] `git status` 只出现本工作包允许的文件（后端 8 修改 + 2 新增、前端 5 修改、docs 4 处）
- [x] 阈值配置表迁移执行成功：`test_p2_schema_alembic_fresh_db_约束降级与再次升级` 等迁移测试通过；downgrade 数据保护守卫测试通过
- [x] 前端 `typecheck` / `build` 通过
- [x] 配置接口与页面不含凭据/DSN/异常详情（AC8 测试 + 人工核对 diff）

## 验证记录

- 后端：`..\.venv\Scripts\python.exe -m pytest tests/test_monitor_thresholds.py -q` → 18 passed
- 后端：`..\.venv\Scripts\python.exe -m pytest tests -q` → **506 passed, 2 skipped**
- 迁移：upgrade head / downgrade（含"存在配置行拒绝回滚"守卫）→ `test_阈值迁移存在配置行时拒绝回滚`、`test_p2_schema_*` 通过
- 前端：`npm run typecheck` → 通过；`npm run build` → 通过；`npm run test` → ServiceDetailPage 10/10、MonitoringOverviewPage 7/7（全量失败集与基线一致，既有 flakiness）
- 门禁：`git diff --check` 干净；ruff 全绿；diff 复核无凭据/DSN/`sk-` 字面量；只暂存工作包文件
- 审查：独立只读子代理 review.md——初审 FAIL（P1：前端趋势标记未按配置复算）→ 修复 + 一致性测试 → 复审 PASS
