# P3 独立审查 — 主前端工作台

> 日期：2026-07-27　|　结论：🟡 P3.2 Design 已提交；P3.2a 已通过独立审查，待用户授权暂存/提交
>
> 已提交基线：`12bed37 docs: 完成P3主前端工作台设计`、`4862752 feat: 初始化P3主前端工程与产品外壳`

## 已完成历史审查

P3 Design 与 P3.1 的 API 边界、产品壳、工程隔离、测试/构建和视觉验收均已通过并提交；本次仅独立审查 P3.2 的设计，不实现前端读取逻辑。

## P3.2 Design 独立审查

### 审查依据

- `backend/src/api/v1/routes.py:169-386`：Session、Message、Session Run、Run 的真实 GET 路由；
- `backend/src/api/v1/schemas.py:27-318`：ResponseMeta、资源、cursor/list 与 Run 响应模型；
- `docs/开发/P0-V1产品化基线/api-v1-contract.md:426-514`：排序、cursor、请求/trace ID、SSE 与旧 API 边界；
- 运行中的 `GET /openapi.json`：v1 路径及公开 schema；
- `frontend/src/app/App.tsx:1-96`、`providers.tsx:1-32`、`use-ui-store.ts:1-13`：P3.1 路由、QueryClient 与 UI-state 基线。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| API 精确性 | 通过 | 设计只列出 Session、Message、Session Run、Run 五个 GET；没有臆造 Result 单端点、Event、SSE 或写接口 |
| OpenAPI 类型 | 通过 | 以生成 TypeScript 类型作为字段真相，正常 build/test 不在线抓取；客户端只定义 transport/diagnostics 外壳，避免第二份资源 schema |
| 刷新顺序 | 通过 | Session → Runs → Message → 选定 Run；Run URL 优先、首个已加载 Run 后备，明确结束于只读 Run，不越级进入 Event/SSE |
| cursor 与缓存 | 通过 | `useInfiniteQuery` 仅原样传 `next_cursor`，Query key 绑定 Session/筛选/limit，切换 Session 清理旧 cursor，禁止跨 Session 复用 |
| ID/错误安全 | 通过 | 每请求 UUID request ID；读 header/meta diagnostics；非 2xx 只暴露安全 `error` 和关联 ID；网络/abort 不伪装为业务 Run 失败 |
| 路由数据隔离 | 通过 | 深链 Run 需验证 `run.session_id`；Session/Run 404、归档只读与无数据均不自动创建资源或展示跨 Session 内容 |
| P3/P4/P5/P6 与旧 API | 通过 | P3.2 禁止写 Session/Run、SSE、结果卡、report 跳转、旧 `/diagnose`、真实数据源与认证；未实现能力无假 UI |
| MSW 与真实联调 | 通过 | MSW 使用固定契约资源/错误，不作为内存降级；当前 FastAPI health/OpenAPI 正常、sessions 返回安全 500 的事实被记录为真实联调前提 |
| 文档交接 | 通过 | P3.1 真实提交基线校正为 `4862752`；P3.2a 被明确为唯一首个实现 Step；规则镜像、A/B Plan 和 P3 日志同步 |

### 发现与处置

1. **发现：** P3 HANDOFF 的当前基线仍指向 `12bed37`，且遗留“P3.1 将提交”措辞；实际 P3.1 已提交为 `4862752`。
   **处置：** 本轮把 P3.1 作为历史完成快照，当前基线更新为 `4862752`，并将暂存清单改为 P3.2 Design 文档。
2. **发现：** 用户启动的后端 `/health` 与 `/openapi.json` 返回 200，但 `/api/v1/sessions?limit=1` 返回安全 `500 INTERNAL_ERROR`；前端服务监听 `::1:5174`，从 `127.0.0.1` 探测会被拒绝。
   **处置：** 不在 P3.2 设计阶段改后端或伪造成功；设计采用 MSW 先行，并把应用 DB migration/连接预检列为真实 API 验收前置。监听地址作为本地启动观察项，不改变 API 契约。

### 已知风险

- OpenAPI 生成物必须在后端 OpenAPI 变化时显式再生成；P3.2a 需把生成命令、输出路径和 schema 断言写入测试/文档，防止字段漂移。
- 当前 API 500 的根因未在本轮读取日志或修复；若 migration/持久化配置未就绪，P3.2c 不能宣称 FastAPI 真实读模型联调通过。
- 资源 cursor 仍不绑定 Session scope；前端限制 cursor 生命周期但不能替代服务端授权/scope 收口。

## 结论

P3.2 Design 已提交为 `ec45ee2`。P3.2a 在既定范围内通过独立审查：已实现 OpenAPI 类型、只读 API client、Query 边界与 MSW 契约测试，未实现路由读模型或任何后端改动。**待用户授权暂存/提交后，唯一下一步为 P3.2b：Session 工作台只读 UI 与刷新/深链恢复实现。**
## P3.2a 实现独立审查

### 审查依据

- `frontend/package.json:7-12`、`frontend/src/api/v1/generated.ts:1`：显式 OpenAPI 生成命令与提交产物；
- `frontend/src/api/v1/client.ts:1-275`：五个 GET、请求关联、安全错误和 transport/protocol 分类；
- `frontend/src/api/v1/queries.ts:1-57`：TanStack Query 的 key/request 边界；
- `frontend/src/test/handlers.ts:54-171`、`frontend/src/api/v1/client.test.ts:7-139`：MSW 场景与客户端断言；
- `docs/开发/P3-主前端工作台/step2a-openapi类型与v1客户端.md`：范围、验证和风险记录。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| P2 v1 GET 契约 | 通过 | 仅实现 Session 列表/详情、Message 列表、Session Run 列表、Run 详情五个 GET；无 Result 单端点、Event/SSE 或写调用 |
| 关联与错误语义 | 通过 | `X-Request-Id`、`X-Trace-Id`、`meta` 与安全 `{ error, meta }` 都进入 diagnostics / `ApiClientError`；网络、取消、非 JSON 不被伪造成 Run failed 或 `INTERNAL_ERROR` |
| cursor 与缓存边界 | 通过 | cursor 只经 `URLSearchParams` 原样传递；Query key 含 Session/筛选参数，未把资源放入 Zustand |
| OpenAPI 类型 | 有风险但可接受 | `generated.ts` 由实际 `/openapi.json` 生成；部分 Pydantic 业务字段为 `unknown`，客户端不以手写 DTO 掩盖此问题，后续加强类型需先审查后端契约 |
| MSW 场景 | 通过 | 覆盖 active/empty/分页/archived、安全 404/500、网络中断和 succeeded Run；正常响应回显请求 ID，避免错误模拟关联语义 |
| P3/P4/P5/P6 和旧 API | 通过 | 没有页面、写操作、Run 受理、SSE、结果卡、Trace 跳转、旧 `/diagnose`、真实数据源或认证 |
| 验证 | 通过 | `npm run typecheck`、`npm test`（2 files / 8 tests）、`npm run build`、`npm run generate:api` 均通过；仅保留既有 Ant Design 大包警告 |
| 工作区隔离 | 通过 | 未改 `report/`、`backend/`、`data/`、`frontend/mockup.html`；三个外部隔离改动未读取、未修改、未暂存 |

### 结论

P3.2a 可以进入提交候选。真实 FastAPI Session 读取仍因既有安全 `500 INTERNAL_ERROR` 而未验收；MSW 通过不等同于真实 API 成功。提交后只进入 P3.2b 的只读 UI 与刷新/深链恢复，不得提前实施写操作或 SSE。
