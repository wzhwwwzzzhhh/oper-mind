import type { ReactElement } from 'react'

import type { DiagnosisAgentSummary, DiagnosisEvidence, DiagnosisResultProjection, DiagnosisRisk, DiagnosisRootCause } from './result-readers'

const SEVERITY_CLASSES: Record<DiagnosisResultProjection['severity'], string> = {
  critical: 'critical',
  high: 'high',
  info: 'info',
  low: 'low',
  medium: 'medium',
}

function EvidenceReferences({ evidence_ids, evidence_by_id }: { evidence_ids: string[]; evidence_by_id: ReadonlyMap<string, DiagnosisEvidence> }): ReactElement {
  if (evidence_ids.length === 0) return <span className="diagnosis-result-panel__muted">未关联结构化证据</span>

  return (
    <span className="diagnosis-result-panel__tags">
      {evidence_ids.map((evidence_id) => (
        evidence_by_id.has(evidence_id)
          ? <span className="diagnosis-result-panel__tag" key={evidence_id}>证据 {evidence_id}</span>
          : <span className="diagnosis-result-panel__tag diagnosis-result-panel__tag--warning" key={evidence_id}>关联证据不可用</span>
      ))}
    </span>
  )
}

function RootCauseItem({ root_cause, evidence_by_id }: { root_cause: DiagnosisRootCause; evidence_by_id: ReadonlyMap<string, DiagnosisEvidence> }): ReactElement {
  return (
    <li className="diagnosis-result-panel__item">
      <div className="diagnosis-result-panel__item-title">{root_cause.title}</div>
      <p className="diagnosis-result-panel__item-copy">{root_cause.summary}</p>
      <div className="diagnosis-result-panel__tags">
        <span className="diagnosis-result-panel__tag diagnosis-result-panel__tag--info">置信度 {(root_cause.confidence * 100).toFixed(0)}%</span>
        <EvidenceReferences evidence_by_id={evidence_by_id} evidence_ids={root_cause.evidence_ids} />
      </div>
    </li>
  )
}

function agent_status_class(status: DiagnosisAgentSummary['status']): string {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'muted'
}

function AgentSummaryItem({ item }: { item: DiagnosisAgentSummary }): ReactElement {
  return (
    <li className="diagnosis-result-panel__item">
      <div className="diagnosis-result-panel__item-title-row">
        <span className="diagnosis-result-panel__item-title">{item.agent}</span>
        <span className={`diagnosis-result-panel__tag diagnosis-result-panel__tag--${agent_status_class(item.status)}`}>{item.status}</span>
        {item.duration_ms !== null && <span className="diagnosis-result-panel__tag">{item.duration_ms} ms</span>}
      </div>
      <p className="diagnosis-result-panel__item-copy">{item.summary}</p>
    </li>
  )
}

function RiskItem({ risk }: { risk: DiagnosisRisk }): ReactElement {
  return (
    <li className="diagnosis-result-panel__item">
      <div className="diagnosis-result-panel__item-title-row">
        <span className={`diagnosis-result-panel__tag diagnosis-result-panel__tag--${SEVERITY_CLASSES[risk.level]}`}>风险 {risk.level}</span>
        <span className="diagnosis-result-panel__item-copy diagnosis-result-panel__item-copy--inline">{risk.summary}</span>
      </div>
      {risk.mitigation && <p className="diagnosis-result-panel__meta-line">缓解：{risk.mitigation}</p>}
    </li>
  )
}

function attribute_text(attributes: DiagnosisEvidence['attributes']): string {
  return Object.entries(attributes).map(([key, value]) => `${key}: ${value === null ? 'null' : String(value)}`).join('；')
}

function EvidenceItem({ evidence }: { evidence: DiagnosisEvidence }): ReactElement {
  const attributes = attribute_text(evidence.attributes)
  return (
    <li className="diagnosis-result-panel__item">
      <div className="diagnosis-result-panel__item-title-row">
        <span className="diagnosis-result-panel__item-title">{evidence.title}</span>
        <span className="diagnosis-result-panel__tag">{evidence.source_type}</span>
        <span className="diagnosis-result-panel__tag diagnosis-result-panel__tag--muted">{evidence.source_name}</span>
      </div>
      <p className="diagnosis-result-panel__item-copy">{evidence.summary}</p>
      <div className="diagnosis-result-panel__details">
        {evidence.observed_at && <span className="diagnosis-result-panel__meta-line">观察时间：{evidence.observed_at}</span>}
        {evidence.locator && <span className="diagnosis-result-panel__meta-line">定位信息：{evidence.locator}</span>}
        {attributes && <span className="diagnosis-result-panel__meta-line">属性：{attributes}</span>}
      </div>
    </li>
  )
}

