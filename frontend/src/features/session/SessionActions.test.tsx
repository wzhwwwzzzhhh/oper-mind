import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'

import { SessionActions } from './SessionActions'
import { api_v1_contract_fixtures } from '../../test/handlers'
import { server } from '../../test/server'

function render_with_query_client(ui: React.ReactNode): void {
  const query_client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  render(<QueryClientProvider client={query_client}>{ui}</QueryClientProvider>)
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

  it('归档状态不展示会话操作入口', () => {
    render_with_query_client(
      <SessionActions session_id={api_v1_contract_fixtures.archived_session_id} status="archived" title="已归档的历史会话" />,
    )

    expect(screen.queryByRole('button', { name: '会话操作：已归档的历史会话' })).not.toBeInTheDocument()
  })
})
