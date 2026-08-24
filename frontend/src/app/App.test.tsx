import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from './App'
import { api_v1_contract_fixtures } from '../test/handlers'
import { server } from '../test/server'
import { save_pending_plain_message } from '../features/workbench/plain-message-intent'
import { create_session_run_send_intent, save_session_run_send_intent } from '../features/workbench/send-intent'

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

  it('顶栏生效模型读后端真实配置，不再写死模型名', async () => {
    render(<App />)

    // 来自 MSW /api/v1/model/config 的真实返回：diagnostic-model · mock
    expect(await screen.findByText(/生效模型 diagnostic-model · Mock/)).toBeInTheDocument()
    expect(screen.queryByText(/OperMind-Reasoner/)).not.toBeInTheDocument()
  })

  it('顶栏在 real 不可用时如实标注暂不可用，不冒充真实调用', async () => {
    server.use(
      http.get('/api/v1/model/config', ({ request }) => response(request, {
        config: {
          mode: 'real',
          mode_source: 'runtime',
          mode_available: false,
          mode_unavailable_reason: '无可用 Provider/API Key',
          diagnostic_model: {
            provider: 'mock.example',
            base_url_host: 'mock.example',
            model: 'diagnostic-model',
            status: 'configured',
          },
          judge_model: null,
          params: { temperature: null, max_tokens: null },
          params_defaults: { temperature: 0.0, max_tokens: null },
        },
      })),
    )
    render(<App />)

    expect(await screen.findByText(/生效模型 diagnostic-model · 真实（暂不可用）/)).toBeInTheDocument()
  })

  it('欢迎页服务数如实展示"已接入"口径，不再写"在线"', async () => {
    render(<App />)

    expect(await screen.findByText(/个服务已接入 · 默认只读调查/)).toBeInTheDocument()
    expect(screen.queryByText(/个服务在线/)).not.toBeInTheDocument()
  })

  it('全局图标轨只放正式模块，服务监控不在这里重复一个入口', () => {
    render(<App />)

    const rail = screen.getByLabelText('全局导航')
    // 产品定义第 4 节：监控是服务中心的责任，不是独立模块。
    expect(rail.querySelector('[aria-label="服务监控"]')).toBeNull()
    for (const label of ['会话工作台', '服务中心', '文档知识库', '模型设置']) {
      expect(rail.querySelector(`[aria-label="${label}"]`)).not.toBeNull()
    }
  })

  it('在服务监控页时点亮服务中心，且监控入口只出现在第二栏子导航', async () => {
    open_path('/monitor')
    render(<App />)

    const rail = screen.getByLabelText('全局导航')
    expect(rail.querySelector('[aria-label="服务中心"]')?.className).toContain('active')

    // 子导航里的"服务监控"是唯一入口，并且处于选中态。
    const context_nav = await screen.findByLabelText('服务中心导航')
    const monitor_link = Array.from(context_nav.querySelectorAll('button')).find(
      (node) => node.textContent?.includes('服务监控'),
    )
    expect(monitor_link?.className).toContain('active')
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
      // 顶栏生效模型标识：壳层挂载即读取模型配置（只读）。
      `/api/v1/model/config`,
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
    const submitted_query = '请检查订单库近期的慢查询。'
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
    open_path(`/workbench/sessions/${session_id}?intent=orders_slow_query.v1`)
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
    fireEvent.change(input, { target: { value: '请排查首次连接池问题。' } })
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
    const submitted_query = '请检查网关连接池。'
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
      // 顶栏生效模型标识：壳层挂载即读取模型配置（只读）。
      `/api/v1/model/config`,
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

  it('归档会话限制录入但保留 Run 与提案既有入口', async () => {
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
    expect(within(screen.getByRole('main')).queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '删除' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新生成' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止调查' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢复会话' })).toBeInTheDocument()
    expect(screen.queryByText('尚未开始调查')).not.toBeInTheDocument()
  })

  it('归档会话中的 running Run 继续展示并允许按既有规则取消', async () => {
    const session_id = api_v1_contract_fixtures.archived_session_id
    const resources = conversation_resources({ include_output: false, run_status: 'running' })
    const run = { ...resources.run, session_id }
    let cancel_posted = 0
    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => response(request, {
        session: {
          id: session_id,
          title: '运行中的归档会话',
          status: 'archived',
          created_at: '2026-07-28T07:00:00.000Z',
          updated_at: '2026-07-28T08:00:00.000Z',
          archived_at: '2026-07-28T08:01:00.000Z',
        },
      })),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [run], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, {
          items: resources.messages.map((message) => ({ ...message, session_id })),
          page: { next_cursor: null, has_more: false },
        }),
      ),
      http.post(new RegExp(`/api/v1/runs/${run.id}/cancel$`), () => {
        cancel_posted += 1
        return HttpResponse.json(null, { status: 204 })
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByRole('button', { name: '停止调查' })).toBeInTheDocument()
    expect(within(screen.getByRole('main')).queryByRole('textbox')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止调查' }))

    await waitFor(() => expect(cancel_posted).toBe(1))
  })

  it('从 archived 详情恢复同一会话后重新提供录入控件', async () => {
    const session_id = api_v1_contract_fixtures.archived_session_id
    let restored = false
    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => response(request, {
        session: {
          id: session_id,
          title: '已归档的历史会话',
          status: restored ? 'active' : 'archived',
          created_at: '2026-07-28T07:00:00.000Z',
          updated_at: restored ? '2026-08-23T02:00:00.000Z' : '2026-07-28T08:00:00.000Z',
          archived_at: restored ? null : '2026-07-28T08:01:00.000Z',
        },
      })),
      http.patch(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => {
        restored = true
        return response(request, {
          session: {
            id: session_id,
            title: '已归档的历史会话',
            status: 'active',
            created_at: '2026-07-28T07:00:00.000Z',
            updated_at: '2026-08-23T02:00:00.000Z',
            archived_at: null,
          },
        })
      }),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText('会话已恢复')).toBeInTheDocument()
    expect(within(screen.getByRole('main')).getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '会话操作：已归档的历史会话' })).toBeInTheDocument()
  })

  it('恢复 archived 会话不会自动提交遗留调查或普通消息意图', async () => {
    const session_id = api_v1_contract_fixtures.archived_session_id
    let restored = false
    let automatic_posts = 0
    save_session_run_send_intent(
      window.sessionStorage,
      create_session_run_send_intent(session_id, '检查恢复后的慢查询', {
        created_at: '2026-08-23T02:00:00.000Z',
        idempotency_keys: ['aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'],
      }),
    )
    save_pending_plain_message(window.sessionStorage, session_id, '恢复后等待用户明确发送')
    server.use(
      http.get(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => response(request, {
        session: {
          id: session_id,
          title: '已归档的历史会话',
          status: restored ? 'active' : 'archived',
          created_at: '2026-07-28T07:00:00.000Z',
          updated_at: restored ? '2026-08-23T02:00:00.000Z' : '2026-07-28T08:00:00.000Z',
          archived_at: restored ? null : '2026-07-28T08:01:00.000Z',
        },
      })),
      http.patch(new RegExp(`/api/v1/sessions/${session_id}$`), ({ request }) => {
        restored = true
        return response(request, {
          session: {
            id: session_id,
            title: '已归档的历史会话',
            status: 'active',
            created_at: '2026-07-28T07:00:00.000Z',
            updated_at: '2026-08-23T02:00:00.000Z',
            archived_at: null,
          },
        })
      }),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
      http.post(new RegExp(`/api/v1/sessions/${session_id}/(?:runs|messages)$`), () => {
        automatic_posts += 1
        return HttpResponse.json({}, { status: 500 })
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText('会话已恢复')).toBeInTheDocument()
    expect(within(screen.getByRole('main')).getByRole('textbox')).toBeInTheDocument()
    await new Promise((resolve) => window.setTimeout(resolve, 100))
    expect(automatic_posts).toBe(0)
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

  it('模型服务页只展示后端真实配置，不再渲染写死的模型卡与假策略开关', async () => {
    open_path('/models')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '模型服务' })).toBeInTheDocument()
    expect((await screen.findAllByText('diagnostic-model')).length).toBeGreaterThan(0)
    expect(screen.getByText('未配置独立裁判模型')).toBeInTheDocument()
    expect(screen.getByText('返回确定性样例，不出网')).toBeInTheDocument()

    // 只写 localStorage 的假开关与写死的示例模型卡已删除，不应再出现。
    expect(screen.queryByRole('button', { name: 'Coordinator 策略开关' })).not.toBeInTheDocument()
    expect(window.localStorage.getItem('opermind:model-policy')).toBeNull()
    expect(screen.queryByText('DeepSeek · 云端示例')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '设为当前偏好' })).not.toBeInTheDocument()

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
    expect(screen.queryByText('DeepSeek · 云端示例')).not.toBeInTheDocument()
  })

  it('服务中心列表展示真实服务目录，不伪装成实时监控', async () => {
    open_path('/services')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '服务中心' })).toBeInTheDocument()
    expect(await screen.findByText('订单服务靶场')).toBeInTheDocument()
    expect(screen.getByText('服务目录')).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('仅展示后端已注册服务'))).toBeInTheDocument()
    // 工作空间/团队名后端没有这个概念，页面不再编造。
    expect(screen.queryByText('研发运维团队')).not.toBeInTheDocument()
    expect(screen.queryByText('platform-team · 受控访问')).not.toBeInTheDocument()
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
    expect(screen.getByText('1 个已配置快照')).toBeInTheDocument()
    // 快照模式来自后端 ServiceMode，不是每行写死的"受控访问"。
    expect(screen.getByText('未接入')).toBeInTheDocument()
    expect(screen.getByText('演示快照')).toBeInTheDocument()
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

  it('普通消息只走轻量回复通道，不创建 Run', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    let run_posted = 0
    server.use(
      http.post(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) => {
        run_posted += 1
        return response(request, { error: { code: 'INTERNAL_ERROR', message: '不应创建 Run', details: null } }, 500)
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    const input = await screen.findByRole('textbox', { name: '调查问题' })
    fireEvent.change(input, { target: { value: '谢谢' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(request_paths.filter((path) => path.endsWith('/messages')).length).toBeGreaterThanOrEqual(2))
    expect(run_posted).toBe(0)
  })

  it('运行中的调查可点击停止并取消 Run', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const run_id = api_v1_contract_fixtures.run_id
    let cancel_posted = 0
    use_conversation_handlers(conversation_resources({ include_output: false, run_status: 'running' }))
    server.use(
      http.post(new RegExp(`/api/v1/runs/${run_id}/cancel$`), () => {
        cancel_posted += 1
        return HttpResponse.json(null, { status: 204 })
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByRole('button', { name: '停止调查' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '停止调查' }))

    await waitFor(() => expect(cancel_posted).toBe(1))
  })

  it('会话侧栏待审批入口导航到提案列表', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '待审批' }))

    expect(await screen.findByRole('heading', { name: '待审批提案' })).toBeInTheDocument()
    expect(await screen.findByText('重建受控靶场联合索引')).toBeInTheDocument()
  })

  it('待审批列表进入提案详情并复用审批面板', async () => {
    open_path('/workbench/approvals')
    render(<App />)

    const rows = await screen.findAllByText('重建受控靶场联合索引')
    fireEvent.click(rows[0]!)

    expect(await screen.findByRole('heading', { name: '提案详情' })).toBeInTheDocument()
    expect(await screen.findByText('固定修复提案')).toBeInTheDocument()
    expect(screen.getByText('本地人工审批限制')).toBeInTheDocument()
  })

  it('已结束调查提供重新生成，点击后发起重跑并进入新调查跟踪', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const run_id = api_v1_contract_fixtures.run_id
    const rerun_run_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa11'
    let rerun_posted = 0
    const resources = conversation_resources()
    const rerun_message = {
      id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa12',
      session_id,
      run_id: null,
      role: 'user',
      content: '请检查 Nginx 5xx。',
      created_at: '2026-07-28T08:01:00.000Z',
    }
    const rerun_run = {
      ...resources.run,
      id: rerun_run_id,
      input_message_id: rerun_message.id,
      status: 'queued',
      result: null,
      error: null,
      rerun_of_run_id: run_id,
      created_at: '2026-07-28T08:01:00.000Z',
      started_at: null,
      finished_at: null,
    }
    use_conversation_handlers(resources)
    server.use(
      http.post(new RegExp(`/api/v1/runs/${run_id}/rerun$`), ({ request }) => {
        rerun_posted += 1
        return response(request, { run: rerun_run }, 202)
      }),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/runs$`), ({ request }) =>
        response(request, { items: [rerun_run, resources.run], page: { next_cursor: null, has_more: false } }),
      ),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, { items: [rerun_message, ...resources.messages], page: { next_cursor: null, has_more: false } }),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByRole('button', { name: '重新生成' }, { timeout: 3000 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新生成' }))

    await waitFor(() => expect(rerun_posted).toBe(1))
    // invalidate 后会话 runs/messages 被重新拉取。
    await waitFor(() => expect(request_paths.filter((path) => path === `/api/v1/sessions/${session_id}/runs`).length).toBeGreaterThanOrEqual(2))
    await waitFor(() => expect(request_paths.filter((path) => path === `/api/v1/sessions/${session_id}/messages`).length).toBeGreaterThanOrEqual(2))
    // 重跑请求发出后 invalidate 会话列表：新 Run 展示「重跑自原 Run」，原 Run 展示「已被重跑」。
    expect(await screen.findByText(/重跑自 Run 33333333/, undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByText(/已被重跑为 Run aaaaaaaa/)).toBeInTheDocument()
    // 新 Run 是 queued：不提供再次重跑按钮。
    expect(screen.getAllByRole('button', { name: '重新生成' })).toHaveLength(1)
  })

  it('未结束调查不提供重新生成按钮', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    use_conversation_handlers(conversation_resources({ include_output: false, run_status: 'running' }))
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByRole('button', { name: '停止调查' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新生成' })).not.toBeInTheDocument()
  })

  it('重新生成失败如实提示且不影响原调查', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const run_id = api_v1_contract_fixtures.run_id
    let rerun_posted = 0
    use_conversation_handlers(conversation_resources())
    server.use(
      http.post(new RegExp(`/api/v1/runs/${run_id}/rerun$`), ({ request }) => {
        rerun_posted += 1
        return response(request, { error: { code: 'RUN_NOT_FOUND', message: '诊断运行不存在', details: null } }, 404)
      }),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '重新生成' }))

    await waitFor(() => expect(rerun_posted).toBe(1))
    expect(await screen.findByText('重新生成未完成')).toBeInTheDocument()
    // 原调查仍展示（页面没有用本地数据伪造新 Run）。
    expect(screen.getByText('初步判断是上游连接池已经耗尽。')).toBeInTheDocument()
  })

  it('编辑用户消息后刷新列表并展示已编辑标注', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const resources = conversation_resources()
    use_conversation_handlers(resources)
    let edited_content = resources.messages[0].content
    server.use(
      http.patch(new RegExp(`/api/v1/sessions/${session_id}/messages/[^/]+$`), async ({ request }) => {
        const payload = await request.json() as { content?: unknown }
        edited_content = typeof payload.content === 'string' ? payload.content : edited_content
        return response(request, {
          message: {
            ...resources.messages[0],
            content: edited_content,
            edited_at: '2026-07-28T09:00:00.000Z',
          },
        })
      }),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, {
          items: [{ ...resources.messages[0], content: edited_content, edited_at: '2026-07-28T09:00:00.000Z' }, ...resources.messages.slice(1)],
          page: { next_cursor: null, has_more: false },
        }),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toHaveTextContent('请检查 Nginx 5xx。')
    fireEvent.click(screen.getByRole('button', { name: '编辑' }))

    const textarea = screen.getByLabelText('编辑消息内容')
    fireEvent.change(textarea, { target: { value: '请检查 Nginx 5xx（更正措辞）。' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    // 保存成功后刷新列表：新内容 + 「已编辑」标注。
    await waitFor(() => expect(request_paths.some((path) => path.includes(`/messages/${resources.messages[0].id}`))).toBe(true))
    await waitFor(() => expect(request_paths.filter((path) => path === `/api/v1/sessions/${session_id}/messages`).length).toBeGreaterThanOrEqual(2))
    expect(await screen.findByText('已编辑')).toBeInTheDocument()
    expect(screen.getByLabelText('用户问题')).toHaveTextContent('请检查 Nginx 5xx（更正措辞）。')
  })

  it('删除用户消息后消息消失且调查卡片保留可追溯', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const resources = conversation_resources()
    use_conversation_handlers(resources)
    let deleted = false
    server.use(
      http.delete(new RegExp(`/api/v1/sessions/${session_id}/messages/[^/]+$`), () => {
        deleted = true
        return HttpResponse.json(null, { status: 204 })
      }),
      http.get(new RegExp(`/api/v1/sessions/${session_id}/messages$`), ({ request }) =>
        response(request, {
          items: deleted ? resources.messages.filter((item) => item.id !== resources.messages[0].id) : resources.messages,
          page: { next_cursor: null, has_more: false },
        }),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    // 删除确认如实提示：有调查回答时说明回答记录保留。
    const dialogs = await screen.findAllByRole('dialog')
    const dialog = dialogs.find((node) => within(node).queryByText('删除这条消息？'))
    expect(dialog).toBeDefined()
    expect(within(dialog!).getByText(/该问题已有调查回答，删除问题不删除回答记录/)).toBeInTheDocument()
    fireEvent.click(within(dialog!).getByRole('button', { name: '确认删除' }))

    // 消息内容消失（占位展示），Run 调查卡片保留可追溯。
    await waitFor(() => expect(screen.queryByText('请检查 Nginx 5xx。')).not.toBeInTheDocument())
    expect(screen.getByText('（问题已删除）')).toBeInTheDocument()
    expect(screen.getByText('初步判断是上游连接池已经耗尽。')).toBeInTheDocument()
  })

  it('删除失败如实提示且消息保留', async () => {
    const session_id = api_v1_contract_fixtures.session_id
    const resources = conversation_resources()
    use_conversation_handlers(resources)
    server.use(
      http.delete(new RegExp(`/api/v1/sessions/${session_id}/messages/[^/]+$`), ({ request }) =>
        response(request, { error: { code: 'MESSAGE_NOT_DELETABLE', message: '只有用户消息可以删除。', details: null } }, 422),
      ),
    )
    open_path(`/workbench/sessions/${session_id}`)
    render(<App />)

    expect(await screen.findByLabelText('用户问题')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    const dialogs = await screen.findAllByRole('dialog')
    const dialog = dialogs.find((node) => within(node).queryByText('删除这条消息？'))
    expect(dialog).toBeDefined()
    fireEvent.click(within(dialog!).getByRole('button', { name: '确认删除' }))

    // 失败态诚实展示：错误提示出现，消息仍保留（未用本地数据伪造删除成功）。
    expect(await screen.findByText('MESSAGE_NOT_DELETABLE：只有用户消息可以删除。')).toBeInTheDocument()
    expect(screen.getByLabelText('用户问题')).toBeInTheDocument()
  })

  it('当前会话归档后返回工作台首页', async () => {
    server.use(
      http.delete(`/api/v1/sessions/${api_v1_contract_fixtures.session_id}`, () =>
        new HttpResponse(null, { status: 204 }),
      ),
    )
    open_path(`/workbench/sessions/${api_v1_contract_fixtures.session_id}`)
    render(<App />)

    const toolbar = await screen.findByLabelText('会话工具栏')
    fireEvent.click(within(toolbar).getByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }))
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    await waitFor(() => expect(window.location.pathname).toBe('/workbench'))
    expect(await screen.findByRole('heading', { name: '你好，我是 OperMind' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '会话标题' })).not.toBeInTheDocument()
  })

})
