import { useInfiniteQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type ActionProposalStatus,
} from '../../api/v1/client'
import { api_v1_query_keys } from '../../api/v1/queries'
import { ActionProposalPanel } from '../workbench/ActionProposalPanel'
import { read_items, read_page, resource_optional_string } from '../workbench/resource-readers'
import { UiAlert, UiButton, UiCard, UiSpace, UiTag, UiText, UiTitle } from '../workbench/ui'

const STATUS_FILTERS: ReadonlyArray<{ key: ActionProposalStatus | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'pending_approval', label: '待审批' },
  { key: 'approved', label: '已批准' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'verified', label: '已验证' },
  { key: 'failed', label: '失败/拦截' },
]

const STATUS_COLORS: Record<string, 'green' | 'red' | 'blue' | 'cyan' | 'gold' | 'orange'> = {
  pending_approval: 'gold', approved: 'blue', rejected: 'red', expired: 'red',
  executing: 'cyan', verifying: 'cyan', verified: 'green', blocked: 'red', failed: 'red',
}

const STATUS_TEXT: Record<string, string> = {
  pending_approval: '等待审批', approved: '已批准', rejected: '已拒绝', expired: '已过期',
  executing: '执行中', verifying: '验证中', verified: '验证通过', blocked: '已拦截', failed: '失败',
}

interface ProposalSummaryView {
  action_id: string
  created_at: string
  id: string
  mode: 'mock' | 'target'
  source_run_id: string
  status: ActionProposalStatus
  title: string
  updated_at: string
}

function read_summary(value: unknown): ProposalSummaryView | null {
  const id = resource_optional_string(value, 'id')
  const source_run_id = resource_optional_string(value, 'source_run_id')
  const action_id = resource_optional_string(value, 'action_id')
  const status = resource_optional_string(value, 'status')
  const mode = resource_optional_string(value, 'mode')
  const title = resource_optional_string(value, 'title')
  const created_at = resource_optional_string(value, 'created_at')
  const updated_at = resource_optional_string(value, 'updated_at')
  if (!id || !source_run_id || !action_id || !status || !mode || !title || !created_at || !updated_at) return null
  return {
    id, source_run_id, action_id, status: status as ActionProposalStatus, mode: mode as 'mock' | 'target',
    title, created_at, updated_at,
  }
}

function ProposalRow({ proposal, on_open }: { proposal: ProposalSummaryView; on_open: () => void }): ReactElement {
  return (
    <button className="proposal-row" onClick={on_open} type="button">
      <UiSpace direction="vertical" size={2} style={{ width: '100%', textAlign: 'left' }}>
        <UiSpace wrap>
          <UiTag color={STATUS_COLORS[proposal.status] ?? 'gold'}>{STATUS_TEXT[proposal.status] ?? proposal.status}</UiTag>
          <UiTag color={proposal.mode === 'mock' ? 'orange' : 'blue'}>{proposal.mode === 'mock' ? '模拟' : '靶场'}</UiTag>
          <UiText className="muted-note">{proposal.created_at}</UiText>
        </UiSpace>
        <UiText strong>{proposal.title}</UiText>
      </UiSpace>
    </button>
  )
}

/** P8 全局提案列表页：跨会话跨 Run 的安全摘要，按状态过滤 + cursor 分页。 */
export function ApprovalsPage(): ReactElement {
  const navigate = useNavigate()
  const [status, set_status] = useState<ActionProposalStatus | 'all'>('pending_approval')
  const filter_status: ActionProposalStatus | undefined = status === 'all' ? undefined : status
  const query = useInfiniteQuery({
    queryKey: api_v1_query_keys.action_proposals({ limit: API_V1_DEFAULT_PAGE_SIZE, status: filter_status }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_action_proposals(
        { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE, status: filter_status },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const proposals = useMemo(
    () => query.data?.pages.flatMap((page) => read_items(page.data).map(read_summary).filter((item): item is ProposalSummaryView => item !== null)) ?? [],
    [query.data],
  )
  const page_info = query.data?.pages.at(-1) ? read_page(query.data.pages.at(-1)!.data) : undefined

  return (
    <section className="approvals-page" aria-labelledby="approvals-title">
      <UiTitle id="approvals-title" level={2}>待审批提案</UiTitle>
      <UiSpace wrap className="proposal-filters">
        {STATUS_FILTERS.map((item) => (
          <UiButton key={item.key} onClick={() => set_status(item.key)} type={status === item.key ? 'primary' : 'default'}>
            {item.label}
          </UiButton>
        ))}
      </UiSpace>
      {query.isPending && <UiText className="muted-note">正在读取提案…</UiText>}
      {query.isError && <UiAlert description="提案列表暂不可读；页面不会用本地数据替代服务端事实。" showIcon title="读取失败" type="error" />}
      {query.isSuccess && proposals.length === 0 && (
        <UiText className="muted-note">当前筛选下没有提案</UiText>
      )}
      {proposals.map((proposal) => (
        <UiCard key={proposal.id}>
          <ProposalRow proposal={proposal} on_open={() => navigate(`/workbench/approvals/${encodeURIComponent(proposal.id)}`)} />
        </UiCard>
      ))}
      {page_info?.has_more && (
        <UiButton className="load-more-button" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()} type="link">
          {query.isFetchingNextPage ? '正在加载…' : '加载更多提案'}
        </UiButton>
      )}
    </section>
  )
}

/** 单个提案详情页：复用既有审批/执行交互，点击列表行进入。 */
export function ApprovalDetailPage(): ReactElement {
  const navigate = useNavigate()
  const { proposal_id } = useParams<{ proposal_id: string }>()
  if (!proposal_id) {
    return <UiAlert description="缺少提案标识。" showIcon title="无效提案" type="warning" />
  }
  return (
    <section className="approvals-page" aria-labelledby="approval-detail-title">
      <UiTitle id="approval-detail-title" level={2}>提案详情</UiTitle>
      <UiButton className="return-workbench" onClick={() => navigate('/workbench/approvals')} type="link">返回提案列表</UiButton>
      <ActionProposalPanel proposal_id={proposal_id} />
    </section>
  )
}
