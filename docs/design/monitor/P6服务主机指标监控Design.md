# P6 服务主机指标监控 · Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/monitor/P6-host-metrics-monitoring.md`（issue #23）、`docs/design/monitor/P5监控历史趋势与页面告警Design.md`、`docs/prd/monitor/P5-monitor-trends.md`、`docs/产品定义.md` §5.5/§6、`docs/开发规范.md` §5、`backend/src/tools/server_tools.py`、`backend/src/infrastructure/monitoring/sampler.py`。

## 1. 目标与范围

**一句话目标**：把后端所在主机的 CPU/内存/磁盘/网络与异常进程作为**结构化主机指标**，纳入服务中心服务详情与 P5 历史采样/趋势，复用现有 psutil 采集能力并做到诚实降级。

### 做什么

- 新增确定性 `HostMetricsCollector` 端口与 `PsutilHostMetricsCollector` 实现：mock 模式读 `data/scenarios.py` 确定性场景，真实模式读 psutil；psutil 缺失或采集失败 → `unavailable` + 标量为 null，**不伪造数值**（对齐 PRD 功能需求 3）。
- `ServiceViewData` 增加 `host_metrics` 字段（**必选**，恒存在，`source_status` 表达诚实状态）；`GET /api/v1/services/{id}` 与 `GET /api/v1/services` 响应增加 `host_metrics` 对象。
- `service_monitor_samples` 历史样本表扩展主机标量列（CPU/内存/磁盘），`MonitorSampler` 每轮采样一次主机指标并写入各服务样本，趋势页自动展示 CPU/内存/磁盘走势（对齐 PRD 功能需求 2）。
- 前端服务详情页新增「主机指标」卡片（CPU/内存/磁盘/网络 + 异常进程），并**显式标注采集范围为「后端所在主机 · 单主机」**；运行趋势区新增 CPU/内存/磁盘走势。
- mock 模式（`set_active_scenario`）行为不变，S1–S4 评测确定性不受影响。

### 明确不做

- 不做远程主机 SSH/Agent 部署（本阶段只采后端所在主机）。
- 不做主机级告警规则（沿用 P5 告警范围，不新增）。
- 不新增独立「主机监控」页面（并入服务详情页）。
- 不接外部监控系统（Prometheus / Grafana 等）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。
- **不修改 `server_tools.py`**：agent 侧字符串工具保持现状（mock 返回不变，保证 S1–S4）；真实模式无 psutil 时的伪造回退属于既有工具实现问题，本工作包的诚实修复落在新的结构化采集路径上，不做 agent 工具行为变更。
- 不新增独立「主机样本表」：历史主机标量并入既有 `service_monitor_samples`。

## 2. 设计决策

### 2.1 主机指标范围与绑定（回答 PRD 开放问题 2）

- **单一后端主机**：只采运行后端的这一台主机（`psutil` 所在进程的主机）。所有已注册服务共享同一主机指标——当前部署形态是后端与受监控服务同机。
- **诚实标注**：产品定义 §5.5 要求「指标语义明确、不冒充」。由于装配允许通过 `OPERMIND_SERVICE_<INSTANCE>_DSN` 接入远程服务，此时展示的 `host_metrics` 是**后端所在主机**、而非服务实际所在主机。因此前端主机指标卡片必须显式标注「后端所在主机 · 单主机采集」，不得让人误以为该指标来自服务所在远端主机。
- 远程主机 / 每个服务独立主机留待后续阶段，不按服务维度建主机实体。
- 快照展示与定时采样**复用同一个 `HostMetricsCollector` 注入点**，避免两套采集逻辑。

### 2.2 领域模型（新增 `src/domain/host_metrics.py`，回答开放问题 1 的建模归属）

为规避 `services.py ↔ monitoring.py` 循环依赖，主机指标领域模型**独立成模块** `src/domain/host_metrics.py`：`services.py`（`ServiceViewData`）与 `monitoring.py`（采样器/样本）都只单向依赖它，`host_metrics.py` 不反向依赖二者。

