# 任务 P2-C：前端点亮 tool_invoked 运行事件

## 背景（只读）
后端已完成：每次工具调用会产出一个 `tool_invoked` 运行事件，其 `data` 含三个字段：
- `data.summary: string` —— 已脱敏的简要说明（例："调用 explain_sql 成功"）
- `data.status: string` —— 网关状态，取值 `ok | rejected | timeout | error`
- `data.duration_ms: number` —— 调用耗时（毫秒）

前端 `PersistedRunEvent.data` 就是这些字段的联合（已有 `merge_persisted_run_events` 把
SSE 事件并入 state，不用你改）。但 `WorkbenchPage.tsx` 的**渲染白名单**和
`run-events.ts` 的**事件类型白名单**都还没有 `tool_invoked`，所以浏览器现在看不到它。

**本任务只动前端，不碰后端。**

## 只允许修改/创建这些文件
1. 改 `frontend/src/features/workbench/run-events.ts`
2. 改 `frontend/src/features/workbench/WorkbenchPage.tsx`
3. 新建 `frontend/src/features/workbench/run-events.test.ts`

**严禁触碰其他任何文件**（不改后端、不改其他前端组件、不改 handlers/mock）。

---

## 改动 1：run-events.ts —— 类型白名单加 tool_invoked
`RUN_EVENT_TYPES` 数组里，在 `'reflection'` 之后加 `'tool_invoked'`：
```ts
  'reflection',
  'tool_invoked',
  'run_succeeded',
```

## 改动 2：WorkbenchPage.tsx —— 渲染 tool_invoked
### 2a. 现有渲染白名单
`const visible_events = events.filter((event) => event.type === 'agent_start' || event.type === 'agent_done' || event.type === 'route_decided')`
改成把 `tool_invoked` 也纳入：
```ts
const visible_events = events.filter((event) =>
  event.type === 'agent_start' || event.type === 'agent_done' ||
  event.type === 'route_decided' || event.type === 'tool_invoked')
```

### 2b. 现有渲染块
```tsx
          {visible_events.map((event) => {
            const role = role_label(event.data.role)
            const duration = event_duration_text(event)
            return (
              <div className="investigation-process-event" key={event.id}>
                {role && <Tag color={event.type === 'agent_done' ? 'green' : 'blue'}>{role}</Tag>}
                <Typography.Text>{run_event_summary(event)}</Typography.Text>
                {duration && <Typography.Text type="secondary">{duration}</Typography.Text>}
              </div>
            )
          })}
```
改成（`tool_invoked` 显示专属状态标签；无状态时不显示标签）：
```tsx
          {visible_events.map((event) => {
            const role = role_label(event.data.role)
            const duration = event_duration_text(event)
            const tool_status = event.type === 'tool_invoked' ? event.data.status : undefined
            return (
              <div className="investigation-process-event" key={event.id}>
                {role && <Tag color={event.type === 'agent_done' ? 'green' : 'blue'}>{role}</Tag>}
                {tool_status && <Tag color={tool_status_color(tool_status)}>{tool_status}</Tag>}
                <Typography.Text>{run_event_summary(event)}</Typography.Text>
                {duration && <Typography.Text type="secondary">{duration}</Typography.Text>}
              </div>
            )
          })}
```

### 2c. 新增 helper（放在 `event_duration_text` 旁边，风格一致）
```ts
function tool_status_color(status: string): string {
  if (status === 'ok') return 'green'
  if (status === 'timeout') return 'orange'
  if (status === 'rejected') return 'blue'
  return 'red'   // error
}
```
注意：用 string literal 写返回值即可，不要依赖 theme token（antd Tag 的 `color` 接受内置预设名）。

## 改动 3：新建 run-events.test.ts
参考 `diagnosis-result.test.tsx` 的写法（`@testing-library/react` + `vitest`）。覆盖：

1. **白名单放行**：`read_persisted_run_event` 接受一条
   `{ type: 'tool_invoked', data: { summary: '调用 explain_sql 成功', status: 'ok', duration_ms: 7 } }`
   （其余字段照 `PersistedRunEvent` 构造：`id/run_id/occurred_at` 以 `Z` 结尾的 UTC 串/`sequence` 正整数），
   返回的对象 `type === 'tool_invoked'`。
2. **未知类型仍被拒**：`type: 'agent_started_fake'`（不在白名单）→ 返回 `undefined`。
3. **merge 保留 tool_invoked**：`merge_persisted_run_events` 输入含一条 tool_invoked 时，结果包含它且按 sequence 排序。

### 构造事件所需的原始 JSON 形状（照此）
`read_persisted_run_event(value, expected_run_id)` 的 `value` 是形如
`{ id, run_id, sequence, type, occurred_at, data }` 的 dict（对应前端 `PersistedRunEvent` 直传）。
如果你更想测 SSE 解析，可用 `read_sse_run_event(payload, run_id)`，payload 是
`JSON.stringify({ event: <同上 dict> })`。任选其一，测试要覆盖上面 3 点即可。

## 验收（在 frontend 目录）
- `npm run test` 全绿（会跑 vitest；若现有测试因其他原因失败，告诉我，不要改那些测试）。
- 手动预期：会话调查过程中，工具被调用时时间线会出现一行
  「[ok|timeout|rejected|error] 调用 <工具> 成功 7 ms」样式的记录。
- `git status` 只应出现上面允许的 3 个前端文件。

## 完成后
**不要 commit。** 停下并告诉我"P2-C 完成"，我审 diff + 跑前端测试后自己提交。
