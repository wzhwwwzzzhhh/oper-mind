import { fireEvent, render, screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_workbench(): void {
  window.history.replaceState({}, '', '/workbench')
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

    expect(await screen.findByText('最近会话')).toBeInTheDocument()
    expect(screen.getByText('Nginx 5xx 排查')).toBeInTheDocument()
  })

  it('提供最近调查入口并跳转', async () => {
    open_workbench()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '最近调查' }))

    expect(window.location.pathname).toBe('/workbench/runs')
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