跨层使用显式 Pydantic 模型（frozen + `extra="forbid"`），不使用隐式字典协议。

`HostMetricsData` 字段：

| 字段 | 类型 | 语义 |
|---|---|---|
| `mode` | enum | `mock / target`：mock 读场景，target 读 psutil |
| `source_status` | enum | `available / unavailable`（后端主机恒存在，**不使用 `not_configured`**） |
| `observed_at` | UTC datetime | 采集观测时间 |
| `cpu_percent` | float or null | CPU 使用率 |
| `cpu_count` | int or null | 逻辑核数 |
| `load_avg_1m` | float or null | 1 分钟负载 |
| `memory_total_bytes` / `memory_used_bytes` | int or null | 内存总量/已用 |
| `memory_percent` | float or null | 内存使用率 |
| `disk_used_percent` | float or null | 跨分区最大使用率（历史趋势标量） |
| `disk_top_partitions` | tuple | 当前展示：`HostDiskPartitionData{mount, percent, used_bytes, total_bytes}` |
| `network_connections` / `network_established` / `network_time_wait` | int or null | 当前展示：连接数收敛标量 |
| `abnormal_processes` | tuple | 当前展示：`HostProcessData{name, pid, cpu_percent?, memory_percent?}`，最多 5 条 |

辅助模型与端口（同文件）：

```text
HostDiskPartitionData: mount / percent / used_bytes / total_bytes
HostProcessData:       name / pid / cpu_percent(可空) / memory_percent(可空)
                       # 单条进程可能只有 CPU 或只有内存超阈（mock 串 S1 仅 CPU、S3 仅内存），字段必须可空

class HostMetricsCollector(Protocol):
    def collect(self) -> HostMetricsData: ...
```

**枚举来源（硬约束，防重建循环依赖）**：`host_metrics.py` 的 `mode`/`source_status` **必须使用本模块内定义的枚举（`HostMetricsMode` = `mock | target`、`HostMetricsSourceStatus` = `available | unavailable`）或 `Literal` 字面量**，**禁止** `from src.domain.services import ServiceMode, ServiceSourceStatus` 复用——`ServiceMode`/`ServiceSourceStatus` 定义在 `services.py`，复用会重建 `services.py ↔ host_metrics.py` 循环依赖。`host_metrics.py` 对 `services.py`/`monitoring.py` 均无 import。

`ServiceMonitorSampleData`（`monitoring.py`，仅标量不依赖模型）扩展主机历史字段：
`host_cpu_percent: float | None`、`host_memory_percent: float | None`、`host_memory_bytes: int | None`、`host_disk_used_percent: float | None`。

`ServiceViewData`（`services.py`）增加 `host_metrics: HostMetricsData`（**必选**，无默认）。

### 2.3 采集实现与诚实降级（`src/infrastructure/monitoring/host_metrics.py`）

`PsutilHostMetricsCollector`：

- **mock 模式**（`get_active_scenario()` 非 None）：从 `active.server["cpu"/"memory"/"disk"/"process"/"network"]` 预格式化串解析确定性标量（S1–S4 字符串固定，解析为纯函数、可单测锁定），`mode=mock`。场景缺键则对应标量置 null；解析需兼容「未发现异常进程」、缺 `CLOSE_WAIT` 等格式变体。
- **真实模式**：psutil 只读采集，CPU 用非阻塞 `cpu_percent(interval=0)`；`mode=target`。
- **诚实降级**：`psutil` `ImportError`、任何采集异常或超时 → `source_status=unavailable`，所有标量为 null，`mode` 保持 target，**不使用 0 代替缺失，不返回伪造串**。
- **显式时间预算**：快照路径（服务详情/列表请求）采集设内部时间预算（默认约 1.5s），超出即返回 `unavailable`，避免高负载主机上 `psutil.net_connections()` / `process_iter()` 长时间占用请求线程。
- **短 TTL 进程内缓存**（默认 10s）：避免每个请求都触发阻塞式 CPU 采样。采样器每轮一次采集与 API 请求**共享同一缓存**——采样器周期性采集天然为缓存保温，API 请求通常读缓存标量；cold cache 首请求的最坏耗时受上述时间预算约束。`observed_at` 取采集真实时刻，缓存仅复用标量值；**样本内主机标量最多滞后 TTL（10s）**，与样本 `observed_at` 存在语义差，在 5 分钟采样间隔下可忽略，测试/文档中写明。

