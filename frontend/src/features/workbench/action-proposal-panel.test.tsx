import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

const api_mocks = vi.hoisted(() => ({
  get_run_action_proposal: vi.fn(),
  list_action_events: vi.fn(),
  decide_action_proposal: vi.fn(),
  request_action_execution: vi.fn(),
}))

vi.mock('../../api/v1/client', () => ({
  ApiClientError: class ApiClientError extends Error {},
  api_v1_client: api_mocks,
}))

import { ActionProposalPanel } from './ActionProposalPanel'

function render_panel(): ReactElement {
  const query_client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={query_client}>
      <ActionProposalPanel run_id="run-p4-2" />
    </QueryClientProvider>
  )
}

describe('ActionProposalPanel', () => {
  it('只显示脱敏的固定修复与 Verify 事实，不渲染 SQL、request id 或原始日志', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-p4-2',
          status: 'verified',
          mode: 'mock',
          title: '重建订单查询联合索引',
          description: '固定修复语义说明。',
          target: { service: 'order-service', scope: '订单慢查询受控靶场' },
          risk_summary: '验证失败不会自动回滚。',
          verification_plan: ['索引和固定计划。', '固定探测三次。', '匹配日志聚合。'],
          verification: {
            status: 'verified',
            summary: '模拟 Verify 已通过；未连接真实数据库、服务或日志。',
            facts: { probe_count: 3, matched_log_count: 3, target_index_exists: true },
          },
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({
      data: {
        items: [{
          sequence: 1,
          type: 'verification_completed',
          data: { status: 'verified', mode: 'mock', summary: '模拟 Verify 已通过。' },
        }],
      },
    })

    render(render_panel())

    expect(await screen.findByText('固定修复提案')).toBeInTheDocument()
    expect(screen.getByText('模拟模式：不含真实 DDL')).toBeInTheDocument()
    expect(screen.getByText('Verify 脱敏事实')).toBeInTheDocument()
    expect(screen.getByText('固定修复语义说明。')).toBeInTheDocument()
    expect(screen.queryByText(/CREATE INDEX/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/request_id/i)).not.toBeInTheDocument()
  })
})
