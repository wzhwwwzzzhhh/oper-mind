import { HttpResponse, http } from 'msw'

const session_id = '11111111-1111-4111-8111-111111111111'
const archived_session_id = '22222222-2222-4222-8222-222222222222'
const run_id = '33333333-3333-4333-8333-333333333333'
const trace_id = '55555555-5555-4555-8555-555555555555'
const accepted_run_id = '99999999-9999-4999-8999-999999999999'
const failed_run_id = '55555555-5555-4555-8555-555555555554'
const cancelled_run_id = '66666666-6666-4666-8666-666666666665'
const empty_result_run_id = '77777777-7777-4777-8777-777777777771'
const protocol_error_run_id = '88888888-8888-4888-8888-888888888885'
const service_session_id = '44444444-4444-4444-8444-444444444444'
const service_run_id = '44444444-4444-4444-8444-444444444445'

const order_service = {
  id: 'order-service',
  title: '订单服务靶场',
  kind: 'postgres_orders_demo',
  supported_investigations: [{
    id: 'orders_slow_query.v1',
    title: '调查订单慢查询',
    description: '针对订单服务的固定慢查询场景收集受控 DB、日志和服务证据。',
    default_query: '订单服务变慢，帮我排查慢查询。',
  }],
  action_boundary: '仅当调查确认固定根因后，才可提出需人工审批和二次确认的固定修复。',
  snapshot: {
    observed_at: '2026-07-31T03:00:00.000Z',
    mode: 'mock',
    availability: 'healthy',
    performance_signal: 'slow_query_detected',
    server_metrics: {
      source_status: 'available',
      window_size: 12,
      p50_ms: 82,
      p95_ms: 210,
      slow_query_count: 10,
      timeout_count: 0,
    },
    database: { source_status: 'available', signal: 'missing_index_seq_scan_detected' },
  },
}

const service_session = {
  id: service_session_id,
  title: '订单服务慢查询调查',
  status: 'active',
  environment_id: null,
  incident_id: null,
  service_id: 'order-service',
  created_at: '2026-07-31T03:01:00.000Z',
  updated_at: '2026-07-31T03:01:00.000Z',
  archived_at: null,
}

const service_activity = {
  session_id: service_session_id,
  session_title: '订单服务慢查询调查',
  run_id: service_run_id,
  run_status: 'succeeded',
  created_at: '2026-07-31T03:02:00.000Z',
  finished_at: '2026-07-31T03:02:10.000Z',
  summary: '已确认固定慢查询根因。',
  severity: 'high',
  confidence: 0.95,
  proposal_status: 'verified',
  verification_status: 'verified',
}

