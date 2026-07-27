import { render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from './App'
import { api_v1_contract_fixtures } from '../test/handlers'
import { server } from '../test/server'

function open_path(path: string): void {
  window.history.replaceState({}, '', path)
}

let request_paths: string[] = []

server.events.on('request:start', ({ request }) => {
  const path = new URL(request.url).pathname
  if (path.startsWith('/api/v1/')) request_paths.push(path)
})

describe('App', () => {
  beforeEach(() => {
    request_paths = []
    open_path('/workbench')
  })

  it('从 v1 active Session 列表恢复工作台入口', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '诊断工作台' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(screen.getByText('环境与数据源：待 P4')).toBeInTheDocument()
  })

  it('按 Session、Runs、Message、Run 的顺序恢复 Run 深链', async () => {
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Nginx 5xx 排查/ })).toBeInTheDocument()
    expect(await screen.findByText('请检查 Nginx 5xx。')).toBeInTheDocument()
    expect(await screen.findByText('结构化结果待展示')).toBeInTheDocument()
    await waitFor(() =>
      expect(request_paths).toEqual([
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/runs`,
        `/api/v1/sessions/${api_v1_contract_fixtures.session_id}/messages`,
        `/api/v1/runs/${api_v1_contract_fixtures.run_id}`,
      ]),
    )
    expect(
      screen.getByText('Run 受理与实时事件待 P3.3，结构化结果视觉待 P3.4；完整 Agent Trace 仍只在研发界面可用。'),
    ).toBeInTheDocument()
  })

  it('Session 不存在时只显示安全读取错误', async () => {
    open_path('/workbench/sessions/not-found')
    render(<App />)

    expect(await screen.findByRole('heading', { name: '无法恢复诊断会话' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('SESSION_NOT_FOUND：会话不存在')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /创建/i })).not.toBeInTheDocument()
  })

  it('Runs 恢复失败时不把下游资源伪造成空状态', async () => {
    server.use(
      http.get(/\/api\/v1\/sessions\/[^/]+\/runs$/, ({ request }) =>
        HttpResponse.json(
          {
            error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: {} },
            meta: { request_id: request.headers.get('X-Request-Id') },
          },
          { status: 500 },
        ),
      ),
    )
    open_path(
      `/workbench/sessions/${api_v1_contract_fixtures.session_id}/runs/${api_v1_contract_fixtures.run_id}`,
    )
    render(<App />)

    expect(await screen.findByText('INTERNAL_ERROR：服务内部错误，请稍后重试')).toBeInTheDocument()
    expect(screen.getByText('等待诊断运行恢复完成后再读取会话消息。')).toBeInTheDocument()
    expect(screen.getByText('等待会话消息恢复完成后再读取当前 Run。')).toBeInTheDocument()
    expect(screen.queryByText('该会话还没有消息')).not.toBeInTheDocument()
  })
})
