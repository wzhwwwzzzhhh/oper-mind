# P8-monitor-threshold-config · 工作包计划

> 关联 PRD：`docs/prd/service-center/P8-monitor-threshold-config.md`（已确认，issue #77）
> 关联 Design：`docs/design/service-center/P8监控阈值与关注项配置Design.md`（已确认，arch-review PASS）
> 分支：`feat/p8-monitor-threshold-config` · worktree：`D:/market-handsome/oper-mind-worktrees/p8-monitor-threshold-config` · 基线：`origin/main`（8a644f3）

## 范围

### 只做

- AC1/AC2：新增 `GET /api/v1/services/{id}/monitor/thresholds`（读）+ `PUT /api/v1/services/{id}/monitor/thresholds`（写），
  按服务维度；GET 未配置返回内置默认 + `source=default`；PUT 保存后 GET 读回一致。
- AC3/AC4：非法配置（阈值 < 0 / 窗口越界 / 未知字段 / 类型错误）→ 422 不落库；服务不存在 → 404。
- AC5/AC6：异常判定引擎改读配置——`_trend_summary` 不再按服务类型硬编码；
  默认配置下与现状行为逐点等价（AC6），配置后按配置计算（AC5）。
- AC7：配置持久化到应用库新表 `service_monitor_thresholds`（涉及迁移），重启读回一致。
- AC8：配置接口与响应不含凭据、DSN、`sk-`、原始异常详情。
- AC9：前端服务中心详情页新增"监控阈值"配置区——只读回显当前生效规则（内置默认/已配置诚实标注）、
  编辑保存、失败/校验诚实提示、空态/加载态正常。
- AC10：回归——既有 `test_monitor_*` / `test_service_center` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- 收尾：`docs/接口清单.md` 欠账行（监控阈值 / 关注项配置）更新为已交付。

### 明确不做

- 不做全局/跨服务阈值（按服务维度；全局默认由内置默认承担，不做全局覆盖）。
- 不做告警通道/通知；不改变采样本身（采样间隔、保留期、采样器不动）。
- 不做复杂规则引擎（只做数值下限 + 窗口 + 关注指标开关 + 可用性变化开关，不做表达式）。
- 不暴露凭据/DSN/原始异常详情。
- 不改变既有 `GET /services`、`GET /services/{id}/monitor/history`、`GET /monitor/overview` 的契约字段
  （仅异常计数/标记的语义按配置计算）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。

## 已确认设计决策（Design §6，用户已确认）

- 按服务维度单行表 `service_monitor_thresholds`（service_id 主键），未配置不落库，不做两级。
- 指标白名单固定三项（slow_query_count / timeout_count / slowlog_count），阈值 null=不关注、数值=关注；
  `count_availability_change` 开关独立配置。
- 窗口语义：当前采样点往前 `window_minutes` 分钟内（含两端）目标指标计数之和 ≥ 阈值 → 该点异常；
  `window_minutes=0` 仅当前采样点自身（内置默认）。
- GET 未配置时完整暴露内置默认 + `source=default`；内置默认 = 三项阈值 1 + 窗口 0 + 可用性变化计异常。
- 概览 `anomaly_sample_count` 后端按配置计算；服务详情页趋势异常点标记前端按同一确定性规则复算
  （规则边界语义钉死：首样本不判可用性异常、相邻既有样本比较；共享 fixture 锁定两端一致）。
- 校验：阈值 ∈ [0, 1000000]（null=不关注）、窗口 ∈ [0, 1440] 分钟、未知字段被 schema 拒绝 → 422 不落库；
  PUT 幂等无 Idempotency-Key。
- 迁移 downgrade 前检查存在配置行则拒绝回滚（对齐 p8_run_rerun / p8_service_registration 惯例）。

## 切片拆分（3 个独立可验收切片）

- [ ] S1：后端领域/持久化/判定引擎——`MonitorThresholdConfig`/`MonitorThresholdView`/`MonitorThresholdSource`/
  `DEFAULT_MONITOR_THRESHOLDS`、ORM `ServiceMonitorThresholdRecord`、仓储 `SqlAlchemyMonitorThresholdRepository`、
  迁移 `20260815_13_p8_monitor_thresholds.py`、`MonitorThresholdApplicationService`、`_trend_summary` 改读配置。
  验收：默认配置下异常计数与现状一致（AC6）；配置后按配置计算（AC5）；读写往返一致（AC2）；
  非法配置拒绝不落库（AC3）；未配置无记录；持久化后重进读回一致（AC7）；
  迁移 upgrade/downgrade（downgrade 存在配置行拒绝回滚）。
