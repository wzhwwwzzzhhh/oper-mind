# Issue #101 结构化诊断结果真实性 · 实施计划

> 状态：实现与真实受控靶场复核完成；等待提交授权
> Design：`docs/design/session/P8结构化诊断结果真实性Design.md`

## S1 后端真实性

- [x] 新增代码内受控动作模板目录，统一 action id、固定目标与匹配规则。
- [x] signal、根因和三类真实数据库证据完整闭合才命中模板。
- [x] 从模板与只读证据派生 recommendations / impact / requires_approval。
- [x] 删除 assembler 的重复证据补齐。
- [x] 提案生成与结构化结果组装复用同一匹配函数。
- [x] 增加报告散文反推、证据不足与目标错配负向测试。

## S2 前端安全呈现

- [x] 引入 react-markdown + GFM + sanitize，并锁入 package-lock。
- [x] assistant 普通回复与调查回复统一接入 SafeMarkdown。
- [x] report_markdown 在“完整诊断报告”折叠区安全呈现。
- [x] 链接降级为不可点击文本，图片不创建 img，原始 HTML 不执行。
- [x] 全空结构化结果收敛为一个诚实空态；部分空板块直接隐藏。
- [x] 明确说明 recommendations 不等同于动作提案。

## 验证与交付

- [x] 后端聚焦测试、ruff、mypy、全量 pytest。
- [x] 前端聚焦测试、typecheck、全量 Vitest、build。
- [x] 确定性 mock API + 隔离端口 Playwright 浏览器复验与截图目检。
- [x] 用户授权固定靶场资源边界。
- [x] 单独确认删除固定索引，构造真实缺失与 Seq Scan 场景。
- [x] 只读调查验证公开 recommendations / impact / 来源追溯。
- [x] 通过既有提案链恢复固定索引并独立 Verify。
- [x] 按真实证据更新完善清单、跑通验证与 workpack Review。
- [x] 检查 diff / 敏感字面量 / 暂存范围后等待提交授权。
