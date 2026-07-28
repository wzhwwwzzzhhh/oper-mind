import { HttpResponse, http } from 'msw'

const session_id = '11111111-1111-4111-8111-111111111111'
const archived_session_id = '22222222-2222-4222-8222-222222222222'
const run_id = '33333333-3333-4333-8333-333333333333'
const trace_id = '55555555-5555-4555-8555-555555555555'
const accepted_run_id = '99999999-9999-4999-8999-999999999999'

const session = {
  id: session_id,
  title: 'Nginx 5xx 排查',
  status: 'active',
  environment_id: null,
  incident_id: null,
  created_at: '2026-07-27T01:00:00.000Z',
  updated_at: '2026-07-27T01:02:00.000Z',
  archived_at: null,
}

const archived_session = {
  ...session,
  id: archived_session_id,
  title: '已归档的历史会话',
  status: 'archived',
  archived_at: '2026-07-27T01:03:00.000Z',
}

const paged_active_session = {
  ...session,
  id: '99999999-9999-4999-8999-999999999999',
  title: '第二页的活跃会话',
  updated_at: '2026-07-27T01:01:00.000Z',
}

const run = {
  id: run_id,
  session_id,
  trace_id,
  input_message_id: '66666666-6666-4666-8666-666666666666',
  status: 'succeeded',
  result: {
    id: '77777777-7777-4777-8777-777777777777',
    run_id,
    summary: 'Nginx 上游连接池已耗尽。',
    severity: 'high',
    confidence: 0.92,
    root_causes: [],
    evidence: [],
    impact: null,
    recommendations: [],
    risks: [],
    requires_approval: false,
    agent_summary: [],
    report_markdown: null,
  },
  error: null,
  created_at: '2026-07-27T01:00:30.000Z',
  started_at: '2026-07-27T01:00:31.000Z',
  finished_at: '2026-07-27T01:00:33.000Z',
}

const run_events = [
  {
    id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    run_id,
    sequence: 1,
    type: 'run_queued',
    occurred_at: '2026-07-27T01:00:30.000Z',
    data: { summary: '诊断请求已持久化并进入队列。' },
  },
  {
    id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    run_id,
    sequence: 2,
    type: 'run_started',
    occurred_at: '2026-07-27T01:00:31.000Z',
    data: { summary: '诊断任务已开始执行。' },
  },
]

const accepted_run = {
  id: accepted_run_id,
  session_id,
  trace_id,
  input_message_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  status: 'queued',
  result: null,
  error: null,
  created_at: '2026-07-27T01:05:00.000Z',
  started_at: null,
  finished_at: null,
}

function correlation(request: Request) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return {
    meta: { request_id, trace_id },
    headers: {
      'Content-Type': 'application/json',
      'X-Request-Id': request_id,
      'X-Trace-Id': trace_id,
    },
  }
}

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const { meta, headers } = correlation(request)
  return HttpResponse.json({ ...body, meta }, { status, headers })
}

function error_response(request: Request, code: string, message: string, status: number) {
  return response(request, { error: { code, message, details: null } }, status)
}

export const api_v1_handlers = [
  http.get(/\/api\/v1\/sessions$/, ({ request }) => {
    const cursor = new URL(request.url).searchParams.get('cursor')
    if (cursor === 'empty-page') {
      return response(request, { items: [], page: { next_cursor: null, has_more: false } })
    }
    if (cursor === 'session-page-2') {
      return response(request, { items: [paged_active_session], page: { next_cursor: null, has_more: false } })
    }
    return response(request, { items: [session], page: { next_cursor: 'session-page-2', has_more: true } })
  }),
  http.get(/\/api\/v1\/sessions\/([^/]+)$/, ({ request }) => {
    const requested_session_id = new URL(request.url).pathname.split('/').at(-1)
    if (requested_session_id === archived_session_id) return response(request, { session: archived_session })
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    return response(request, { session })
  }),
  http.get(/\/api\/v1\/sessions\/([^/]+)\/messages$/, ({ request }) => {
    const url = new URL(request.url)
    const requested_session_id = url.pathname.split('/').at(-2)
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    const cursor = url.searchParams.get('cursor')
    return response(request, {
      items: cursor
        ? [{ id: '88888888-8888-4888-8888-888888888888', session_id, run_id, role: 'assistant', content: '诊断已完成。', created_at: '2026-07-27T01:00:34.000Z' }]
        : [{ id: '66666666-6666-4666-8666-666666666666', session_id, run_id: null, role: 'user', content: '请检查 Nginx 5xx。', created_at: '2026-07-27T01:00:00.000Z' }],
      page: cursor ? { next_cursor: null, has_more: false } : { next_cursor: 'message-page-2', has_more: true },
    })
  }),
  http.post(/\/api\/v1\/sessions\/([^/]+)\/runs$/, async ({ request }) => {
    const requested_session_id = new URL(request.url).pathname.split('/').at(-2)
    const idempotency_key = request.headers.get('Idempotency-Key')
    const payload = await request.json() as { query?: unknown }
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    if (!idempotency_key) return error_response(request, 'VALIDATION_ERROR', '缺少幂等键', 422)
    if (payload.query !== '请检查 Nginx 5xx。') return error_response(request, 'VALIDATION_ERROR', '问题内容无效', 422)
    return response(request, { run: accepted_run }, 202)
  }),
  http.get(/\/api\/v1\/sessions\/([^/]+)\/runs$/, ({ request }) => {
    const url = new URL(request.url)
    const requested_session_id = url.pathname.split('/').at(-2)
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    const cursor = url.searchParams.get('cursor')
    return response(request, {
      items: cursor ? [] : [run],
      page: cursor ? { next_cursor: null, has_more: false } : { next_cursor: 'run-page-2', has_more: true },
    })
  }),
  http.get(/\/api\/v1\/runs\/([^/]+)\/events$/, ({ request }) => {
    const url = new URL(request.url)
    const requested_run_id = url.pathname.split('/').at(-2)
    if (requested_run_id !== run_id) return error_response(request, 'RUN_NOT_FOUND', '诊断运行不存在', 404)
    const cursor = url.searchParams.get('cursor')
    return response(request, {
      items: cursor ? [run_events[1]] : [run_events[0]],
      page: cursor ? { next_cursor: null, has_more: false } : { next_cursor: 'run-event-page-2', has_more: true },
    })
  }),
  http.get(/\/api\/v1\/runs\/([^/]+)$/, ({ request }) => {
    const requested_run_id = new URL(request.url).pathname.split('/').at(-1)
    if (requested_run_id === accepted_run_id) return response(request, { run: accepted_run })
    if (requested_run_id !== run_id) return error_response(request, 'RUN_NOT_FOUND', '诊断运行不存在', 404)
    return response(request, { run })
  }),
]

export const api_v1_contract_scenarios = {
  active_empty_session_list: http.get(/\/api\/v1\/sessions$/, ({ request }) =>
    response(request, { items: [], page: { next_cursor: null, has_more: false } }),
  ),
  internal_error: http.get(/\/api\/v1\/sessions$/, ({ request }) =>
    error_response(request, 'INTERNAL_ERROR', '服务内部错误，请稍后重试', 500),
  ),
  network_interruption: http.get(/\/api\/v1\/sessions$/, () => HttpResponse.error()),
}

export const api_v1_contract_fixtures = { accepted_run_id, archived_session_id, run_events, run_id, session_id, trace_id }
