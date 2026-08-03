# 任务 P4：服务中心变真（接真实 PostgreSQL 只读服务）

## 背景（只读）
Design 文档：`docs/P4服务中心变真Design.md`（已确认）。
当前 `ServiceRegistry(())` 是空的，`GET /services` 返回空列表，前端服务中心/详情页显示空态。
本任务实现第一个真实 `PostgresServiceConnector`，装配进 registry，让服务快照变真。

**已确认的决策**：
- 第一个服务：PostgreSQL（只读诊断）
- 凭据：单一环境变量 `OPERMIND_PG_DSN`（postgresql://user:pass@host:5432/db）
- 范围：只做「服务快照变真」，会话里 DBAgent 的工具仍走假数据（后置）
- 前端接口契约不变，无需改前端

## 只允许修改/创建这些文件
1. 新建 `backend/src/infrastructure/services/postgres_connector.py`（PostgresServiceConnector）
2. 新建 `backend/tests/test_postgres_connector.py`（单元测试，不连真库）
3. 改 `backend/src/config.py`（加 `OPERMIND_PG_DSN` 环境变量映射 + `load_service_settings()`）
4. 改 `backend/src/api/v1/dependencies.py`（装配 PostgresServiceConnector 进 ServiceRegistry）

**严禁触碰其他文件**（不改 domain/services.py、不改前端、不改 DBAgent/工具、不改 mock 数据源）。

## 被依赖的现有契约（照此实现，不要臆测）
- `from src.domain.services import ServiceConnector, ServiceDefinitionData, ServiceSnapshotData, ServiceMode, ServiceAvailability, ServiceSourceStatus, DatabaseSignal, PerformanceSignal, ServiceServerMetricsData, ServiceDatabaseStateData, ServiceInvestigationData, ORDER_SERVICE_ID`
- `ServiceConnector` 协议（domain/services.py）：
  - `definition(self) -> ServiceDefinitionData`
  - `health_snapshot(self) -> ServiceSnapshotData`
- `ServiceDefinitionData` 字段：`id`、`title`、`kind`、`supported_investigations: tuple[ServiceInvestigationData,...]`、`action_boundary`、`session_title`
- `ServiceSnapshotData` 字段：`observed_at`（UTC aware）、`mode`、`availability`、`performance_signal`、`server_metrics: ServiceServerMetricsData`、`database: ServiceDatabaseStateData`
- 装配点：`src/api/v1/dependencies.py:68` 的 `ServiceRegistry(())`

## 实现要求

### 1. config.py
在 `_ENV_TO_CONFIG_KEY` 加：
```python
"OPERMIND_PG_DSN": ("services", "pg_dsn"),
```
新增：
```python
@dataclass(frozen=True)
class ServiceSettings:
    """真实外部服务连接设置；缺省表示未配置。"""
    pg_dsn: str | None


def load_service_settings() -> ServiceSettings:
    """加载外部服务 DSN；未配置时返回 None，不允许在此读取或打印凭据。"""
    config = _apply_env_overrides(_load_yaml_config())
    services = config.get("services") or {}
    dsn = services.get("pg_dsn")
    if not isinstance(dsn, str) or not dsn.strip():
        return ServiceSettings(pg_dsn=None)
    return ServiceSettings(pg_dsn=dsn)
```
**不打印 dsn、不落日志、不落文档。**

### 2. postgres_connector.py
```python
class PostgresServiceConnector:
    """静态注册的 PostgreSQL 只读 Connector。"""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn
```
- `definition()`：返回静态 `ServiceDefinitionData`。id 用 `"postgres-production"`（或类似），
  title 如 `"生产 PostgreSQL 主库"`，kind `"postgres"`，supported_investigations 一个慢查询调查，action_boundary 说明"只读"，session_title 如 `"PostgreSQL 慢查询调查"`。
- `health_snapshot()`：
  - `dsn is None` → `availability=not_configured`、`mode=disabled`、`performance_signal=not_configured`、server_metrics/database source_status=not_configured、database.signal=not_configured
  - `dsn` 存在 → 尝试只读连接 + 有限查询（见下）；失败/超时 → `unavailable`；成功 → `healthy` + 指标填充
  - **失败时绝不抛异常**，返回 unavailable/not_configured 快照
  - 每次快照读取限时（如 3 秒超时）
- **只读**：连接用 `SET TRANSACTION READ ONLY`（或只发 SELECT），无任何写路径
- **脱敏**：快照字段只含收敛标量，不含 SQL、对象名、凭据、原始日志

### 3. 快照读取（有限、脱敏，用 SQLAlchemy 或 psycopg 均可）
可选来源（按可用性选一个即可，重点是"有限且脱敏"）：
- `SELECT 1` 连通性
- 慢查询/延迟：从 `pg_stat_statements` 或 `pg_stat_database` 读有限窗口统计（p50/p95 延迟、慢查询计数）
- 若无这些扩展：可只做 `SELECT 1` + availability，指标留 None（诚实，不硬造数字）

**不读取**：具体慢 SQL 原文、表结构、索引明细、用户数据、系统目录原始内容。
**没有扩展/查询失败时**：指标为 None，availability 依连通性判定。

### 4. dependencies.py 装配
```python
from src.config import load_service_settings
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
# 替换 ServiceRegistry(()) 为：
ServiceRegistry((PostgresServiceConnector(load_service_settings().pg_dsn),))
```
注意：缺省 dsn 时注册的不是空 Connector，而是 `PostgresServiceConnector(None)`（返回 not_configured 空态，不崩）。

## 测试 `tests/test_postgres_connector.py`（不连真库，用注入/构造）
用中文 docstring 覆盖：
1. **无凭据**：`PostgresServiceConnector(None)` → snapshot.availability == `not_configured`，不抛异常
2. **连接失败**：注入假连接抛异常 → availability == `unavailable`
3. **超时**：注入超时 → availability == `unavailable`
4. **正常**：注入成功连接返回有限指标 → availability == `healthy`，指标填充
5. **脱敏**：快照 dict 不含 `password`、`://`、SQL 关键字、凭据明文
6. **definition 静态完整**：definition 各字段非空，kind/title/id 合理
（用 mock 或假对象注入连接，不真连 PG。）

## 验收
- `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_postgres_connector.py -q` 全绿
- 现有回归：`../.venv/Scripts/python.exe -m pytest tests/test_p2_application_services.py tests/test_p2_diagnosis_adapter.py -q` 全绿
- 手动（可选）：设 `OPERMIND_PG_DSN` 指向可连的 PG，`GET /services` 返回真快照；不设则返回 not_configured 空态
- `git status` 只出现上面允许的 4 个文件

## 完成后
**不要 commit。** 停下告诉我"P4完成"，我审 diff + 跑测试后自己提交。

## 交差前自审清单（必须在完成报告里逐条回答）
1. `git status --short` 完整输出 —— 确认只出现本任务允许的 4 个文件。
2. pytest 结果 —— 新测试全绿 + 现有回归全绿；确认没为了绿改现有测试。
3. typecheck（如有）是否绿。
4. 明确说明：没有打印/记录 dsn、没有动 domain/services.py、没有改前端、没有改 DBAgent 工具。
5. 列出每个文件的改动点。