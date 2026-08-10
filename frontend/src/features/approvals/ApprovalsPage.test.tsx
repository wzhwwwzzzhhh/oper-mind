import { fireEvent, render, screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_approvals(): void {
  window.history.replaceState({}, '', '/workbench/approvals')
}

function response(request: Request, body: Record<string, unknown>, status = 200) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { ...body, meta: { request_id } },
    { status, headers: { 'Content-Type': 'application/json', 'X-Request-Id': request_id } },
  )
}

describe('ApprovalsPage', () => {
  it('按状态过滤只展示匹配的提案', async () => {
    open_approvals()
    render(<App />)

    expect(await screen.findByRole('heading', { name: '待审批提案' })).toBeInTheDocument()
    expect((await screen.findAllByText('等待审批')).length).toBe(1)
    expect(screen.queryByText('验证通过')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(await screen.findByText('验证通过')).toBeInTheDocument()
    expect(screen.getAllByText('重建受控靶场联合索引').length).toBeGreaterThanOrEqual(2)
  })

  it('空列表显示诚实空态而不伪造', async () => {
    server.use(
      http.get('/api/v1/action-proposals', ({ request }) =>
        response(request, { items: [], page: { next_cursor: null, has_more: false } }),
      ),
    )
    open_approvals()
    render(<App />)

    expect(await screen.findByText('当前筛选下没有提案')).toBeInTheDocument()
  })
})