function EmptyState({ children }: { children: string }): ReactElement {
  return <div className="diagnosis-result-panel__empty">{children}</div>
}

/**
 * 仅渲染已通过运行时校验的 P2 结构化结果；不解析 Markdown 或跳转 Trace。
 */
export function DiagnosisResultPanel({ result }: { result: DiagnosisResultProjection }): ReactElement {
  const evidence_by_id = new Map(result.evidence.map((evidence) => [evidence.id, evidence]))

  return (
    <article className="diagnosis-result-panel">
      <header className="diagnosis-result-panel__header">
        <h3 className="diagnosis-result-panel__title">结构化诊断结果</h3>
        <div className="diagnosis-result-panel__meta">
          <span className={`diagnosis-result-panel__badge diagnosis-result-panel__badge--${SEVERITY_CLASSES[result.severity]}`}>严重度 {result.severity}</span>
          <span className="diagnosis-result-panel__badge diagnosis-result-panel__badge--info">置信度 {(result.confidence * 100).toFixed(0)}%</span>
          <span className="diagnosis-result-panel__badge">结果时间 {result.created_at}</span>
        </div>
      </header>

      <p aria-label="诊断结果摘要" className="diagnosis-result-panel__summary">{result.summary}</p>

      <section aria-labelledby="root-causes-heading" className="diagnosis-result-panel__section">
        <h4 className="diagnosis-result-panel__section-title" id="root-causes-heading">可能根因</h4>
        {result.root_causes.length === 0
          ? <EmptyState>服务未返回结构化根因</EmptyState>
          : <ul className="diagnosis-result-panel__list">{result.root_causes.map((root_cause) => <RootCauseItem evidence_by_id={evidence_by_id} key={root_cause.id} root_cause={root_cause} />)}</ul>}
      </section>

      <section aria-labelledby="evidence-heading" className="diagnosis-result-panel__section">
        <h4 className="diagnosis-result-panel__section-title" id="evidence-heading">结构化证据</h4>
        {result.evidence.length === 0
          ? <EmptyState>服务未返回结构化证据</EmptyState>
          : <ul className="diagnosis-result-panel__list">{result.evidence.map((evidence) => <EvidenceItem evidence={evidence} key={evidence.id} />)}</ul>}
      </section>

      <section aria-labelledby="agent-summary-heading" className="diagnosis-result-panel__section">
        <h4 className="diagnosis-result-panel__section-title" id="agent-summary-heading">调查角色摘要</h4>
        {result.agent_summary.length === 0
          ? <EmptyState>服务未返回角色调查摘要</EmptyState>
          : <ul className="diagnosis-result-panel__list">{result.agent_summary.map((item) => <AgentSummaryItem item={item} key={`${item.agent}-${item.status}`} />)}</ul>}
      </section>

      <section aria-labelledby="risks-heading" className="diagnosis-result-panel__section">
        <h4 className="diagnosis-result-panel__section-title" id="risks-heading">调查范围与风险</h4>
        {result.risks.length === 0
          ? <EmptyState>服务未返回风险说明</EmptyState>
          : <ul className="diagnosis-result-panel__list">{result.risks.map((risk) => <RiskItem key={risk.id} risk={risk} />)}</ul>}
      </section>

      <section aria-labelledby="result-relations-heading" className="diagnosis-result-panel__relations">
        <h4 className="diagnosis-result-panel__section-title" id="result-relations-heading">结果关联</h4>
        <dl className="diagnosis-result-panel__relation-grid">
          <div className="diagnosis-result-panel__relation">
            <dt>结果 ID</dt>
            <dd>{result.id}</dd>
          </div>
          <div className="diagnosis-result-panel__relation">
            <dt>Run ID</dt>
            <dd>{result.run_id}</dd>
          </div>
        </dl>
      </section>
    </article>
  )
}
