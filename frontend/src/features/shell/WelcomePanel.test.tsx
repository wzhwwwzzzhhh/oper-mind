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
})
