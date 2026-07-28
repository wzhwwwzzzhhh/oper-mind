# P3 独立审查 — P3.4 Design：结构化结果、终态收口与受控 Trace 边界

> 日期：2026-07-28　|　结论：✅ 设计审查通过，尚未开始 P3.4 代码实现
>
> 审查基线：`306724d docs: 校正P3.3c提交状态并进入P3.4`　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次只审查 P3.4 的文档设计、P2 v1 Result/Run 终态契约、既有 P3 工作台消费点与 Mock 验收边界。未修改前端/后端源码、MSW、独立 Mock、`report/`、数据库、Alembic、旧 `/diagnose*` 或运行时资产。

## 2. 审查依据

- P2 公开契约：`docs/开发/P0-V1产品化基线/api-v1-contract.md:260-510`；
- 后端 Pydantic 终态不变量：`backend/src/api/v1/schemas.py:129-254`；
- 当前 v1 Query/client：`frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`；
- 当前选定 Run、事件和归档展示：`frontend/src/features/workbench/WorkbenchPage.tsx:437-671`、`run-events.ts`、`use-run-event-stream.ts`；
- P3 总设计与本 Step：`docs/开发/P3-主前端工作台/design.md`、`step4-结构化结果与终态收口.md`；
- 计划与规则镜像：`docs/开发/_A-Plan-总览.md`、`docs/开发/_B-V1产品化开发计划.md`、`AGENTS.md`、`CLAUDE.md`。

## 3. 独立审查结果

| 检查项 | 结果 | 审查结论 |
|---|---|---|
| P2 Result/Run 契约 | 通过 | 设计只消费 `GET /api/v1/runs/{run_id}` 的嵌入式 `DiagnosisResult`，覆盖 summary、severity、confidence、root_causes、evidence、impact、recommendations、risks、requires_approval、agent_summary、report_markdown 与 UTC `created_at`；不自建 Result API 或字段别名 |
| 终态与错误模型 | 通过 | `succeeded → result`、`failed → error`、非终态不带二者的后端不变量已映射为前端状态矩阵；读取/API/SSE 网络异常不伪造成业务失败 |
| 刷新与 SSE | 通过 | 结果只由重读 Run 获得；事件仅触发状态恢复，不能拼接结构化结果；非终态才监听 SSE，终态关闭并重读 Run |
| 空状态与归档 | 通过 | 无 Run、空数组、无 Event、归档历史只读、404、跨 Session 与协议错配均有明确诚实显示；未设计重新激活、重新执行或取消能力 |
| 建议/审批与 P4–P6 边界 | 通过 | 建议和风险只读；`requires_approval` 仅显示 P5 未实现标签；未创建环境、数据源、告警、Incident、审批、知识、报告、导出或统计能力 |
| `report/` / Trace 边界 | 通过 | P3.4 不渲染外部 Trace 入口、URL、iframe 或 `report_markdown`；P6 前置条件以显式配置、deep-link、认证授权、隔离和回退为停止条件 |
| Mock 与真实资源 | 通过（有后续门槛） | 发现 P3.3c 成功 Mock Result 缺少 P2 必填 `created_at`，仅适用于此前非空占位，不能作为 P3.4 结果验收；已明确列为 P3.4c 的合同补齐，不以真实 8000/数据库替代 |
| 文档/计划/唯一下一步 | 通过 | Design、step4、HANDOFF、A/B-Plan、AGENTS/CLAUDE 均指向 P3.4a，且镜像文件应逐字一致 |

## 4. 发现、风险与处理

1. **Mock Result 合同不足**：当前独立 Mock 的成功 Result 缺少 `created_at`，并只含简化空数组。它不是 P3.3 的契约缺陷（P3.3 未渲染结构化字段），但会阻断 P3.4 端到端验收。处理：P3.4a 使用完整静态契约夹具做 reader/组件测试，P3.4c 单独补齐 MSW/Mock 并执行独立代理验收。
2. **`report_markdown` 的范围风险**：若直接解析/导出 Markdown，会提前混入 P6 报告能力，且可能扩大展示安全面。处理：P3.4 只保留结构化字段，不渲染该补充字段。
3. **Trace 跳转的配置/认证风险**：仅有 `trace_id` 不足以安全生成外部链接。处理：P3.4 不实现入口，P6 前必须完成受控目标与权限等前置条件。
4. **真实接入仍延后**：Mock 通过不能代表 persistence、后台执行器或真实数据库联调。C1–C8 继续保留；不访问用户运行中的 8000/5174。

## 5. 结论与下一步

P3.4 Design 对 P2 结构化结果、终态、刷新/SSE、失败/空/归档和 Trace/report 边界的消费准确，未发现需要改动 P2 契约或越过 P3 范围的设计问题。P3.4a 可在用户明确授权后作为最小实现切片开始。

**当前唯一下一步：P3.4a——结构化结果读取模型与摘要面板实现（需用户后续代码授权）。**
