import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from './App'
import { api_v1_contract_fixtures } from '../test/handlers'
import { TestEventSource } from '../test/event-source'
import { server } from '../test/server'

function open_path(path: string): void {
  window.history.replaceState({}, '', path)
}

let request_paths: string[] = []

server.events.on('request:start', ({ request }) => {
  const path = new URL(request.url).pathname
  if (path.startsWith('/api/v1/')) request_paths.push(path)
})

function run_response_handler(run: Record<string, unknown>) {
  return http.get(/\/api\/v1\/runs\/[^/]+$/, ({ request }) => {
    const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
    return HttpResponse.json(
      { run, meta: { request_id, trace_id: api_v1_contract_fixtures.trace_id } },
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Request-Id': request_id,
          'X-Trace-Id': api_v1_contract_fixtures.trace_id,
        },
      },
    )
  })
}

function complete_result(run_id: string): Record<string, unknown> {
  return {
    agent_summary: [],
    confidence: 0.92,
    created_at: '2026-07-28T08:00:00.000Z',
    evidence: [],
    id: '77777777-7777-4777-8777-777777777777',
    impact: null,
    recommendations: [],
    report_markdown: null,
    requires_approval: false,
    risks: [],
    root_causes: [],
    run_id,
    severity: 'high',
    summary: 'Nginx 上游连接池已耗尽。',
  }
}

function run_resource({
  error = null,
  result = null,
  session_id = api_v1_contract_fixtures.session_id,
  status,
}: {
  error?: unknown
  result?: unknown
  session_id?: string
  status: 'cancelled' | 'failed' | 'queued' | 'running' | 'succeeded'
}): Record<string, unknown> {
  return {
    created_at: '2026-07-28T07:59:00.000Z',
    error,
    finished_at: status === 'queued' || status === 'running' ? null : '2026-07-28T08:00:00.000Z',
    id: api_v1_contract_fixtures.run_id,
    input_message_id: '66666666-6666-4666-8666-666666666666',
    result,
    session_id,
    started_at: status === 'queued' ? null : '2026-07-28T07:59:01.000Z',
    status,
    trace_id: api_v1_contract_fixtures.trace_id,
  }
}

