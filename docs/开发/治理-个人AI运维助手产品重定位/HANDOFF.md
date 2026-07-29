# R1 / P3.6a 交接（已关闭）

> 关闭日期：2026-07-29　|　分支：`feat/p3-workbench`
> 前序基线：`ef5deab docs: 收口文档层级与历史交接入口`
> 状态：P3.6a「会话壳与只读 Turn 投影」已完成 Code/Test/Review，且已通过用户人工验收并提交。

## 已完成

- R1/P3.5 产品重定位与设计已提交：`6b0290b`；
- P3.6a 仅在用户明确授权后开始，且仅修改 `frontend/` 与治理/计划文档；
- 前端把既有 P2 GET Session、Runs、Messages 投影为 user Message → Investigation → persisted assistant Message；
- 成功缺答复、失败/取消/未终态、Result/关联异常、空/归档/读取错误均保持诚实状态；
- 保留正序 cursor 并提供继续加载 Runs/Message，不宣称完整长期历史；
- 旧 Run 深链兼容为进入对应会话，不再读取单个 Run；
- `npm run typecheck`、`npm run test`（5 files / 33 tests）、`npm run build` 与 `npm run test:mock-api`（11 passed）均通过；
- 用户已使用独立 8100 Mock 与非 Windows TCP 排除端口完成 P3.6a 人工验收。

## 关闭后的恢复入口

1. 先执行 `git status --short` 与查看最近提交；
2. 阅读 `docs/开发/_A-Plan-总览.md`、`docs/开发/README.md`、本目录 `README.md`、`review.md` 与本文件；
3. 当前唯一下一步是 **P3.6b「调查型发送、稳定幂等键与刷新/SSE 恢复」的 Design**，不是直接实现；必须先完成 Design → Review，并获得用户新的明确授权；
4. 继续继承 P2 `/api/v1` 契约，不得把 P3.6a 的只读页面错误扩展为普通聊天、假监控、假告警或自动处理。

## 持续约束

- 不得触碰隔离文件：`docs/00-项目方案说明书.md`、`backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py`、以及其他 agent 持有的治理 `design.md` 元数据状态；禁止 `git add .`；
- 不改 `report/`、后端 `/api/v1`、Application Service、Repository、ORM、Alembic、旧 `/diagnose*`、Mock API 或运行时资产，除非未来独立 Step 明确授权；
- 不接入真实 8000、真实 DB、数据源、认证、在线迁移或执行器；不伪造监控、告警、Action、Approval、Incident 或多人协作；
- P3.6b 的发送只能是调查型受理，必须先设计稳定 Idempotency-Key、刷新对账、持久化 events 与 SSE `Last-Event-ID` 恢复；不得假装是普通聊天。
