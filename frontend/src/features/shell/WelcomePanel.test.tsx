import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WelcomePanel } from './WelcomePanel'

describe('WelcomePanel', () => {
  it('允许多选已接入服务并回调 service_ids', () => {
    const on_service_change = vi.fn()

    render(
      <WelcomePanel
        on_prompt={vi.fn()}
        on_service_change={on_service_change}
        services={[
          { id: 'postgres-production', title: '生产 PostgreSQL 主库' },
          { id: 'postgres-staging', title: '预发布 PostgreSQL 主库' },
        ]}
      />,
    )

    fireEvent.click(screen.getByRole('checkbox', { name: '生产 PostgreSQL 主库' }))

    expect(on_service_change).toHaveBeenCalledWith(['postgres-production'])
  })

  it('服务数如实展示"已接入"（注册口径），不再写"在线"', () => {
    render(<WelcomePanel on_prompt={vi.fn()} service_count={2} />)

    expect(screen.getByText('2 个服务已接入 · 默认只读调查')).toBeInTheDocument()
    expect(screen.queryByText(/个服务在线/)).not.toBeInTheDocument()
  })

  it('没有传入服务数时默认 0，不写死 3', () => {
    render(<WelcomePanel on_prompt={vi.fn()} />)

    expect(screen.getByText('0 个服务已接入 · 默认只读调查')).toBeInTheDocument()
  })

  it('服务列表加载中/失败时如实展示，不冒充 0 个服务', () => {
    const { rerender } = render(<WelcomePanel on_prompt={vi.fn()} services_loading />)
    expect(screen.getByText('正在读取已接入服务… · 默认只读调查')).toBeInTheDocument()
    expect(screen.queryByText(/个服务已接入/)).not.toBeInTheDocument()

    rerender(<WelcomePanel on_prompt={vi.fn()} services_error />)
    expect(screen.getByText('服务列表暂不可读 · 默认只读调查')).toBeInTheDocument()
    expect(screen.getByText('服务列表暂不可读，稍后可重试')).toBeInTheDocument()
  })
})
