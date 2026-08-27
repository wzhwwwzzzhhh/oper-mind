# Issue #105 完善阶段验收与仓库收口 · AC 证据

> 日期：2026-08-27
> 状态：体验、功能与最终全量验证完成；PR #111 交付。

## P7 与 mock 主链

| 验收项 | 环境与操作 | 结果 |
|---|---|---|
| 文档知识库 | 隔离数据库；配置工作树 `docs/` 后浏览目录与检索，再以未配置知识目录的独立后端复验 | PASS：50 个文档、5 条检索结果；未配置时展示诚实空态 |
| 服务监控概览 | 显式清空全部服务 DSN，浏览监控聚合页 | PASS：4 个服务实例均如实显示 DSN 未配置；历史采样提示可见 |
| 锁等待诊断 | 正式会话输入“检查锁等待” | PASS：进入 DB Agent，`check_lock_status` 成功，Trace 展示脱敏摘要“无锁等待 (mock)” |
| 连接池诊断 | 正式会话输入“检查连接池” | PASS：进入 DB Agent，`check_connection_pool` 成功，Trace 展示受控摘要 |
| mock 多角色主链 | S1 慢查询场景 | PASS：Run 完成，公开 Trace 中 server/db/log 三类工具角色可见 |
| 浏览器质量 | 两套隔离 Vite/后端实例 | PASS：JavaScript console error 0、page error 0；仅两个 `/favicon.ico` 404，无 API 4xx/5xx |

浏览器截图已人工检查：配置/未配置知识页、监控概览和会话 Trace 均无明显遮挡、截断或误导占位。截图与临时数据库仅为本地验收产物，不提交仓库。

## 验收中发现并修复的问题

- 普通消息分类器缺少“锁等待/数据库锁”关键词，可能进入普通问答而不创建调查。
- 图运行时 SQL/数据库关键词不足，直调图时可能不启动 DB Agent。
- mock 规划器先命中泛化 explain 分支，显式锁问题无法选择 `check_lock_status`。
- 已扩充三处路由/规划规则，并为锁等待、数据库锁、连接池增加 API、图运行时和 planner 回归测试。
- 全量测试环境曾继承真实 target DSN，导致默认装配测试污染；测试现显式清除此变量，保持环境隔离。

## 真实受控动作证据边界

- issue #100 / PR #107 已完成真实 target 的提案 → 人工审批 → 二次确认 → 固定白名单执行 → 独立 Verify，终态 `verified`。
- issue #101 / PR #109 在同日再次复核结构化建议、真实证据、影响面投影和受控恢复链。
- 本次复核发现固定索引已存在，脚本以 `TARGET_INDEX_ALREADY_EXISTS` 安全停止，`target_write_may_have_started=false`；未执行 DDL/DML，也未删除已验证索引。
- 因此 #105 采用“已完成真实闭环证据 + 当前只读后置状态”验收，不以破坏性回滚制造可重跑前置条件。

## 仓库收口

- 以 patch-id 验证 #100/#101/#102 分支与对应 squash merge 等价后，删除三个已合并本地分支；#100 远端旧分支也已删除。
- 移除三个干净 worktree 登记；Windows 遗留目录已发送到回收站，可恢复。
- 停止仅指向上述旧 worktree 的遗留开发进程。
- 对 `docs/` 做 SHA-256 精确重复扫描，未发现内容完全相同的重复文档；不做主观内容删除。
- 主工作区和 `p6-cross-service-investigation` worktree 均含用户未提交改动，已原样保留。

## 自动化

| 检查 | 结果 |
|---|---|
| 后端聚焦回归 | PASS：43 passed（runtime/plain API）；6 passed（service center 环境隔离） |
| 后端全量 | PASS：639 passed / 1 个既有 StarletteDeprecationWarning |
| 后端 ruff | PASS：All checks passed |
| 后端 mypy | PASS：113 个源文件无错误 |
| 前端 typecheck | PASS |
| 前端 test | PASS：217 passed / 21 files |
| 前端 build | PASS（仅既有 chunk size 提示） |
| `git diff --check` | PASS |
