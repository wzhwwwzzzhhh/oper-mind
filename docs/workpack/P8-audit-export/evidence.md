# P8-audit-export · AC 证据表

> 关联 PRD：`docs/prd/audit/P8-audit-export.md`（进行中，issue #79）
> 分支：`feat/p8-audit-export`（基线 main，已合入 origin/main @ 22d2d68）
> 更新：2026-08-15

## S1 后端导出 API（commit `51745a7`）

| AC | 验收标准 | 证据 | 结果 |
|---|---|---|---|
| AC1 | GET /audit/export 返回可下载文件，内容与列表同构 | `test_导出内容与列表同构且排序一致`：CSV 表头 18 字段同投影、行与列表同条件一致、Content-Disposition attachment | PASS |
| AC2 | 过滤条件与列表语义一致 | `test_过滤条件与列表一致`：service_id/action_type/result/from/to 各自断言；`test_窗口不合法返回422` | PASS |
| AC3 | 无匹配记录 → 明确空态（0 条元信息） | `test_空结果返回0条元信息空文件`：200 + `# 条数: 0` + 表头，X-Export-Count=0 | PASS |
| AC4 | 超限明确提示，不返回截断文件 | `test_结果超过上限返回422明确提示`（5001 条 → 422 EXPORT_LIMIT_EXCEEDED，message 含 5000 与收窄建议）；`test_边界恰5000条可导出`（5000 条 → 200） | PASS |
| AC5 | 不含 CoT/Prompt/原始工具输出/原始 SQL/异常/凭据/`sk-`/DSN | `test_敏感字面量不进导出文件`：sk-、user:pass@ 被 desensitize 兜底为 `[已脱敏…]` | PASS |
| AC6 | 审批人字段如实"未记录" | `test_审批人字段如实未记录`：approval_recorded 行含"未记录"，无 local_operator | PASS |
| AC7 | 导出文件含元信息（时间/条件/条数/快照标注） | `test_导出元信息四要素齐全`：`# 导出时间`、`# 过滤条件`（未过滤项"无"）、`# 条数`、`# 说明: 只读快照…`；响应头 X-Export-Count | PASS |
| AC8 | 相同条件重复导出内容一致 | `test_相同条件重复导出内容一致`：两次导出除导出时间行外逐字节一致 | PASS |
| AC9 | 前端导出入口（S2） | S2 证据见下 | PASS |
| AC10 | 回归：test_audit_api.py 全绿 | `pytest tests/test_audit_export_api.py tests/test_audit_api.py` = 28 passed（S1 提交时） | PASS |

## S2 前端导出入口（commit `bbe8227`）

| AC | 验收标准 | 证据 | 结果 |
|---|---|---|---|
| AC9 | 导出按钮携带当前过滤条件；空/超限/失败态诚实展示 | `AuditPage.test.tsx`：`导出按钮携带当前过滤条件并触发下载`（format=csv + action_type 参数 + 空结果提示"没有可导出的记录"）、`导出超限显示收窄建议`（422 → "导出结果超限"+收窄建议）、`导出失败显示错误并可重试`（500 → "导出失败"+重试成功） | PASS |
| AC10 | 前端 typecheck/test/build 通过 | `npm run typecheck` 通过；`vitest run src/features/audit/AuditPage.test.tsx` 10 passed；全量 `npm run test` 148 passed / 3 failed（详见下） | PASS* |

\* 全量前端测试的 3 个失败（App.test.tsx：运行中停止、未结束不提供重新生成、重新生成失败）经**干净 main 基线 worktree（origin/main @ 22d2d68）复现一致**，属 rerun/cancel 相关基线既有问题，非本工作包引入。

## 合并后回归（commit `f525dc6`，合入 origin/main @ 22d2d68）

- 后端：`pytest tests/test_audit_export_api.py tests/test_audit_api.py tests/test_session_export.py` = **36 passed**
- 前端：`npm run typecheck` 通过；`vitest run AuditPage.test.tsx + session-export.test.tsx` = 13 passed
- 冲突解决：errors.py（AuditExportLimitExceededError + SessionExportUnavailableError 并存）、docs/prd/README.md（知识分页=完成、审计导出=进行中）、client.ts（request_download + request_text 并存）；generated.ts 由合并后 OpenAPI 重新生成（含 audit/export 与 sessions/{id}/export 两端点）
- 门禁：`git diff --check` 干净；无凭据/`sk-` 内容；只暂存本工作包文件
