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
})
