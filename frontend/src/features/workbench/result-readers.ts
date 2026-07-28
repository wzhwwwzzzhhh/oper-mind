import { read_boolean, read_record, read_string } from './resource-readers'

const DIAGNOSIS_SEVERITIES = ['info', 'low', 'medium', 'high', 'critical'] as const
const EVIDENCE_SOURCE_TYPES = ['tool', 'log', 'metric', 'database', 'agent', 'user'] as const
const RECOMMENDATION_PRIORITIES = ['p0', 'p1', 'p2', 'p3'] as const
const RISK_LEVELS = ['none', 'low', 'medium', 'high', 'critical'] as const
const AGENT_STATUSES = ['completed', 'skipped', 'failed'] as const

export type DiagnosisSeverity = (typeof DIAGNOSIS_SEVERITIES)[number]
export type EvidenceSourceType = (typeof EVIDENCE_SOURCE_TYPES)[number]
export type RecommendationPriority = (typeof RECOMMENDATION_PRIORITIES)[number]
export type RiskLevel = (typeof RISK_LEVELS)[number]
export type AgentStatus = (typeof AGENT_STATUSES)[number]
export type EvidenceAttributeValue = boolean | number | string | null

export interface ResultProtocolIssue {
  field: string
  message: string
}

export interface DiagnosisEvidence {
  attributes: Record<string, EvidenceAttributeValue>
  id: string
  locator: string | null
  observed_at: string | null
  source_name: string
  source_type: EvidenceSourceType
  summary: string
  title: string
}

export interface DiagnosisRootCause {
  confidence: number
  evidence_ids: string[]
  id: string
  summary: string
  title: string
}

export interface DiagnosisImpact {
  affected_scope: string | null
  affected_services: string[]
  summary: string
}

export interface DiagnosisRecommendation {
  description: string
  evidence_ids: string[]
  id: string
  priority: RecommendationPriority
  requires_approval: boolean
  risk_level: RiskLevel
  title: string
}

export interface DiagnosisRisk {
  id: string
  level: Exclude<RiskLevel, 'none'>
  mitigation: string | null
  summary: string
}

export interface DiagnosisAgentSummary {
  agent: string
  duration_ms: number | null
  status: AgentStatus
  summary: string
}

export interface DiagnosisResultProjection {
  agent_summary: DiagnosisAgentSummary[]
  confidence: number
  created_at: string
  evidence: DiagnosisEvidence[]
  id: string
  impact: DiagnosisImpact | null
  recommendations: DiagnosisRecommendation[]
  report_markdown: string | null
  requires_approval: boolean
  risks: DiagnosisRisk[]
  root_causes: DiagnosisRootCause[]
  run_id: string
  severity: DiagnosisSeverity
  summary: string
}

export interface DiagnosisResultReadResult {
  issues: ResultProtocolIssue[]
  result?: DiagnosisResultProjection
}

function has_value<TValue>(value: TValue | undefined, field: string, issues: ResultProtocolIssue[]): value is TValue {
  if (value !== undefined) return true
  issues.push({ field, message: '缺少必填字段。' })
  return false
}

function read_required_string(record: Record<string, unknown>, key: string, field: string, issues: ResultProtocolIssue[]): string | undefined {
  const value = read_string(record[key])
  if (value === undefined) {
    issues.push({ field, message: '必须是字符串。' })
    return undefined
  }
  return value
}

function read_nullable_string(record: Record<string, unknown>, key: string, field: string, issues: ResultProtocolIssue[]): string | null | undefined {
  if (!(key in record)) {
    issues.push({ field, message: '缺少必填字段。' })
    return undefined
  }
  if (record[key] === null) return null
  const value = read_string(record[key])
  if (value === undefined) {
    issues.push({ field, message: '必须是字符串或 null。' })
    return undefined
  }
  return value
}

function read_string_array(value: unknown, field: string, issues: ResultProtocolIssue[]): string[] | undefined {
  if (!Array.isArray(value) || value.some((item) => read_string(item) === undefined)) {
    issues.push({ field, message: '必须是字符串数组。' })
    return undefined
  }
  return value as string[]
}

function read_enum<TValue extends string>(
  value: unknown,
  allowed_values: readonly TValue[],
  field: string,
  issues: ResultProtocolIssue[],
): TValue | undefined {
  if (typeof value === 'string' && allowed_values.includes(value as TValue)) return value as TValue
  issues.push({ field, message: `必须是允许的枚举值：${allowed_values.join('、')}。` })
  return undefined
}

function read_confidence(value: unknown, field: string, issues: ResultProtocolIssue[]): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1) return value
  issues.push({ field, message: '必须是 0 到 1 之间的有限数值。' })
  return undefined
}

