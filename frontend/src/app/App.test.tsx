import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from './App'
import { api_v1_contract_fixtures } from '../test/handlers'
import { server } from '../test/server'

function open_path(path: string): void {
  window.history.replaceState({}, '', path)
}

let request_paths: string[] = []

server.events.on('request:start', ({ request }) => {
  const path = new URL(request.url).pathname
  if (path.startsWith('/api/v1/')) request_paths.push(path)
})

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
    expect(await screen.findByText('结构化结果待展示')).toBeInTheDocument()
    await waitFor(() =>
      expect(request_paths).toEqual([
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
        `/api/v1/runs/${api_v1_contract_fixtures.run_id}`,
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
})
