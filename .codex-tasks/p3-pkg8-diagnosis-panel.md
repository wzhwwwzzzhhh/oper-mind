# 任务 P3-包8：重写诊断结果面板为自绘 CSS

## 背景（只读）
P3 前端重构已基本完成（三栏壳 / 会话主链路 / 服务中心 / 模型设置）。
目前 `frontend/src/features/workbench/DiagnosisResultPanel.tsx` 仍用 antd（Card/List/Tag/Empty/Descriptions/Space/Typography）。
本任务把它重写为**自绘 CSS**，去掉对 antd 的依赖。

**注意：`ActionProposalPanel.tsx`（P4.2 动作闭环）保持 antd 不动**——它是 P4 的活，本次不碰。
因此 antd 依赖暂不删（仅剩 ActionProposalPanel 用），package.json 不改。

## 只允许修改/创建这些文件
1. 改 `frontend/src/features/workbench/DiagnosisResultPanel.tsx`（重写为自绘 CSS）
2. 改 `frontend/src/styles/workbench.css`（追加诊断结果面板的样式）
3. 可改 `frontend/src/features/workbench/diagnosis-result.test.tsx`（若测试断言 antd 特有结构，改成等价的 aria/文本断言）

**严禁触碰其他任何文件**（不改 ActionProposalPanel、不改 WorkbenchPage、不改 package.json、不改后端）。

## 面板展示的数据（保持语义不变）
诊断结果投影 `DiagnosisResultProjection`（来自 `result-readers.ts`，类型已存在，不要改）：
- `severity`（critical/high/info/low/medium）、`confidence`、`created_at`、`summary`
- `root_causes`：`title`、`summary`、`confidence`、`evidence_ids`
- `evidence`：`id`、`title`、`summary`、`source_type`、`source_name`、`observed_at`、`locator`、`attributes`
- `agent_summary`：`agent`、`status`、`duration_ms`、`summary`
- `risks`：`level`、`summary`、`mitigation`
- `id`、`run_id`

## 重写要求（保持测试可过）
现有测试断言的关键点（**必须保留**）：
- `aria-label="诊断结果摘要"` 显示 summary
- 文本 `结构化诊断结果`（面板标题）
- 文本 `严重度 {severity}`、`置信度 {pct}%`、`结果时间 {created_at}`
- 区块标题：`可能根因`、`结构化证据`、`调查角色摘要`、`调查范围与风险`
- 空态文案：`服务未返回结构化根因`、`服务未返回结构化证据`、`服务未返回角色调查摘要`、`服务未返回风险说明`
- 关联区：`结果 ID`、`Run ID`
- 每个根因/证据/风险/摘要项的关键文本（title/summary/source_type 等）

**改 CSS 类名可以，但 aria-label、标题文本、空态文案、可见文本一律不变。**

## 样式方向
- 用设计 token（`var(--surface)`、`var(--border)`、`var(--text)`、`var(--text-muted)`、`var(--success)` 等），不用硬编码色
- 面板外层一个 bordered card（圆角 8px，边框 `var(--border)`，背景 `var(--surface)`）
- 严重度颜色：critical→`var(--danger)`、high→`var(--danger)`、info→`var(--accent)`、low→`var(--success)`、medium→`var(--warning)`
- 各区块上下留白，区块标题小号加粗
- 空态用居中的 muted 文本，不用 antd Empty 图标

## 验收
- `npm run typecheck` / `npm run test` / `npm run build` 全绿
- 手动：会话调查成功后展开"结论、证据与建议"，诊断结果面板为自绘风格，功能同前
- `git status` 只出现上面允许的 3 个文件

## 完成后
**不要 commit。** 停下告诉我"包8完成"，我审 diff + 跑测试后自己提交。

## 交差前自审清单（必须在完成报告里逐条回答）
1. `git status --short` 完整输出 —— 确认只出现本任务允许的文件（DiagnosisResultPanel.tsx、workbench.css、diagnosis-result.test.tsx）。
2. `npm run test` 最终通过数 —— 确认没有为了通过而删/改已有测试断言。**不许为了绿而改测试。** 若测试因 antd 结构改了，必须列出"改了哪条断言、改成什么、为什么语义等价"。
3. typecheck / build 是否绿。
4. 明确说明：没有动 ActionProposalPanel、没有改 package.json、没有改后端。
5. 列出每个文件的改动点。