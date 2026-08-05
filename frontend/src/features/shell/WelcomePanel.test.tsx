import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { WelcomePanel } from './WelcomePanel'

describe('WelcomePanel', () => {
  it('允许选择已接入服务并回调 service_id', () => {
    const on_service_change = vi.fn()

    render(
      <WelcomePanel
        on_prompt={vi.fn()}
        on_service_change={on_service_change}
        services={[{ id: 'postgres-production', title: '生产 PostgreSQL 主库' }]}
      />,
    )

    fireEvent.change(screen.getByRole('combobox', { name: '调查目标服务' }), {
      target: { value: 'postgres-production' },
    })

    expect(on_service_change).toHaveBeenCalledWith('postgres-production')
  })
})