- [ ] S2：阈值 API 契约与路由——schema（Request/Response/Resource）+ `monitor_threshold_resource` mapper +
  GET/PUT 路由 + API 测试。验收：GET 未配置返回默认 + `source=default`（AC1）；PUT 保存后 GET 读回一致（AC2）；
  非法 422（AC3）；不存在服务 404（AC4）；响应无凭据/DSN（AC8）；既有监控接口回归。
- [ ] S3：前端配置区——`client.ts`/`queries.ts`（+`generated.ts` 经 generate:api 更新）、
  `ServiceDetailPage.tsx` 配置区、`handlers.ts` fixture、交互测试。验收：回显生效规则与来源标注（AC1/AC9）；
  编辑保存与失败/校验诚实提示（AC9）；加载/空态；`typecheck`/`test`/`build`（AC10）。

## 改动面（文件级）

### 后端

- `backend/src/domain/monitoring.py`：新增 `MonitorThresholdConfig`、`MonitorThresholdView`、`MonitorThresholdSource`、`DEFAULT_MONITOR_THRESHOLDS`。
- `backend/src/infrastructure/persistence/models.py`：新增 `ServiceMonitorThresholdRecord`。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：新增 `SqlAlchemyMonitorThresholdRepository`。
- `backend/src/application/monitoring.py`：新增 `MonitorThresholdApplicationService`；`_trend_summary` 按配置计算；`_service_overview` 注入配置读取。
- `backend/src/api/v1/schemas.py`：新增 `MonitorThresholdConfigResource`、`MonitorThresholdRequest`、`MonitorThresholdResponse`。
- `backend/src/api/v1/resources.py`：新增 `monitor_threshold_resource`。
- `backend/src/api/v1/routes.py`：新增 GET/PUT `/api/v1/services/{service_id}/monitor/thresholds`。
- `backend/migrations/versions/20260815_13_p8_monitor_thresholds.py`（新增，down_revision=20260812_12_p8_run_rerun，合并时按 §8.3 重指最新 head）。
- `backend/tests/test_monitor_thresholds.py`（新增）；`backend/tests/test_monitor_overview.py`（适配按配置计算）。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`：新增 `get_service_monitor_thresholds`、`update_service_monitor_thresholds`；`generated.ts` 仅经 `npm run generate:api` 更新。
- `frontend/src/features/services/ServiceDetailPage.tsx`：新增"监控阈值"配置区。
- `frontend/src/features/services/ServiceDetailPage.test.tsx`：新增配置区交互测试。
- `frontend/src/test/handlers.ts`：新增阈值 GET/PUT fixture。
- 样式复用 `service-detail.css`，一般不新增样式文件。

### 文档（随工作包 PR 交付）

- `docs/design/service-center/P8监控阈值与关注项配置Design.md`（已确认）。
- `docs/prd/service-center/P8-monitor-threshold-config.md`、`docs/prd/README.md`、`docs/prd/service-center/README.md`（PRD 状态推进）。
- `docs/workpack/README.md`（工作包登记）、`docs/workpack/P8-monitor-threshold-config/{plan,review,evidence}.md`。
- `docs/接口清单.md`：欠账行更新为已交付。

### 无功能改动

- 无新 Connector、无凭据/连接改动、无新配置项、无新服务类型；采样器/采样间隔/保留期不动。
- `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径不改；既有三个监控接口契约字段不变。

## 验证方法

- 后端（worktree 内 `backend/` 执行）：`..\.venv\Scripts\python.exe -m pytest tests/test_monitor_thresholds.py tests/test_monitor_overview.py -q`；
  回归 `..\.venv\Scripts\python.exe -m pytest tests/test_monitor_history_api.py tests/test_monitor_overview_api.py tests/test_monitoring.py tests/test_p4_service_center.py tests/test_p2_api_v1.py -q`；
  最后 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head` 在临时库验证 upgrade/downgrade（含 downgrade 数据保护）。
- 前端（worktree 内 `frontend/` 执行）：`npm install` 后 `npm run generate:api`、`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；审查变更确认无凭据、DSN、环境变量名、原始日志、原始异常或 `sk-` 字面量；
  只暂存工作包文件。

## 提交计划

- S1：`feat: P8 监控阈值领域模型、持久化与判定引擎读配置`
- S2：`feat: P8 监控阈值读写 API 契约与路由`
- S3：`feat: P8 服务详情页监控阈值配置区`
- 收尾：`docs: P8 监控阈值配置工作包与验收证据`

## 停审阅点

计划已就绪，待用户确认范围、切片、改动面、验证方法后进入 `dev-execute`。
