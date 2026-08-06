import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('展示受控靶场 target 模式和人工审批边界', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-p5-target',
          status: 'pending_approval',
          mode: 'target',
          title: '重建受控靶场联合索引',
          description: '只对受控靶场固定目标执行代码内联合索引动作。',
          target: {
            service_id: 'postgres-target',
            schema: 'public',
            table: 'orders',
            columns: 'customer_id,created_at',
            index_name: 'idx_orders_customer_created_at',
          },
          risk_summary: '这是受控靶场结构变更；生产和预发布实例不会执行。',
          verification_plan: ['确认受控靶场目标表存在', '确认固定联合索引存在且有效', '只读执行计划确认固定索引可用'],
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })

    render(render_panel())

    expect(await screen.findByText('受控靶场 target 模式')).toBeInTheDocument()
    expect(screen.getByText('postgres-target')).toBeInTheDocument()
    expect(screen.getByText('批准固定修复')).toBeInTheDocument()
    expect(screen.getByText(/当前没有多用户身份或 RBAC/)).toBeInTheDocument()
    expect(screen.queryByText(/CREATE INDEX/i)).not.toBeInTheDocument()
  })

  it('通过人工审批和二次确认调用既有 action API', async () => {
    api_mocks.get_run_action_proposal
      .mockResolvedValueOnce({
        data: {
          proposal: {
            id: 'proposal-p5-flow', status: 'pending_approval', mode: 'target',
            title: '重建受控靶场联合索引', description: '固定动作',
            target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
          },
        },
      })
      .mockResolvedValue({
        data: {
          proposal: {
            id: 'proposal-p5-flow', status: 'approved', mode: 'target',
            title: '重建受控靶场联合索引', description: '固定动作',
            target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
          },
        },
      })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })
    api_mocks.decide_action_proposal.mockResolvedValue({ data: {} })
    api_mocks.request_action_execution.mockResolvedValue({ data: {} })

    render(render_panel())
    fireEvent.click(await screen.findByText('批准固定修复'))
    fireEvent.click(screen.getByText('确认批准'))
    await waitFor(() => expect(api_mocks.decide_action_proposal).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByText('执行固定修复')).toBeInTheDocument())
    fireEvent.click(screen.getByText('执行固定修复'))
    fireEvent.click(screen.getByText('确认执行'))
    await waitFor(() => expect(api_mocks.request_action_execution).toHaveBeenCalledTimes(1))
  })
})
