import { describe, expect, it } from 'vitest'

import {
  merge_persisted_run_events,
  read_persisted_run_event,
} from './run-events'

const run_id = '33333333-3333-4333-8333-333333333333'
const base_event = {
  id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  run_id,
  sequence: 2,
  type: 'tool_invoked',
  occurred_at: '2026-08-02T00:00:07.000Z',
  data: { summary: '调用 explain_sql 成功', status: 'ok', duration_ms: 7 },
}

const earlier_event = {
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  run_id,
  sequence: 1,
  type: 'route_decided',
  occurred_at: '2026-08-02T00:00:01.000Z',
  data: { summary: '路由完成' },
}

describe('tool_invoked 运行事件', () => {
  it('白名单接受 tool_invoked 事件', () => {
    const event = read_persisted_run_event(base_event, run_id)

    expect(event?.type).toBe('tool_invoked')
  })

  it('仍拒绝未知运行事件类型', () => {
    const event = read_persisted_run_event({ ...base_event, type: 'agent_started_fake' }, run_id)

    expect(event).toBeUndefined()
  })

  it('合并时保留 tool_invoked 并按 sequence 升序排列', () => {
    const events = merge_persisted_run_events(run_id, [], [base_event, earlier_event])

    expect(events).toHaveLength(2)
    expect(events[0]?.sequence).toBe(1)
    expect(events[1]?.type).toBe('tool_invoked')
    expect(events[1]?.sequence).toBe(2)
  })
})
