import { fireEvent, render, screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_runs(): void {
  window.history.replaceState({}, '', '/workbench/runs')
}

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { ...body, meta: { request_id } },
    { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': request_id } },
  )
}

/** 侧栏最近会话也含「Nginx 5xx 排查」，断言一律收在页面主区，避免与侧栏文本混淆。 */
function main(): HTMLElement {
  return screen.getByRole('main')
}

function run_rows(): Promise<HTMLElement[]> {
  return within(main()).findAllByRole('button', { name: /Nginx 5xx 排查/ })
}

describe('RunsPage 最近调查', () => {
  it('展示跨会话 Run 安全摘要列表', async () => {
    open_runs()
    render(<App />)

    expect(await within(main()).findByRole('heading', { name: '最近调查' })).toBeInTheDocument()
    const rows = await run_rows()
    expect(rows.length).toBe(3)
    expect(within(rows[0]).getByText('成功')).toBeInTheDocument()
    expect(within(rows[1]).getByText('失败')).toBeInTheDocument()
    expect(within(rows[1]).getByText('诊断执行失败，请稍后重试')).toBeInTheDocument()
    expect(within(rows[2]).getByText('已取消')).toBeInTheDocument()
    expect(within(main()).getAllByText('未关联服务').length).toBe(2)
  })

  it('按状态过滤只展示匹配的调查', async () => {
    open_runs()
    render(<App />)
    await within(main()).findByRole('heading', { name: '最近调查' })

    fireEvent.click(within(main()).getByRole('button', { name: '失败' }))

    const rows = await run_rows()
    expect(rows.length).toBe(1)
    expect(within(rows[0]).getByText('失败')).toBeInTheDocument()
    expect(within(rows[0]).getByText('诊断执行失败，请稍后重试')).toBeInTheDocument()
  })

  it('按服务过滤只展示该服务的调查', async () => {
    open_runs()
    render(<App />)
    await within(main()).findByRole('heading', { name: '最近调查' })

    const service_select = within(main()).getByRole('combobox', { name: '按服务过滤调查' })
    await within(service_select).findByRole('option', { name: '订单服务靶场' })
    fireEvent.change(service_select, { target: { value: 'postgres-production' } })

    const rows = await run_rows()
    expect(rows.length).toBe(1)
    expect(within(rows[0]).getByText('失败')).toBeInTheDocument()
    expect(within(rows[0]).getByText('postgres-production')).toBeInTheDocument()
  })

  it('点击调查行进入既有 Run 详情', async () => {
    open_runs()
    render(<App />)
    await within(main()).findByRole('heading', { name: '最近调查' })

    fireEvent.click((await run_rows())[0])

    expect(window.location.pathname).toMatch(/^\/workbench\/sessions\/[^/]+\/runs\/[^/]+$/)
  })

  it('无匹配时显示诚实空态', async () => {
    server.use(
      http.get('/api/v1/runs', ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
    )
    open_runs()
    render(<App />)

    expect(await within(main()).findByText('当前筛选下还没有调查')).toBeInTheDocument()
  })
})
