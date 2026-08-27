# Issue #101 结构化诊断结果真实性 · 验收证据

> 更新：2026-08-27
> 当前结论：自动化、本地浏览器与 AC8 真实受控靶场链全部 PASS。

## 自动化结果

| 检查 | 结果 |
|---|---|
| 后端聚焦 `tests/test_p5_controlled_action.py` | 15 passed |
| Ruff（src + 聚焦测试） | PASS |
| mypy | 113 source files，PASS |
| 后端全量 pytest | 632 passed，2 条第三方弃用 warning |
| 前端聚焦 Vitest | 15 passed / 2 files |
| 前端 typecheck | PASS |
| 前端全量 Vitest | 212 passed / 21 files |
| 前端 build | PASS；仅既有 chunk size warning |
| `git diff --check` | PASS |

## 真实性证据

- 完整匹配：固定 signal + 匹配根因 + “目标表存在 / 固定联合索引缺失 / 顺序扫描信号”三类
  `database/postgres_read_only` 证据，才生成一条建议与影响面。
- 来源追溯：建议描述包含既有公开 action id；建议稳定 UUID 由 action id 派生；`evidence_ids`
  精确指向三类只读证据。
- 负向：报告正文即使写出缺索引、action id 和虚构业务影响，在无确定性 investigation 时仍输出
  `recommendations=[]`、`impact=None`、`requires_approval=False`。
- 证据不足：signal 存在但证据不闭合时不再复制 EvidenceFact，也不生成建议或提案。
- 单一规则：结果组装器与 ActionApplicationService 都调用 `match_compound_index_result`。

## Markdown 安全证据

- 白名单覆盖标题、段落、列表、引用、代码和表格。
- `<script>`、原始 `<img onerror>`、`javascript:` 链接与外链图片测试后，DOM 中无 script / a / img，
  无 `onerror` 与外站 URL。
- 链接只保留不可点击文本；Markdown 图片只显示“图片已禁用”与 alt 文案。
- 空结构化结果只有“只读调查未产生可展示的结构化证据”一个空态。

## 浏览器复验

- 工具：webapp-testing 规程下的原生 Python Playwright，Chromium headless。
- 隔离端口：mock API 8111，Vite 5181；测试结束后进程与临时文件均已清理。
- 页面：`/workbench/sessions/11111111-1111-4111-8111-111111111111`。
- 验证：assistant 回答进入 `.safe-markdown`；报告折叠/展开成功；Markdown h1 正常；impact、
  recommendations 与“说明性建议，不等同于动作提案”可见；安全区无 a/img/script；浏览器 console/pageerror 为零。
- 视觉目检：1440×1100 全页截图中结构化面板、报告区和主要标签无重叠、截断或横向溢出。

## AC8 真实受控靶场复核

- 授权边界：仅本机映射 `postgres-target:5433`、`public.orders` 与固定索引
  `idx_orders_customer_created_at(customer_id, created_at)`；未访问生产或预发布。
- 场景重置：用户单独确认后，固定脚本再次校验表、列与有效索引，再删除唯一固定索引；只读复核为
  `index_exists=false`、`index_valid=false`、`plan_seq_scan=true`。
- 只读调查：Run `succeeded`；公开结构化投影包含 1 条固定模板建议、3 条关联
  `database/postgres_read_only` 证据、非空 impact，且 `requires_approval=true`。建议稳定 id 为
  `45f7c3e2-b526-556b-b7b7-a94cdf7bcc47`。
- 人工门禁：新提案由用户明确批准，随后用户再次确认执行；approval digest 与 proposal 一致，
  actor 为 `local_operator`，未自动批准。
- 恢复与 Verify：固定 target executor 执行成功；独立 Verify 为 `index_exists=true`、
  `index_valid=true`、`plan_uses_index=true`；Postflight 为 Seq Scan=false 且只使用目标索引。
- 审计：proposal 终态 `verified`；proposal_created 至 verification_completed 共 8 类事件各一次、顺序完整。
- 诚实限制：LLM provider 使用确定性 mock；PostgreSQL collector、DDL executor、独立 Verify、API、
  persistence、审批与审计路径均为真实执行。成功索引按安全边界保留，不自动清理。
