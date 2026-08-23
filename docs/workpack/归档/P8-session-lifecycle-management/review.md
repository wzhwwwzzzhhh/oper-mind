# P8-session-lifecycle-management · 独立代码 Review

> 审查者：独立子代理 `issue96_design_review`
> 日期：2026-08-23
> 最终结论：PASS（第三轮，无 P0–P2）

## 第一轮：NEEDS_CHANGES

- P1：restore 使用预先生成的时间无条件覆盖 `updated_at`，可能回退并发 Run 已写入的更晚活动时间。
- P1：archived 页面加载的 sessionStorage 遗留发送意图，会在恢复 active 后自动创建 Run/Message。
- P2：Escape/清空搜索未取消 pending debounce，旧 q 可能回写。
- P2：已确认 Design 中的归档分页、完整不确定回读、running Run、关联保留与竞态覆盖不足。
- P3：恢复成功 notice 没有清除时机。

## 修复与新增证据

- restore 的 `updated_at` 改为 CASE/max 单调更新，补“较晚 touch 先提交、较早 restore 后执行”的反向交错测试。
- 记录首次权威 Session 状态；只有首次即 active 的新会话导航允许自动提交预写意图，archived → active
  只恢复录入控件；测试同时预置两类意图并断言恢复后 0 POST。
- 搜索清空统一取消 timer，补 400ms 后旧关键词未回写测试。
- 补 archived cursor 分页、下一页失败重试、无效 2xx/回读 archived/错 id、running Run 取消、
  消息/Run/事件关联集合保持等回归。
- 生命周期 notice 5 秒后自动清除。

## 第二轮：NEEDS_CHANGES

- P2：缺少恢复前在途 archived detail GET 最晚返回后的缓存不覆盖测试，以及 PATCH 5xx、回读 404 分支。
- P2：关联保留只覆盖 Run/Message/Event，未显式包含 session services、proposal 与 action audit event。
- P3：5 秒内连续发布相同 notice 不会重启计时。

上述缺口已补：延迟旧 GET 测试最终断言精确 detail key 为 active；503→GET active 与 network→GET 404
均经过生产错误分类；Repository 完整关系图覆盖 session services、Message、Run、RunEvent、Proposal、
ActionEvent，恢复后逐对象/事件集合相等；notice revision 每次发布递增并重启 timer。

## 第三轮终审：PASS

- 无 P0–P2。
- 已确认 restore CASE/反向交错、archived 恢复零自动 POST、debounce cancel、分页失败重试、running
  Run 取消、完整不确定结果回读、旧 GET 缓存保护、关联/事件集合保持与 notice 重启均正确。

残余风险：尚无真实 PostgreSQL 并发集成测试；notice revision 无独立 fake-timer 测试；延迟旧 GET
由 MSW 模拟而非真实浏览器弱网。以上不阻断本切片，且本工作包按范围禁止连接真实外部资源。
