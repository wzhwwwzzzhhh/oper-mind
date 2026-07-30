# Work 1 Review — 订单慢 SQL 受控靶场

> 审查日期：2026-07-30　|　结论：**✅ 已通过并提交；P4.1 仍等待用户实施授权。**

## 代码与隔离边界

- [x] 靶场独立于 `config/`、`data/`、应用元数据数据库和既有 mock 数据。
- [x] 连接配置只从环境变量读取，且硬校验 `127.0.0.1:5433/opermind_demo`。
- [x] 运行时 DDL/DML 只定位 `opermind_demo.orders` 和 `idx_orders_user_created`。
- [x] 无任意 SQL、LLM SQL、用户 SQL、任意 Shell、`pg_sleep`、假耗时或假指标。
- [x] 本地服务只监听 `127.0.0.1:18080`；日志路径受限在靶场目录。
- [x] `clean` 仅删除专用 schema 和自己启动的进程/运行时文件，不删除数据库。
- [x] 代码没有访问、探测、读取或写入 `gongkar` 的路径。

## 验收质量

- [x] `backend/tests/scripts` 最终 11 passed；
- [x] 控制脚本、smoke 和订单服务 Python 编译通过；
- [x] 真实 smoke 验证正常、故障、修复、恢复和最终清理；
- [x] 故障判定使用索引、执行计划、P50 性能门和日志的交叉证据；P95 保留审计；
- [x] 恢复判定不将“DDL 成功”当作验证成功。

## 真实结果复核

`backend/scripts/smoke_demo_orders.py --samples 10` 于 2026-07-30 通过：baseline P95 `60.539 ms` / Index Scan；删索引后 P95 `84.127 ms` / Seq Scan / 10 条慢日志；恢复后 P95 `61.451 ms` / Index Scan / 0 条慢日志。最终确认专用 schema 被清理。

## 提交与后续边界

Work 1 已由提交 `9560c15 feat: 建立订单慢SQL受控靶场` 收口。以下既有改动不属于 Work 1，**不得暂存**：

- `backend/src/domain/__init__.py`
- `backend/src/infrastructure/persistence/__init__.py`

P4.1 的产品蓝图、Design 与 Review 已完成。只有在用户明确确认蓝图并授权实施后，才能开始会话触发的只读慢查询调查；审批、执行、Verify 和知识库不属于 P4.1。
