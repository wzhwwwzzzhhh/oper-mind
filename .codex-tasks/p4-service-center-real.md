# 任务 P4：服务中心变真（接真实 PostgreSQL 只读服务）

## 背景（只读）
Design 文档：`docs/design/service-center/P4服务中心变真Design.md`（已确认）。
当前 `ServiceRegistry(())` 是空的，`GET /services` 返回空列表，前端服务中心/详情页显示空态。
本任务实现第一个真实 `PostgresServiceConnector`，装配进 registry，让服务快照变真。

**已确认的决策**：
- 第一个服务：PostgreSQL（只读诊断）
- 凭据：单一环境变量 `OPERMIND_PG_DSN`（`postgresql://user:pass@host:5432/db`）
- 范围：只做「服务快照变真」，会话里 DBAgent 的工具仍走假数据（后置）
- 前端接口契约不变，无需改前端

## 技术约束（已确认，不要改）
- **驱动**：SQLAlchemy 2.0 + `postgresql+psycopg` URL（psycopg[binary]==3.3.4 已在 requirements.txt）
- PostgreSQL 连接必须用 `postgresql+psycopg`（`src/infrastructure/persistence/database.py` 已校验此规则）
- 只读：连接用 `SET TRANSACTION READ ONLY`（或 `pg_read_only` 风格），无任何写路径
- 每次快照读取限时 3 秒

## 允许修改/创建这些文件
1. 新建 `backend/src/infrastructure/services/postgres_connector.py`
2. 新建 `backend/tests/test_postgres_connector.py`
3. 改 `backend/src/config.py`
4. 改 `backend/src/api/v1/dependencies.py`
5. 改 `backend/src/domain/services.py`（只补 DatabaseSignal 枚举值，见下）
6. 改 `backend/src/api/v1/schemas.py`（把写死的 P2 演示字面量改通用字符串，见下）
7. 新建/改 `backend/tests/test_p4_service_center.py`（API 级测试，见下）

**严禁触碰其他文件**（不改前端、不改 DBAgent/工具、不改 mock 数据源、不改 requirements.txt——psycopg 已存在）。

### 修复 1：schemas.py 去掉 P2 写死字面量（必须做）
现有 `ServiceInvestigationResource.id: Literal["orders_slow_query.v1"]`、
`ServiceResource.id: Literal["order-service"]`、`ServiceResource.kind: Literal["postgres_orders_demo"]`
是 P2 演示服务写死的，导致 P4 的 `postgres-production` / `postgres` / `postgres_slow_query.v1`
无法通过 `service_resource()` 校验。改成通用字符串字段：
```python
# ServiceInvestigationResource
id: str = Field(min_length=1, max_length=80)
# ServiceResource
id: str = Field(min_length=1, max_length=64)
kind: str = Field(min_length=1, max_length=80)
```
同时把 `ServiceSnapshotResource.signal` 的 Literal 补上 `"no_slow_query_detected"`（见修复 2）。

### 修复 2：domain/services.py 补 DatabaseSignal 枚举值（必须做）
现有 `DatabaseSignal` 缺 `NO_SLOW_QUERY_DETECTED`（健康分支要用的诚实结论）。
补一个枚举值：
```python
NO_SLOW_QUERY_DETECTED = "no_slow_query_detected"
```
同时 `schemas.py` 的 `ServiceDatabaseStateResource.signal` Literal 也补 `"no_slow_query_detected"`。
health_snapshot 健康分支用 `DatabaseSignal.NO_SLOW_QUERY_DETECTED`。

## 被依赖的现有契约（照此实现）
```python
from src.domain.services import (
    ServiceConnector, ServiceDefinitionData, ServiceSnapshotData,
    ServiceMode, ServiceAvailability, ServiceSourceStatus,
    DatabaseSignal, PerformanceSignal,
    ServiceServerMetricsData, ServiceDatabaseStateData, ServiceInvestigationData,
)
```
- `ServiceConnector` 协议：
  - `definition(self) -> ServiceDefinitionData`
  - `health_snapshot(self) -> ServiceSnapshotData`
