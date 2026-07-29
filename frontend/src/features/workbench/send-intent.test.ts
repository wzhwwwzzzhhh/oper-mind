import { describe, expect, it } from 'vitest'

import {
  clear_session_run_send_intent,
  create_session_run_send_intent,
  load_session_run_send_intent,
  mark_session_run_send_intent_accepted,
  save_session_run_send_intent,
} from './send-intent'

const SESSION_ID = '11111111-1111-4111-8111-111111111111'
const KEY = '22222222-2222-4222-8222-222222222222'
const RUN_ID = '33333333-3333-4333-8333-333333333333'
const INPUT_ID = '44444444-4444-4444-8444-444444444444'

function storage(): Storage {
  return new MapStorage()
}

class MapStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length(): number {
    return this.values.size
  }

  clear(): void {
    this.values.clear()
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }
}

describe('Session Run 发送意图', () => {
  it('发送前创建可跨刷新读取的稳定幂等意图', () => {
    const target = storage()
    const intent = create_session_run_send_intent(SESSION_ID, '请检查网关错误。', {
      created_at: '2026-07-29T01:00:00.000Z',
      idempotency_key: KEY,
    })

    save_session_run_send_intent(target, intent)

    expect(load_session_run_send_intent(target, SESSION_ID)).toEqual(intent)
  })

  it('只在合法 202 对账后写入 Run 和 input Message 标识', () => {
    const initial = create_session_run_send_intent(SESSION_ID, '请检查网关错误。', {
      created_at: '2026-07-29T01:00:00.000Z',
      idempotency_key: KEY,
    })

    expect(mark_session_run_send_intent_accepted(initial, RUN_ID, INPUT_ID)).toMatchObject({
      accepted_run_id: RUN_ID,
      input_message_id: INPUT_ID,
      phase: 'accepted',
    })
    expect(() => mark_session_run_send_intent_accepted(initial, 'invalid', INPUT_ID)).toThrow('受理响应缺少合法')
  })

  it('拒绝跨会话、损坏或含非法标识的 storage 数据', () => {
    const target = storage()
    target.setItem('opermind:p3.6b:send-intent:other', JSON.stringify({ version: 1 }))
    target.setItem('opermind:p3.6b:send-intent:' + SESSION_ID, JSON.stringify({
      accepted_run_id: RUN_ID,
      created_at: '2026-07-29T01:00:00.000Z',
      endpoint: '/api/v1/sessions/{session_id}/runs',
      idempotency_key: 'invalid',
      input_message_id: INPUT_ID,
      phase: 'accepted',
      query: '请检查网关错误。',
      session_id: SESSION_ID,
      version: 1,
    }))

    expect(load_session_run_send_intent(target, SESSION_ID)).toBeUndefined()
  })

  it('对账完成后只清除当前 Session 的意图', () => {
    const target = storage()
    const current = create_session_run_send_intent(SESSION_ID, '当前会话', {
      created_at: '2026-07-29T01:00:00.000Z',
      idempotency_key: KEY,
    })
    const other = create_session_run_send_intent('55555555-5555-4555-8555-555555555555', '其他会话', {
      created_at: '2026-07-29T01:00:00.000Z',
      idempotency_key: '66666666-6666-4666-8666-666666666666',
    })
    save_session_run_send_intent(target, current)
    save_session_run_send_intent(target, other)

    clear_session_run_send_intent(target, SESSION_ID)

    expect(load_session_run_send_intent(target, SESSION_ID)).toBeUndefined()
    expect(load_session_run_send_intent(target, other.session_id)).toEqual(other)
  })
})
