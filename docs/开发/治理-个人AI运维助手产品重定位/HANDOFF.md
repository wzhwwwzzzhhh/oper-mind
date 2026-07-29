# R1 / P3.6b.1 交接（已关闭）

> 更新日期：2026-07-29　|　分支：`feat/p3-workbench`
> 实现基线：`eb664dd feat: 完成P3.6a会话壳与只读Turn投影`
> 当前状态：P3.6b.1「发送意图与 202 对账」已完成 Code/Test/Review 与用户边界验收，**由本提交收口**。

## 已完成

- P3.6b Design 已完成，P3.6b.1 获用户授权后仅实现了 active Session 的调查输入、sessionStorage 稳定意图、POST Run、202 后 Run / Message authoritative 对账；
- 没有 optimistic Message；成功 Turn 必须经 `run.input_message_id` 与持久化 user Message 对账形成；
- 网络未知重试使用同一 key / query；409 幂等冲突必须由用户明确丢弃意图；422 可编辑后新建意图；归档会话不发送；
- 对账先完整读取 Runs 再读取 Messages，防止并行读取的不一致快照；
- 已通过 typecheck、40 个 Vitest、build、11 个 Mock pytest；未修改 Mock / 后端 / report。

## 恢复与边界

1. 先读 `_A-Plan-总览.md`、`docs/开发/README.md`、本目录 `step5-*`、`step6-*`、`review.md`，再核对 `git status --short` 和未提交 diff；
2. P3.6b.1 当前候选中包括此前未提交的 P3.6b Design / 计划文档；不要遗漏新 `step5-*`，也不要将隔离文件或治理 `design.md` 元数据状态混入；
3. 当前不能进入 SSE、events、Last-Event-ID、多 Run 注册表、Fetch stream、Mock API 行为扩展、后端或真实资源；这些分别属于 P3.6b.2 / P3.6b.3；
4. 不得触碰 `docs/00-项目方案说明书.md`、`backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py`、治理 `design.md`；禁止 `git add .`。

## 用户验收

使用独立 8100 Mock + 非 `5141–5240` 的 Vite 端口，只确认：

- active 会话出现调查输入，archived 会话没有；
- 页面明确说明是调查而非普通聊天；
- 输入为空不发送；
- 独立 Mock 成功受理后如果没有动态 user Message，页面显示“正在恢复已保存的调查”或安全恢复错误，**不能假装已成功显示用户 Turn**；
- 不能看到 SSE、Trace、监控、告警、Action 或处理功能。

不要把当前 Mock 的动态 Message 缺口当作后端失败，也不能通过改连真实 8000 绕过。

## 本提交精确文件清单

```text
AGENTS.md
CLAUDE.md
docs/README.md
docs/开发/README.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/治理-个人AI运维助手产品重定位/README.md
docs/开发/治理-个人AI运维助手产品重定位/step5-P3.6b调查型发送幂等与SSE恢复设计.md
docs/开发/治理-个人AI运维助手产品重定位/step6-P3.6b1发送意图与202对账.md
docs/开发/治理-个人AI运维助手产品重定位/review.md
docs/开发/治理-个人AI运维助手产品重定位/HANDOFF.md
frontend/src/app/App.tsx
frontend/src/app/App.test.tsx
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/features/workbench/send-intent.ts
frontend/src/features/workbench/send-intent.test.ts
frontend/src/styles/global.css
```

## 唯一下一步

**本提交已收口 P3.6b.1。** 后续需要用户确认是否先进行 P3.6b.3 Mock 合同，还是先进行 P3.6b.2 Fetch SSE 的独立技术验证与实现；不得自动跨入其中任一步。
