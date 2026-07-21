# M5 Step2 — 多故障 mock 世界

> 状态：✅ 完成（2026-07-20）
> 分支：`feat/m5-agent-comparison`

## 背景与发现

原计划以为改 `data/mock_*.py` 即可，实测发现 mock 数据**散落且有死代码**：

- DB：`data/mock_db.py`（db_tools、agent_langgraph 在用）。
- 日志：**内联在 `log_tools.py`**（在用）；`data/mock_logs.py` 无人 import（死代码）。
- 服务器：`server_tools.py` **真调 psutil**，mock 兜底仅在 `ImportError` 触发，psutil 已装 → 兜底永不触发，mock 模式下返回真机指标（违反 CLAUDE.md「psutil 必须有确定性 mock fallback、mock 一等公民」）；`data/mock_server.py` 死代码。

故实际范围扩为：建单一数据源 + 重构 2 个工具 + 改 bootstrap + 删 2 个死文件。

## 四起故障（根因刻意分散）

| key | 故障 | 表象 | 真根因（域） |
|---|---|---|---|
| S1 | DB 慢查询级联（基准，等价旧世界） | CPU 高 | orders 缺索引（db） |
| S2 | 磁盘写满 | 应用写失败 | /data 98%（server） |
| S3 | 应用内存泄漏 | 内存高/OOM | java 堆泄漏（app） |
| S4 | 连接数配置过低（表象误导） | too many connections | max_connections=100（config） |

区分点：**S1 vs S3** 同表象（内存/OOM）不同根因（热点进程 mysqld vs java）；**S4** 报连接错像 DB 慢，但 SQL 快、资源正常 → 加索引无用，须改配置。这三处正是多 Agent 跨源印证能赢单模型的地方。

## Code 改动

- **新增 `data/scenarios.py`**：`Scenario` 冻结数据类（logs / slow_queries / server 三域数据）+ S1–S4 注册表 + 激活状态机（`set_active_scenario` / `get_active_scenario` / `clear_active_scenario` / `active_or_default`）。
- **`src/tools/log_tools.py`**：删内联 `MOCK_LOGS`，SearchLogs / AggregateErrors / QuerySlowLog 改读 `active_or_default()`；清理未用 import。
- **`src/tools/server_tools.py`**：5 个工具在 `get_active_scenario()` 非空时返回场景指标，否则才走 psutil——同时修了那条 CLAUDE.md 红线。
- **`src/core/bootstrap.py`**：`api_key=="mock"` 时 `set_active_scenario("S1")`，否则 `clear`。
- **删除** `data/mock_logs.py`、`data/mock_server.py`（确认无引用）。

## 向后兼容

默认激活 S1 = 旧 mock 世界，现有 65 用例、smoke 行为不变；真实模式（无激活场景）server_tools 仍走 psutil。

## Test 证据

`tests/test_scenarios.py` 新增 9 条：场景注册/根因分散、非法 key、激活状态机、`active_or_default` 回落、日志/慢查询/服务器工具随场景切换、S1↔S3 热点进程区分、S4 连接卡上限+资源正常。

```text
python -m pytest tests/test_scenarios.py -q  →  9 passed
python -m pytest -q                           →  66 passed（step1 后 57，+9）
python scripts/smoke_pipeline.py              →  退出码 0，三路径 + debate 全跑通
```

## 已知限制 / 交给 step3

- `EvalCase` 加 `scenario` 字段 + Runner 按用例切场景 + 真正编写区分度用例（表象误导/真分歧），留 step3。
- **step3 前置项（审查发现）**：当前「激活场景」是进程级全局，并行按用例切场景有并发隐患；step3 接入 Runner 前须改为 contextvar 或显式传参，勿用进程级全局做并行切换。
- **已知限制**：真实模式（无激活场景）下 server 走 psutil、log/db 仍走 S1，两者可能不一致；这是 M8 真 MySQL 落地前的过渡态，不影响 mock 主实验。
- `db_tools` 的 explain/schema 仍是 S1 取向（SQL 文本驱动）；misleading 用例通过"查询本身正常 + 无慢查询"体现 DB 健康，不需改 explain_sql。