### 2.4 配置（`src/config.py`）

新增配置字段，环境变量优先于 YAML：

| 配置 | 默认值 | 约束 |
|---|---:|---|
| `OPERMIND_HOST_METRICS_CACHE_SECONDS` | `10` | 0–600 秒（0 = 不缓存） |

配置非法时启动失败并返回明确配置错误（沿用 P5 校验模式）。**读取载体**：新增 `load_host_metrics_settings() -> HostMetricsSettings` loader（`src/config.py`），在 `dependencies.py` 装配 `PsutilHostMetricsCollector` 时读取并传入。同步更新 `config/config.example.yaml`。

### 2.5 历史采样（复用 P5 采样器/样本表，回答开放问题 1/3）

- `MonitorSampler` 注入 `host_collector: HostMetricsCollector`。
- 每轮 `sample_once` / `sample_once_async` 先**收集一次主机指标**（`asyncio.to_thread` + 3s 超时，沿用 P5 限时机制；失败收敛为 `unavailable` 主机状态），再写入本轮**每个服务样本**的主机字段。
- 同一轮内所有服务样本的主机标量相同（冗余但查询友好，趋势接口按 `service_id` 查询不变）。
- **历史样本携带 CPU / 内存 / 内存字节 / 磁盘使用率**四个主机标量（对齐 PRD 功能需求 2「CPU/内存/磁盘走势」）。**进程 / 网络仅当前快照展示，不入历史**（回答开放问题 3）。
- **失败语义隔离（硬约束）**：主机采集失败**只将该样本的主机字段置 null，绝不改动服务 `availability` / `performance_signal` / `source_status`**——避免把健康服务的历史样本误标为 `unavailable`，污染 P5 历史 `status` 聚合（`application/monitoring.py` 按 `source_status` 计算状态）。需补对应测试锁定。

### 2.6 持久化与迁移

- **扩展既有 `service_monitor_samples` 表**，新增列：`host_cpu_percent REAL NULL`、`host_memory_percent REAL NULL`、`host_memory_bytes INTEGER NULL`、`host_disk_used_percent REAL NULL`。
- 加 CheckConstraint：`X IS NULL OR X >= 0`；不修改既有列、索引、约束。
- **迁移沿用既有 SQLite 安全模式**：参照 `20260807_06_p6_redis_monitor_metrics.py` 的 `batch_alter_table` + `PRAGMA foreign_keys=OFF`，保证 SQLite upgrade/downgrade 稳定。
- 迁移提供 upgrade / downgrade；不新增表；不删除既有样本数据。

### 2.7 API 契约

- `ServiceResource`（`GET /api/v1/services/{id}`、`GET /api/v1/services`）增加 `host_metrics: HostMetricsResource`（**必选**，恒存在，`source_status` 表达诚实状态）。列表与详情都携带（单一主机、所有服务相同；共享 TTL 缓存 + 采样器保温，cold cache 最坏耗时受 §2.3 时间预算约束）。**`list_services` 每请求只调用一次 `collect()`，4 个服务共享同一份 `HostMetricsData`**，不得实现为每服务一次全量采集。
- `HostMetricsResource` 只暴露上述领域字段的安全子集（枚举用字面量、null 保持 null），不复用快照响应。**None 回退明确**：`service_resource` mapper 恒产出 `host_metrics` 对象；领域层 collector 注入为 None 时（防御性装配），产出 `source_status=unavailable` 全空对象，不出现字段缺失。
- `MonitorSampleResource`（历史接口）增加 `host_cpu_percent / host_memory_percent / host_memory_bytes / host_disk_used_percent`。样本映射走 `sample.model_dump()`，领域模型加字段后自动带出。
- 既有字段兼容：`ServiceSnapshotResource`、`ServiceServerMetricsResource` 不变；`host_metrics` 为新增兄弟字段，不破坏既有快照契约。