- `ServiceDefinitionData` 字段：`id`（str, 1-64）、`title`（str, 1-120）、`kind`（str, 1-80）、`supported_investigations`（tuple）、`action_boundary`（str, 1-280）、`session_title`（str, 1-200）
- `ServiceSnapshotData` 字段：`observed_at`（UTC aware datetime）、`mode`、`availability`、`performance_signal`、`server_metrics: ServiceServerMetricsData`、`database: ServiceDatabaseStateData`
- `ServiceServerMetricsData` 字段：`source_status`、`window_size: int|None`、`p50_ms: float|None`、`p95_ms: float|None`、`slow_query_count: int|None`、`timeout_count: int|None`
- `ServiceDatabaseStateData` 字段：`source_status`、`signal`
- 装配点：`src/api/v1/dependencies.py:68` 的 `ServiceRegistry(())`

## 具体实现（照此做，不要自行设计变体）

### 1. config.py
在 `_ENV_TO_CONFIG_KEY` 字典加一行：
```python
"OPERMIND_PG_DSN": ("services", "pg_dsn"),
```
在文件底部新增：
```python
@dataclass(frozen=True)
class ServiceSettings:
    """外部服务连接设置；缺省表示未配置。"""
    pg_dsn: str | None


def load_service_settings() -> ServiceSettings:
    """读取外部服务 DSN；未配置返回 None。只读环境变量，不打印/记录 dsn。"""
    config = _apply_env_overrides(_load_yaml_config())
    services = config.get("services") or {}
    dsn = services.get("pg_dsn")
    if not isinstance(dsn, str) or not dsn.strip():
        return ServiceSettings(pg_dsn=None)
    return ServiceSettings(pg_dsn=dsn)
```

### 2. postgres_connector.py
```python
"""静态注册的 PostgreSQL 只读 Connector。"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.domain.services import (...上面 import...)


class PostgresServiceConnector:
    """只读 PostgreSQL 服务快照 Connector，实现 ServiceConnector 协议。"""

    def __init__(self, dsn: str | None, engine: Engine | None = None) -> None:
        self._dsn = dsn
        # engine 注入点：测试传假 engine；生产传 create_engine(dsn)。
        self._engine = engine

    def definition(self) -> ServiceDefinitionData:
        return ServiceDefinitionData(
            id="postgres-production",
            title="生产 PostgreSQL 主库",
            kind="postgres",
            supported_investigations=(
                ServiceInvestigationData(
                    id="postgres_slow_query.v1",
                    title="PostgreSQL 慢查询调查",
                    description="通过只读查询定位慢 SQL 与索引问题。",
                    default_query="生产 PostgreSQL 变慢，请只读排查慢查询。",
                ),
            ),
            action_boundary="只读调查，不执行任何写入或结构变更。",
            session_title="PostgreSQL 慢查询调查",
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限只读快照；失败/超时返回 unavailable，不抛异常。"""
        observed = datetime.now(timezone.utc)
        if self._dsn is None:
            return self._not_configured(observed)
        engine = self._engine or create_engine(self._dsn, pool_pre_ping=True)
        try:
            # 限时：engine 连接 + 查询在 3 秒内完成（用 timeout 参数或 connect_args）
            return self._read_healthy(engine, observed)
        except Exception:
            return self._unavailable(observed)

    # ---- 私有辅助：每个分支构造完整快照，字段值写死来源 ----
```

**关键：**
- `definition()` 的 id 必须是 `"postgres-production"`（写死，测试依赖）
- `health_snapshot()` 永不抛异常：任何异常 → `_unavailable`；无 dsn → `_not_configured`
- `engine` 参数用于测试注入（假 engine），生产不传则 `create_engine`

**`_read_healthy` 的只读查询方案（定死，用这个）：**
```python
def _read_healthy(self, engine: Engine, observed: datetime) -> ServiceSnapshotData:
    # 1. 连通性：SELECT 1
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SELECT 1"))
        # 2. 有限指标：从 pg_stat_database 读取当前库的调用计数与慢查询数
        #    （不用 pg_stat_statements，避免依赖扩展；读不到就留 None）
        row = conn.execute(text(
            "SELECT numbackends, xact_commit, xact_rollback, blks_read "
            "FROM pg_stat_database WHERE datname = current_database()"
        )).mappings().first()
```
- 慢查询计数：如果 `pg_stat_statements` 可用则读 `calls` 总和作为 slow_query_count；不可用留 None
- p50/p95：若 `pg_stat_statements` 有 `mean_exec_time` 可算 p50/p95；否则 None
- **读不到任何指标 → 指标全 None，availability 仍按 SELECT 1 成功 = healthy**
- 绝不在快照里放 SQL 原文、表结构、索引明细、凭据

