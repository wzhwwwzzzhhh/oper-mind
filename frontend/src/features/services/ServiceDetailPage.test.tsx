import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'
import {
  api_v1_contract_fixtures,
  reset_stored_monitor_thresholds,
} from '../../test/handlers'

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

describe('ServiceDetailPage 监控阈值配置区（P8，issue #77）', () => {
  beforeEach(() => {
    reset_stored_monitor_thresholds()
  })

  it('未配置服务回显内置默认规则并诚实标注来源（AC1/AC9）', async () => {
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('未配置阈值，当前使用内置默认规则（出现即异常）。')).toBeInTheDocument()
    expect(screen.getByText('监控阈值')).toBeInTheDocument()
    expect(screen.getByText('内置默认')).toBeInTheDocument()
    expect(screen.getByText('慢查询计数')).toBeInTheDocument()
    expect(screen.getByText('超时计数')).toBeInTheDocument()
    expect(screen.getByText('慢日志计数')).toBeInTheDocument()
    const spinbuttons = screen.getAllByRole('spinbutton')
    expect(spinbuttons).toHaveLength(3)
    expect((spinbuttons[0] as HTMLInputElement).value).toBe('1')
    expect((spinbuttons[1] as HTMLInputElement).value).toBe('1')
    expect((spinbuttons[2] as HTMLInputElement).value).toBe('1')
  })

  it('已配置服务回显已保存规则并标注已配置（AC9）', async () => {
    server.use(
      http.get('/api/v1/services/postgres-production/monitor/thresholds', () =>
        HttpResponse.json({
          service_id: 'postgres-production',
          source: 'configured',
          config: {
            slow_query_count_threshold: 3,
            timeout_count_threshold: null,
            slowlog_count_threshold: 2,
            window_minutes: 10,
            count_availability_change: false,
          },
          meta: { request_id: 'test-configured-thresholds' },
        }),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('以下为保存后的生效规则，保存即生效。')).toBeInTheDocument()
    expect(screen.getByText('监控阈值')).toBeInTheDocument()
    expect(screen.getByText('已配置')).toBeInTheDocument()
    const spinbuttons = screen.getAllByRole('spinbutton')
    expect((spinbuttons[0] as HTMLInputElement).value).toBe('3')
    expect((spinbuttons[1] as HTMLInputElement).value).toBe('0')
    expect((spinbuttons[2] as HTMLInputElement).value).toBe('2')
    const window_select = screen.getByDisplayValue('10 分钟')
    expect(window_select).toBeInTheDocument()
  })

  it('编辑阈值并保存成功后提示已保存，来源转为已配置（AC9）', async () => {
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('未配置阈值，当前使用内置默认规则（出现即异常）。')).toBeInTheDocument()
    expect(screen.getByText('内置默认')).toBeInTheDocument()

    const spinbuttons = screen.getAllByRole('spinbutton')
    fireEvent.change(spinbuttons[0], { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并生效' }))

    expect(await screen.findByText('已保存，概览与趋势按新规则计算。')).toBeInTheDocument()
    expect(await screen.findByText('已配置')).toBeInTheDocument()
    expect((screen.getAllByRole('spinbutton')[0] as HTMLInputElement).value).toBe('3')
  })

  it('保存失败时诚实提示后端错误，不伪装成功（AC9）', async () => {
    server.use(
      http.put('/api/v1/services/postgres-production/monitor/thresholds', () =>
        HttpResponse.json(
          {
            error: { code: 'VALIDATION_ERROR', message: '判定窗口必须在 0 到 1440 分钟之间', details: null },
            meta: { request_id: 'test-threshold-422' },
          },
          { status: 422 },
        ),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('未配置阈值，当前使用内置默认规则（出现即异常）。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存并生效' }))

    expect(await screen.findByText('判定窗口必须在 0 到 1440 分钟之间')).toBeInTheDocument()
    expect(screen.queryByText('已保存，概览与趋势按新规则计算。')).not.toBeInTheDocument()
  })

  it('阈值读取失败时保持诚实空态，不展示示例规则（AC9）', async () => {
    server.use(
      http.get('/api/v1/services/postgres-production/monitor/thresholds', () =>
        HttpResponse.json(
          {
            error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: null },
            meta: { request_id: 'test-threshold-error' },
          },
          { status: 500 },
        ),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('暂时无法读取监控阈值配置')).toBeInTheDocument()
    expect(screen.queryByText('保存并生效')).not.toBeInTheDocument()
  })

  it('配置阈值后运行趋势异常标记按配置复算，与后端一致（AC5）', async () => {
    server.use(
      http.get('/api/v1/services/postgres-production/monitor/history', () =>
        HttpResponse.json({
          service_id: 'postgres-production',
          status: 'available',
          source: 'scheduled_sampling',
          sample_interval_seconds: 300,
          retention_hours: 24,
          from: '2026-07-31T02:40:00.000Z',
          to: '2026-07-31T03:00:00.000Z',
          samples: [
            { id: 'dddddddd-dddd-4ddd-8ddd-ddddddddddf1', service_id: 'postgres-production', observed_at: '2026-07-31T02:50:00.000Z', availability: 'healthy', p50_ms: 10, p95_ms: 20, slow_query_count: 1, timeout_count: 0, memory_bytes: null, client_connections: null, slowlog_count: null, performance_signal: 'no_slow_query_detected', source_status: 'available' },
            { id: 'dddddddd-dddd-4ddd-8ddd-ddddddddddf2', service_id: 'postgres-production', observed_at: '2026-07-31T02:55:00.000Z', availability: 'healthy', p50_ms: 10, p95_ms: 20, slow_query_count: 2, timeout_count: 0, memory_bytes: null, client_connections: null, slowlog_count: null, performance_signal: 'slow_query_detected', source_status: 'available' },
          ],
          meta: { request_id: 'test-trend-config' },
        }),
      ),
      http.get('/api/v1/services/postgres-production/monitor/thresholds', () =>
        HttpResponse.json({
          service_id: 'postgres-production',
          source: 'configured',
          config: {
            slow_query_count_threshold: 3,
            timeout_count_threshold: null,
            slowlog_count_threshold: null,
            window_minutes: 10,
            count_availability_change: false,
          },
          meta: { request_id: 'test-trend-config' },
        }),
      ),
    )
    open_service('postgres-production')
    render(<App />)

    expect(await screen.findByText('采样点异常')).toBeInTheDocument()
    // 窗口 10 分钟聚合：仅 02:55 采样点（1+2=3 ≥ 3）计为异常，02:50（1 < 3）不计。
    expect(screen.getByText(/02:55 · 慢查询 3/)).toBeInTheDocument()
    expect(screen.queryByText(/02:50 · /)).not.toBeInTheDocument()
  })
})
