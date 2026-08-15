import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_knowledge(): void {
  window.history.replaceState({}, '', '/knowledge')
}

function error_response(request: Request) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: null }, meta: { request_id } },
    { status: 500, headers: { 'X-Request-Id': request_id } },
  )
}

function paged_response(request: Request, items: Array<Record<string, string>>, page_size: number) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  const url = new URL(request.url)
  const cursor = url.searchParams.get('cursor')
  const filtered = cursor ? items.filter((item) => item.relative_path > cursor) : [...items]
  const page_items = filtered.slice(0, page_size)
  const next_cursor = page_items.length === page_size ? page_items[page_items.length - 1].relative_path : null
  return HttpResponse.json(
    {
      status: 'ok',
      items: page_items,
      page: { next_cursor, has_more: next_cursor !== null },
      meta: { request_id },
    },
    { status: 200, headers: { 'X-Request-Id': request_id } },
  )
}

describe('KnowledgePage', () => {
  it('导航入口可用并渲染文档列表与来源标注', async () => {
    open_knowledge()
    render(<App />)

    expect((await screen.findAllByText('文档知识库')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('受管知识目录 · 只读').length).toBeGreaterThan(0)
    expect(await screen.findByText('kill 慢查询 SOP')).toBeInTheDocument()
    expect(screen.getByText('索引优化手册')).toBeInTheDocument()
    expect(screen.getByText('sop/kill-slow-query.md')).toBeInTheDocument()
  })

  it('点击文档进入详情并返回列表', async () => {
    open_knowledge()
    render(<App />)

    fireEvent.click(await screen.findByText('kill 慢查询 SOP'))
    expect(await screen.findByText(/执行 kill 慢查询前先确认会话/)).toBeInTheDocument()
    expect(screen.getByText(/只读受管知识目录/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /返回文档列表/ }))
    expect(await screen.findByText('全部文档')).toBeInTheDocument()
  })

  it('页面内检索命中并展示片段', async () => {
    open_knowledge()
    render(<App />)

    const input = await screen.findByLabelText('检索知识文档')
    fireEvent.change(input, { target: { value: 'kill' } })
    fireEvent.click(screen.getByRole('button', { name: '检索' }))

    expect(await screen.findByText('检索结果')).toBeInTheDocument()
    expect(screen.getByText(/执行 kill 慢查询前先确认会话/)).toBeInTheDocument()
  })

  it('无匹配时显示诚实空态', async () => {
    open_knowledge()
    render(<App />)

    const input = await screen.findByLabelText('检索知识文档')
    fireEvent.change(input, { target: { value: '不存在的关键词' } })
    fireEvent.click(screen.getByRole('button', { name: '检索' }))

    expect(await screen.findByText('无匹配文档：请尝试更换检索词。')).toBeInTheDocument()
  })

  it('列表读取失败时显示失败空态并可重试', async () => {
    server.use(
      http.get('/api/v1/knowledge/documents', ({ request }) => error_response(request)),
    )
    open_knowledge()
    render(<App />)

    expect(await screen.findByText(/读取知识库失败/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  })

  it('目录超过页大小时按「加载更多」分页浏览且不误显空态', async () => {
    const docs = [
      { title: '数据库备份手册', relative_path: 'ops/db-backup.md' },
      { title: '故障应急手册', relative_path: 'ops/incident-runbook.md' },
      { title: '上线检查清单', relative_path: 'ops/release-checklist.md' },
    ]
    server.use(
      http.get('/api/v1/knowledge/documents', ({ request }) => paged_response(request, docs, 2)),
    )
    open_knowledge()
    render(<App />)

    // 首页只渲染第一页
    expect(await screen.findByText('数据库备份手册')).toBeInTheDocument()
    expect(screen.getByText('故障应急手册')).toBeInTheDocument()
    expect(screen.queryByText('上线检查清单')).not.toBeInTheDocument()

    // 点击「加载更多」追加第二页，末尾按钮消失
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('上线检查清单')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '加载更多' })).not.toBeInTheDocument()

    // 翻页到底后不误显「知识库为空」/「暂无文档」空态
    expect(screen.queryByText('知识库为空。')).not.toBeInTheDocument()
    expect(screen.queryByText(/暂无文档/)).not.toBeInTheDocument()
  })

  it('加载更多失败时诚实展示并可重试', async () => {
    const docs = [
      { title: '数据库备份手册', relative_path: 'ops/db-backup.md' },
      { title: '故障应急手册', relative_path: 'ops/incident-runbook.md' },
    ]
    server.use(
      http.get('/api/v1/knowledge/documents', ({ request }) => {
        const url = new URL(request.url)
        if (url.searchParams.get('cursor')) {
          return error_response(request)
        }
        return paged_response(request, docs, 1)
      }),
    )
    open_knowledge()
    render(<App />)

    expect(await screen.findByText('数据库备份手册')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText(/加载更多失败/)).toBeInTheDocument()

    // 修复后点「重试」恢复加载
    server.use(
      http.get('/api/v1/knowledge/documents', ({ request }) => paged_response(request, docs, 1)),
    )
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('故障应急手册')).toBeInTheDocument()
  })
})
