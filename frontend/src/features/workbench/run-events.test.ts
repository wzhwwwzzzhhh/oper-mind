import { describe, expect, it } from 'vitest'

import {
  merge_persisted_run_events,
  read_sse_run_event,
} from './run-events'

const run_id = '33333333-3333-4333-8333-333333333333'
const event_one = {
  id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  run_id,
  sequence: 1,
  type: 'run_queued',
  occurred_at: '2026-07-27T01:00:30.000Z',
  data: { summary: '已入队。' },
}
const event_two = {
  id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  run_id,
  sequence: 2,
  type: 'run_started',
  occurred_at: '2026-07-27T01:00:31.000Z',
  data: { summary: '已开始。' },
}

describe('RunEvent 合并器', () => {
  it('按 sequence 去重并升序合并 REST 与 SSE 事件', () => {
    expect(merge_persisted_run_events(run_id, [], [event_two, event_one, event_two])).toEqual([
      event_one,
      event_two,
    ])
  })

  it('拒绝跨 Run、非 UTC Z 或未知事件类型', () => {
    expect(merge_persisted_run_events(run_id, [], [
      { ...event_one, run_id: 'other-run' },
      { ...event_one, occurred_at: '2026-07-27T01:00:30+08:00' },
      { ...event_one, type: 'not-supported' },
    ])).toEqual([])
  })

  it('仅从 run_event envelope 读取合法 SSE payload', () => {
    expect(read_sse_run_event(JSON.stringify({ event: event_two }), run_id)).toEqual(event_two)
    expect(read_sse_run_event('{bad json', run_id)).toBeUndefined()
  })
})
