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
    window.sessionStorage.clear()
    window.localStorage.clear()
    open_path('/workbench')
  })

  it('从 v1 active Session 列表恢复 DevOps Copilot 会话入口', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '你好，我是 OperMind' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /排查慢查询/ })).toBeInTheDocument()
    expect(screen.getByLabelText('全局导航')).toBeInTheDocument()
  })

  it('欢迎页快捷卡创建会话并进入新会话', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    let create_body: unknown
    server.use(
      http.post(/\/api\/v1\/sessions$/, async ({ request }) => {
        create_body = await request.json()
        return response(request, {
          session: {
            id: session_id,
            title: '帮我排查订单服务最近的慢查询，先从数据库只读调查开始。',
            status: 'active',
            service_id: null,
            created_at: '2026-07-28T09:00:00.000Z',
            updated_at: '2026-07-28T09:00:00.000Z',
            archived_at: null,
          },
        }, 201)
      }),
    )
    use_conversation_handlers(conversation_resources({ include_output: false, run_status: 'queued' }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /排查慢查询/ }))

    await waitFor(() => expect(create_body).toEqual({ title: '帮我排查订单服务最近的慢查询，先从数据库只读调查开始。' }))
    await waitFor(() =>
      expect(request_paths).toContain(`/api/v1/sessions/${session_id}`),
    )
  })

  it('按 Session、Runs、Message 的顺序恢复只读 Conversation Turn', async () => {
    use_conversation_handlers(conversation_resources())
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toHaveTextContent('请检查 Nginx 5xx。')
    expect(await screen.findByLabelText('助手答复')).toHaveTextContent('初步判断是上游连接池已经耗尽。')
    expect(screen.getByText((content) => content.includes('调查已完成'))).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '调查问题' })).toBeInTheDocument()
    await waitFor(() => expect(request_paths).toEqual([
      `/api/v1/sessions`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
      `/api/v1/runs/${api_v1_contract_fixtures.run_id}/events`,
    ]))
  })

  it('active 会话只在 202 后通过已保存 Run 与 Message 显示新调查', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const run_id = '99999999-9999-4999-8999-999999999991'
    const input_message_id = '99999999-9999-4999-8999-999999999992'
    const submitted_query = '请检查支付网关近期的 5xx。'
    let accepted = false
    let captured_key: string | null = null

    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) => response(request, {
        items: accepted ? [{
          id: run_id,
          session_id,
          trace_id: api_v1_contract_fixtures.trace_id,
          input_message_id,
          status: 'queued',
          result: null,
          error: null,
          created_at: '2026-07-29T02:00:00.000Z',
          started_at: null,
          finished_at: null,
        }] : [],
        page: { next_cursor: null, has_more: false },
      })),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) => response(request, {
        items: accepted ? [{
          id: input_message_id,
          session_id,
          run_id: null,
          role: 'user',
          content: submitted_query,
          created_at: '2026-07-29T02:00:00.000Z',
        }] : [],
        page: { next_cursor: null, has_more: false },
      })),
      http.post(new RegExp(`/api/v1/sessions/${session_id}/runs$`), async ({ request }) => {
        captured_key = request.headers.get('Idempotency-Key')
        expect(await request.json()).toEqual({ query: submitted_query })
        accepted = true
        return response(request, {
          run: {
            id: run_id,
            session_id,
            trace_id: api_v1_contract_fixtures.trace_id,
            input_message_id,
            status: 'queued',
            result: null,
            error: null,
            created_at: '2026-07-29T02:00:00.000Z',
            started_at: null,
            finished_at: null,
          },
        }, 202)
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '调查问题' })
    fireEvent.change(input, { target: { value: submitted_query } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(await screen.findByLabelText('用户问题')).toHaveTextContent(submitted_query)
    expect(screen.getAllByText((content) => content.includes('正在准备调查')).length).toBeGreaterThanOrEqual(1)
    expect(captured_key).toMatch(/^[0-9a-f-]{36}$/i)
    expect(request_paths.filter((path) => path === `/api/v1/sessions/${session_id}/runs`).length).toBeGreaterThanOrEqual(2)
    expect(request_paths.filter((path) => path === `/api/v1/sessions/${session_id}/messages`).length).toBeGreaterThanOrEqual(2)
  })

  it('幂等键冲突时不自动换 key，必须明确丢弃当前发送意图', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    let post_attempts = 0
    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
      http.post(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) => {
        post_attempts += 1
        return response(request, {
          error: { code: 'IDEMPOTENCY_KEY_REUSED', message: '幂等键已用于不同问题。', details: null },
        }, 409)
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '调查问题' })
    fireEvent.change(input, { target: { value: '请检查首次问题。' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(await screen.findByText('IDEMPOTENCY_KEY_REUSED：幂等键已用于不同问题。')).toBeInTheDocument()
    expect(input).toBeDisabled()
    expect(post_attempts).toBe(1)
    fireEvent.click(screen.getByRole('button', { name: '丢弃当前发送意图' }))
    expect(input).not.toBeDisabled()
  })

  it('网络未知时使用相同幂等键重试，而不创建第二个本地意图', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const run_id = '99999999-9999-4999-8999-999999999993'
    const input_message_id = '99999999-9999-4999-8999-999999999994'
    const submitted_query = '请检查网关连接。'
    const idempotency_keys: string[] = []
    let post_attempts = 0
    let accepted = false

    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) => response(request, {
        items: accepted ? [{
          id: run_id,
          session_id,
          trace_id: api_v1_contract_fixtures.trace_id,
          input_message_id,
          status: 'queued',
          result: null,
          error: null,
          created_at: '2026-07-29T02:00:00.000Z',
          started_at: null,
          finished_at: null,
        }] : [],
        page: { next_cursor: null, has_more: false },
      })),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) => response(request, {
        items: accepted ? [{
          id: input_message_id,
          session_id,
          run_id: null,
          role: 'user',
          content: submitted_query,
          created_at: '2026-07-29T02:00:00.000Z',
        }] : [],
        page: { next_cursor: null, has_more: false },
      })),
      http.post(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) => {
        idempotency_keys.push(request.headers.get('Idempotency-Key') ?? '')
        post_attempts += 1
        if (post_attempts === 1) return HttpResponse.error()
        accepted = true
        return response(request, {
          run: {
            id: run_id,
            session_id,
            trace_id: api_v1_contract_fixtures.trace_id,
            input_message_id,
            status: 'queued',
            result: null,
            error: null,
            created_at: '2026-07-29T02:00:00.000Z',
            started_at: null,
            finished_at: null,
          },
        }, 202)
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '调查问题' })
    fireEvent.change(input, { target: { value: submitted_query } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    expect(await screen.findByText('NETWORK_ERROR：无法连接到服务。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(await screen.findByLabelText('用户问题')).toHaveTextContent(submitted_query)
    expect(idempotency_keys).toHaveLength(2)
    expect(idempotency_keys[0]).toBe(idempotency_keys[1])
  })

  it('旧 Run 深链回到对应会话，不额外读取单个 Run 资源', async () => {
    use_conversation_handlers(conversation_resources())
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toBeInTheDocument()
    await waitFor(() => expect(request_paths).toEqual([
      `/api/v1/sessions`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
      `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
      `/api/v1/runs/${api_v1_contract_fixtures.run_id}/events`,
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
    expect(await screen.findAllByText((content) => content.includes('调查已取消'))).toHaveLength(2)
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

  it('从服务中心服务目录发起只读调查，进入对应会话', async () => {
    open_path('/services')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '服务中心' })).toBeInTheDocument()
    const investigate = await screen.findByRole('button', { name: '发起调查' })
    fireEvent.click(investigate)

    await waitFor(() => expect(request_paths).toContain('/api/v1/services/postgres-production/sessions'))
  })

  it('服务中心将多选服务创建为联合调查会话，且保留单服务快捷入口', async () => {
    let create_body: unknown
    server.use(
      http.post('/api/v1/sessions', async ({ request }) => {
        create_body = await request.json()
        return response(request, {
          session: {
            id: api_v1_contract_fixtures.session_id, title: '联合服务调查', status: 'active',
            service_id: null, service_ids: ['postgres-production', 'redis-production'],
            created_at: '2026-07-28T09:00:00.000Z', updated_at: '2026-07-28T09:00:00.000Z', archived_at: null,
          },
        }, 201)
      }),
      http.get('/api/v1/services', ({ request }) => response(request, {
        items: [api_v1_contract_fixtures.order_service, api_v1_contract_fixtures.redis_service],
      })),
    )
    open_path('/services')
    render(<App />)

    fireEvent.click(await screen.findByRole('checkbox', { name: '选择 订单服务靶场' }))
    fireEvent.click(screen.getByRole('checkbox', { name: '选择 生产 Redis 缓存' }))
    expect(screen.getByRole('button', { name: '发起调查' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '联合发起调查 (2)' }))

    await waitFor(() => expect(create_body).toEqual({
      title: '联合服务调查', service_ids: ['postgres-production', 'redis-production'],
    }))
  })

  it('会话页展示服务端返回的真实调查目标服务', async () => {
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.service_session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('本次调查目标服务')).toHaveTextContent('订单服务靶场')
  })

  it('服务详情读取真实快照和历史趋势，并标记异常采样点', async () => {
    open_path('/services/postgres-production')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '订单服务靶场' })).toBeInTheDocument()
    expect(screen.getByText('82 ms')).toBeInTheDocument()
    expect(screen.getByText('210 ms')).toBeInTheDocument()
    expect(screen.getByText('定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录')).toBeInTheDocument()
    expect(screen.getByText('采样点异常')).toBeInTheDocument()
    expect(screen.getByText(/慢查询 3/)).toBeInTheDocument()
    expect(screen.queryByText('99.98%')).not.toBeInTheDocument()
  })

  it('服务详情无历史采样时展示诚实空态，不绘制假趋势线', async () => {
    open_path('/services/postgres-production')
    server.use(
      http.get('/api/v1/services/postgres-production/monitor/history', ({ request }) =>
        response(request, {
          service_id: 'postgres-production',
          status: 'not_sampled',
          source: 'scheduled_sampling',
          sample_interval_seconds: 300,
          retention_hours: 24,
          from: '2026-07-31T02:00:00.000Z',
          to: '2026-07-31T03:00:00.000Z',
          samples: [],
        }),
      ),
    )
    render(<App />)

    expect(await screen.findByRole('heading', { name: '订单服务靶场' })).toBeInTheDocument()
    expect(await screen.findByText('暂无历史采样')).toBeInTheDocument()
    expect(screen.getByText(/不会绘制假趋势线/)).toBeInTheDocument()
    expect(screen.queryByText('采样点异常')).not.toBeInTheDocument()
    expect(screen.getByText('定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录')).toBeInTheDocument()
  })

  it('模型服务页展示后端真实配置并保留本地 Agent 偏好', async () => {
    open_path('/models')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '模型服务' })).toBeInTheDocument()
    expect((await screen.findAllByText('diagnostic-model')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/Mock 模式/)).length).toBeGreaterThan(0)
    expect(screen.getByText('未配置独立裁判模型')).toBeInTheDocument()
    const coordinator_toggle = screen.getByRole('button', { name: 'Coordinator 策略开关' })
    fireEvent.click(coordinator_toggle)
    expect(JSON.parse(window.localStorage.getItem('opermind:model-policy') ?? '{}')).toMatchObject({ coordinator: false })

    expect(screen.getByRole('button', { name: '＋ 添加模型服务' })).toBeEnabled()
    expect(await screen.findByText('DeepSeek 生产')).toBeInTheDocument()
  })

  it('模型配置接口失败时显示错误且不回退静态 Provider', async () => {
    server.use(
      http.get('/api/v1/model/config', ({ request }) => response(request, {
        error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: null },
      }, 500)),
    )
    open_path('/models')
    render(<App />)

    expect(await screen.findByText('暂时无法读取模型配置，请稍后重试。')).toBeInTheDocument()
    expect(screen.queryByText('diagnostic-model')).not.toBeInTheDocument()
    expect(screen.queryByText('示例配置')).not.toBeInTheDocument()
    expect(screen.queryByText('本地页面偏好')).not.toBeInTheDocument()
  })

  it('服务中心列表展示真实服务目录，不伪装成实时监控', async () => {
    open_path('/services')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '服务中心' })).toBeInTheDocument()
    expect(await screen.findByText('订单服务靶场')).toBeInTheDocument()
    expect(screen.getByText('服务目录')).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('仅展示当前工作空间授权范围内的信息'))).toBeInTheDocument()
  })

  it('服务中心列表展示多个实例并标记未配置实例', async () => {
    const staging_service = {
      ...api_v1_contract_fixtures.order_service,
      id: 'postgres-staging',
      title: '预发布 PostgreSQL 主库',
      kind: 'postgres',
      snapshot: {
        ...api_v1_contract_fixtures.order_service.snapshot,
        availability: 'not_configured',
        mode: 'disabled',
        performance_signal: 'not_configured',
        server_metrics: { source_status: 'not_configured' },
        database: { source_status: 'not_configured', signal: 'not_configured' },
      },
    }
    server.use(
      http.get('/api/v1/services', ({ request }) =>
        response(request, { items: [api_v1_contract_fixtures.order_service, staging_service] }),
      ),
    )
    open_path('/services')
    render(<App />)

    expect(await screen.findByText('预发布 PostgreSQL 主库')).toBeInTheDocument()
    expect(screen.getByText('未配置')).toBeInTheDocument()
    expect(screen.getByText('1 个已配置')).toBeInTheDocument()
  })

  it('服务中心列表展示 Redis 实例并对无调查服务诚实标注未启用', async () => {
    server.use(
      http.get('/api/v1/services', ({ request }) =>
        response(request, { items: [api_v1_contract_fixtures.order_service, api_v1_contract_fixtures.redis_service] }),
      ),
    )
    open_path('/services')
    render(<App />)

    expect(await screen.findByText('生产 Redis 缓存')).toBeInTheDocument()
    expect(screen.getByText('Redis · 已接入')).toBeInTheDocument()
    const redis_investigate = screen.getByRole('button', { name: '未启用' })
    expect(redis_investigate).toBeDisabled()
    expect(screen.getByRole('button', { name: '发起调查' })).toBeEnabled()
  })

  it('Redis 服务详情展示专用指标且不冒充数据库延迟', async () => {
    open_path('/services/redis-production')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '生产 Redis 缓存' })).toBeInTheDocument()
    expect(screen.getAllByText('内存占用').length).toBeGreaterThan(0)
    expect(screen.getByText('8.0 MB')).toBeInTheDocument()
    expect(screen.getByText('客户端连接')).toBeInTheDocument()
    expect(screen.getByText('12 个')).toBeInTheDocument()
    expect(screen.getByText('定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录')).toBeInTheDocument()
    expect(screen.getByText('采样点异常')).toBeInTheDocument()
    expect(screen.getByText(/慢日志 3/)).toBeInTheDocument()
    expect(screen.queryByText('P50 延迟')).not.toBeInTheDocument()
    expect(screen.queryByText('P95 延迟')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '调查未启用' })).toBeDisabled()
  })

  it('Redis 未配置实例详情显示未配置且指标为空', async () => {
    const not_configured_redis = {
      ...api_v1_contract_fixtures.redis_service,
      snapshot: {
        ...api_v1_contract_fixtures.redis_service.snapshot,
        availability: 'not_configured',
        mode: 'disabled',
        performance_signal: 'not_configured',
        server_metrics: { source_status: 'not_configured' },
        database: { source_status: 'not_configured', signal: 'not_configured' },
      },
    }
    server.use(
      http.get('/api/v1/services/redis-production', ({ request }) => response(request, { service: not_configured_redis })),
    )
    open_path('/services/redis-production')
    render(<App />)

    expect((await screen.findAllByText('未配置')).length).toBeGreaterThan(0)
    expect(screen.getByText('服务状态：未配置')).toBeInTheDocument()
  })

})
