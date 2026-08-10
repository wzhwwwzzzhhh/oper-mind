import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TraceCard } from './TraceCard'
import type { PersistedRunEvent, RunEventType } from './run-events'

const RUN_ID = '44444444-4444-4444-8444-444444444444'

function event(
  sequence: number,
  type: RunEventType,
  data: Record<string, unknown> = {},
): PersistedRunEvent {
  return {
    data,
    id: `event-${sequence}`,
    occurred_at: '2026-07-28T08:00:00.000Z',
    run_id: RUN_ID,
    sequence,
    type,
  }
}

describe('TraceCard', () => {
  it('把后端四种工具状态映射到各自的中文标签，不把失败画成成功', () => {
    render(<TraceCard events={[
      event(1, 'tool_invoked', { status: 'ok', summary: '读取慢查询统计。', tool: 'pg_slow_query' }),
      event(2, 'tool_invoked', { status: 'rejected', summary: '越界参数已拦截。', tool: 'pg_explain' }),
      event(3, 'tool_invoked', { status: 'timeout', summary: '采集超时。', tool: 'pg_index_check' }),
      event(4, 'tool_invoked', { status: 'error', summary: '连接失败。', tool: 'redis_slowlog' }),
    ]} />)

    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('已拒绝')).toBeInTheDocument()
    expect(screen.getByText('超时')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    // 非 ok 状态必须带上告警/严重视觉等级，而不是复用成功徽标。
    expect(screen.getByText('已拒绝').className).toContain('trace-badge--warn')
    expect(screen.getByText('超时').className).toContain('trace-badge--warn')
    expect(screen.getByText('失败').className).toContain('trace-badge--danger')
    expect(screen.getByText('成功').className).not.toContain('trace-badge--')
  })

  it('头部如实汇总未通过的工具调用数量', () => {
    render(<TraceCard events={[
      event(1, 'tool_invoked', { status: 'ok', tool: 'pg_slow_query' }),
      event(2, 'tool_invoked', { status: 'error', tool: 'redis_slowlog' }),
    ]} />)

    expect(screen.getByText('1 个工具调用未通过')).toBeInTheDocument()
    expect(screen.getByText('2 个事件 · 2 个工具调用')).toBeInTheDocument()
  })

  it('全部通过时才显示通过结论', () => {
    render(<TraceCard events={[event(1, 'tool_invoked', { status: 'ok', tool: 'pg_slow_query' })]} />)

    expect(screen.getByText('工具调用全部通过')).toBeInTheDocument()
  })

  it('非工具事件展示中文阶段名，不暴露内部事件标识，也不带状态徽标', () => {
    render(<TraceCard events={[
      event(1, 'route_decided'),
      event(2, 'agent_start'),
      event(3, 'agent_done'),
    ]} />)

    expect(screen.getByText('路由决策')).toBeInTheDocument()
    expect(screen.getByText('Agent 启动')).toBeInTheDocument()
    expect(screen.getByText('Agent 完成')).toBeInTheDocument()
    expect(screen.queryByText('route_decided')).not.toBeInTheDocument()
    expect(screen.queryByText('agent_start')).not.toBeInTheDocument()
    expect(screen.queryByText('成功')).not.toBeInTheDocument()
  })

  it('折叠触发器是可聚焦按钮并回报展开状态', () => {
    render(<TraceCard events={[event(1, 'tool_invoked', { status: 'ok', tool: 'pg_slow_query' })]} />)

    const toggle = screen.getByRole('button', { expanded: true })
    expect(toggle).toBeInTheDocument()
  })

  it('没有可展示事件时不谎报状态', () => {
    render(<TraceCard events={[event(1, 'run_queued')]} />)

    expect(screen.getByText('暂无事件')).toBeInTheDocument()
    expect(screen.queryByText('工具调用全部通过')).not.toBeInTheDocument()
  })

  it('运行中时显示进行中而不是已完成', () => {
    render(<TraceCard events={[event(1, 'run_queued')]} running />)

    expect(screen.getByText('进行中')).toBeInTheDocument()
  })
})
