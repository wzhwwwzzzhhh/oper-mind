import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from '../../app/App'
import { api_v1_contract_fixtures } from '../../test/handlers'

describe('WorkbenchPage P12 服务调查 intent', () => {
  it('只接受已知健康 intent 并预填固定问题', async () => {
    window.history.replaceState(
      {},
      '',
      `/workbench/sessions/${api_v1_contract_fixtures.service_session_id}?intent=service_health_pressure.v1`,
    )
    render(<App />)

    expect(await screen.findByRole('textbox', { name: '调查问题' })).toHaveValue(
      '请对当前服务执行只读健康与连接压力调查。',
    )
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