function read_utc_z(value: unknown, field: string, issues: ResultProtocolIssue[]): string | undefined {
  const text = read_string(value)
  if (text && text.endsWith('Z') && !Number.isNaN(Date.parse(text))) return text
  issues.push({ field, message: '必须是有效的 UTC Z 时间。' })
  return undefined
}

function read_attributes(value: unknown, field: string, issues: ResultProtocolIssue[]): Record<string, EvidenceAttributeValue> | undefined {
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  for (const [key, attribute] of Object.entries(record)) {
    if (attribute !== null && typeof attribute !== 'string' && typeof attribute !== 'number' && typeof attribute !== 'boolean') {
      issues.push({ field: `${field}.${key}`, message: '属性值必须是字符串、数值、布尔值或 null。' })
    }
  }
  return issues.some((issue) => issue.field.startsWith(field))
    ? undefined
    : record as Record<string, EvidenceAttributeValue>
}

function read_root_cause(value: unknown, index: number, issues: ResultProtocolIssue[]): DiagnosisRootCause | undefined {
  const field = `root_causes[${index}]`
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  const id = read_required_string(record, 'id', `${field}.id`, issues)
  const title = read_required_string(record, 'title', `${field}.title`, issues)
  const summary = read_required_string(record, 'summary', `${field}.summary`, issues)
  const confidence = read_confidence(record.confidence, `${field}.confidence`, issues)
  const evidence_ids = read_string_array(record.evidence_ids, `${field}.evidence_ids`, issues)
  if (id === undefined || title === undefined || summary === undefined || confidence === undefined || evidence_ids === undefined) return undefined
  return { confidence, evidence_ids, id, summary, title }
}

function read_evidence(value: unknown, index: number, issues: ResultProtocolIssue[]): DiagnosisEvidence | undefined {
  const field = `evidence[${index}]`
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  const id = read_required_string(record, 'id', `${field}.id`, issues)
  const source_type = read_enum(record.source_type, EVIDENCE_SOURCE_TYPES, `${field}.source_type`, issues)
  const source_name = read_required_string(record, 'source_name', `${field}.source_name`, issues)
  const title = read_required_string(record, 'title', `${field}.title`, issues)
  const summary = read_required_string(record, 'summary', `${field}.summary`, issues)
  const locator = read_nullable_string(record, 'locator', `${field}.locator`, issues)
  const observed_at = read_nullable_string(record, 'observed_at', `${field}.observed_at`, issues)
  if (observed_at !== undefined && observed_at !== null && !read_utc_z(observed_at, `${field}.observed_at`, issues)) return undefined
  const attributes = read_attributes(record.attributes, `${field}.attributes`, issues)
  if (id === undefined || source_type === undefined || source_name === undefined || title === undefined || summary === undefined || locator === undefined || observed_at === undefined || attributes === undefined) return undefined
  return { attributes, id, locator, observed_at, source_name, source_type, summary, title }
}

function read_impact(value: unknown, issues: ResultProtocolIssue[]): DiagnosisImpact | null | undefined {
  if (value === null) return null
  const record = read_record(value)
  if (!record) {
    issues.push({ field: 'impact', message: '必须是对象或 null。' })
    return undefined
  }
  const summary = read_required_string(record, 'summary', 'impact.summary', issues)
  const affected_services = read_string_array(record.affected_services, 'impact.affected_services', issues)
  const affected_scope = read_nullable_string(record, 'affected_scope', 'impact.affected_scope', issues)
  if (summary === undefined || affected_services === undefined || affected_scope === undefined) return undefined
  return { affected_scope, affected_services, summary }
}

function read_recommendation(value: unknown, index: number, issues: ResultProtocolIssue[]): DiagnosisRecommendation | undefined {
  const field = `recommendations[${index}]`
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  const id = read_required_string(record, 'id', `${field}.id`, issues)
  const title = read_required_string(record, 'title', `${field}.title`, issues)
  const description = read_required_string(record, 'description', `${field}.description`, issues)
  const priority = read_enum(record.priority, RECOMMENDATION_PRIORITIES, `${field}.priority`, issues)
  const risk_level = read_enum(record.risk_level, RISK_LEVELS, `${field}.risk_level`, issues)
  const requires_approval = read_boolean(record.requires_approval)
  if (requires_approval === undefined) issues.push({ field: `${field}.requires_approval`, message: '必须是布尔值。' })
  const evidence_ids = read_string_array(record.evidence_ids, `${field}.evidence_ids`, issues)
  if (id === undefined || title === undefined || description === undefined || priority === undefined || risk_level === undefined || requires_approval === undefined || evidence_ids === undefined) return undefined
  return { description, evidence_ids, id, priority, requires_approval, risk_level, title }
}