### 2.8 前端（`frontend/src/features/services/ServiceDetailPage.tsx`）

- 新增「主机指标」卡片：CPU / 内存 / 磁盘 / 网络当前状态 + 异常进程（≤5 条）。
- **采集范围标注（硬约束）**：卡片标题与摘要必须标注「后端所在主机 · 单主机采集」，明确指标来自后端进程所在主机，防止远程 DSN 场景下冒充实况。
- 数据来源标注诚实：`mode=mock` → 「演示场景」，`mode=target` → 「真实采集」，`source_status=unavailable` → 「不可用」；不可用时不绘制数值。
- 运行趋势区基于样本 `host_cpu_percent / host_memory_percent / host_disk_used_percent` 增加 CPU / 内存 / 磁盘走势（复用 P5 CSS/HTML 时间序列轨道，不引入图表库）。
- API 类型经 `npm run generate:api` 重新生成 `frontend/src/api/v1/generated.ts`（禁止手工编辑）；`client.ts` / `queries.ts` 按契约同步更新。
- 异常进程仅展示名称/PID/占用率标量，不展示原始命令行、凭据或敏感信息。

## 3. 文件改动面

### 后端

- `backend/src/domain/host_metrics.py`（**新增**）：`HostMetricsData` / `HostDiskPartitionData` / `HostProcessData` / `HostMetricsCollector`（规避 `services.py ↔ monitoring.py` 循环依赖）。
- `backend/src/domain/services.py`：`ServiceViewData` 增加必选 `host_metrics` 字段（单向依赖 `host_metrics.py`）。
- `backend/src/domain/monitoring.py`：`ServiceMonitorSampleData` 增加 4 个主机标量字段（仅标量，无模型依赖）。
- `backend/src/infrastructure/monitoring/host_metrics.py`（**新增**）：`PsutilHostMetricsCollector`（psutil / mock 解析 / 诚实降级 / 时间预算 / TTL 缓存）。
- `backend/src/infrastructure/monitoring/sampler.py`：注入 host collector，每轮采集一次并写入各样本主机字段（失败只置 null，不改服务状态）。
- `backend/src/application/service_center.py`：注入 host collector（**`host_metrics_collector: HostMetricsCollector | None = None`，默认 None**，未注入时防御性产出 `source_status=unavailable` 全空 `HostMetricsData`），`list_services` / `get_service` 附加 `host_metrics`。既有测试两参构造可零改动沿用，测试补断言 fallback `host_metrics` 存在。
- `backend/src/infrastructure/persistence/models.py`：`ServiceMonitorSampleRecord` 增加 4 个主机列。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：读写主机字段。
- `backend/src/config.py`：新增 `OPERMIND_HOST_METRICS_CACHE_SECONDS` 配置与校验。
- `backend/src/api/v1/schemas.py`：新增 `HostMetricsResource`；`ServiceResource.host_metrics`；`MonitorSampleResource` 主机字段。
- `backend/src/api/v1/resources.py`：新增 `host_metrics_resource` mapper；`service_resource` 接入（恒产出，unavailable 兜底）。
- `backend/src/api/v1/dependencies.py`：装配 host collector（sampler + service_center）。
- `backend/migrations/versions/<timestamp>_p6_host_metrics.py`：加 4 列 + 约束 + downgrade，沿用 `batch_alter_table` + PRAGMA 模式。
- `config/config.example.yaml`：新增配置项说明。
- 测试：`backend/tests/test_host_metrics.py`（**新增**）、`backend/tests/test_server_tools.py`（**新增**，锚定 AC5 mock 路径回归）、`test_monitoring.py`、`test_monitor_history_api.py`、`test_p4_service_center.py`（service 构造走 host_collector 默认 None 的 fallback，补断言 `host_metrics` 存在）、迁移测试。

### 前端

