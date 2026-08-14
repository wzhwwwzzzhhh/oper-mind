import { describe, expect, it } from 'vitest'

import { project_conversation_turns } from './conversation-turns'

const SESSION_ID = '11111111-1111-4111-8111-111111111111'
const INPUT_ID = '22222222-2222-4222-8222-222222222222'
const RUN_ID = '33333333-3333-4333-8333-333333333333'

function user_message() {
  return {
    id: INPUT_ID,
    session_id: SESSION_ID,
    run_id: null,
    role: 'user',
    content: '请检查网关错误。',
    created_at: '2026-07-29T01:00:00.000Z',
  }
}

function run() {
  return {
    id: RUN_ID,
    session_id: SESSION_ID,
    trace_id: '44444444-4444-4444-8444-444444444444',
    input_message_id: INPUT_ID,
    status: 'succeeded',
    result: { id: '55555555-5555-4555-8555-555555555555' },
    error: null,
  }
}

describe('project_conversation_turns', () => {
  it('按用户消息、调查和成功助手消息投影一个只读 Turn', () => {
    const projection = project_conversation_turns([
      user_message(),
      {
        id: '66666666-6666-4666-8666-666666666666',
        session_id: SESSION_ID,
        run_id: RUN_ID,
        role: 'assistant',
        content: '已确认网关连接池异常。',
        created_at: '2026-07-29T01:00:03.000Z',
      },
    ], [run()], SESSION_ID)

    expect(projection.issues).toEqual([])
    expect(projection.timeline).toHaveLength(1)
    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: {
        input: { content: '请检查网关错误。' },
        investigations: [{ investigation: { id: RUN_ID, status: 'succeeded' }, output: { content: '已确认网关连接池异常。' } }],
      },
    })
  })

  it('关联不一致时只报告协议问题，不选择任意调查或助手消息', () => {
    const projection = project_conversation_turns([
      user_message(),
      {
        id: '77777777-7777-4777-8777-777777777777',
        session_id: SESSION_ID,
        run_id: RUN_ID,
        role: 'assistant',
        content: '不应被投影。',
        created_at: '2026-07-29T01:00:03.000Z',
      },
    ], [
      run(),
      { ...run(), id: '88888888-8888-4888-8888-888888888888' },
    ], SESSION_ID)

    expect(projection.issues).toContain('RUN_INPUT_MESSAGE_DUPLICATED：一条用户消息关联了多个调查，当前只读视图不会自行选择。')
    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: { input: { id: INPUT_ID }, investigations: [{ investigation: { id: RUN_ID } }] },
    })
  })

  it('合并时间相邻的相同问题，并保留每个服务的独立调查', () => {
    const second_input = '99999999-9999-4999-8999-999999999991'
    const second_run = '99999999-9999-4999-8999-999999999992'
    const projection = project_conversation_turns([
      user_message(),
      { ...user_message(), id: second_input, created_at: '2026-07-29T01:00:02.000Z' },
    ], [
      { ...run(), service_id: 'postgres-production' },
      { ...run(), id: second_run, input_message_id: second_input, service_id: 'postgres-staging' },
    ], SESSION_ID)
    expect(projection.issues).toEqual([])
    expect(projection.timeline).toHaveLength(1)
    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: { investigations: [{ investigation: { service_id: 'postgres-production' } }, { investigation: { service_id: 'postgres-staging' } }] },
    })
  })

  it('不合并缺少服务或重复同一服务的相邻问题', () => {
    const second_input = '99999999-9999-4999-8999-999999999993'
    const second_run = '99999999-9999-4999-8999-999999999994'
    const inputs = [user_message(), { ...user_message(), id: second_input, created_at: '2026-07-29T01:00:02.000Z' }]

    const service_less = project_conversation_turns(inputs, [run(), { ...run(), id: second_run, input_message_id: second_input }], SESSION_ID)
    const repeated_service = project_conversation_turns(inputs, [
      { ...run(), service_id: 'redis-production' },
      { ...run(), id: second_run, input_message_id: second_input, service_id: 'redis-production' },
    ], SESSION_ID)

    expect(service_less.timeline).toHaveLength(2)
    expect(repeated_service.timeline).toHaveLength(2)
  })

  it('无 Run 关联的 assistant 消息作为普通回复配对到前一条用户消息', () => {
    const projection = project_conversation_turns([
      user_message(),
      {
        id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02',
        session_id: SESSION_ID,
        run_id: null,
        role: 'assistant',
        content: '这是普通对话回复：本次未启动调查。',
        created_at: '2026-07-29T01:00:00.001Z',
      },
    ], [], SESSION_ID)

    expect(projection.issues).toEqual([])
    expect(projection.timeline).toHaveLength(1)
    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: {
        input: { content: '请检查网关错误。' },
        investigations: [],
        plain_reply: { content: '这是普通对话回复：本次未启动调查。' },
      },
    })
  })

  it('普通回复不与调查输出混淆，多条普通消息按顺序配对', () => {
    const second_input = '99999999-9999-4999-8999-999999999995'
    const projection = project_conversation_turns([
      user_message(),
      { ...user_message(), id: second_input, content: '谢谢', created_at: '2026-07-29T01:00:02.000Z' },
      {
        id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa03',
        session_id: SESSION_ID,
        run_id: null,
        role: 'assistant',
        content: '回复一。',
        created_at: '2026-07-29T01:00:02.001Z',
      },
      {
        id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa04',
        session_id: SESSION_ID,
        run_id: null,
        role: 'assistant',
        content: '回复二。',
        created_at: '2026-07-29T01:00:03.001Z',
      },
    ], [run()], SESSION_ID)

    expect(projection.issues).toEqual([])
    expect(projection.timeline).toHaveLength(3)
    expect(projection.timeline[0]).toMatchObject({ kind: 'turn', turn: { input: { content: '请检查网关错误。' }, investigations: [{ investigation: { id: RUN_ID } }] } })
    expect(projection.timeline[1]).toMatchObject({
      kind: 'turn',
      turn: {
        input: { content: '谢谢' },
        investigations: [],
        plain_reply: { content: '回复一。' },
      },
    })
    // 多余的无前驱普通回复作为独立回复展示，不静默丢弃。
    expect(projection.timeline[2]).toMatchObject({ kind: 'plain_reply', message: { content: '回复二。' } })
  })

  it('无前驱的普通回复作为独立回复展示而不静默丢弃', () => {
    const projection = project_conversation_turns([
      {
        id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa05',
        session_id: SESSION_ID,
        run_id: null,
        role: 'assistant',
        content: '分页边界孤儿回复。',
        created_at: '2026-07-29T01:10:00.000Z',
      },
    ], [], SESSION_ID)

    expect(projection.issues).toEqual([])
    expect(projection.timeline).toHaveLength(1)
    expect(projection.timeline[0]).toMatchObject({
      kind: 'plain_reply',
      message: { content: '分页边界孤儿回复。' },
    })
  })

  it('投影重跑来源并推导原 Run 的最新重跑', () => {
    const rerun_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa11'
    const rerun_message = {
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
      session_id: SESSION_ID,
      run_id: null,
      role: 'user',
      content: '请检查网关错误。',
      created_at: '2026-07-29T01:10:00.000Z',
    }
    const later_rerun_message = {
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
      session_id: SESSION_ID,
      run_id: null,
      role: 'user',
      content: '请检查网关错误。',
      created_at: '2026-07-29T01:11:00.000Z',
    }
    const original_run = { ...run(), rerun_of_run_id: null }
    const first_rerun = { ...run(), id: rerun_id, input_message_id: rerun_message.id, rerun_of_run_id: RUN_ID }
    const second_rerun = { ...run(), id: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1', input_message_id: later_rerun_message.id, rerun_of_run_id: RUN_ID }

    // runs 按创建时间倒序：最新重跑在前。
    const projection = project_conversation_turns(
      [later_rerun_message, rerun_message, user_message()],
      [second_rerun, first_rerun, original_run],
      SESSION_ID,
    )

    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: { investigations: [{ investigation: { id: second_rerun.id, rerun_of_run_id: RUN_ID } }] },
    })
    // 倒序先到先得：最新重跑（second_rerun）胜出，原 Run 的映射指向它。
    expect(projection.rerun_by_latest.get(RUN_ID)).toBe(second_rerun.id)
    expect(projection.rerun_by_latest.has(rerun_id)).toBe(false)
    expect(projection.issues).toEqual([])
  })

  it('重跑来源字段缺失时按普通调查投影且映射为空', () => {
    const projection = project_conversation_turns([user_message()], [run()], SESSION_ID)

    expect(projection.issues).toEqual([])
    expect(projection.timeline[0]).toMatchObject({
      kind: 'turn',
      turn: { investigations: [{ investigation: { id: RUN_ID, rerun_of_run_id: undefined } }] },
    })
    expect(projection.rerun_by_latest.size).toBe(0)
  })
})
