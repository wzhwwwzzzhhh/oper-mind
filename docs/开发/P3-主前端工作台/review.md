# P3 独立审查 — 主前端工作台

> 日期：2026-07-27　|　结论：🟡 P3.2a 已提交 `75d6598`；P3.2b 已通过独立 Review，待用户授权暂存/提交
>
> 已提交基线：`12bed37 docs: 完成P3主前端工作台设计`、`4862752 feat: 初始化P3主前端工程与产品外壳`、`ec45ee2 docs: 完成P3.2接口与恢复读模型设计`、`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`

## 1. 历史基线

P3 Design、P3.1 产品外壳、P3.2 Design 与 P3.2a 已完成对应的设计、测试、独立审查并提交。本审查仅覆盖未提交的 P3.2b：Session 工作台只读 UI 与刷新/深链恢复；不审查或修改后端安全 500 的根因。

## 2. 审查依据

- P2 契约：`backend/src/api/v1/routes.py:169-386`、`backend/src/api/v1/schemas.py:27-318`、`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-514`；
- P3.2a 基础：`frontend/src/api/v1/generated.ts`、`frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`、`frontend/src/test/handlers.ts`；
- P3.2b 实现：`frontend/src/app/App.tsx`、`frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/workbench/resource-readers.ts`、`frontend/src/styles/global.css`；
- 回归：`frontend/src/app/App.test.tsx`、`frontend/src/api/v1/client.test.ts`、`frontend/vite.config.ts`；
- 记录：`design.md`、`step2-v1-api客户端与会话恢复读模型.md`、`step2a-openapi类型与v1客户端.md`、`step2b-session工作台只读恢复.md`、`HANDOFF.md`、A/B Plan 与镜像规则文件。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| P2 API 契约 | 通过 | 工作台只消费 Session list/detail、Session Runs、Session Messages、Run detail 五个 GET；未新增字段语义、未手写第二套资源 DTO |
| 路由与刷新恢复 | 通过 | 只提供 `/workbench`、Session 深链与 Run 深链；页面测试锁定 Session → Runs → Message → Run 顺序，无 URL Run 时才在 Message 成功后回填首个 Run |
| cursor / ID / 错误资源 | 通过 | TanStack Query 将服务端 `next_cursor` 原样传回；client 发送 `X-Request-Id`，错误区只呈现安全 code、message、request/trace 关联信息 |
| 上游失败诚实性 | 通过 | Runs 失败时 Message 与当前 Run 改为等待上游，不再误显示空状态或访问未加载 Run；新增页面回归测试锁定该行为 |
| Session 隔离 | 通过 | `get_run` 返回的 `run.session_id` 与 URL Session 不匹配时显示 `RUN_SESSION_MISMATCH`，不渲染跨会话内容 |
| 阶段边界 | 通过 | 无 POST/PATCH/DELETE、`Idempotency-Key`、Run 受理、RunEvent/SSE、结果卡、Trace 跳转、P4/P5/P6 页面或假资源；旧 `/diagnose`、`/diagnose/stream` 未被调用 |
| `frontend/` / `report/` 边界 | 通过 | 修改仅位于主产品 `frontend/`；未修改、引入或改造 `report/`，`frontend/mockup.html` 未触碰 |
| 真实数据与运行时资产 | 通过 | MSW 只用于测试；本机真实 `/api/v1/sessions` 安全 500 被如实展示，无本地数据降级、无 DB/SQLite/认证/数据源接入 |
| 文档与唯一下一步 | 通过 | A-Plan、B-Plan、P3 日志与 `AGENTS.md`/`CLAUDE.md` 同步为 P3.2b 待提交；镜像文件 SHA-256 一致 |

## 4. 发现与处置

1. **默认 v1 client 在模块初始化时捕获 `fetch`。**这会令全局 client 在 MSW 安装之前绕过拦截。已改为每次请求读取当前 `fetch`，浏览器空 base URL 解析为同源 URL；新增回归测试，Vite `/api` 代理语义不变。
2. **MSW handler 曾依赖固定相对 origin。**已改为仅匹配精确 `/api/v1` pathname 的端口无关规则，并在 Vitest 固定 jsdom URL；这只提升测试确定性，不改变生产 API 路径。
3. **Runs 失败时下游被禁用却可能显示“空消息”。**已改为明确等待文案，并覆盖 deep Run 链路的失败场景；不以空状态掩盖上游错误。

## 5. 验证与人工观察

在 `frontend/` 已通过：

```text
npm run typecheck  → 通过
npm test           → 2 个测试文件、12 个测试通过
npm run build      → 通过
```

- 页面测试覆盖 active Session 入口、Run 深链、严格恢复顺序、Session 404、Runs 失败时的下游等待；client 测试继续覆盖 request ID、cursor、安全错误、网络/abort/协议错误与延迟读取 fetch。
- 本机人工访问 `http://[::1]:5174/workbench` 时，真实后端目前仍返回安全 `INTERNAL_ERROR`；页面显示通用消息、错误码和 request ID，未伪造 Session。MSW 成功路径不等价于真实持久化读取成功。
- 构建仍保留 Ant Design 主 bundle 超过 500 kB 的警告（约 732 kB，gzip 约 234 kB）。这记录为后续性能工作，不在 P3.2b 通过拆包扩大范围。

## 6. 已知风险与非目标

- P3.2c 必须分开执行 mock FastAPI 联调、浏览器刷新/深链验收，并补足空列表、cursor、归档、Run 404、跨 Session Run、网络中断等场景；不得把其混入 P3.2b 提交。
- 真实读模型验收前必须共同确认 Alembic 迁移、连接目标、最小权限、可用 mock 数据、契约、回退路径和验收场景。当前 500 未定位，P3.2b 不修后端。
- OpenAPI 改变时仍需显式执行 `npm run generate:api` 并复核生成类型；cursor 的服务端 scope/授权不是前端可替代的职责。

## 7. 结论与唯一下一步

P3.2b 在约定范围内通过独立 Review，可以进入提交候选；待用户明确授权后只能按 `HANDOFF.md` 的逐文件清单暂存和提交。建议提交信息：`feat: 完成P3.2b会话工作台只读恢复`。

**P3.2b 提交后的唯一下一步为 P3.2c：mock FastAPI 联调、刷新/深链人工验收与真实读模型前置条件核对。**
