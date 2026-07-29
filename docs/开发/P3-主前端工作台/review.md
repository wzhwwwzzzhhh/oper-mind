# P3 独立审查 — P3.4c：完整 Result Mock 合同与验收

> 日期：2026-07-29　|　结论：✅ P3.4c 的代码、自动验证、P2 schema 交叉校验与独立 Mock HTTP 代理核验通过，可提交；⚠️ 页面可视化验收受 Windows 排除端口阻断后置，未伪记为通过。
>
> 审查基线：`94539b5 feat: 完成P3.4b结果接入与终态收口`　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次只审查 P3.4c 对完整结构化 Result 的 MSW/独立 Mock FastAPI 合同补齐及离线/代理验收。待提交实现文件仅为：

- `frontend/scripts/mock_v1_api.py`
- `frontend/scripts/test_mock_v1_api.py`
- `frontend/src/test/handlers.ts`
- `frontend/src/app/App.test.tsx`

未修改后端 `/api/v1`、OpenAPI、Application Service、Repository、ORM、Alembic、旧 `/diagnose*`、`report/`、真实数据库/数据源或运行时资产；未增加 Trace URL、iframe、Markdown 渲染、审批/执行、报告、P4–P6 假能力。

## 2. 审查依据与执行记录

- P2 资源/终态约束：`backend/src/api/v1/schemas.py:129-254`；
- v1 Result、关联 ID、UTC `Z`、错误与 SSE 契约：`docs/开发/P0-V1产品化基线/api-v1-contract.md`；
- P3.4 设计与 Step：`docs/开发/P3-主前端工作台/design.md:153-214`、`step4-结构化结果与终态收口.md`；
- 本次验证：`npm run test:mock-api`（11 passed）、`npm run typecheck`、`npm run test`（4 files / 38 passed）、`npm run build`；
- P2 schema 交叉校验：合法成功/归档/空数组/failed/cancelled Run 均通过 `DiagnosisRunResource.model_validate`；协议错误夹具确认故意缺 `created_at`。

## 3. 独立审查结果

| 检查项 | 结果 | 审查结论 |
|---|---|---|
| 完整 P2 Result 字段 | 通过 | MSW 与独立 Mock 均有 `id`、`run_id`、严重度、置信度、根因、证据、影响、建议、风险、审批标记、Agent 摘要、Markdown 补充和 `created_at`；嵌套资源 ID 改为 UUID 格式 |
| 成功、空与协议错误区分 | 通过 | 成功/归档和合法空数组均是完整资源；空数组进入面板局部空状态；只有故意缺 `created_at` 的夹具显示 `RESULT_PROTOCOL_ERROR`，不伪造结果 |
| P2 Run 终态不变量 | 通过 | `failed` 仅带安全 error；`cancelled` 不带 result/error；空数组仍为 succeeded 的合法 Result；合法夹具由后端 Pydantic schema 交叉验证 |
| 刷新/事件恢复 | 通过 | 新终态 Run 在 MSW/Mock 都返回合法空 Event 页，避免 Session→Runs→Messages→Run→Events 恢复链将终态误报 404；既有 SSE/`Last-Event-ID` 自动测试保持通过 |
| 关联、时间和安全错误 | 通过 | Mock 自动测试校验 UTC `Z`、request/trace 关联、cursor、安全 404/500；5175 代理请求返回并回显 `X-Request-Id`、`X-Trace-Id` |
| 独立代理隔离 | 通过 | 对运行中 `localhost:5175 → localhost:8100` 的 HTTP 核验命中 Mock 请求日志；未访问 8000、真实数据库或真实数据源 |
| `report/`/P4–P6 边界 | 通过 | 无 `report/` 变更、Trace 外链/iframe、Markdown 渲染、环境/数据源/告警/Incident/审批/知识/报告假数据 |
| 自动质量门 | 通过 | Mock 11 passed；Vitest 38 passed；类型检查、生产构建通过。仅有已知 Starlette 弃用警告和 Vite 大 chunk 非阻断提示 |
| 可视化验收 | 后置/环境阻断 | 2026-07-29 Windows TCP 排除范围 `5141–5240` 使 Vite 的 5174–5176 监听均返回 `EACCES`；自动与代理核验不能冒充 UI 通过。待环境允许使用独立非排除端口后补做，且不得改连 8000。 |

## 4. 已知风险与非目标

1. 2026-07-29 的 Windows TCP 排除范围 `5141–5240` 使 5174、5175、5176 都无法监听（`EACCES`），故先提交可复现的 Mock 合同与自动核验；页面验收必须在恢复后以独立 Mock 和非排除端口完成，不得转而访问 8000。
2. 独立 Mock 仅为进程内确定性合同/代理验收，不代表 P2 持久化、队列、真实 Agent 或真实数据库验收。
3. 主生产 chunk 约 892.65 kB，Vite 仍提示大于 500 kB；功能正确，拆包留给后续非功能/生产加固范围。
4. P4/P5/P6、Trace 外部地址与真实 API/数据库接入仍是非目标；C1–C8 真实只读验收前置不降低。

## 5. 结论与当前唯一下一步

P3.4c 的代码、自动回归、后端 schema 交叉校验与独立 HTTP 代理核验均通过，且发现并修正了 MSW 嵌套资源 ID 不符合 P2 UUID 类型的夹具问题。页面可视化验收尚未完成的原因是 Windows 系统端口排除，而非产品或合同失败；该状态已如实记录，允许本独立技术切片提交。

**当前唯一下一步：提交 P3.4c 后只做产品定位研究与现有计划拷打；在未形成研究结论前，不锁定前端转向方案，不开始新的 UI 实现。**
