import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_audit(): void {
  window.history.replaceState({}, '', '/audit')
}

describe('AuditPage 审计操作记录（P8）', () => {
  it('审计入口可达并展示活动列表（AC10）', async () => {
    open_audit()
    render(<App />)

    // 页面标题与第二栏入口
    expect(await screen.findByRole('heading', { level: 1, name: '审计操作记录' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '审计操作记录' })).toBeInTheDocument()
    // 等待列表加载（审批摘要文本只出现在行内，无下拉 option 重复）
    expect(await screen.findByText('本地操作者已批准固定修复。')).toBeInTheDocument()
    // 三类活动行（类型标签与过滤下拉共享文案，故按出现次数断言）
    expect(screen.getAllByText('审批已记录').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('提案已生成').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('调查完成').length).toBeGreaterThanOrEqual(2)
    // 三行共享同一会话标题
    expect(screen.getAllByText('订单服务慢查询调查').length).toBe(3)
    // 脱敏摘要与诚实来源声明
    expect(screen.getByText('已确认固定慢查询根因。')).toBeInTheDocument()
    expect(screen.getByText(/不含原始证据、工具输出与凭据/)).toBeInTheDocument()
  })

  it('审批人字段如实展示"未记录"（AC7）', async () => {
    open_audit()
    render(<App />)

    expect(await screen.findByText('审批人：未记录')).toBeInTheDocument()
  })

  it('空列表显示诚实空态（AC8）', async () => {
    server.use(
      http.get('/api/v1/audit/activities', () =>
        HttpResponse.json({ items: [], page: { next_cursor: null, has_more: false }, meta: {} }),
      ),
    )
    open_audit()
    render(<App />)

    expect(await screen.findByText('当前过滤条件下没有活动记录。')).toBeInTheDocument()
  })

  it('接口失败显示失败空态并可重试（AC10）', async () => {
    server.use(
      http.get('/api/v1/audit/activities', () =>
        HttpResponse.json(
          { error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试' } },
          { status: 500 },
        ),
      ),
    )
    open_audit()
    render(<App />)

    expect(await screen.findByText('暂时无法读取审计活动')).toBeInTheDocument()
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  it('类型过滤请求携带 action_type 参数（AC4 前端接线）', async () => {
    let requested: URLSearchParams | null = null
    server.use(
      http.get('/api/v1/audit/activities', ({ request }) => {
        requested = new URL(request.url).searchParams
        return HttpResponse.json({ items: [], page: { next_cursor: null, has_more: false }, meta: {} })
      }),
    )
    open_audit()
    render(<App />)

    const select = await screen.findByLabelText('类型过滤')
    fireEvent.change(select, { target: { value: 'run_completed' } })

    await waitFor(() => expect(requested?.get('action_type')).toBe('run_completed'))
  })

  it('run 行点击进入 Run 详情（AC10）', async () => {
    open_audit()
    render(<App />)

    const summary = await screen.findByText('已确认固定慢查询根因。')
    summary.closest('button')?.click()

    await waitFor(() => {
      expect(window.location.pathname).toBe(
        '/workbench/sessions/44444444-4444-4444-8444-444444444444/runs/44444444-4444-4444-8444-444444444445',
      )
    })
  })

  it('action 行点击进入提案详情（AC10）', async () => {
    open_audit()
    render(<App />)

    const summary = await screen.findByText('本地操作者已批准固定修复。')
    summary.closest('button')?.click()

    await waitFor(() => {
      expect(window.location.pathname).toBe('/workbench/approvals/cccccccc-cccc-4ccc-8ccc-ccccccccccc1')
    })
  })
})