const service_monitor_history = {
  service_id: 'order-service',
  status: 'available',
  source: 'scheduled_sampling',
  sample_interval_seconds: 300,
  retention_hours: 24,
  from: '2026-07-31T02:00:00.000Z',
  to: '2026-07-31T03:00:00.000Z',
  samples: [
    { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', service_id: 'order-service', observed_at: '2026-07-31T02:00:00.000Z', availability: 'healthy', p50_ms: 82, p95_ms: 210, slow_query_count: 0, timeout_count: 0, performance_signal: 'no_slow_query_detected', source_status: 'available' },
    { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', service_id: 'order-service', observed_at: '2026-07-31T02:05:00.000Z', availability: 'unhealthy', p50_ms: 120, p95_ms: 340, slow_query_count: 3, timeout_count: 1, performance_signal: 'slow_query_detected', source_status: 'available' },
  ],
}

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
    root_causes: [{
      id: '88888888-8888-4888-8888-888888888881',
      title: '上游连接池不足',
      summary: '连接池长期耗尽，导致 Nginx 无法建立新的上游连接。',
      confidence: 0.88,
      evidence_ids: ['88888888-8888-4888-8888-888888888882'],
    }],
    evidence: [{
      id: '88888888-8888-4888-8888-888888888882',
      source_type: 'log',
      source_name: 'nginx-access',
      title: 'Nginx 错误日志',
      summary: '上游连接池耗尽。',
      locator: 'nginx/upstream',
      observed_at: '2026-07-27T01:00:32.000Z',
      attributes: { active_connections: 120, saturation: 0.98, healthy: false, note: null },
    }],
    impact: {
      summary: '支付入口请求出现 5xx。',
      affected_services: ['gateway', 'payment-api'],
      affected_scope: '支付入口',
    },
    recommendations: [{
      id: '88888888-8888-4888-8888-888888888883',
      title: '分批扩容上游连接池',
      description: '在受控窗口内逐步提高连接池上限，并观察错误率。',
      priority: 'p1',
      risk_level: 'medium',
      requires_approval: true,
      evidence_ids: ['88888888-8888-4888-8888-888888888882'],
    }],
    risks: [{
      id: '88888888-8888-4888-8888-888888888884',
      level: 'medium',
      summary: '连接池上限调整可能增加后端连接压力。',
      mitigation: '分批调整并回滚异常实例。',
    }],
    requires_approval: true,
    agent_summary: [{
      agent: 'server',
      status: 'completed',
      summary: '已完成服务侧连接池诊断。',
      duration_ms: 120,
    }],
    report_markdown: '# Mock 结果补充\n\n该字段仅用于契约覆盖，P3 不渲染。',
    created_at: '2026-07-27T01:00:33.000Z',
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

const failed_run = {
  ...run,
  id: failed_run_id,
  status: 'failed',
  result: null,
  error: { code: 'TOOL_TIMEOUT', message: '上游日志查询超时。' },
  created_at: '2026-07-27T01:01:00.000Z',
  started_at: '2026-07-27T01:01:01.000Z',
  finished_at: '2026-07-27T01:01:02.000Z',
}

const cancelled_run = {
  ...run,
  id: cancelled_run_id,
  status: 'cancelled',
  result: null,
  error: null,
  created_at: '2026-07-27T01:02:00.000Z',
  started_at: '2026-07-27T01:02:01.000Z',
  finished_at: '2026-07-27T01:02:02.000Z',
}

const empty_result_run = {
  ...run,
  id: empty_result_run_id,
  result: {
    ...run.result,
    id: '88888888-8888-4888-8888-888888888886',
    run_id: empty_result_run_id,
    summary: '服务返回了完整但为空的结构化结果。',
    root_causes: [],
    evidence: [],
    impact: null,
    recommendations: [],
    risks: [],
    requires_approval: false,
    agent_summary: [],
    report_markdown: null,
    created_at: '2026-07-27T01:03:03.000Z',
  },
  created_at: '2026-07-27T01:03:00.000Z',
  started_at: '2026-07-27T01:03:01.000Z',
  finished_at: '2026-07-27T01:03:03.000Z',
}

const protocol_error_run = {
  ...run,
  id: protocol_error_run_id,
  result: (() => {
    const { created_at: _created_at, ...incomplete_result } = run.result
    return { ...incomplete_result, id: '88888888-8888-4888-8888-888888888887', run_id: protocol_error_run_id }
  })(),
  created_at: '2026-07-27T01:04:00.000Z',
  started_at: '2026-07-27T01:04:01.000Z',
  finished_at: '2026-07-27T01:04:03.000Z',
}

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
  http.get('/api/v1/model/config', ({ request }) => response(request, {
    config: {
      mode: 'mock',
      diagnostic_model: {
        provider: 'mock.example',
        base_url_host: 'mock.example',
        model: 'diagnostic-model',
        status: 'configured',
      },
      judge_model: null,
    },
  })),
  http.get('/api/v1/services', ({ request }) => response(request, { items: [order_service] })),
  http.get('/api/v1/services/order-service', ({ request }) => response(request, { service: order_service })),
  http.get('/api/v1/services/order-service/monitor/history', ({ request }) => response(request, service_monitor_history)),
  http.get('/api/v1/services/order-service/activities', ({ request }) =>
    response(request, { items: [service_activity], page: { next_cursor: null, has_more: false } }),
  ),
  http.post('/api/v1/services/order-service/sessions', ({ request }) =>
    response(request, { session: service_session }, 201),
  ),
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
    if (requested_session_id === service_session_id) return response(request, { session: service_session })
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    return response(request, { session })
  }),
  http.get(/\/api\/v1\/sessions\/([^/]+)\/messages$/, ({ request }) => {
    const url = new URL(request.url)
    const requested_session_id = url.pathname.split('/').at(-2)
    if (requested_session_id === service_session_id) {
      return response(request, { items: [], page: { next_cursor: null, has_more: false } })
    }
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
    if (requested_session_id === service_session_id) {
      return response(request, { items: [], page: { next_cursor: null, has_more: false } })
    }
    if (requested_session_id !== session_id) return error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404)
    const cursor = url.searchParams.get('cursor')
    return response(request, {
      items: cursor ? [] : [run, empty_result_run, protocol_error_run, failed_run, cancelled_run],
      page: cursor ? { next_cursor: null, has_more: false } : { next_cursor: 'run-page-2', has_more: true },
    })
  }),
  http.get(/\/api\/v1\/runs\/([^/]+)\/events$/, ({ request }) => {
    const url = new URL(request.url)
    const requested_run_id = url.pathname.split('/').at(-2)
    if ([failed_run_id, cancelled_run_id, empty_result_run_id, protocol_error_run_id].includes(requested_run_id ?? '')) {
      return response(request, { items: [], page: { next_cursor: null, has_more: false } })
    }
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
    if (requested_run_id === failed_run_id) return response(request, { run: failed_run })
    if (requested_run_id === cancelled_run_id) return response(request, { run: cancelled_run })
    if (requested_run_id === empty_result_run_id) return response(request, { run: empty_result_run })
    if (requested_run_id === protocol_error_run_id) return response(request, { run: protocol_error_run })
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

export const api_v1_contract_fixtures = { accepted_run_id, archived_session_id, cancelled_run_id, empty_result_run_id, failed_run_id, order_service, protocol_error_run_id, run_events, run_id, service_activity, service_monitor_history, service_run_id, service_session, service_session_id, session_id, trace_id }
