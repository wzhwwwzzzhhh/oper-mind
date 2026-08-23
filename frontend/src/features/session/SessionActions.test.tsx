import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { SessionActions } from './SessionActions'
import { SessionNavigationProvider, use_session_navigation } from './SessionNavigationContext'
import { api_v1_query_keys, get_session_query } from '../../api/v1/queries'
import { api_v1_contract_fixtures } from '../../test/handlers'
import { server } from '../../test/server'

function render_with_query_client(ui: React.ReactNode): QueryClient {
  const query_client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  render(
    <QueryClientProvider client={query_client}>
      <MemoryRouter initialEntries={['/workbench']}>
        <SessionNavigationProvider>
          {ui}
          <LifecycleNotice />
        </SessionNavigationProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return query_client
}

function LifecycleNotice(): React.ReactNode {
  const navigation = use_session_navigation()
  return navigation.lifecycle_notice ? <div role="status">{navigation.lifecycle_notice}</div> : null
}

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const request_id = request.headers.get('X-Request-Id') ?? 'session-actions-request-id'
  return HttpResponse.json(
    { ...body, meta: { request_id } },
    { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': request_id } },
  )
}

afterEach(() => server.resetHandlers())

describe('SessionActions', () => {
  it('保存新标题后显示成功提示并发送 PATCH', async () => {
    const requests: Request[] = []
    server.use(
      http.patch('/api/v1/sessions/:session_id', async ({ request }) => {
        requests.push(request)
        const body = await request.json() as { title?: string }
        return response(request, {
          session: {
            id: api_v1_contract_fixtures.session_id,
            title: body.title ?? 'Nginx 5xx 排查',
            status: 'active',
          },
        })
      }),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.session_id} status="active" title="Nginx 5xx 排查" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    const input = screen.getByRole('textbox', { name: '会话标题' })
    fireEvent.change(input, { target: { value: '网关错误排查' } })
    fireEvent.click(screen.getByRole('button', { name: '保存标题' }))

    expect(await screen.findByText('会话标题已更新')).toBeInTheDocument()
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('PATCH')
  })

  it('空标题不会发送请求并显示校验提示', async () => {
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.session_id} status="active" title="Nginx 5xx 排查" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '会话标题' }), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存标题' }))

    expect(await screen.findByText('会话标题不能为空')).toBeInTheDocument()
  })

  it('归档前显示 Run 继续执行提示，确认后发送 DELETE', async () => {
    const requests: Request[] = []
    server.use(
      http.delete('/api/v1/sessions/:session_id', ({ request }) => {
        requests.push(request)
        return new HttpResponse(null, { status: 204, headers: { 'X-Request-Id': 'archive-request-id' } })
      }),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.session_id} status="active" title="Nginx 5xx 排查" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }))

    expect(screen.getByText(/归档后会话将从最近会话中隐藏/)).toBeInTheDocument()
    expect(screen.getByText(/进行中的调查.*继续执行/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(await screen.findByText('会话已归档')).toBeInTheDocument()
    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('DELETE')
  })

  it('归档失败时显示安全错误', async () => {
    server.use(
      http.delete('/api/v1/sessions/:session_id', ({ request }) =>
        response(request, { error: { code: 'SESSION_NOT_FOUND', message: '会话不存在', details: null } }, 404),
      ),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.session_id} status="active" title="Nginx 5xx 排查" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }))
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(await screen.findByText(/SESSION_NOT_FOUND：会话不存在/)).toBeInTheDocument()
  })

  it('归档状态只展示恢复入口', () => {
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    expect(screen.queryByRole('button', { name: '会话操作：已归档的历史会话' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢复会话' })).toBeInTheDocument()
  })

  it('恢复确认说明不复制内容且成功只发送一次 PATCH', async () => {
    const requests: Request[] = []
    server.use(
      http.patch('/api/v1/sessions/:session_id', async ({ request, params }) => {
        requests.push(request)
        return response(request, {
          session: {
            id: params.session_id,
            title: '已归档的历史会话',
            status: 'active',
            archived_at: null,
            updated_at: '2026-08-23T02:00:00.000Z',
          },
        })
      }),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    expect(screen.getByText(/重新提供消息与调查录入/)).toBeInTheDocument()
    expect(screen.getByText(/不会复制历史内容.*不会创建或启动调查/)).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: '确认恢复' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    expect(await screen.findByRole('status')).toHaveTextContent('会话已恢复')
    expect(requests).toHaveLength(1)
    await expect(requests[0]?.json()).resolves.toEqual({ status: 'active' })
  })

  it('网络失败后直接回读 active 事实并按幂等成功收敛', async () => {
    let detail_reads = 0
    server.use(
      http.patch('/api/v1/sessions/:session_id', () => HttpResponse.error()),
      http.get('/api/v1/sessions/:session_id', ({ request, params }) => {
        detail_reads += 1
        return response(request, {
          session: {
            id: params.session_id,
            title: '已归档的历史会话',
            status: 'active',
            archived_at: null,
          },
        })
      }),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByRole('status')).toHaveTextContent('会话已恢复')
    expect(detail_reads).toBe(1)
  })

  it('无效成功响应后用新 GET 校验 active 事实', async () => {
    let detail_reads = 0
    server.use(
      http.patch('/api/v1/sessions/:session_id', ({ request }) => response(request, {
        session: { id: '11111111-1111-4111-8111-111111111111', status: 'active' },
      })),
      http.get('/api/v1/sessions/:session_id', ({ request, params }) => {
        detail_reads += 1
        return response(request, { session: { id: params.session_id, status: 'active', archived_at: null } })
      }),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByRole('status')).toHaveTextContent('会话已恢复')
    expect(detail_reads).toBe(1)
  })

  it('网络失败回读仍为 archived 时保留恢复入口', async () => {
    server.use(
      http.patch('/api/v1/sessions/:session_id', () => HttpResponse.error()),
      http.get('/api/v1/sessions/:session_id', ({ request, params }) => response(request, {
        session: { id: params.session_id, status: 'archived' },
      })),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText('NETWORK_ERROR：无法连接到服务。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认恢复' })).toBeEnabled()
  })

  it('回读返回错会话时不宣称恢复成功', async () => {
    server.use(
      http.patch('/api/v1/sessions/:session_id', () => HttpResponse.error()),
      http.get('/api/v1/sessions/:session_id', ({ request }) => response(request, {
        session: { id: '11111111-1111-4111-8111-111111111111', status: 'active' },
      })),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText('恢复结果尚未确认，请刷新会话状态后重试。')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('恢复前在途 archived 详情最晚返回也不能覆盖 active 缓存', async () => {
    const session_id = api_v1_contract_fixtures.archived_session_id
    let release_old_response: (() => void) | undefined
    let mark_old_request_started: (() => void) | undefined
    const old_response_gate = new Promise<void>((resolve) => { release_old_response = resolve })
    const old_request_started = new Promise<void>((resolve) => { mark_old_request_started = resolve })
    server.use(
      http.get('/api/v1/sessions/:session_id', async ({ request, params }) => {
        mark_old_request_started?.()
        await old_response_gate
        return response(request, { session: { id: params.session_id, status: 'archived' } })
      }),
      http.patch('/api/v1/sessions/:session_id', ({ request, params }) => response(request, {
        session: { id: params.session_id, status: 'active', archived_at: null },
      })),
    )
    const query_client = render_with_query_client(
      <SessionActions session_id={session_id} status="archived" title="已归档的历史会话" />,
    )
    const old_request = query_client.fetchQuery(get_session_query(session_id)).catch(() => undefined)
    await old_request_started

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))
    expect(await screen.findByRole('status')).toHaveTextContent('会话已恢复')

    release_old_response?.()
    await old_request
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    const cached = query_client.getQueryData(api_v1_query_keys.session(session_id)) as
      | { data?: { session?: { status?: unknown } } }
      | undefined
    expect(cached?.data?.session?.status).toBe('active')
  })

  it('PATCH 5xx 后回读 active 仍按幂等成功', async () => {
    server.use(
      http.patch('/api/v1/sessions/:session_id', ({ request }) => response(request, {
        error: { code: 'RESTORE_TEMPORARY_ERROR', message: '暂时不可用', details: null },
      }, 503)),
      http.get('/api/v1/sessions/:session_id', ({ request, params }) => response(request, {
        session: { id: params.session_id, status: 'active', archived_at: null },
      })),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByRole('status')).toHaveTextContent('会话已恢复')
  })

  it('结果不确定且回读 404 时显示 SESSION_NOT_FOUND', async () => {
    server.use(
      http.patch('/api/v1/sessions/:session_id', () => HttpResponse.error()),
      http.get('/api/v1/sessions/:session_id', ({ request }) => response(request, {
        error: { code: 'SESSION_NOT_FOUND', message: '会话不存在', details: null },
      }, 404)),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText('SESSION_NOT_FOUND：会话不存在')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('明确拒绝保留恢复入口并显示安全错误', async () => {
    server.use(
      http.patch('/api/v1/sessions/:session_id', ({ request }) =>
        response(request, { error: { code: 'SESSION_NOT_FOUND', message: '会话不存在', details: null } }, 404),
      ),
    )
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复会话' }))
    fireEvent.click(screen.getByRole('button', { name: '确认恢复' }))

    expect(await screen.findByText(/SESSION_NOT_FOUND：会话不存在/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认恢复' })).toBeEnabled()
  })

  it('状态刷新中不展示归档或恢复动作', () => {
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.session_id} status="unknown" title="状态读取中" />,
    )

    expect(screen.queryByRole('button', { name: /恢复会话|会话操作/ })).not.toBeInTheDocument()
  })
})
