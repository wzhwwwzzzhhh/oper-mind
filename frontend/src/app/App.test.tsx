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

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { ...body, meta: { request_id, trace_id: api_v1_contract_fixtures.trace_id } },
    {
      status,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': request_id,
        'X-Trace-Id': api_v1_contract_fixtures.trace_id,
      },
    },
  )
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

function conversation_resources({
  run_status = 'succeeded',
  result = complete_result(api_v1_contract_fixtures.run_id),
  error = null,
  include_output = true,
}: {
  error?: unknown
  include_output?: boolean
  result?: unknown
  run_status?: 'cancelled' | 'failed' | 'queued' | 'running' | 'succeeded'
} = {}) {
  const session_id = api_v1_contract_fixtures.session_id
  const run_id = api_v1_contract_fixtures.run_id
  const input_message_id = '66666666-6666-4666-8666-666666666666'
  const run = {
    id: run_id,
    session_id,
    trace_id: api_v1_contract_fixtures.trace_id,
    input_message_id,
    status: run_status,
    result: run_status === 'succeeded' ? result : null,
    error: run_status === 'failed' ? error : null,
    created_at: '2026-07-28T07:59:00.000Z',
    started_at: run_status === 'queued' ? null : '2026-07-28T07:59:01.000Z',
    finished_at: ['queued', 'running'].includes(run_status) ? null : '2026-07-28T08:00:00.000Z',
  }
  const messages = [
    {
      id: input_message_id,
      session_id,
      run_id: null,
      role: 'user',
      content: '请检查 Nginx 5xx。',
      created_at: '2026-07-28T07:59:00.000Z',
    },
    ...(include_output ? [{
      id: '88888888-8888-4888-8888-888888888888',
      session_id,
      run_id,
      role: 'assistant',
      content: '初步判断是上游连接池已经耗尽。',
      created_at: '2026-07-28T08:00:01.000Z',
    }] : []),
  ]
  return { messages, run }
}

function use_conversation_handlers(resources: ReturnType<typeof conversation_resources>): void {
  const session_id = api_v1_contract_fixtures.session_id
  server.use(
    http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
      response(request, { items: [resources.run], page: { next_cursor: null, has_more: false } }),
    ),
    http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
      response(request, { items: resources.messages, page: { next_cursor: null, has_more: false } }),
    ),
  )
}

describe('App', () => {
  beforeEach(() => {
    request_paths = []
    open_path('/workbench')
  })

  it('从 v1 active Session 列表恢复个人会话入口', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '我的会话' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(screen.getByText('发送与实时过程：后续 P3.6b')).toBeInTheDocument()
  })

  it('按 Session、Runs、Message 的顺序恢复只读 Conversation Turn', async () => {
    use_conversation_handlers(conversation_resources())
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(await screen.findByLabelText('用户问题')).toHaveTextContent('请检查 Nginx 5xx。')
    expect(await screen.findByLabelText('助手答复')).toHaveTextContent('初步判断是上游连接池已经耗尽。')
    expect(screen.getByText('调查已完成')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await waitFor(() => expect(request_paths).toEqual([
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
    ]))
  })

  it('旧 Run 深链回到对应会话，不额外读取单个 Run 资源', async () => {
    use_conversation_handlers(conversation_resources())
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toBeInTheDocument()
    await waitFor(() => expect(request_paths).toEqual([
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
    ]))
  })

  it('将结构化 Result 收在助手答复的按需展开层，而不是默认 Run 面板', async () => {
    use_conversation_handlers(conversation_resources())
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('助手答复')).toBeInTheDocument()
    expect(screen.queryByText('结构化诊断结果')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('展开结论、证据与建议'))
    expect(await screen.findByText('结构化诊断结果')).toBeInTheDocument()
  })

  it('结构化 Result 协议异常时保留已保存答复，并明确标示异常', async () => {
    use_conversation_handlers(conversation_resources({ result: { id: 'incomplete-result' } }))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('助手答复')).toHaveTextContent('初步判断是上游连接池已经耗尽。')
    expect(screen.getByText('RESULT_PROTOCOL_ERROR')).toBeInTheDocument()
    expect(screen.queryByText('展开结论、证据与建议')).not.toBeInTheDocument()
  })

  it('成功调查缺少持久化助手消息时只显示恢复提示，不伪造答复', async () => {
    use_conversation_handlers(conversation_resources({ include_output: false }))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    expect(await screen.findByText('ANSWER_RECOVERY_PENDING')).toBeInTheDocument()
    expect(screen.queryByLabelText('助手答复')).not.toBeInTheDocument()
  })

  it('failed 与 cancelled 调查只显示真实状态，不伪造结构化答复', async () => {
    use_conversation_handlers(conversation_resources({
      error: { code: 'TOOL_TIMEOUT', message: '上游日志查询超时。' },
      include_output: false,
      run_status: 'failed',
    }))
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    const failed_view = render(<App />)

    expect(await screen.findByText('TOOL_TIMEOUT')).toBeInTheDocument()
    expect(screen.queryByLabelText('助手答复')).not.toBeInTheDocument()
    failed_view.unmount()

    use_conversation_handlers(conversation_resources({ include_output: false, run_status: 'cancelled' }))
    render(<App />)
    expect(await screen.findAllByText('调查已取消')).toHaveLength(2)
    expect(screen.queryByLabelText('助手答复')).not.toBeInTheDocument()
  })

  it('归档会话仍只读展示历史 Turn，不提供发送能力', async () => {
    const session_id = api_v1_contract_fixtures.archived_session_id
    const resources = conversation_resources()
    const archived_run = { ...resources.run, session_id }
    const archived_messages = resources.messages.map((message) => ({ ...message, session_id }))
    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => response(request, {
        session: {
          id: session_id,
          title: '已归档的历史会话',
          status: 'archived',
          environment_id: null,
          incident_id: null,
          created_at: '2026-07-28T07:00:00.000Z',
          updated_at: '2026-07-28T08:00:00.000Z',
          archived_at: '2026-07-28T08:01:00.000Z',
        },
      })),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [archived_run], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, { items: archived_messages, page: { next_cursor: null, has_more: false } }),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByText('已归档会话')).toBeInTheDocument()
    expect(await screen.findByLabelText('助手答复')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
