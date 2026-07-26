import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/workbench')
  })

  it('展示不伪造会话数据的工作台外壳', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: '诊断工作台' })).toBeInTheDocument()
    expect(screen.getByText('尚未接入会话数据')).toBeInTheDocument()
    expect(screen.getByText('环境与数据源：待 P4')).toBeInTheDocument()
  })
})