# P8-service-registration · 独立代码审查

> 审查时间：2026-08-10
> 审查方式：独立只读子代理（两轮：初审查出 P1，修复后复审 PASS）

## 初审查（FAIL → 修复）

总体：FAIL（存在 1 个 P1）

| 级别 | 发现 | 修复 |
|---|---|---|
| P1 | `delete()` 无差别 `registry.remove`，DELETE 硬编码实例会从运行时 registry 移除静态服务，违反 plan「不改变既有硬编码实例读取方式」与 AC11 | 仅 DB 删除成功才 `registry.remove`；硬编码实例（无 DB 行）不做 registry 变更 |
| P2 | `ServiceRegistry` 写方就地增删 dict，与读方 `tuple(values())` 撞 resize 竞态，违反 Design D3 并发契约 | 写方复制当前表后整体替换（单次 dict 赋值） |
| P3 | `create()` 并发竞态下 `registry.register` 抛 ValueError → 500 | 转 `ServiceInstanceConflictError`（409） |
| P3 | 迁移 downgrade 恢复的 sessions CHECK 为 4 个 ID，与 P8 前（3 个 PG）不对称 | 恢复为 3 个 PG ID，session_services 仍 4 个 |
| P3 | `load_registered_services` 用 `except Exception` 兜底 | 收窄为 `SQLAlchemyError` |
| P3 | AC8 无 DB 行级密文断言 | 补 `service_registry` 行断言 `dsn_encrypted` 非明文 |
| P3 | 命令层 ValidationError 未转 422 | register/update 端点捕获转 422 |

## 复审（PASS）

总体：PASS（7 项全部修复，无新增 P0/P1）

已知 P3 遗留（可接受）：
- 前端对硬编码实例仍渲染「移除」按钮，点击为后端 no-op 但 toast 显示「服务已移除」（数据安全、可恢复）。
- 前端 `ServiceCenterPage.test.tsx` 的 AC6 用例用硬编码 fixture 模拟删除，与真实后端 no-op 语义有偏差。

## AC 覆盖

AC1–AC11 全部 PASS（见 evidence.md）。