function read_risk(value: unknown, index: number, issues: ResultProtocolIssue[]): DiagnosisRisk | undefined {
  const field = `risks[${index}]`
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  const id = read_required_string(record, 'id', `${field}.id`, issues)
  const level = read_enum(record.level, RISK_LEVELS.filter((item) => item !== 'none'), `${field}.level`, issues)
  const summary = read_required_string(record, 'summary', `${field}.summary`, issues)
  const mitigation = read_nullable_string(record, 'mitigation', `${field}.mitigation`, issues)
  if (id === undefined || level === undefined || summary === undefined || mitigation === undefined) return undefined
  return { id, level, mitigation, summary }
}

function read_agent_summary(value: unknown, index: number, issues: ResultProtocolIssue[]): DiagnosisAgentSummary | undefined {
  const field = `agent_summary[${index}]`
  const record = read_record(value)
  if (!record) {
    issues.push({ field, message: '必须是对象。' })
    return undefined
  }
  const agent = read_required_string(record, 'agent', `${field}.agent`, issues)
  const status = read_enum(record.status, AGENT_STATUSES, `${field}.status`, issues)
  const summary = read_required_string(record, 'summary', `${field}.summary`, issues)
  let duration_ms: number | null | undefined
  if (record.duration_ms === null) duration_ms = null
  else if (typeof record.duration_ms === 'number' && Number.isSafeInteger(record.duration_ms) && record.duration_ms >= 0) duration_ms = record.duration_ms
  else {
    issues.push({ field: `${field}.duration_ms`, message: '必须是非负整数或 null。' })
    duration_ms = undefined
  }
  if (agent === undefined || status === undefined || summary === undefined || duration_ms === undefined) return undefined
  return { agent, duration_ms, status, summary }
}

function read_array<TValue>(
  value: unknown,
  field: string,
  issues: ResultProtocolIssue[],
  reader: (item: unknown, index: number, current_issues: ResultProtocolIssue[]) => TValue | undefined,
): TValue[] | undefined {
  if (!Array.isArray(value)) {
    issues.push({ field, message: '必须是数组。' })
    return undefined
  }
  const items = value.map((item, index) => reader(item, index, issues))
  return items.some((item) => item === undefined) ? undefined : items as TValue[]
}

/**
 * 将未知 API 载荷投影为可安全渲染的结构化诊断结果。
 */
export function read_diagnosis_result(value: unknown, expected_run_id: string): DiagnosisResultReadResult {
  const issues: ResultProtocolIssue[] = []
  const record = read_record(value)
  if (!record) return { issues: [{ field: 'result', message: '必须是对象。' }] }

  const id = read_required_string(record, 'id', 'id', issues)
  const run_id = read_required_string(record, 'run_id', 'run_id', issues)
  if (run_id && run_id !== expected_run_id) issues.push({ field: 'run_id', message: '必须与当前选定 Run 一致。' })
  const summary = read_required_string(record, 'summary', 'summary', issues)
  const severity = read_enum(record.severity, DIAGNOSIS_SEVERITIES, 'severity', issues)
  const confidence = read_confidence(record.confidence, 'confidence', issues)
  const root_causes = read_array(record.root_causes, 'root_causes', issues, read_root_cause)
  const evidence = read_array(record.evidence, 'evidence', issues, read_evidence)
  const impact = has_value(record.impact, 'impact', issues) ? read_impact(record.impact, issues) : undefined
  const recommendations = read_array(record.recommendations, 'recommendations', issues, read_recommendation)
  const risks = read_array(record.risks, 'risks', issues, read_risk)
  const requires_approval = read_boolean(record.requires_approval)
  if (requires_approval === undefined) issues.push({ field: 'requires_approval', message: '必须是布尔值。' })
  const agent_summary = read_array(record.agent_summary, 'agent_summary', issues, read_agent_summary)
  const report_markdown = read_nullable_string(record, 'report_markdown', 'report_markdown', issues)
  const created_at = read_utc_z(record.created_at, 'created_at', issues)

  if (
    issues.length > 0 || id === undefined || run_id === undefined || summary === undefined || severity === undefined || confidence === undefined || root_causes === undefined || evidence === undefined
    || impact === undefined || recommendations === undefined || risks === undefined || requires_approval === undefined || agent_summary === undefined
    || report_markdown === undefined || !created_at
  ) {
    return { issues }
  }

  return {
    issues: [],
    result: {
      agent_summary,
      confidence,
      created_at,
      evidence,
      id,
      impact,
      recommendations,
      report_markdown,
      requires_approval,
      risks,
      root_causes,
      run_id,
      severity,
      summary,
    },
  }
}
