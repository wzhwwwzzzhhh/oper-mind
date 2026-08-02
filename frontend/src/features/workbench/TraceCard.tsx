import type { ReactElement } from 'react'
import { useState } from 'react'

import type { PersistedRunEvent } from './run-events'
import { run_event_summary } from './run-events'

function event_duration_text(event: PersistedRunEvent): string | undefined {
  const duration_ms = event.data.duration_ms
  if (typeof duration_ms !== 'number' || !Number.isSafeInteger(duration_ms) || duration_ms < 0) return undefined
  return `${duration_ms} ms`
}

function trace_icon(event: PersistedRunEvent): string {
  if (event.type === 'tool_invoked') return '⚙'
  if (event.type === 'agent_done') return '✓'
  if (event.type === 'agent_start') return '↗'
  return '·'
}

function trace_badge_class(status: string | undefined): string {
  if (status === 'ok') return ''
  if (status === 'warn') return 'warn'
  return ''
}

function trace_state_text(status: string | undefined): string {
  if (status === 'ok') return 'ok'
  if (status === 'running') return 'running'
  return status ?? 'ok'
}

interface TraceCardProps {
  events: PersistedRunEvent[]
  running?: boolean
}

/** 调查过程折叠卡 —— 按设计稿的平面审计时间线渲染工具调用事件。 */
export function TraceCard({ events, running }: TraceCardProps): ReactElement {
  const [collapsed, set_collapsed] = useState(false)
  const visible = events.filter((event) =>
    event.type === 'agent_start' || event.type === 'agent_done' ||
    event.type === 'route_decided' || event.type === 'tool_invoked')
  const tool_count = events.filter((event) => event.type === 'tool_invoked').length
  const all_ok = visible.length > 0 && visible.every((event) => event.data.status === 'ok' || event.type !== 'tool_invoked')

  if (visible.length === 0) {
    return (
      <div className="trace-card">
        <div className="trace-head" onClick={() => set_collapsed((value) => !value)}>
          <span className="trace-head-left">
            <span className="trace-title">
              <i className="pulse" />
              调查过程
            </span>
            <span className="trace-meta">{running ? '进行中' : '暂无事件'}</span>
          </span>
          <span className="trace-toggle">⌄</span>
        </div>
      </div>
    )
  }

  return (
    <div className={`trace-card${collapsed ? ' collapsed' : ''}`}>
      <div className="trace-head" onClick={() => set_collapsed((value) => !value)}>
        <span className="trace-head-left">
          <span className="trace-title">
            <i className="pulse" />
            调查过程
          </span>
          <span className="trace-meta">{visible.length} 个事件{tool_count > 0 ? ` · ${tool_count} 个工具调用` : ''}</span>
          <span className="trace-state">{running ? 'running' : all_ok ? '已验证' : 'completed'}</span>
        </span>
        <span className="trace-toggle">⌄</span>
      </div>
      <div className="trace-body">
        {visible.map((event) => {
          const duration = event_duration_text(event)
          const tool_status = event.type === 'tool_invoked' ? event.data.status : undefined
          const badge = trace_badge_class(typeof tool_status === 'string' ? tool_status : undefined)
          return (
            <div className="trace-row" key={event.id}>
              <span className="trace-icon">{trace_icon(event)}</span>
              <div>
                <strong>{event.type === 'tool_invoked' ? (typeof event.data.tool === 'string' ? event.data.tool : '工具调用') : event.type}</strong>
                <span>
                  {run_event_summary(event)}
                  {duration ? ` · ${duration}` : ''}
                </span>
              </div>
              <span className={`trace-badge${badge}`}>{trace_state_text(typeof tool_status === 'string' ? tool_status : 'ok')}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
