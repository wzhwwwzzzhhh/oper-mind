import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { api_v1_contract_fixtures } from '../../test/handlers'
import { server } from '../../test/server'

describe('WorkbenchPage P12 服务调查 intent', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('健康 intent 使用固定动作直接创建精确 service Run', async () => {
    let run_payload: Record<string, unknown> | undefined
    let plain_message_posts = 0
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({
        items: [{
          ...api_v1_contract_fixtures.order_service,
          supported_investigations: [{
            id: 'service_health_pressure.v1',
            title: 'PostgreSQL 健康与连接压力概览',
            description: '固定只读标量',
            default_query: '请对当前服务执行只读健康与连接压力调查。',
          }],
        }],
        meta: { request_id: '99999999-9999-4999-8999-999999999990' },
      })),
      http.post('/api/v1/sessions/:session_id/runs', async ({ request }) => {
        run_payload = await request.json() as Record<string, unknown>
        return HttpResponse.json({
          run: {
            id: '99999999-9999-4999-8999-999999999991',
            session_id: api_v1_contract_fixtures.service_session_id,
            trace_id: api_v1_contract_fixtures.trace_id,
            input_message_id: '99999999-9999-4999-8999-999999999992',
            service_id: 'postgres-production',
            rerun_of_run_id: null,
            status: 'queued',
            result: null,
            error: null,
            created_at: '2026-09-04T10:30:00.000Z',
            started_at: null,
            finished_at: null,
          },
          meta: { request_id: '99999999-9999-4999-8999-999999999993' },
        }, { status: 202 })
      }),
      http.post('/api/v1/sessions/:session_id/messages', () => {
        plain_message_posts += 1
        return new HttpResponse(null, { status: 500 })
      }),
    )
    window.history.replaceState(
      {},
      '',
      `/workbench/sessions/${api_v1_contract_fixtures.service_session_id}?intent=service_health_pressure.v1`,
    )
    render(<App />)

    expect(await screen.findByText(/将提交固定问题“请对当前服务执行只读健康与连接压力调查。/)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '调查问题' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '开始只读健康调查' }))

    await waitFor(() => expect(run_payload).toEqual({
      query: '请对当前服务执行只读健康与连接压力调查。',
      service_id: 'postgres-production',
    }))
    expect(plain_message_posts).toBe(0)
  })

  it('服务未声明健康 capability 时不因已知 URL intent 启动调查', async () => {
    window.history.replaceState(
      {},
      '',
      `/workbench/sessions/${api_v1_contract_fixtures.service_session_id}?intent=service_health_pressure.v1`,
    )
    render(<App />)

    expect(await screen.findByText('健康调查未启用')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始只读健康调查' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '调查问题' })).not.toBeInTheDocument()
  })

  it('已有其他待恢复调查时不复用其问题或幂等键', async () => {
    window.sessionStorage.setItem(
      `opermind:p3.6b:send-intent:${api_v1_contract_fixtures.service_session_id}`,
      JSON.stringify({
        created_at: '2026-09-04T10:30:00.000Z',
        endpoint: '/api/v1/sessions/{session_id}/runs',
        query: '这是之前尚未确认受理的调查。',
        runs: [{
          idempotency_key: '99999999-9999-4999-8999-999999999994',
          phase: 'acceptance_unknown',
          service_id: 'postgres-production',
        }],
        session_id: api_v1_contract_fixtures.service_session_id,
        version: 2,
      }),
    )
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({
        items: [{
          ...api_v1_contract_fixtures.order_service,
          supported_investigations: [{ id: 'service_health_pressure.v1' }],
        }],
        meta: { request_id: '99999999-9999-4999-8999-999999999995' },
      })),
    )
    window.history.replaceState(
      {},
      '',
      `/workbench/sessions/${api_v1_contract_fixtures.service_session_id}?intent=service_health_pressure.v1`,
    )
    render(<App />)

    expect(await screen.findByText('存在待恢复的其他调查')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始只读健康调查' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '丢弃旧发送意图' }))

    expect(await screen.findByRole('button', { name: '开始只读健康调查' })).toBeInTheDocument()
  })

  it('未知 intent 不自动创建调查内容', async () => {
    window.history.replaceState(
      {},
      '',
      `/workbench/sessions/${api_v1_contract_fixtures.service_session_id}?intent=tampered.v1`,
    )
    render(<App />)

    expect(await screen.findByRole('textbox', { name: '调查问题' })).toHaveValue('')
  })
})
