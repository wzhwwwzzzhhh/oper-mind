import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'
import { api_v1_contract_fixtures } from '../../test/handlers'

function open_monitor(): void {
  window.history.replaceState({}, '', '/monitor')
}

describe('MonitoringOverviewPage 服务监控概览（P7）', () => {
  it('展示全部已接入服务与逐服务诚实状态（AC1/AC2/AC4）', async () => {
    open_monitor()
    render(<App />)

    expect(await screen.findByText('订单服务靶场')).toBeInTheDocument()
    expect(screen.getByText('生产 Redis 缓存')).toBeInTheDocument()
    expect(screen.getByText('可用')).toBeInTheDocument()
    expect(screen.getAllByText('未配置').length).toBeGreaterThan(0)
    expect(screen.getByText('3 条 · 1 次')).toBeInTheDocument()
  })

  it('异常采样点标记为"采样点异常"而非告警（AC6）', async () => {
    open_monitor()
    render(<App />)

    expect(await screen.findByText('采样点异常')).toBeInTheDocument()
    expect(screen.getByText('12 个采样点')).toBeInTheDocument()
    expect(screen.queryByText(/正在告警/)).not.toBeInTheDocument()
    expect(screen.queryByText(/正在推送/)).not.toBeInTheDocument()
  })

  it('诚实标注数据来源且不含"实时监控"表述（AC5）', async () => {
    open_monitor()
    render(<App />)

    expect(await screen.findByText(/定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录/)).toBeInTheDocument()
    expect(screen.queryByText(/实时监控/)).not.toBeInTheDocument()
  })

  it('概览接口失败时显示失败空态并可重试（AC9）', async () => {
    server.use(
      http.get('/api/v1/monitor/overview', () =>
        HttpResponse.json(
          { error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试' } },
          { status: 500 },
        ),
      ),
    )
    open_monitor()
    render(<App />)

    expect(await screen.findByText('暂时无法读取监控概览')).toBeInTheDocument()
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  it('概览行可进入对应服务详情页（AC7）', async () => {
    open_monitor()
    render(<App />)

    const row = await screen.findByText('订单服务靶场')
    row.click()

    expect(await screen.findByText('当前健康概览')).toBeInTheDocument()
  })

  it('概览接口仅展示脱敏标量，不含敏感字段（AC8）', async () => {
    open_monitor()
    render(<App />)

    expect(await screen.findByText('订单服务靶场')).toBeInTheDocument()
    const raw = JSON.stringify(api_v1_contract_fixtures.service_monitor_overview).toLowerCase()
    for (const sensitive of ['password', 'dsn=', 'sk-', 'select ', 'username']) {
      expect(raw).not.toContain(sensitive)
    }
  })
})
