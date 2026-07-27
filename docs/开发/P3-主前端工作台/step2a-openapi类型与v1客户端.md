# P3.2a Step — OpenAPI 类型与 v1 客户端

> 日期：2026-07-27　|　状态：✅ 已提交 `75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`
>
> 范围：P3.2 的基础只读 client、OpenAPI 类型、Query 描述和 MSW 契约；不包含工作台路由或写接口。

## 已交付

- OpenAPI 生成类型位于 `frontend/src/api/v1/generated.ts`；`npm run generate:api` 使用本机后端 OpenAPI，产物不手写替代协议。
- `frontend/src/api/v1/client.ts` 只实现 Session list/detail、Session Message list、Session Run list 与 Run detail 五个 GET；所有 client 请求使用 `/api/v1`，传递 cursor、`Accept`、`X-Request-Id`，读取安全关联信息。
- 默认浏览器 client 在**发起请求时**读取当前 `fetch`，并解析同源 `/api/v1` URL；这避免模块加载早于 MSW 安装时绕过测试拦截，同时仍由 Vite `/api` 代理处理开发环境请求。
- `frontend/src/api/v1/queries.ts` 描述稳定 query key 与读取 options；`frontend/src/test/handlers.ts` 以确定性 MSW fixture 覆盖成功、空列表、分页、归档、安全 404/500、网络中断和 Run result。
- 已在提交前通过类型检查、测试、构建与 OpenAPI 生成。

## 边界

- 不实现 `POST /sessions`、`PATCH/DELETE /sessions/{id}`、`POST /sessions/{id}/runs`、Event 或 SSE；`Idempotency-Key`、`Last-Event-ID` 留给 P3.3。
- MSW 仅用于测试，不是持久化不可用时的运行时降级。当前真实 `/api/v1/sessions` 的安全 500 不被吞掉或伪造成成功。
- 不调用旧 `/diagnose`、`/diagnose/stream`，不修改后端、`report/`、`frontend/mockup.html`、真实数据源或运行时资产。

## 后续衔接

P3.2b 已在 `step2b-session工作台只读恢复.md` 完成 Code / Test / 独立 Review，待用户授权提交；它消费本 Step 的五个 GET 与 Query 描述，增加 Session → Runs → Message → Run 的只读恢复 UI。

**P3.2b 提交后的唯一下一步为 P3.2c：mock FastAPI 联调、刷新/深链人工验收与真实读模型前置条件核对。**
