# R1 / P3.5 产品重定位 HANDOFF

> 日期：2026-07-29　|　状态：产品重定位与 P3.5 Design 已完成，等待用户审阅；无实现授权。
>
> 基线提交：`37317e7 feat: 完成P3.4c结构化结果Mock契约验收`

## 已完成

- 用户确认 OperMind V1 面向个人、轻量、日常使用；一个用户拥有多个长期、多轮会话；
- 用户确认主动提问、真实监控发现和已接入告警未来都应进入同一会话主线；
- 用户确认 Agent 默认显示概要，展开后查看细节；处理目标必须经明确授权、权限、审计与验证；
- `治理-个人AI运维助手产品重定位/` 成为产品体验设计入口；旧 P0/P3 工作台布局、导航和旧下一步只作历史/技术证据，已发布 API/SSE 契约与测试事实继续继承；
- P3.5a 定义个人会话、调查摘要、答复、错误/空/归档/SSE 的体验状态；
- P3.5b 定义以 P2 调查型 Run 投影为 Conversation Turn、刷新恢复、幂等和 cursor/普通聊天的 API 差距；
- P3.5c 拆分后续 P3.6a/P3.6b/P3.6c 的实现与验收边界；
- A-Plan、B-Plan、开发规范、AGENTS/CLAUDE 已同步产品方向和当前下一步。

## 当前唯一下一步

**用户审阅 `design.md`、`step1-个人会话主体验设计.md`、`step2-会话契约与恢复设计.md`、`step3-后续最小切片与验收设计.md` 与 `review.md`。若认可，先授权提交本次文档；提交后仍需单独授权才可开始 P3.6a「会话壳与只读 Turn 投影」实现。**

## 严格边界

- 不改 `frontend/`、`report/`、后端 `/api/v1`、Application Service、Repository、ORM、Alembic 或旧 `/diagnose*`；
- 不接入真实 8000、数据库、数据源、认证、在线迁移或执行器；
- 不创建假监控大盘、Alert、Incident、Approval、Action、自动修复或多用户协作数据；
- P3.4c 页面可视化验收仍待以独立 8100 Mock 和非排除端口补做；不能改连 8000；
- 隔离文件 `docs/00-项目方案说明书.md`、`backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py` 不得修改、暂存、提交或 reset；禁止 `git add .`。

## 如用户授权提交

候选暂存文件：

```text
AGENTS.md
CLAUDE.md
docs/开发规范.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/治理-产品定位复核/research.md
docs/开发/治理-产品定位复核/review.md
docs/开发/治理-产品定位复核/HANDOFF.md
docs/开发/治理-个人AI运维助手产品重定位/README.md
docs/开发/治理-个人AI运维助手产品重定位/design.md
docs/开发/治理-个人AI运维助手产品重定位/step1-个人会话主体验设计.md
docs/开发/治理-个人AI运维助手产品重定位/step2-会话契约与恢复设计.md
docs/开发/治理-个人AI运维助手产品重定位/step3-后续最小切片与验收设计.md
docs/开发/治理-个人AI运维助手产品重定位/review.md
docs/开发/治理-个人AI运维助手产品重定位/HANDOFF.md
```

提交前逐项 `git add`、`git diff --cached --check`、核对 `AGENTS.md` 与 `CLAUDE.md` 的哈希一致。建议提交信息：

```text
docs: 完成个人AI运维助手产品重定位与P3.5设计
```
