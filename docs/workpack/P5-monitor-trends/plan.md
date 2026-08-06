# P5-monitor-trends · 工作包计划

## 范围

### 只做

- AC1–AC3：对静态注册服务周期采样，将可用、未配置、不可用状态和脱敏标量写入历史样本。
- AC4：提供按 `service_id` 和时间窗口查询的只读历史接口，返回按时间升序的脱敏样本。
- AC5：服务详情页无历史数据时展示“暂无历史采样”诚实空态，不绘制假趋势。
- AC6：对慢查询、超时和可用性变化采样点做页面内高亮，并展示“采样点异常”摘要。
- AC7：展示定时采样频率、保留窗口和历史记录来源标注，不使用实时监控表述。
- AC8：保持 mock 模式、现有服务快照接口和既有服务中心回归路径不变。
- AC9：样本、API 和页面不出现 SQL、对象名、原始日志、DSN、凭据或 `sk-` 内容。

### 明确不做

- 外部告警推送、通知渠道、告警确认/恢复和可配置告警规则。
- 秒级或近实时监控、SSE/WebSocket 推送、跨进程协调、采样器高可用和补采样。
- 跨服务对比、历史搜索、导出、聚合报表和独立监控大盘。
- 新服务类型、Connector、凭据管理、连接测试和动态服务注册。
- 修改 mock 数据源、S1–S4 评测路径或既有 `GET /services`、`GET /services/{id}` 契约。

## 切片拆分

- [x] S1：历史样本领域模型、ORM/迁移、仓储和单进程定时采样器，覆盖 AC1–AC3、AC8、AC9。
- [x] S2：历史趋势查询应用服务与 v1 API，覆盖 AC1–AC4、AC9。
- [x] S3：服务详情页历史趋势、异常点高亮、诚实状态和前端交互测试，覆盖 AC5–AC8。

## 改动面

### 后端

- `backend/src/config.py`：采样频率、保留窗口和最大查询窗口配置。
- `backend/src/domain/monitoring.py`：样本、查询响应和状态模型。
- `backend/src/infrastructure/persistence/models.py`：历史样本 ORM。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：样本写入、查询和清理。
- `backend/src/application/monitoring.py`：采样与历史查询用例。
- `backend/src/infrastructure/monitoring/sampler.py`：lifespan 后台采样任务。
- `backend/src/api/v1/schemas.py`、`routes.py`：历史查询 API 契约和路由。
- `backend/src/api/v1/dependencies.py`、`backend/src/app.py`：依赖和生命周期装配。
- `backend/migrations/versions/<timestamp>_p5_monitor_samples.py`：新增历史表、索引和约束，提供 downgrade。
- `backend/tests/test_monitoring.py`、`backend/tests/test_monitor_history_api.py` 及迁移测试。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`、`generated.ts`：历史接口 client、query 和生成类型。
- `frontend/src/features/services/ServiceDetailPage.tsx`：趋势轨道、异常点和状态空态。
- `frontend/src/features/services/ServiceDetailPage.test.tsx` 或现有页面测试文件。
- `frontend/src/test/handlers.ts`：历史样本 MSW fixture。

## 验证方法

- 后端迁移：从干净测试数据库执行 `..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`，验证表、索引、约束；执行 downgrade 测试。
- 后端测试：`..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端类型：`npm run typecheck`。
- 前端测试：`npm run test`。
- 前端构建：`npm run build`。
- 门禁：仅检查本工作包文件范围的 `git diff --check` 和敏感字面量；确认 mock 路径与既有服务接口回归通过。

## 提交计划

- S1：`feat: 增加服务历史采样与样本持久化`
- S2：`feat: 增加服务历史趋势查询接口`
- S3：`feat: 接入服务详情历史趋势与异常标记`

## 前置设计

- 设计文档：[P5监控历史趋势与页面告警Design.md](../../P5监控历史趋势与页面告警Design.md)
- 设计状态：已完成 Design → Review → 用户确认。
