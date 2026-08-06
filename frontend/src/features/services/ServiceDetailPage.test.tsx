import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'
import { api_v1_contract_fixtures } from '../../test/handlers'

function open_service(service_id: string): void {
  window.history.replaceState({}, '', `/services/${encodeURIComponent(service_id)}`)
}

describe('ServiceDetailPage 主机指标（P6）', () => {
  it('挂载时展示主机当前状态与异常进程，并标注单主机采集范围（AC1）', async () => {
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('主机指标')).toBeInTheDocument()
    expect(screen.getByText('CPU 使用率')).toBeInTheDocument()
    expect(screen.getByText('92 %')).toBeInTheDocument()
    expect(screen.getByText('81 %')).toBeInTheDocument()
    expect(screen.getByText('70 %')).toBeInTheDocument()
    expect(screen.getByText('异常进程（2 个）')).toBeInTheDocument()
    expect(screen.getByText(/mysqld/)).toBeInTheDocument()
    expect(screen.getByText(/java/)).toBeInTheDocument()
    expect(screen.getByText('后端所在主机（单主机）')).toBeInTheDocument()
    expect(screen.getByText('演示场景')).toBeInTheDocument()
  })

  it('主机指标不可用时展示诚实不可用状态，不伪造数值（AC2/AC4）', async () => {
    const unavailable = {
      ...api_v1_contract_fixtures.order_service,
      host_metrics: {
        mode: 'target',
        source_status: 'unavailable',
        observed_at: '2026-08-06T03:00:00.000Z',
        cpu_percent: null,
        cpu_count: null,
        load_avg_1m: null,
        memory_total_bytes: null,
        memory_used_bytes: null,
        memory_percent: null,
        disk_used_percent: null,
        disk_top_partitions: [],
        network_connections: null,
        network_established: null,
        network_time_wait: null,
        abnormal_processes: [],
      },
    }
    server.use(
      http.get('/api/v1/services/postgres-production', () =>
        HttpResponse.json({ service: unavailable, meta: { request_id: 'test-host-unavailable' } }),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('主机指标不可用')).toBeInTheDocument()
    expect(screen.queryByText('92 %')).not.toBeInTheDocument()
  })

  it('历史采样包含主机走势轨道（AC3）', async () => {
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('主机 CPU')).toBeInTheDocument()
    expect(screen.getByText('主机内存')).toBeInTheDocument()
    expect(screen.getByText('主机磁盘')).toBeInTheDocument()
  })

  it('后端未返回主机指标时保持诚实空态，不展示示例数据', async () => {
    const { host_metrics: _omitted_host, ...no_host } = api_v1_contract_fixtures.order_service
    server.use(
      http.get('/api/v1/services/postgres-production', () =>
        HttpResponse.json({ service: no_host, meta: { request_id: 'test-no-host' } }),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('后端未返回主机指标，不展示示例数据。')).toBeInTheDocument()
    expect(screen.queryByText('92 %')).not.toBeInTheDocument()
  })
})
