import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useMemo, useState } from 'react'

import {
  ApiClientError,
  api_v1_client,
  type ActionApprovalRequest,
  type ActionExecutionRequest,
} from '../../api/v1/client'
import {
  UiAlert,
  UiButton,
  UiCard,
  UiDescriptions,
  UiDescriptionsItem,
  UiList,
  UiModal,
  UiParagraph,
  UiSpace,
  UiSpin,
  UiTag,
  UiText,
  UiTitle,
} from './ui'


type ProposalStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'expired'
  | 'executing'
  | 'verifying'
  | 'verified'
  | 'blocked'
  | 'failed'

type ActionProposalView = {
  id: string
  status: ProposalStatus
  mode: 'mock' | 'target'
  title: string
  description: string
  target: Record<string, string>
  risk_summary: string
  verification_plan: string[]
  failure_message?: string
  approval?: { actor: string; decision: string }
  execution?: { status: string; precondition_summary?: string; action_summary?: string; failure_message?: string }
  verification?: { status: string; summary: string; facts: Record<string, string | number | boolean> }
}

type ActionEventView = {
  sequence: number
  type: string
  summary?: string
  status?: string
  mode?: string
}

function read_record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : undefined
}

function read_string(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function read_string_array(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every((item) => typeof item === 'string') ? value : undefined
}

function read_target(value: unknown): Record<string, string> | undefined {
  const record = read_record(value)
  if (!record || Object.values(record).some((item) => typeof item !== 'string')) return undefined
  return record as Record<string, string>
}

function read_facts(value: unknown): Record<string, string | number | boolean> | undefined {
  const record = read_record(value)
  if (!record || Object.values(record).some((item) => !['string', 'number', 'boolean'].includes(typeof item))) return undefined
  return record as Record<string, string | number | boolean>
}

function read_proposal(value: unknown): ActionProposalView | null {
  const root = read_record(value)
  const proposal = read_record(root?.proposal)
  if (!proposal) return null
  const id = read_string(proposal.id)
  const status = read_string(proposal.status)
  const mode = read_string(proposal.mode)
  const title = read_string(proposal.title)
  const description = read_string(proposal.description)
  const target = read_target(proposal.target)
  const risk_summary = read_string(proposal.risk_summary)
  const verification_plan = read_string_array(proposal.verification_plan)
  const allowed_statuses: ProposalStatus[] = ['pending_approval', 'approved', 'rejected', 'expired', 'executing', 'verifying', 'verified', 'blocked', 'failed']
  if (!id || !status || !allowed_statuses.includes(status as ProposalStatus) || (mode !== 'mock' && mode !== 'target') || !title || !description || !target || !risk_summary || !verification_plan) {
    return null
  }
  const approval_record = read_record(proposal.approval)
  const execution_record = read_record(proposal.execution)
  const verification_record = read_record(proposal.verification)
  const approval = approval_record && read_string(approval_record.actor) && read_string(approval_record.decision)
    ? { actor: read_string(approval_record.actor) as string, decision: read_string(approval_record.decision) as string }
    : undefined
  const execution = execution_record && read_string(execution_record.status)
    ? {
        status: read_string(execution_record.status) as string,
        precondition_summary: read_string(execution_record.precondition_summary),
        action_summary: read_string(execution_record.action_summary),
        failure_message: read_string(execution_record.failure_message),
      }
    : undefined
  const verification = verification_record && read_string(verification_record.status) && read_string(verification_record.summary) && read_facts(verification_record.facts)
    ? {
        status: read_string(verification_record.status) as string,
        summary: read_string(verification_record.summary) as string,
        facts: read_facts(verification_record.facts) as Record<string, string | number | boolean>,
      }
    : undefined
  return { id, status: status as ProposalStatus, mode, title, description, target, risk_summary, verification_plan, failure_message: read_string(proposal.failure_message), approval, execution, verification }
}

function read_action_events(value: unknown): ActionEventView[] {
  const root = read_record(value)
  const raw_items = root?.items
  if (!Array.isArray(raw_items)) return []
  return raw_items.flatMap((item) => {
    const event = read_record(item)
    const data = read_record(event?.data)
    const sequence = event?.sequence
    const type = read_string(event?.type)
    if (typeof sequence !== 'number' || !type) return []
    return [{ sequence, type, summary: read_string(data?.summary), status: read_string(data?.status), mode: read_string(data?.mode) }]
  })
}

function status_color(status: ProposalStatus): 'green' | 'red' | 'blue' | 'cyan' | 'gold' {
  if (status === 'verified') return 'green'
  if (status === 'failed' || status === 'blocked' || status === 'rejected' || status === 'expired') return 'red'
  if (status === 'approved') return 'blue'
  if (status === 'executing' || status === 'verifying') return 'cyan'
  return 'gold'
}

function status_text(status: ProposalStatus): string {
  const labels: Record<ProposalStatus, string> = {
    pending_approval: '等待人工审批', approved: '已批准，等待二次确认', rejected: '已拒绝', expired: '批准已过期',
    executing: '正在执行固定修复', verifying: '正在独立验证', verified: '验证通过', blocked: '执行被安全拦截', failed: '执行或验证失败',
  }
  return labels[status]
}

function safe_error(error: unknown): string {
  if (error instanceof ApiClientError) return `${error.code}：${error.message}`
  return '请求未完成；页面没有用本地状态替代服务端事实。'
}

function terminal(status: ProposalStatus): boolean {
  return ['rejected', 'expired', 'verified', 'blocked', 'failed'].includes(status)
}

/**
 * P4.2 最小产品面板：只读取服务器快照，用户不能编辑 SQL、目标或动作参数。
 */
export function ActionProposalPanel({ run_id }: { run_id: string }): ReactElement | null {
  const query_client = useQueryClient()
  const [confirm, set_confirm] = useState<'approve' | 'execute' | null>(null)
  const proposal_query = useQuery({
    queryKey: ['api-v1', 'run-action-proposal', run_id],
    queryFn: ({ signal }) => api_v1_client.get_run_action_proposal(run_id, { signal }).then((response) => response.data),
    refetchInterval: (query) => {
      const latest = read_proposal(query.state.data)
      return latest && !terminal(latest.status) ? 1500 : false
    },
  })
  const proposal = useMemo(() => read_proposal(proposal_query.data), [proposal_query.data])
  const events_query = useQuery({
    queryKey: ['api-v1', 'action-events', proposal?.id],
    queryFn: ({ signal }) => api_v1_client.list_action_events(proposal?.id ?? '', { limit: 20 }, { signal }).then((response) => response.data),
    enabled: Boolean(proposal?.id),
    refetchInterval: proposal && !terminal(proposal.status) ? 1500 : false,
  })
  const approve_mutation = useMutation({
    mutationFn: () => api_v1_client.decide_action_proposal(
      proposal?.id ?? '',
      { decision: 'approve' } satisfies ActionApprovalRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => {
      set_confirm(null)
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'run-action-proposal', run_id] })
    },
  })
  const reject_mutation = useMutation({
    mutationFn: () => api_v1_client.decide_action_proposal(
      proposal?.id ?? '',
      { decision: 'reject', comment: '本地操作者暂不批准该固定修复。' } satisfies ActionApprovalRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => query_client.invalidateQueries({ queryKey: ['api-v1', 'run-action-proposal', run_id] }),
  })
  const execute_mutation = useMutation({
    mutationFn: () => api_v1_client.request_action_execution(
      proposal?.id ?? '',
      {} satisfies ActionExecutionRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => {
      set_confirm(null)
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'run-action-proposal', run_id] })
    },
  })

  if (proposal_query.isLoading) return <UiSpin label="正在读取固定修复提案" />
  if (proposal_query.isError) return <UiAlert description={safe_error(proposal_query.error)} showIcon title="固定修复提案暂不可读取" type="warning" />
  if (!proposal) return null

  const events = read_action_events(events_query.data)
  const busy = approve_mutation.isPending || reject_mutation.isPending || execute_mutation.isPending
  const failure = proposal.failure_message ?? proposal.execution?.failure_message
  return (
    <UiCard title="固定修复提案">
      <UiSpace direction="vertical" size="middle" style={{ width: '100%' }}>
        <UiSpace wrap>
          <UiTag color={status_color(proposal.status)}>{status_text(proposal.status)}</UiTag>
          <UiTag color={proposal.mode === 'mock' ? 'orange' : 'blue'}>{proposal.mode === 'mock' ? '模拟模式：不含真实 DDL' : '受控靶场 target 模式'}</UiTag>
        </UiSpace>
        <UiText strong>{proposal.title}</UiText>
        <UiParagraph>{proposal.description}</UiParagraph>
        <UiAlert description="当前没有多用户身份或 RBAC；审批 actor 固定记录为 local_operator，只表示本地操作者明确确认。" showIcon title="本地人工审批限制" type="info" />
        <UiDescriptions title="固定边界">
          {Object.entries(proposal.target).map(([key, value]) => <UiDescriptionsItem key={key} label={key}>{value}</UiDescriptionsItem>)}
          <UiDescriptionsItem label="风险">{proposal.risk_summary}</UiDescriptionsItem>
        </UiDescriptions>
        <section aria-labelledby={`verify-plan-${proposal.id}`}>
          <UiTitle id={`verify-plan-${proposal.id}`} level={5}>独立 Verify 计划</UiTitle>
          <UiList dataSource={proposal.verification_plan} renderItem={(item) => item} />
        </section>
        {proposal.status === 'pending_approval' && (
          <UiSpace wrap>
            <UiButton disabled={busy} onClick={() => set_confirm('approve')} type="primary">批准固定修复</UiButton>
            <UiButton danger disabled={busy} loading={reject_mutation.isPending} onClick={() => reject_mutation.mutate()}>拒绝</UiButton>
          </UiSpace>
        )}
        {proposal.status === 'approved' && (
          <UiButton danger disabled={busy} onClick={() => set_confirm('execute')} type="primary">执行固定修复</UiButton>
        )}
        {(proposal.status === 'executing' || proposal.status === 'verifying') && <UiAlert description="页面正在轮询已提交的 action 审计事件；不会显示思维链、SQL、日志原文或内部请求 ID。" showIcon title="固定修复处理中" type="info" />}
        {proposal.status === 'verified' && proposal.verification && (
          <UiAlert description={proposal.verification.summary} showIcon title="Verify 已通过" type="success" />
        )}
        {failure && <UiAlert description={`${failure} 请重新发起调查以生成新提案。`} showIcon title="该提案不能重试" type="error" />}
        {proposal.verification && (
          <UiDescriptions title="Verify 脱敏事实">
            {Object.entries(proposal.verification.facts).map(([key, value]) => <UiDescriptionsItem key={key} label={key}>{String(value)}</UiDescriptionsItem>)}
          </UiDescriptions>
        )}
        {events.length > 0 && (
          <section aria-labelledby={`action-events-${proposal.id}`}>
            <UiTitle id={`action-events-${proposal.id}`} level={5}>审批与执行时间线</UiTitle>
            <UiList
              dataSource={events}
              renderItem={(event) => (
                <UiSpace direction="vertical" size={2}>
                  <UiSpace wrap><UiTag>#{event.sequence}</UiTag><UiTag>{event.type}</UiTag>{event.status && <UiTag color="blue">{event.status}</UiTag>}{event.mode && <UiTag>{event.mode}</UiTag>}</UiSpace>
                  {event.summary && <UiText>{event.summary}</UiText>}
                </UiSpace>
              )}
            />
          </section>
        )}
        {(approve_mutation.isError || reject_mutation.isError || execute_mutation.isError) && <UiAlert description={safe_error(approve_mutation.error ?? reject_mutation.error ?? execute_mutation.error)} showIcon title="固定修复操作未完成" type="error" />}
      </UiSpace>
      <UiModal
        cancelText="取消"
        confirmLoading={confirm === 'approve' ? approve_mutation.isPending : execute_mutation.isPending}
        okButtonProps={{ danger: confirm === 'execute' }}
        okText={confirm === 'approve' ? '确认批准' : '确认执行'}
        onCancel={() => set_confirm(null)}
        onOk={() => confirm === 'approve' ? approve_mutation.mutate() : execute_mutation.mutate()}
        open={confirm !== null}
        title={confirm === 'approve' ? '确认本地人工审批' : '再次确认执行固定修复'}
      >
        <UiParagraph>
          {confirm === 'approve'
            ? '你将以 local_operator 记录对不可编辑固定提案的明确批准；这不是企业级多人审批。'
            : '系统只会对受控靶场执行代码内固定的联合索引重建，并在之后独立 Verify；验证失败不会自动回滚。'}
        </UiParagraph>
      </UiModal>
    </UiCard>
  )
}
