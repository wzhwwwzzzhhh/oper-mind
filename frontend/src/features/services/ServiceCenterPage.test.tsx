import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'
import { api_v1_contract_fixtures } from '../../test/handlers'

function open_service_center(): void {
  window.history.replaceState({}, '', '/services')
}

describe('ServiceCenterPage 服务注册（P8）', () => {
  it('列表展示掩码尾号与已配置状态（AC1/AC4）', async () => {
    const service = {
      ...api_v1_contract_fixtures.order_service,
      has_dsn: true,
      dsn_masked_tail: 'ders',
    }
    server.use(http.get('/api/v1/services', () => HttpResponse.json({ items: [service], meta: { request_id: 't1' } })))
    open_service_center()
    render(<App />)

    expect(await screen.findByText('订单服务靶场')).toBeInTheDocument()
    expect(screen.getByText(/DSN 已存 · 尾号 ders/)).toBeInTheDocument()
  })

  it('添加服务表单提交并即时出现在列表（AC1）', async () => {
    let items: object[] = []
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({ items, meta: { request_id: 'c1' } })),
      http.post('/api/v1/services', async ({ request }) => {
        const payload = await request.json() as Record<string, unknown>
        const item = {
          ...api_v1_contract_fixtures.order_service,
          id: payload.instance_id,
          title: payload.title,
          kind: payload.kind,
          has_dsn: true,
          dsn_masked_tail: String(payload.dsn).slice(-4),
        }
        items = [item]
        return HttpResponse.json({ service: item, meta: { request_id: 'c2' } }, { status: 201 })
      }),
    )
    open_service_center()
    render(<App />)

    await screen.findByText('服务目录')
    fireEvent.click(screen.getByText('＋ 添加服务'))

    fireEvent.change(screen.getByLabelText('实例 ID'), { target: { value: 'postgres-orders' } })
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '订单 PostgreSQL' } })
    fireEvent.change(screen.getByLabelText('DSN'), { target: { value: 'postgresql://u:p@127.0.0.1:5432/orders' } })
    fireEvent.click(screen.getByRole('button', { name: '接入服务' }))

    await waitFor(() => {
      expect(screen.getByText('服务已接入。')).toBeInTheDocument()
    })
    expect(screen.getByText('订单 PostgreSQL')).toBeInTheDocument()
  })

  it('测试连接反馈不可达（AC7）', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({ items: [api_v1_contract_fixtures.order_service], meta: { request_id: 't2' } })),
      http.post('/api/v1/services/postgres-production/test-connection', () =>
        HttpResponse.json({ service_id: 'postgres-production', availability: 'unavailable', error_code: 'connection_failed', meta: { request_id: 't3' } }),
      ),
    )
    open_service_center()
    render(<App />)

    await screen.findByText('订单服务靶场')
    fireEvent.click(screen.getByText('测试连接'))

    await waitFor(() => {
      expect(screen.getByText(/连接测试：不可达/)).toBeInTheDocument()
    })
  })

  it('编辑服务提交更新（AC5）', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({ items: [api_v1_contract_fixtures.order_service], meta: { request_id: 't4' } })),
      http.put('/api/v1/services/postgres-production', () =>
        HttpResponse.json({ service: { ...api_v1_contract_fixtures.order_service, title: '订单库已换', has_dsn: true, dsn_masked_tail: 'ouse' }, meta: { request_id: 't5' } }),
      ),
    )
    open_service_center()
    render(<App />)

    await screen.findByText('订单服务靶场')
    fireEvent.click(screen.getByText('编辑'))

    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '订单库已换' } })
    fireEvent.click(screen.getByText('保存修改'))

    await waitFor(() => {
      expect(screen.getByText('服务已更新。')).toBeInTheDocument()
    })
  })

  it('移除服务确认后从列表消失（AC6）', async () => {
    let deleted = false
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json({ items: deleted ? [] : [api_v1_contract_fixtures.order_service], meta: { request_id: 't6' } })),
      http.delete('/api/v1/services/postgres-production', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    open_service_center()
    render(<App />)

    await screen.findByText('订单服务靶场')
    fireEvent.click(screen.getByText('移除'))
    fireEvent.click(screen.getByText('确认移除'))

    await waitFor(() => {
      expect(screen.getByText('服务已移除。')).toBeInTheDocument()
    })
    expect(screen.queryByText('订单服务靶场')).not.toBeInTheDocument()
  })
})
