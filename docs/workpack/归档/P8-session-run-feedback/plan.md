# Issue #102 会话回答与运行反馈 · 实施计划

> 状态：已交付；PR #110 于 2026-08-27 squash 合并
> 流程：`docs/开发规范.md` §7.1 轻流程（无 Design 门）

## 边界

- 只修改前端反馈与测试，不新增公开 API、迁移、Connector 或真实外部连接。
- 不改变普通消息/调查意图分流、Run 幂等恢复、SSE、取消或后端状态机。
- 乐观回显必须明确标注为发送中/未确认，不能伪装成已持久化消息。
- queued/running 阶段文案只根据公开 Run 状态表达，不推断隐藏推理或工具事实。

## 切片

- [x] S1：Composer 支持可访问的 loading spinner 与阶段标签。
- [x] S2：发送后立即显示临时用户消息和诚实的提交状态，服务端消息恢复后无重复。
- [x] S3：queued/running 助手气泡展示公开状态对应的阶段文字。
- [x] S4：创建会话时 WelcomePanel/快捷入口/Composer 同步 loading，阻断重复创建。
- [x] S5：补交互测试、typecheck/test/build、浏览器复验与文档收口。

## 预计文件

- `frontend/src/features/shell/Composer.tsx`
- `frontend/src/features/shell/WelcomePanel.tsx`
- `frontend/src/features/workbench/WorkbenchPage.tsx`
- `frontend/src/styles/workbench.css`
- `frontend/src/app/App.test.tsx`
- `docs/完善清单.md`、`docs/跑通验证.md` 与本 workpack
