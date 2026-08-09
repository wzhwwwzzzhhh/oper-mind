import type { ReactElement } from 'react'
import { useState } from 'react'

import { Icon, type IconName } from '../shell/Icon'
import type { PersistedRunEvent, RunEventType } from './run-events'
import { run_event_summary } from './run-events'

/** 后端 ToolInvocation.status 的四个取值；没有 "warn"。 */
type ToolStatus = 'ok' | 'rejected' | 'timeout' | 'error'

const TOOL_STATUS_LABELS: Readonly<Record<ToolStatus, string>> = {
  error: '失败',
  ok: '成功',
  rejected: '已拒绝',
  timeout: '超时',
}

/** 状态 → 徽标视觉等级：拒绝/超时是需关注，失败是严重。 */
const TOOL_STATUS_CLASSES: Readonly<Record<ToolStatus, string>> = {
  error: ' trace-badge--danger',
  ok: '',
  rejected: ' trace-badge--warn',
  timeout: ' trace-badge--warn',
}

/** 事件类型 → 中文阶段名；不把 agent_start 这种内部标识直接给用户看。 */
const EVENT_LABELS: Readonly<Partial<Record<RunEventType, string>>> = {
  agent_done: 'Agent 完成',
  agent_start: 'Agent 启动',
  route_decided: '路由决策',
  tool_invoked: '工具调用',
}

/** 工具角色 → 图标；图标本身就是允许展示的"工具类别"。 */
const ROLE_ICONS: Readonly<Record<string, IconName>> = {
  db: 'database',
  log: 'book',
  server: 'stack',
}

function read_tool_status(event: PersistedRunEvent): ToolStatus | undefined {
  if (event.type !== 'tool_invoked') return undefined
  const status = event.data.status
  return status === 'ok' || status === 'rejected' || status === 'timeout' || status === 'error'
    ? status
    : undefined
}

function event_duration_text(event: PersistedRunEvent): string | undefined {
  const duration_ms = event.data.duration_ms
  if (typeof duration_ms !== 'number' || !Number.isSafeInteger(duration_ms) || duration_ms < 0) return undefined
  return `${duration_ms} ms`
}

function event_icon(event: PersistedRunEvent): IconName {
  if (event.type === 'agent_done') return 'check'
  if (event.type === 'agent_start') return 'spark'
  if (event.type === 'route_decided') return 'stack'
  const role = event.data.role
  return typeof role === 'string' && role in ROLE_ICONS ? ROLE_ICONS[role] : 'pulse'
}

/** 行标题：工具事件用真实工具名，其余用中文阶段名。 */
function event_title(event: PersistedRunEvent): string {
  if (event.type === 'tool_invoked' && typeof event.data.tool === 'string' && event.data.tool) {
    return event.data.tool
  }
  return EVENT_LABELS[event.type] ?? event.type
}

/** 只有 tool_invoked 携带 data；其余事件的 summary 是同一句兜底文案，不重复渲染。 */
function event_detail(event: PersistedRunEvent): string | undefined {
  return event.type === 'tool_invoked' ? run_event_summary(event) : undefined
}

function event_time_text(occurred_at: string): string {
  const parsed = Date.parse(occurred_at)
  if (Number.isNaN(parsed)) return ''
  return new Date(parsed).toLocaleTimeString('zh-CN', { hour: '2-digit', hour12: false, minute: '2-digit', second: '2-digit' })
}

interface TraceCardProps {
  events: PersistedRunEvent[]
  running?: boolean
}

/** 调查过程折叠卡：按事件时间线展示阶段、工具类别、状态与耗时，不展示 CoT 或原始输出。 */
export function TraceCard({ events, running }: TraceCardProps): ReactElement {
  const [collapsed, set_collapsed] = useState(false)
  const visible = events.filter((event) =>
    event.type === 'agent_start' || event.type === 'agent_done' ||
    event.type === 'route_decided' || event.type === 'tool_invoked')
  const tool_events = visible.filter((event) => event.type === 'tool_invoked')
  const failed_count = tool_events.filter((event) => {
    const status = read_tool_status(event)
    return status !== undefined && status !== 'ok'
  }).length

  const state_text = running
    ? '进行中'
    : failed_count > 0
      ? `${failed_count} 个工具调用未通过`
      : tool_events.length > 0
        ? '工具调用全部通过'
        : '已完成'

  const head = (
    <button
      aria-expanded={!collapsed}
      className="trace-head"
      onClick={() => set_collapsed((value) => !value)}
      type="button"
    >
      <span className="trace-head-left">
        <span className="trace-title">
          <i className={`pulse${running ? ' running' : ''}${failed_count > 0 ? ' attention' : ''}`} />
          调查过程
        </span>
        <span className="trace-meta">
          {visible.length === 0
            ? running ? '进行中' : '暂无事件'
            : `${visible.length} 个事件${tool_events.length > 0 ? ` · ${tool_events.length} 个工具调用` : ''}`}
        </span>
        {visible.length > 0 && (
          <span className={`trace-state${failed_count > 0 ? ' trace-state--attention' : ''}`}>{state_text}</span>
        )}
      </span>
      <Icon className="trace-toggle" name="chevron-down" size={14} />
    </button>
  )

  if (visible.length === 0) {
    return <div className="trace-card collapsed">{head}</div>
  }

  return (
    <div className={`trace-card${collapsed ? ' collapsed' : ''}`}>
      {head}
      <div className="trace-body">
        {visible.map((event) => {
          const duration = event_duration_text(event)
          const detail = event_detail(event)
          const status = read_tool_status(event)
          return (
            <div className="trace-row" key={event.id}>
              <span className="trace-icon">
                <Icon name={event_icon(event)} size={11} />
              </span>
              <div className="trace-row__body">
                <strong>{event_title(event)}</strong>
                <span className="trace-row__desc">
                  {detail ?? event_time_text(event.occurred_at)}
                  {duration ? ` · ${duration}` : ''}
                </span>
              </div>
              {status !== undefined && (
                <span className={`trace-badge${TOOL_STATUS_CLASSES[status]}`}>{TOOL_STATUS_LABELS[status]}</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
