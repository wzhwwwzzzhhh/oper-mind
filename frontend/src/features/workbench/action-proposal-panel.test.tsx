import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

const api_mocks = vi.hoisted(() => ({
  get_run_action_proposal: vi.fn(),
  get_action_proposal: vi.fn(),
  list_action_events: vi.fn(),
  decide_action_proposal: vi.fn(),
  request_action_execution: vi.fn(),
  rerun_run: vi.fn(),
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

  it('批准/执行提交期间按钮进入 loading（请求未决）', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-loading', status: 'pending_approval', mode: 'target',
          title: '重建受控靶场联合索引', description: '固定动作',
          target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })
    let resolve_approve: (value: { data: object }) => void = () => {}
    api_mocks.decide_action_proposal.mockImplementation(() => new Promise((resolve) => {
      resolve_approve = resolve
    }))

    render(render_panel())
    fireEvent.click(await screen.findByText('批准固定修复'))
    fireEvent.click(screen.getByText('确认批准'))
    await waitFor(() => expect(api_mocks.decide_action_proposal).toHaveBeenCalledTimes(1))
    // 二次确认弹窗的确认按钮进入 loading（spinner），且按钮被禁用。
    expect(screen.getByText('确认批准').closest('.ui-btn')?.querySelector('.ui-btn__spinner')).not.toBeNull()
    expect(screen.getByText('确认批准').closest('.ui-btn')?.getAttribute('disabled')).not.toBeNull()
    resolve_approve({ data: {} })
    await waitFor(() => expect(screen.queryByText('确认批准')).not.toBeInTheDocument())
  })

  it('失败态提供"重新发起调查"入口并调用既有 rerun API（取 source_run_id 优先）', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-failed', source_run_id: 'run-source-abc', status: 'failed', mode: 'target',
          title: '重建受控靶场联合索引', description: '固定动作',
          target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
          failure_message: '固定修复执行失败，未自动回滚。',
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })
    api_mocks.rerun_run.mockResolvedValue({ data: { run: { id: 'run-reran' } } })

    render(render_panel())

    expect(await screen.findByText('该提案不能重试')).toBeInTheDocument()
    fireEvent.click(screen.getByText('重新发起调查'))
    await waitFor(() => expect(api_mocks.rerun_run).toHaveBeenCalledTimes(1))
    // 面板以 run_id="run-p4-2" 打开，但提案回传 source_run_id 不同，应优先使用 source_run_id。
    expect(api_mocks.rerun_run).toHaveBeenCalledWith('run-source-abc', expect.objectContaining({ idempotency_key: expect.any(String) }))
    expect(await screen.findByText('已重新发起调查')).toBeInTheDocument()
  })

  it('rejected/expired/blocked 终态同样提供"重新发起调查"入口', async () => {
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })
    const failure_by_status: Record<string, string | undefined> = {
      rejected: undefined,
      expired: '批准已过期，请重新调查后生成新提案。',
      blocked: '执行被安全拦截：前置条件不满足。',
    }
    for (const status of ['rejected', 'expired', 'blocked'] as const) {
      api_mocks.get_run_action_proposal.mockResolvedValue({
        data: {
          proposal: {
            id: `proposal-${status}`, source_run_id: 'run-source-def', status, mode: 'target',
            title: '重建受控靶场联合索引', description: '固定动作',
            target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
            failure_message: failure_by_status[status],
          },
        },
      })
      const { unmount } = render(render_panel())
      expect(await screen.findByText('重建受控靶场联合索引')).toBeInTheDocument()
      // 三种终态都必须给出"重新发起调查"入口。
      expect(screen.getByText('重新发起调查')).toBeInTheDocument()
      if (status === 'rejected') {
        // rejected 无 failure_message：不显示失败 Alert，而显示诚实的中性说明。
        expect(screen.queryByText('该提案不能重试')).not.toBeInTheDocument()
        expect(screen.getByText(/提案已被拒绝；可重新发起调查以生成新提案/)).toBeInTheDocument()
      } else {
        // expired/blocked 有 failure_message：保留"该提案不能重试"失败提示。
        expect(screen.getByText('该提案不能重试')).toBeInTheDocument()
      }
      unmount()
    }
  })

  it('执行期间二次确认按钮进入 loading（请求未决）', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-execute-loading', status: 'approved', mode: 'target',
          title: '重建受控靶场联合索引', description: '固定动作',
          target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })
    let resolve_execute: (value: { data: object }) => void = () => {}
    api_mocks.request_action_execution.mockImplementation(() => new Promise((resolve) => {
      resolve_execute = resolve
    }))

    render(render_panel())
    fireEvent.click(await screen.findByText('执行固定修复'))
    fireEvent.click(screen.getByText('确认执行'))
    await waitFor(() => expect(api_mocks.request_action_execution).toHaveBeenCalledTimes(1))
    expect(screen.getByText('确认执行').closest('.ui-btn')?.querySelector('.ui-btn__spinner')).not.toBeNull()
    expect(screen.getByText('确认执行').closest('.ui-btn')?.getAttribute('disabled')).not.toBeNull()
    resolve_execute({ data: {} })
    await waitFor(() => expect(screen.queryByText('确认执行')).not.toBeInTheDocument())
  })

  it('终态失败但缺少来源 Run 时给出诚实警告，不渲染入口', async () => {
    api_mocks.get_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-no-source', status: 'failed', mode: 'target',
          title: '重建受控靶场联合索引', description: '固定动作',
          target: { service_id: 'postgres-target' }, risk_summary: '仅限靶场', verification_plan: ['独立 Verify'],
          failure_message: '固定修复执行失败，未自动回滚。',
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })

    const query_client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={query_client}>
        <ActionProposalPanel proposal_id="proposal-no-source" />
      </QueryClientProvider>,
    )

    expect(await screen.findByText('缺少来源 Run')).toBeInTheDocument()
    expect(screen.queryByText('重新发起调查')).not.toBeInTheDocument()
  })

  it('字段缺失时按可用字段降级渲染，不整卡消失', async () => {
    api_mocks.get_run_action_proposal.mockResolvedValue({
      data: {
        proposal: {
          id: 'proposal-partial',
          status: 'pending_approval',
          // title/description/target/risk_summary/verification_plan 缺失
        },
      },
    })
    api_mocks.list_action_events.mockResolvedValue({ data: { items: [] } })

    render(render_panel())

    expect(await screen.findByText('固定修复提案')).toBeInTheDocument()
    expect(screen.getByText('模式未返回')).toBeInTheDocument()
    expect(screen.getByText('（服务端未返回标题）')).toBeInTheDocument()
    expect(screen.getByText('（服务端未返回描述）')).toBeInTheDocument()
    expect(screen.getByText('（服务端未返回固定边界）')).toBeInTheDocument()
    expect(screen.getByText('（服务端未返回风险说明）')).toBeInTheDocument()
    expect(screen.getByText('（服务端未返回验证计划）')).toBeInTheDocument()
    expect(screen.getByText('批准固定修复')).toBeInTheDocument()
  })
})
