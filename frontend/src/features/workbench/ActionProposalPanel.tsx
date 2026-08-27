import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useMemo, useState } from 'react'

import {
  ApiClientError,
  api_v1_client,
  type ActionApprovalRequest,
  type ActionExecutionRequest,
  type CreateRunOptions,
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
  mode?: 'mock' | 'target'
  source_run_id?: string
  title?: string
  description?: string
  target?: Record<string, string>
  risk_summary?: string
  verification_plan?: string[]
  failure_message?: string
  approval?: { actor: string; decision: string }
  execution?: { status: string; precondition_summary?: string; action_summary?: string; failure_message?: string }
  verification?: { status: string; summary: string; facts?: Record<string, string | number | boolean> }
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

/**
 * P1-11：字段缺失降级渲染——只要求核心字段（id/status）必须存在；
 * 其余字段缺失时返回部分视图，由渲染层按可用字段降级展示，不让整卡消失。
 */
function read_proposal(value: unknown): ActionProposalView | null {
  const root = read_record(value)
  const proposal = read_record(root?.proposal)
  if (!proposal) return null
  const id = read_string(proposal.id)
  const status = read_string(proposal.status)
  const allowed_statuses: ProposalStatus[] = ['pending_approval', 'approved', 'rejected', 'expired', 'executing', 'verifying', 'verified', 'blocked', 'failed']
  if (!id || !status || !allowed_statuses.includes(status as ProposalStatus)) return null
  const mode_value = read_string(proposal.mode)
  const mode = mode_value === 'mock' || mode_value === 'target' ? mode_value : undefined
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
  const verification = verification_record && read_string(verification_record.status) && read_string(verification_record.summary)
    ? {
        status: read_string(verification_record.status) as string,
        summary: read_string(verification_record.summary) as string,
        facts: read_facts(verification_record.facts),
      }
    : undefined
  return {
    id,
    status: status as ProposalStatus,
    mode,
    source_run_id: read_string(proposal.source_run_id),
    title: read_string(proposal.title),
    description: read_string(proposal.description),
    target: read_target(proposal.target),
    risk_summary: read_string(proposal.risk_summary),
    verification_plan: read_string_array(proposal.verification_plan),
    failure_message: read_string(proposal.failure_message),
    approval,
    execution,
    verification,
  }
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

function mode_label(mode: ActionProposalView['mode']): string {
  if (mode === 'mock') return '模拟模式：不含真实 DDL'
  if (mode === 'target') return '受控靶场 target 模式'
  return '模式未返回'
}

function safe_error(error: unknown): string {
  if (error instanceof ApiClientError) return `${error.code}：${error.message}`
  return '请求未完成；页面没有用本地状态替代服务端事实。'
}

function terminal(status: ProposalStatus): boolean {
  return ['rejected', 'expired', 'verified', 'blocked', 'failed'].includes(status)
}

/** 结束且未验证的状态可使用"重新发起调查"入口生成新提案（提案本身不可重试）。 */
function retryable(status: ProposalStatus): boolean {
  return ['blocked', 'failed', 'expired', 'rejected'].includes(status)
}

/**
 * P4.2 最小产品面板：只读取服务器快照，用户不能编辑 SQL、目标或动作参数。
 * 支持两种取数方式：按 run_id 读取该 Run 产生的提案；或按 proposal_id 直达提案详情。
 * P1-11：批准/执行按钮 loading；失败态"重新发起调查"入口；字段缺失按可用字段降级渲染。
 */
export function ActionProposalPanel({ run_id, proposal_id, read_only = false, session_id }: { run_id?: string; proposal_id?: string; read_only?: boolean; session_id?: string }): ReactElement | null {
  const query_client = useQueryClient()
  const [confirm, set_confirm] = useState<'approve' | 'execute' | null>(null)
  const proposal_query = useQuery({
    queryKey: ['api-v1', 'action-proposal', proposal_id ?? run_id ?? ''],
    queryFn: ({ signal }) =>
      proposal_id
        ? api_v1_client.get_action_proposal(proposal_id, { signal }).then((response) => response.data)
        : api_v1_client.get_run_action_proposal(run_id ?? '', { signal }).then((response) => response.data),
    enabled: Boolean(proposal_id ?? run_id),
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
  const invalidate_proposal = async (): Promise<void> => {
    await query_client.invalidateQueries({ queryKey: ['api-v1', 'action-proposal', proposal_id ?? run_id ?? ''] })
    if (run_id) {
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'run-action-proposal', run_id] })
    }
  }
  const approve_mutation = useMutation({
    mutationFn: () => api_v1_client.decide_action_proposal(
      proposal?.id ?? '',
      { decision: 'approve' } satisfies ActionApprovalRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => {
      set_confirm(null)
      await invalidate_proposal()
    },
  })
  const reject_mutation = useMutation({
    mutationFn: () => api_v1_client.decide_action_proposal(
      proposal?.id ?? '',
      { decision: 'reject', comment: '本地操作者暂不批准该固定修复。' } satisfies ActionApprovalRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => invalidate_proposal(),
  })
  const execute_mutation = useMutation({
    mutationFn: () => api_v1_client.request_action_execution(
      proposal?.id ?? '',
      {} satisfies ActionExecutionRequest,
      { idempotency_key: globalThis.crypto.randomUUID() },
    ),
    onSuccess: async () => {
      set_confirm(null)
      await invalidate_proposal()
    },
  })
  const rerun_mutation = useMutation({
    mutationFn: (source_run_id: string) => api_v1_client.rerun_run(
      source_run_id,
      { idempotency_key: globalThis.crypto.randomUUID() } satisfies CreateRunOptions,
    ),
    onSuccess: async () => {
      await invalidate_proposal()
      if (session_id) {
        // 前缀命中原会话的 runs/messages 查询，让新 Run 出现在会话工作台。
        await query_client.invalidateQueries({ queryKey: ['api-v1', 'session-runs', session_id] })
        await query_client.invalidateQueries({ queryKey: ['api-v1', 'session-messages', session_id] })
      }
    },
  })

  if (proposal_query.isLoading) return <UiSpin label="正在读取固定修复提案" />
  if (proposal_query.isError) return <UiAlert description={safe_error(proposal_query.error)} showIcon title="固定修复提案暂不可读取" type="warning" />
  if (!proposal) return null

  const events = read_action_events(events_query.data)
  const busy = approve_mutation.isPending || reject_mutation.isPending || execute_mutation.isPending
  const failure = proposal.failure_message ?? proposal.execution?.failure_message
  const rerun_target = proposal.source_run_id ?? run_id
  const show_rerun_entrance = !read_only && retryable(proposal.status) && Boolean(rerun_target)
  return (
    <UiCard title="固定修复提案">
      <UiSpace direction="vertical" size="middle" style={{ width: '100%' }}>
        <UiSpace wrap>
          <UiTag color={status_color(proposal.status)}>{status_text(proposal.status)}</UiTag>
          <UiTag color={proposal.mode === 'mock' ? 'orange' : proposal.mode === 'target' ? 'blue' : 'gold'}>{mode_label(proposal.mode)}</UiTag>
        </UiSpace>
        <UiText strong>{proposal.title ?? '（服务端未返回标题）'}</UiText>
        <UiParagraph>{proposal.description ?? '（服务端未返回描述）'}</UiParagraph>
        <UiAlert description="当前没有多用户身份或 RBAC；审批 actor 固定记录为 local_operator，只表示本地操作者明确确认。" showIcon title="本地人工审批限制" type="info" />
        <UiDescriptions title="固定边界">
          {proposal.target && Object.keys(proposal.target).length > 0
            ? Object.entries(proposal.target).map(([key, value]) => <UiDescriptionsItem key={key} label={key}>{value}</UiDescriptionsItem>)
            : <UiDescriptionsItem label="边界">（服务端未返回固定边界）</UiDescriptionsItem>}
          <UiDescriptionsItem label="风险">{proposal.risk_summary ?? '（服务端未返回风险说明）'}</UiDescriptionsItem>
        </UiDescriptions>
        <section aria-labelledby={`verify-plan-${proposal.id}`}>
          <UiTitle id={`verify-plan-${proposal.id}`} level={5}>独立 Verify 计划</UiTitle>
          {proposal.verification_plan && proposal.verification_plan.length > 0
            ? <UiList dataSource={proposal.verification_plan} renderItem={(item) => item} />
            : <UiText className="muted-note">（服务端未返回验证计划）</UiText>}
        </section>
        {!read_only && proposal.status === 'pending_approval' && (
          <UiSpace wrap>
            <UiButton disabled={busy} loading={approve_mutation.isPending} onClick={() => set_confirm('approve')} type="primary">批准固定修复</UiButton>
            <UiButton danger disabled={busy} loading={reject_mutation.isPending} onClick={() => reject_mutation.mutate()}>拒绝</UiButton>
          </UiSpace>
        )}
        {!read_only && proposal.status === 'approved' && (
          <UiButton danger disabled={busy} loading={execute_mutation.isPending} onClick={() => set_confirm('execute')} type="primary">执行固定修复</UiButton>
        )}
        {(proposal.status === 'executing' || proposal.status === 'verifying') && <UiAlert description="页面正在轮询已提交的 action 审计事件；不会显示思维链、SQL、日志原文或内部请求 ID。" showIcon title="固定修复处理中" type="info" />}
        {proposal.status === 'verified' && proposal.verification && (
          <UiAlert description={proposal.verification.summary} showIcon title="Verify 已通过" type="success" />
        )}
        {failure && (
          <UiAlert
            description={`${failure} 该提案本身不能重试；可重新发起调查生成新提案。`}
            showIcon
            title="该提案不能重试"
            type="error"
          />
        )}
        {retryable(proposal.status) && !rerun_target && (
          <UiAlert description="服务端未返回来源 Run 标识，无法从面板直接重新发起调查；请回到会话工作台处理。" showIcon title="缺少来源 Run" type="warning" />
        )}
        {show_rerun_entrance && (
          <UiSpace wrap>
            <UiButton loading={rerun_mutation.isPending} onClick={() => rerun_target && rerun_mutation.mutate(rerun_target)} type="primary">重新发起调查</UiButton>
            {!failure && proposal.status === 'rejected' && <UiText className="muted-note">提案已被拒绝；可重新发起调查以生成新提案。</UiText>}
          </UiSpace>
        )}
        {rerun_mutation.isSuccess && <UiAlert description="已按原 Run 的会话与服务上下文重新发起调查；新提案将绑定新 Run。" showIcon title="已重新发起调查" type="success" />}
        {rerun_mutation.isError && <UiAlert description={safe_error(rerun_mutation.error)} showIcon title="重新发起调查未完成" type="error" />}
        {proposal.verification && (
          <UiDescriptions title="Verify 脱敏事实">
            {proposal.verification.facts
              ? Object.entries(proposal.verification.facts).map(([key, value]) => <UiDescriptionsItem key={key} label={key}>{String(value)}</UiDescriptionsItem>)
              : <UiDescriptionsItem label="事实">（服务端未返回 Verify 脱敏事实）</UiDescriptionsItem>}
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
        {!read_only && (approve_mutation.isError || reject_mutation.isError || execute_mutation.isError) && <UiAlert description={safe_error(approve_mutation.error ?? reject_mutation.error ?? execute_mutation.error)} showIcon title="固定修复操作未完成" type="error" />}
      </UiSpace>
      {!read_only && (
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
      )}
    </UiCard>
  )
}