- `frontend/src/api/v1/generated.ts`（重新生成，禁止手工编辑）、`client.ts`、`queries.ts`（按契约更新）。
- `frontend/src/features/services/ServiceDetailPage.tsx`：主机指标卡片 + 采集范围标注 + CPU/内存/磁盘走势。
- `frontend/src/features/services/ServiceDetailPage.test.tsx`：成功 / 不可用 / 空态 / 异常进程 / 采集范围标注 / 诚实标注。
- `frontend/src/test/handlers.ts`：MSW 主机指标与样本 fixture。

### 无功能改动部分

- `server_tools.py`、`data/scenarios.py`、`data/mock_db.py`、S1–S4 评测路径不改。

## 4. 切片与验证（指引，不写死）

建议拆 3 片（切片拆解、验证命令、提交计划归 `dev-plan` 的 plan.md）：

- S1：`src/domain/host_metrics.py` 模型与端口 + `PsutilHostMetricsCollector`（psutil / mock 解析 / 诚实降级 / 时间预算 / TTL）+ 单元测试 + `test_server_tools.py` 回归锚点。
- S2：快照 `host_metrics`（`ServiceViewData` + mapper + 装配） + `ServiceResource`/`MonitorSampleResource` API 契约 + `service_monitor_samples` 迁移 + 采样器主机字段与失败隔离 + 历史 API。
- S3：前端主机指标卡片 + 采集范围标注 + CPU/内存/磁盘走势 + 交互测试。

涉及门禁项：**数据库迁移、公开 API 契约扩展、产品主脊监控采集**——必须经本 Design → Review → 用户确认后方可进入 dev-plan。

## 5. 风险、回滚与门禁

- **风险**：`psutil.cpu_percent(interval=1)` 阻塞 → 非阻塞采集 + TTL 缓存 + 显式时间预算缓解；mock 字符串解析脆弱 → 纯函数 + 单测锁定格式（含「无异常进程」/缺 `CLOSE_WAIT` 变体）；样本表加列 → 提供 downgrade；缓存掩盖采样语义 → `observed_at` 取真实时刻、缓存仅复用标量；循环依赖 → 主机模型独立成 `host_metrics.py` 模块。
- **回滚**：迁移 downgrade 移除 4 个主机列；API 移除 `host_metrics` 字段即回滚前端入口；不删除既有样本、服务或会话数据。
- **门禁**：新监控采集（产品主脊）、数据库迁移、公开 API 契约扩展 → 本 Design `arch-review` PASS + 用户确认 + 状态改为「已确认」后，才放行 dev-plan。

## 6. 待用户确认的设计决策

1. 是否确认主机指标**只采后端所在主机（单一主机）**，所有服务共享同一主机指标，前端标注「后端所在主机 · 单主机采集」？（远程主机留待后续阶段）
2. 是否确认历史样本**扩展既有 `service_monitor_samples` 表**加 4 个主机标量列（CPU/内存/内存字节/磁盘），而非新增独立主机样本表？
3. 是否确认**进程 / 网络仅当前快照展示，不进入历史采样**；历史仅含 CPU/内存/磁盘走势（对齐 PRD 功能需求 2）？
4. 是否确认 `server_tools.py`（agent 侧字符串工具）**在 P6 不修改**，诚实降级由新的结构化 `HostMetricsCollector` 承担（保证 mock S1–S4 不变）？
5. 是否确认新增 `OPERMIND_HOST_METRICS_CACHE_SECONDS` 配置（默认 10s，范围 0–600）？
6. **PRD AC7 引用更正**：PRD 验收标准 AC7 引用的 `test_server_agent.py` 在仓库中不存在；P6 将新增 `backend/tests/test_server_tools.py`（锚定 AC5 mock 路径）并补充主机指标测试。是否确认在 P6 交付时**同步更正 PRD AC7 的测试文件引用**（改为实际新增/存在的测试文件），保证 AC 可核验？
7. 是否确认本 Design 审查通过后，P6 PRD 状态保持「已确认」，并在 dev-plan 计划获用户确认后推进为「进行中」（issue #23 同步标 in-progress）？
