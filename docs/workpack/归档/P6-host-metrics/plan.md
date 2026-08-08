# P6-host-metrics · 工作包计划

> 关联 Design：`docs/design/monitor/P6服务主机指标监控Design.md`（已确认）
> 关联 PRD：`docs/prd/monitor/P6-host-metrics-monitoring.md`（issue #23，状态：已确认）
> 分支：`feat/P6-host-metrics`，worktree：`D:/market-handsome/oper-mind-worktrees/P6-host-metrics`，基线：`main`

## 范围

### 只做（映射到 PRD 功能需求/AC）

- AC1：服务详情页展示主机 CPU/内存/磁盘/网络当前状态与异常进程（真实采集，mock 模式读场景）。
- AC2：psutil 不可用时主机指标返回「不可用」降级，不伪造数值。
- AC3：主机指标被 `MonitorSampler` 定时采样，历史样本（CPU/内存/磁盘）进入趋势接口，详情页可看走势。
- AC4：不可用/未采样时主机标量置 null，不用 0 代替缺失。
- AC5：mock 模式（`set_active_scenario("S1")`）主机指标返回原 mock 结果，与改动前一致。
- AC6：主机指标经网关脱敏；无凭据/DSN/原始异常进日志、Trace、结果、前端。
- AC7：回归 —— `test_monitoring.py`、`test_monitor_history_api.py`、新增 `test_server_tools.py`/`test_host_metrics.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

### 明确不做

- 远程主机 SSH/Agent 部署（只采后端所在主机）。
- 主机级告警规则、独立主机监控页面、外部监控系统（Prometheus/Grafana）。
- 修改 `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径。
- 修改 `server_tools.py`（agent 侧字符串工具保持现状）。
- 新增独立主机样本表（扩展既有 `service_monitor_samples`）。

## 切片拆分（3 个独立可验收切片）

- [ ] S1：`src/domain/host_metrics.py` 模型与端口 + `PsutilHostMetricsCollector`（psutil / mock 解析 / 诚实降级 / 时间预算 / TTL 缓存）+ `test_host_metrics.py`、`test_server_tools.py`（AC5 mock 回归锚点）。验收：AC2/AC4/AC5 后端单测全绿。
- [ ] S2：`ServiceViewData.host_metrics` + service_center 装配 + API schemas/resources + `service_monitor_samples` 迁移 + 采样器主机字段（失败只置 null 不改服务状态）+ 历史接口。验收：AC1/AC3/AC6 后端 + API 测试全绿，迁移 upgrade/downgrade 通过。
- [ ] S3：前端主机指标卡片 + 「后端所在主机·单主机采集」标注 + CPU/内存/磁盘走势 + 交互测试 + `generate:api` 再生成。验收：AC1/AC3/AC6/AC7 前端 `typecheck`/`test`/`build` 通过。

## 改动面（文件级，按 Design §3）

### 后端（新增/修改）

- `backend/src/domain/host_metrics.py`（新增）：`HostMetricsData` / `HostDiskPartitionData` / `HostProcessData` / `HostMetricsCollector`；`HostMetricsMode` / `HostMetricsSourceStatus` 本地枚举，不 import `services.py` 枚举。
- `backend/src/domain/services.py`：`ServiceViewData` 加必选 `host_metrics: HostMetricsData`（单向依赖 `host_metrics.py`）。
- `backend/src/domain/monitoring.py`：`ServiceMonitorSampleData` 加 4 个主机标量（`host_cpu_percent` / `host_memory_percent` / `host_memory_bytes` / `host_disk_used_percent`）。
- `backend/src/infrastructure/monitoring/host_metrics.py`（新增）：`PsutilHostMetricsCollector`。
- `backend/src/infrastructure/monitoring/sampler.py`：注入 host collector，每轮一次采集写入各样本主机字段，失败只置 null。
- `backend/src/application/service_center.py`：注入 `host_metrics_collector: HostMetricsCollector | None = None`，防御性 fallback unavailable，list/get_service 附加 host_metrics；list 每请求一次 collect。
- `backend/src/infrastructure/persistence/models.py`：`ServiceMonitorSampleRecord` 加 4 个主机列。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：读写主机字段。
- `backend/src/config.py`：`OPERMIND_HOST_METRICS_CACHE_SECONDS`（默认 10，0–600）+ `load_host_metrics_settings()`。
- `backend/src/api/v1/schemas.py`：`HostMetricsResource`、`ServiceResource.host_metrics`、`MonitorSampleResource` 4 个主机字段。
- `backend/src/api/v1/resources.py`：`host_metrics_resource` mapper、`service_resource` 接入（恒产出，unavailable 兜底）。
- `backend/src/api/v1/dependencies.py`：装配 host collector（sampler + service_center）。
- `backend/migrations/versions/<ts>_p6_host_metrics.py`（新增）：加 4 列 + CheckConstraint + downgrade，沿用 `batch_alter_table` + PRAGMA 模式。
- `config/config.example.yaml`：新增配置项说明。
- 测试：`backend/tests/test_host_metrics.py`（新增）、`backend/tests/test_server_tools.py`（新增）、更新 `test_monitoring.py` / `test_monitor_history_api.py` / `test_p4_service_center.py` / 迁移测试。

### 前端（新增/修改）

- `frontend/src/api/v1/generated.ts`（重新生成，禁止手工编辑）、`client.ts`、`queries.ts`。
- `frontend/src/features/services/ServiceDetailPage.tsx`：主机指标卡片 + 采集范围标注 + CPU/内存/磁盘走势。
- `frontend/src/features/services/ServiceDetailPage.test.tsx`：成功 / 不可用 / 空态 / 异常进程 / 采集范围标注 / 诚实标注。
- `frontend/src/test/handlers.ts`：MSW 主机指标与样本 fixture。

### 迁移 / 接口契约 / 数据库变更标注

- **数据库迁移**：`service_monitor_samples` 加 4 列（upgrade + downgrade，batch_alter_table）。
- **公开 API 契约扩展**：`ServiceResource.host_metrics`、`MonitorSampleResource` 主机字段（既有字段兼容）。

## 验证方法

- 后端（从 worktree `backend/` 执行，仓库根 `.venv`）：
  - `..\.venv\Scripts\python.exe -m pytest tests/test_host_metrics.py tests/test_server_tools.py -q`
  - `..\.venv\Scripts\python.exe -m pytest tests/test_monitoring.py tests/test_monitor_history_api.py tests/test_p4_service_center.py -q`
- 迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head` 与 `downgrade -1`。
- 前端（worktree `frontend/`）：`npm install` 后 `npm run typecheck`、`npm run test`、`npm run build`；`npm run generate:api`（后端 8000 提供 OpenAPI 时）。
- 门禁：`git diff --check`；相关 pytest 全绿；只暂存工作包文件。

## 提交计划

- S1：`feat: P6 主机指标采集器与领域模型（host_metrics）`
- S2：`feat: P6 主机指标接入服务快照/历史采样与 API 契约`
- S3：`feat: P6 服务详情页主机指标卡片与 CPU/内存/磁盘走势`
- 收尾：`docs: P6 主机指标工作包归档与 PRD/Design 状态推进`

## 分支记录

- 分支名：`feat/P6-host-metrics`
- worktree 路径：`D:/market-handsome/oper-mind-worktrees/P6-host-metrics`
- 基线：`main`（`0f532ab`）