describe('App', () => {
  beforeEach(() => {
    request_paths = []
    open_path('/workbench')
  })

  it('从 v1 active Session 列表恢复工作台入口', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '诊断工作台' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(screen.getByText('环境与数据源：待 P4')).toBeInTheDocument()
  })

  it('按 Session、Runs、Message、Run 的顺序恢复 Run 深链', async () => {
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(await screen.findByText('请检查 Nginx 5xx。')).toBeInTheDocument()
    expect(await screen.findByText('RESULT_PROTOCOL_ERROR')).toBeInTheDocument()
    await waitFor(() =>
      expect(request_paths).toEqual([
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
        `/api/v1/runs/${api_v1_contract_fixtures.run_id}`,
        `/api/v1/runs/${api_v1_contract_fixtures.run_id}/events`,
      ]),
    )
    expect(
      screen.getByText('Run 受理与实时事件待 P3.3，结构化结果视觉待 P3.4；完整 Agent Trace 仍只在研发界面可用。'),
    ).toBeInTheDocument()
  })

  it('以服务端返回的 Run 深链受理诊断，并发送 UUID 幂等键', async () => {
    const received_requests: Array<{ idempotency_key: string | null; query: unknown }> = []
    server.use(
      http.post(/\/api\/v1\/sessions\/[^/]+\/runs$/, async ({ request }) => {
        received_requests.push({
          idempotency_key: request.headers.get('Idempotency-Key'),
          query: (await request.json() as { query?: unknown }).query,
        })
        return HttpResponse.json(
          {
            run: {
              id: api_v1_contract_fixtures.accepted_run_id,
              session_id: api_v1_contract_fixtures.session_id,
              trace_id: api_v1_contract_fixtures.trace_id,
              status: 'queued',
              result: null,
              error: null,
            },
            meta: { request_id: request.headers.get('X-Request-Id'), trace_id: api_v1_contract_fixtures.trace_id },
          },
          {
            status: 202,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': request.headers.get('X-Request-Id') ?? '',
              'X-Trace-Id': api_v1_contract_fixtures.trace_id,
            },
          },
        )
      }),
    )
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '诊断问题' })
    fireEvent.change(input, { target: { value: '请检查 Nginx 5xx。' } })
    fireEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    await waitFor(() => expect(received_requests).toHaveLength(1))
    expect(received_requests[0]?.query).toBe('请检查 Nginx 5xx。')
    expect(received_requests[0]?.idempotency_key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    )
    await waitFor(() =>
      expect(window.location.pathname).toBe(
        `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.accepted_run_id}`,
      ),
    )
  })

  it('网络结果未知时重试复用同一幂等键和问题', async () => {
    const received_requests: Array<{ idempotency_key: string | null; query: unknown; request_id: string | null }> = []
    let request_count = 0
    server.use(
      http.post(/\/api\/v1\/sessions\/[^/]+\/runs$/, async ({ request }) => {
        request_count += 1
        received_requests.push({
          idempotency_key: request.headers.get('Idempotency-Key'),
          query: (await request.json() as { query?: unknown }).query,
          request_id: request.headers.get('X-Request-Id'),
        })
        if (request_count === 1) return HttpResponse.error()
        return HttpResponse.json(
          {
            run: {
              id: api_v1_contract_fixtures.accepted_run_id,
              session_id: api_v1_contract_fixtures.session_id,
              trace_id: api_v1_contract_fixtures.trace_id,
              status: 'queued',
              result: null,
              error: null,
            },
            meta: { request_id: request.headers.get('X-Request-Id'), trace_id: api_v1_contract_fixtures.trace_id },
          },
          {
            status: 202,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': request.headers.get('X-Request-Id') ?? '',
              'X-Trace-Id': api_v1_contract_fixtures.trace_id,
            },
          },
        )
      }),
    )
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '诊断问题' })
    fireEvent.change(input, { target: { value: '请检查 Nginx 5xx。' } })
    fireEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByRole('button', { name: '按原请求重试' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '按原请求重试' }))

    await waitFor(() => expect(received_requests).toHaveLength(2))
    expect(received_requests.map((item) => item.query)).toEqual(['请检查 Nginx 5xx。', '请检查 Nginx 5xx。'])
    expect(received_requests[0]?.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i)
    expect(received_requests[1]?.idempotency_key).toBe(received_requests[0]?.idempotency_key)
    expect(received_requests[1]?.request_id).not.toBe(received_requests[0]?.request_id)
  })

  it('受理冲突时显示安全错误且不自动更换幂等键重发', async () => {
    let request_count = 0
    server.use(
      http.post(/\/api\/v1\/sessions\/[^/]+\/runs$/, ({ request }) => {
        request_count += 1
        return HttpResponse.json(
          {
            error: { code: 'IDEMPOTENCY_KEY_REUSED', message: '幂等键已用于不同问题', details: null },
            meta: { request_id: request.headers.get('X-Request-Id'), trace_id: api_v1_contract_fixtures.trace_id },
          },
          {
            status: 409,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': request.headers.get('X-Request-Id') ?? '',
              'X-Trace-Id': api_v1_contract_fixtures.trace_id,
            },
          },
        )
      }),
    )
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '诊断问题' })
    fireEvent.change(input, { target: { value: '请检查 Nginx 5xx。' } })
    fireEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByText('IDEMPOTENCY_KEY_REUSED：幂等键已用于不同问题')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '按原请求重试' })).not.toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(request_count).toBe(1)
  })

  it('归档会话禁用新的诊断受理', async () => {
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.archived_session_id}`)
    render(<App />)

    expect(await screen.findByText('会话已归档，仅可读取历史内容，不能受理新的诊断运行。')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '诊断问题' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始诊断' })).not.toBeInTheDocument()
  })

  it('对非终态 Run 用无 after_sequence 的 EventSource 去重事件，并在终态后重读持久化资源', async () => {
    let terminal = false
    server.use(
      http.get(/\/api\/v1\/runs\/99999999-9999-4999-8999-999999999999$/, ({ request }) =>
        HttpResponse.json(
          {
            run: {
              id: api_v1_contract_fixtures.accepted_run_id,
              session_id: api_v1_contract_fixtures.session_id,
              trace_id: api_v1_contract_fixtures.trace_id,
              status: terminal ? 'succeeded' : 'running',
              result: terminal ? { id: 'result-id' } : null,
              error: null,
            },
            meta: { request_id: request.headers.get('X-Request-Id'), trace_id: api_v1_contract_fixtures.trace_id },
          },
          {
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': request.headers.get('X-Request-Id') ?? '',
              'X-Trace-Id': api_v1_contract_fixtures.trace_id,
            },
          },
        ),
      ),
      http.get(/\/api\/v1\/runs\/99999999-9999-4999-8999-999999999999\/events$/, ({ request }) =>
        HttpResponse.json(
          {
            items: terminal
              ? [{
                  id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
                  run_id: api_v1_contract_fixtures.accepted_run_id,
                  sequence: 2,
                  type: 'run_succeeded',
                  occurred_at: '2026-07-27T01:05:02.000Z',
                  data: { summary: '诊断已完成。' },
                }]
              : [{
                  id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                  run_id: api_v1_contract_fixtures.accepted_run_id,
                  sequence: 1,
                  type: 'run_started',
                  occurred_at: '2026-07-27T01:05:01.000Z',
                  data: { summary: '诊断正在执行。' },
                }],
            page: { next_cursor: null, has_more: false },
            meta: { request_id: request.headers.get('X-Request-Id'), trace_id: api_v1_contract_fixtures.trace_id },
          },
          {
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': request.headers.get('X-Request-Id') ?? '',
              'X-Trace-Id': api_v1_contract_fixtures.trace_id,
            },
          },
        ),
      ),
    )
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.accepted_run_id}`)
    render(<App />)

    expect(await screen.findByText('诊断正在执行。')).toBeInTheDocument()
    await waitFor(() => expect(TestEventSource.instances).toHaveLength(1))
    const source = TestEventSource.instances[0]
    expect(source?.url).toBe(`/api/v1/runs/${api_v1_contract_fixtures.accepted_run_id}/stream`)
    expect(source?.url).not.toContain('after_sequence')

    source?.emit_open()
    expect(await screen.findByText('正在接收已持久化的诊断事件。')).toBeInTheDocument()
    source?.emit_error()
    expect(await screen.findByText('事件连接中断，正在从持久化记录恢复。')).toBeInTheDocument()
    await waitFor(() => expect(request_paths.filter((path) => path.endsWith('/events')).length).toBeGreaterThanOrEqual(2))
    expect(TestEventSource.instances).toHaveLength(1)
    expect(screen.queryByText('诊断运行返回安全错误')).not.toBeInTheDocument()
    source?.emit_run_event({
      event: {
        id: 'duplicate-event',
        run_id: api_v1_contract_fixtures.accepted_run_id,
        sequence: 1,
        type: 'run_started',
        occurred_at: '2026-07-27T01:05:01.000Z',
        data: { summary: '重复事件不应重复渲染。' },
      },
    })
    expect(screen.getAllByText('#1')).toHaveLength(1)

    terminal = true
    source?.emit_run_event({
      event: {
        id: 'terminal-event',
        run_id: api_v1_contract_fixtures.accepted_run_id,
        sequence: 2,
        type: 'run_succeeded',
        occurred_at: '2026-07-27T01:05:02.000Z',
        data: { summary: '诊断已完成。' },
      },
    })
    expect(source?.closed).toBe(true)
    expect(await screen.findByText('诊断已完成。')).toBeInTheDocument()
    await waitFor(() => expect(request_paths.filter((path) => path.endsWith('/events')).length).toBeGreaterThanOrEqual(2))
  })

  it('Session 不存在时只显示安全读取错误', async () => {
    open_path('/workbench/sessions/not-found')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '无法恢复诊断会话' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('SESSION_NOT_FOUND：会话不存在')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /创建/i })).not.toBeInTheDocument()
  })

  it('Runs 恢复失败时不把下游资源伪造成空状态', async () => {
    server.use(
      http.get(/\/api\/v1\/sessions\/[^/]+\/runs$/, ({ request }) =>
        HttpResponse.json(
          {
            error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: {} },
            meta: { request_id: request.headers.get('X-Request-Id') },
          },
          { status: 500 },
        ),
      ),
    )
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    expect(await screen.findByText('INTERNAL_ERROR：服务内部错误，请稍后重试')).toBeInTheDocument()
    expect(screen.getByText('等待诊断运行恢复完成后再读取会话消息。')).toBeInTheDocument()
    expect(screen.getByText('等待会话消息恢复完成后再读取当前 Run。')).toBeInTheDocument()
    expect(screen.queryByText('该会话还没有消息')).not.toBeInTheDocument()
  })

  it('成功 Run 仅在完整结构化 Result 通过 reader 后展示摘要面板', async () => {
    server.use(run_response_handler(run_resource({ status: 'succeeded', result: complete_result(api_v1_contract_fixtures.run_id) })))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByText('结构化诊断结果')).toBeInTheDocument()
    expect(screen.getByLabelText('诊断结果摘要')).toHaveTextContent('Nginx 上游连接池已耗尽。')
    expect(screen.queryByText('RESULT_PROTOCOL_ERROR')).not.toBeInTheDocument()
  })

  it('成功 Run 的不完整 Result 显示协议错误，而不伪造结构化结论', async () => {
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByText('RESULT_PROTOCOL_ERROR')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
  })

  it('failed Run 只显示服务端安全错误，不展示结果面板', async () => {
    server.use(run_response_handler(run_resource({
      error: { code: 'TOOL_TIMEOUT', message: '上游日志查询超时。' },
      status: 'failed',
    })))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByText('TOOL_TIMEOUT')).toBeInTheDocument()
    expect(screen.getByText('上游日志查询超时。')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
  })

  it('cancelled、queued 与 running Run 诚实显示终态或进度，不展示旧结果', async () => {
    server.use(run_response_handler(run_resource({ status: 'cancelled' })))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    const cancelled_view = render(<App />)

    expect(await screen.findByText('诊断运行已取消')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
    cancelled_view.unmount()

    server.use(run_response_handler(run_resource({ status: 'queued' })))
    const queued_view = render(<App />)

    expect(await screen.findByText('诊断正在排队')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
    queued_view.unmount()

    server.use(run_response_handler(run_resource({ status: 'running' })))
    render(<App />)

    expect(await screen.findByText('诊断正在运行')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
  })

  it('归档 Session 可只读展示历史成功 Result，且仍不提供新的诊断提交', async () => {
    const archived_run = run_resource({
      result: complete_result(api_v1_contract_fixtures.run_id),
      session_id: api_v1_contract_fixtures.archived_session_id,
      status: 'succeeded',
    })
    server.use(
      http.get(/\/api\/v1\/sessions\/22222222-2222-4222-8222-222222222222\/runs$/, ({ request }) => {
        const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
        return HttpResponse.json({ items: [archived_run], page: { next_cursor: null, has_more: false }, meta: { request_id, trace_id: api_v1_contract_fixtures.trace_id } })
      }),
      http.get(/\/api\/v1\/sessions\/22222222-2222-4222-8222-222222222222\/messages$/, ({ request }) => {
        const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
        return HttpResponse.json({ items: [], page: { next_cursor: null, has_more: false }, meta: { request_id, trace_id: api_v1_contract_fixtures.trace_id } })
      }),
      run_response_handler(archived_run),
    )
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.archived_session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByText('会话已归档，仅可读取历史内容，不能受理新的诊断运行。')).toBeInTheDocument()
    expect(await screen.findByText('结构化诊断结果')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '诊断问题' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始诊断' })).not.toBeInTheDocument()
  })

})
