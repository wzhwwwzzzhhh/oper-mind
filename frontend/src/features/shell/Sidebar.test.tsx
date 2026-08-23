import { fireEvent, render, screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_workbench(): void {
  window.history.replaceState({}, '', '/workbench')
}

function open_session(): void {
  window.history.replaceState({}, '', '/workbench/sessions/11111111-1111-4111-8111-111111111111')
}

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { ...body, meta: { request_id } },
    { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': request_id } },
  )
}

function error_response(request: Request, code: string, message: string, status: number) {
  return response(request, { error: { code, message, details: null } }, status)
}

describe('Sidebar 会话搜索与 Ctrl K', () => {
  it('Ctrl K 聚焦会话搜索框（真实键盘监听，替代假提示）', () => {
    open_workbench()
    render(<App />)

    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })

    expect(screen.getByRole('textbox', { name: '搜索会话' })).toHaveFocus()
  })

  it('输入关键词后服务端搜索并展示匹配会话', async () => {
    open_workbench()
    render(<App />)

    const search_box = await screen.findByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: 'Nginx' } })

    expect(await screen.findByText('搜索结果')).toBeInTheDocument()
    expect(await screen.findByText('Nginx 5xx 排查')).toBeInTheDocument()
  })

  it('无匹配会话时展示诚实空态', async () => {
    open_workbench()
    render(<App />)

    const search_box = await screen.findByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: '不存在的会话' } })

    expect(await screen.findByText('无匹配会话')).toBeInTheDocument()
  })

  it('Esc 清空搜索恢复最近会话列表', async () => {
    open_workbench()
    render(<App />)

    const search_box = await screen.findByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: 'Nginx' } })
    await screen.findByText('搜索结果')

    fireEvent.keyDown(search_box, { key: 'Escape' })

    expect(await screen.findByRole('button', { name: '最近会话', pressed: true })).toBeInTheDocument()
    expect(screen.getByText('Nginx 5xx 排查')).toBeInTheDocument()
  })

  it('在 debounce 到期前清空不会让旧关键词回写', async () => {
    const queries: Array<string | null> = []
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) => {
        queries.push(new URL(request.url).searchParams.get('q'))
        return response(request, { items: [], page: { next_cursor: null, has_more: false } })
      }),
    )
    open_workbench()
    render(<App />)

    const search_box = await screen.findByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: '不应回写' } })
    fireEvent.click(screen.getByRole('button', { name: '清空搜索' }))
    await new Promise((resolve) => window.setTimeout(resolve, 400))

    expect(search_box).toHaveValue('')
    expect(queries).not.toContain('不应回写')
  })

  it('提供最近调查入口并跳转', async () => {
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '最近调查' }))

    expect(window.location.pathname).toBe('/workbench/runs')
  })

  it('切换已归档视图后只请求并展示 archived 会话', async () => {
    const statuses: Array<string | null> = []
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) => {
        const status = new URL(request.url).searchParams.get('status')
        statuses.push(status)
        const items = status === 'archived'
          ? [{ id: '99999999-9999-4999-8999-999999999999', title: '历史故障复盘', status: 'archived' }]
          : [{ id: '11111111-1111-4111-8111-111111111111', title: 'Nginx 5xx 排查', status: 'active' }]
        return response(request, { items, page: { next_cursor: null, has_more: false } })
      }),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '已归档' }))

    expect(await screen.findByText('历史故障复盘')).toBeInTheDocument()
    expect(screen.getByText('已归档', { selector: 'small' })).toBeInTheDocument()
    expect(statuses).toContain('archived')
    expect(screen.queryByText('Nginx 5xx 排查')).not.toBeInTheDocument()
  })

  it('归档视图搜索无匹配时不回退 active 会话充数', async () => {
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '已归档' }))
    const search_box = screen.getByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: '不存在' } })

    expect(await screen.findByText('无匹配归档会话')).toBeInTheDocument()
    expect(screen.queryByText('Nginx 5xx 排查')).not.toBeInTheDocument()
  })

  it('归档视图按 cursor 加载下一页并保留已加载记录', async () => {
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        return cursor === 'archived-next'
          ? response(request, {
              items: [{ id: '88888888-8888-4888-8888-888888888888', title: '归档第二页', status: 'archived' }],
              page: { next_cursor: null, has_more: false },
            })
          : response(request, {
              items: [{ id: '99999999-9999-4999-8999-999999999999', title: '归档第一页', status: 'archived' }],
              page: { next_cursor: 'archived-next', has_more: true },
            })
      }),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '已归档' }))
    expect(await screen.findByText('归档第一页')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '加载更多会话' }))

    expect(await screen.findByText('归档第二页')).toBeInTheDocument()
    expect(screen.getByText('归档第一页')).toBeInTheDocument()
  })

  it('归档下一页失败时保留首屏并允许重试', async () => {
    let next_attempts = 0
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor !== 'retry-next') {
          return response(request, {
            items: [{ id: '99999999-9999-4999-8999-999999999999', title: '保留的归档首屏', status: 'archived' }],
            page: { next_cursor: 'retry-next', has_more: true },
          })
        }
        next_attempts += 1
        return next_attempts === 1
          ? error_response(request, 'INTERNAL_ERROR', '暂时失败', 500)
          : response(request, {
              items: [{ id: '88888888-8888-4888-8888-888888888888', title: '重试后的下一页', status: 'archived' }],
              page: { next_cursor: null, has_more: false },
            })
      }),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '已归档' }))
    fireEvent.click(await screen.findByRole('button', { name: '加载更多会话' }))
    expect(await screen.findByText('加载更多失败')).toBeInTheDocument()
    expect(screen.getByText('保留的归档首屏')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('重试后的下一页')).toBeInTheDocument()
    expect(next_attempts).toBe(2)
  })

  it('从会话侧栏重命名并调用 PATCH', async () => {
    const requests: Request[] = []
    let title = 'Nginx 5xx 排查'
    let updated_title = ''
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) =>
        response(request, {
          items: [{ id: '11111111-1111-4111-8111-111111111111', title, status: 'active' }],
          page: { next_cursor: null, has_more: false },
        }),
      ),
      http.patch(/\/api\/v1\/sessions\/[^/]+$/, async ({ request }) => {
        requests.push(request)
        const body = await request.json() as { title?: string }
        updated_title = body.title ?? ''
        title = body.title ?? title
        return response(request, { session: { id: '11111111-1111-4111-8111-111111111111', title, status: 'active' } })
      }),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }))
    fireEvent.change(screen.getByRole('textbox', { name: '会话标题' }), { target: { value: '网关错误排查' } })
    fireEvent.click(screen.getByRole('button', { name: '保存标题' }))

    expect(await screen.findByText('会话标题已更新')).toBeInTheDocument()
    expect(requests).toHaveLength(1)
    expect(updated_title).toBe('网关错误排查')
  })

  it('从当前会话的侧栏归档后返回工作台首页', async () => {
    open_session()
    render(<App />)

    const sidebar = screen.getByLabelText('会话导航')
    fireEvent.click(await within(sidebar).findByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(within(sidebar).getByRole('menuitem', { name: '归档' }))
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(await screen.findByRole('heading', { name: '你好，我是 OperMind' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/workbench')
  })

  it('从会话侧栏归档后移除 active 会话', async () => {
    let archived = false
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) =>
        response(request, {
          items: archived ? [] : [{ id: '11111111-1111-4111-8111-111111111111', title: 'Nginx 5xx 排查', status: 'active' }],
          page: { next_cursor: null, has_more: false },
        }),
      ),
      http.delete(/\/api\/v1\/sessions\/[^/]+$/, () => {
        archived = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }))
    expect(screen.getByText(/归档后会话将从最近会话中隐藏/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(await screen.findByText('还没有会话')).toBeInTheDocument()
    expect(screen.queryByText('Nginx 5xx 排查')).not.toBeInTheDocument()
  })

  it('归档失败时保留会话并显示安全错误', async () => {
    server.use(
      http.delete(/\/api\/v1\/sessions\/[^/]+$/, ({ request }) =>
        error_response(request, 'SESSION_NOT_FOUND', '会话不存在', 404),
      ),
    )
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '会话操作：Nginx 5xx 排查' }))
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }))
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    expect(await screen.findByText(/SESSION_NOT_FOUND：会话不存在/)).toBeInTheDocument()
    expect(screen.getByText('Nginx 5xx 排查')).toBeInTheDocument()
  })

  it('会话搜索请求失败时如实提示', async () => {
    server.use(
      http.get(/\/api\/v1\/sessions$/, ({ request }) => {
        const q = new URL(request.url).searchParams.get('q')
        if (!q) {
          return response(request, { items: [], page: { next_cursor: null, has_more: false } })
        }
        return error_response(request, 'INTERNAL_ERROR', '服务内部错误，请稍后重试', 500)
      }),
    )
    open_workbench()
    render(<App />)

    const search_box = await screen.findByRole('textbox', { name: '搜索会话' })
    fireEvent.change(search_box, { target: { value: 'Nginx' } })

    expect(await screen.findByText('会话搜索暂不可用')).toBeInTheDocument()
  })
})