**三个分支快照（字段值写死）：**
```python
def _not_configured(self, observed):
    return ServiceSnapshotData(
        observed_at=observed, mode=ServiceMode.DISABLED,
        availability=ServiceAvailability.NOT_CONFIGURED,
        performance_signal=PerformanceSignal.NOT_CONFIGURED,
        server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.NOT_CONFIGURED),
        database=ServiceDatabaseStateData(source_status=ServiceSourceStatus.NOT_CONFIGURED, signal=DatabaseSignal.NOT_CONFIGURED),
    )

def _unavailable(self, observed):
    return ServiceSnapshotData(
        observed_at=observed, mode=ServiceMode.TARGET,
        availability=ServiceAvailability.UNAVAILABLE,
        performance_signal=PerformanceSignal.UNAVAILABLE,
        server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.UNAVAILABLE),
        database=ServiceDatabaseStateData(source_status=ServiceSourceStatus.UNAVAILABLE, signal=DatabaseSignal.UNAVAILABLE),
    )
```
`_read_healthy` 返回 `availability=HEALTHY`、`performance_signal=NO_SLOW_QUERY_DETECTED`（或按指标判定）、`server_metrics.source_status=AVAILABLE`、`database.signal=NO_SLOW_QUERY_DETECTED`、`mode=TARGET`。

### 3. dependencies.py 装配
```python
from src.config import load_service_settings
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
# 替换 ServiceRegistry(())：
ServiceRegistry((PostgresServiceConnector(load_service_settings().pg_dsn),))
```

## 测试（两处）

### 1. tests/test_postgres_connector.py（不连真库，用假 engine 注入）
用 `unittest.mock` 或最小假对象构造 Engine，覆盖：
1. **无凭据**：`PostgresServiceConnector(None)` → snapshot.availability == ServiceAvailability.NOT_CONFIGURED，不抛异常
2. **连接失败**：假 engine 的 connect 抛 `OperationalError` → availability == UNAVAILABLE
3. **超时**：假 engine 的 connect 抛超时异常 → UNAVAILABLE
4. **正常**：假 engine 返回 `SELECT 1` 成功 + 指标行 → HEALTHY，指标字段填充
5. **脱敏**：把 `ServiceSnapshotData.model_dump()` 转字符串，断言不含 `password`、`://`、`SELECT 1`、凭据明文
6. **definition 完整**：id == "postgres-production"，各字段非空
（中文 docstring；用 `PostgresServiceConnector("postgresql://u:p@h/db", engine=fake_engine)` 注入假 engine。）

### 2. tests/test_p4_service_center.py（API 级测试，验证全链路）
用假 engine 装配一个 `ServiceRegistry((PostgresServiceConnector(None),))`，
通过 `ServiceCenterApplicationService` + `service_resource()` 冒烟：
1. **无凭据时 API 可响应**：`list_services()` 返回 1 个服务，`service_resource(view)` 不抛校验错误，availability == not_configured
2. **健康分支 API 可响应**：注入假 healthy engine，`service_resource(view)` 不抛校验错误，availability == healthy、database.signal == no_slow_query_detected
3. **get_service 同样可映射**：`get_service("postgres-production")` → `service_resource` 不抛错
（中文 docstring；参考现有 `tests/test_p2_*` 的装配方式。）

## 验收
- `cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_postgres_connector.py tests/test_p4_service_center.py -q` 全绿
- 回归：`../.venv/Scripts/python.exe -m pytest tests/test_p2_application_services.py tests/test_p2_diagnosis_adapter.py -q` 全绿
- `git status` 只出现允许的文件

## 完成后
**不要 commit。** 停下告诉我"P4完成"，我审 diff + 跑测试后自己提交。

## 交差前自审清单（必须在完成报告里逐条回答）
1. `git status --short` 完整输出 —— 确认只出现本任务允许的文件。
2. pytest 结果 —— 新测试全绿 + 现有回归全绿；确认没为了绿改现有测试。
3. 明确说明：没有打印/记录 dsn、没有改前端、没有改 DBAgent 工具、没有改 requirements.txt。
4. schemas.py 改动说明 —— 列出改了哪些 Literal 为通用字符串、哪些信号枚举补了值。
5. domain/services.py 改动说明 —— 确认只补了 DatabaseSignal 枚举值，没改其他。
6. 列出每个文件的改动点。