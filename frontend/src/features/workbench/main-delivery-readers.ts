import { read_record, read_string } from './resource-readers'
import type { ResultProtocolIssue } from './result-readers'
import type { PersistedRunEvent } from './run-events'

const DELIVERY_KINDS = ['answer', 'needs_input', 'comparison'] as const
const DIFF_BLOCK_KINDS = ['added', 'deleted', 'modified'] as const
const COMPARISON_STATUSES = ['no_difference', 'has_difference'] as const
const MATERIAL_SIDES = ['text_a', 'text_b'] as const
const COMPARISON_CAPABILITY_ID = 'text.literal_compare'
const LITERAL_RULE_VERSION = 'literal-lines@1'
const CAPABILITY_KINDS = ['knowledge', 'execution'] as const
const CAPABILITY_USE_STATUSES = ['loaded', 'ok', 'unavailable'] as const
const CAPABILITIES_STATUSES = ['available', 'unavailable', 'absent'] as const
const LIVE_DECISIONS = ['answer', 'needs_input', 'load_skill', 'invoke_capability', 'budget_exhausted', 'failed'] as const
const MAX_LIVE_STEPS = 6
const AGENT_OUTCOMES = [
  'answer',
  'answer_with_knowledge',
  'needs_input',
  'comparison',
  'failed',
  'budget_exhausted',
  'canceled',
] as const

/** 知识辅助回答的固定标注；页面不展示「已校验／已读取／已诊断」。 */
export const KNOWLEDGE_GROUNDING_NOTE = '知识辅助回答 · 未读取实时数据'

export type MainDeliveryKind = (typeof DELIVERY_KINDS)[number]
export type MainDiffBlockKind = (typeof DIFF_BLOCK_KINDS)[number]
export type MainComparisonStatus = (typeof COMPARISON_STATUSES)[number]
export type MainMaterialSide = (typeof MATERIAL_SIDES)[number]
export type MainCapabilityKind = (typeof CAPABILITY_KINDS)[number]
export type MainCapabilityUseStatus = (typeof CAPABILITY_USE_STATUSES)[number]
export type MainCapabilitiesStatus = (typeof CAPABILITIES_STATUSES)[number]

export interface MainKnowledgeGroundingProjection {
  capability_id: string
  capability_version: number
  data_access: 'none'
  note: typeof KNOWLEDGE_GROUNDING_NOTE
  skill_id: string
  skill_version: number
}

export interface MainAnswerDeliveryProjection {
  kind: 'answer'
  knowledge_grounding: MainKnowledgeGroundingProjection | null
  text: string
}

export interface MainCapabilityUseProjection {
  capability_id: string
  capability_version: number
  kind: MainCapabilityKind
  status: MainCapabilityUseStatus
}

export interface MainCapabilitiesProjection {
  degraded: MainCapabilityUseProjection[]
  steps: number | null
  used: MainCapabilityUseProjection[]
}

export interface MainCapabilitiesReadResult {
  capabilities?: MainCapabilitiesProjection
  issues: ResultProtocolIssue[]
  status?: MainCapabilitiesStatus
}

export interface MainKnowledgeReadResult {
  grounding?: MainKnowledgeGroundingProjection
  issues: ResultProtocolIssue[]
}

export interface MainNeedsInputDeliveryProjection {
  kind: 'needs_input'
  missing: MainMaterialSide[]
  prompt: string
}

export interface MainTextDiffBlockProjection {
  a_end: number | null
  a_quote: string | null
  a_start: number | null
  b_end: number | null
  b_quote: string | null
  b_start: number | null
  kind: MainDiffBlockKind
}

export interface MainComparisonDeliveryProjection {
  a_material_id: string
  b_material_id: string
  blocks: MainTextDiffBlockProjection[]
  capability_id: typeof COMPARISON_CAPABILITY_ID
  capability_version: number
  kind: 'comparison'
  rule_version: typeof LITERAL_RULE_VERSION
  status: MainComparisonStatus
}

export type MainDeliveryProjection =
  | MainAnswerDeliveryProjection
  | MainNeedsInputDeliveryProjection
  | MainComparisonDeliveryProjection

export interface MainMaterialProjection {
  content_sha256: string
  material_id: string
  original_text: string
}

export interface MainInputSnapshotProjection {
  query: string
  rule_version: typeof LITERAL_RULE_VERSION
  text_a: MainMaterialProjection | null
  text_b: MainMaterialProjection | null
}

export interface MainDeliveryReadResult {
  delivery?: MainDeliveryProjection
  issues: ResultProtocolIssue[]
}

export interface MainInputSnapshotReadResult {
  issues: ResultProtocolIssue[]
  snapshot?: MainInputSnapshotProjection
}

function push(issues: ResultProtocolIssue[], field: string, message: string): void {
  issues.push({ field, message })
}

function read_object(value: unknown, field: string, issues: ResultProtocolIssue[]): Record<string, unknown> | undefined {
  const record = read_record(value)
  if (record === undefined) push(issues, field, '必须是对象。')
  return record
}

function read_text(value: unknown, field: string, issues: ResultProtocolIssue[]): string | undefined {
  const text = read_string(value)
  if (text === undefined) push(issues, field, '必须是字符串。')
  return text
}

function read_number(value: unknown, field: string, issues: ResultProtocolIssue[]): number | undefined {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value
  push(issues, field, '必须是正整数行号。')
  return undefined
}

function read_text_or_null(
  record: Record<string, unknown>,
  key: string,
  field: string,
  issues: ResultProtocolIssue[],
): string | null | undefined {
  if (record[key] === null || record[key] === undefined) return null
  return read_text(record[key], field, issues)
}

function read_line_range(
  record: Record<string, unknown>,
  side: 'a' | 'b',
  field: string,
  issues: ResultProtocolIssue[],
): { start: number | null; end: number | null } | undefined {
  if (record[`${side}_start`] === null || record[`${side}_start`] === undefined) return { start: null, end: null }
  const start = read_number(record[`${side}_start`], `${field}.${side}_start`, issues)
  const end = read_number(record[`${side}_end`], `${field}.${side}_end`, issues)
  if (start === undefined || end === undefined) return undefined
  if (start > end) {
    push(issues, `${field}.${side}_end`, '结束行号不得早于起始行号。')
    return undefined
  }
  return { start, end }
}

function read_diff_block(value: unknown, index: number, issues: ResultProtocolIssue[]): MainTextDiffBlockProjection | undefined {
  const field = `blocks[${index}]`
  const record = read_object(value, field, issues)
  if (record === undefined) return undefined
  const kind = read_enum(record.kind, DIFF_BLOCK_KINDS, `${field}.kind`, issues)
  const range_a = read_line_range(record, 'a', field, issues)
  const range_b = read_line_range(record, 'b', field, issues)
  const a_quote = read_text_or_null(record, 'a_quote', `${field}.a_quote`, issues)
  const b_quote = read_text_or_null(record, 'b_quote', `${field}.b_quote`, issues)
  if (kind === undefined || range_a === undefined || range_b === undefined) return undefined
  if (a_quote === undefined || b_quote === undefined) return undefined
  return {
    a_end: range_a.end,
    a_quote,
    a_start: range_a.start,
    b_end: range_b.end,
    b_quote,
    b_start: range_b.start,
    kind,
  }
}

function read_enum<TValue extends string>(
  value: unknown,
  allowed: readonly TValue[],
  field: string,
  issues: ResultProtocolIssue[],
): TValue | undefined {
  if (typeof value === 'string' && allowed.includes(value as TValue)) return value as TValue
  push(issues, field, `必须是允许的枚举值：${allowed.join('、')}。`)
  return undefined
}

function read_enum_or_undefined<TValue extends string>(
  value: unknown,
  allowed: readonly TValue[],
): TValue | undefined {
  return typeof value === 'string' && allowed.includes(value as TValue) ? (value as TValue) : undefined
}

function read_nonempty_text(value: unknown, field: string, issues: ResultProtocolIssue[]): string | undefined {
  const text = read_text(value, field, issues)
  if (text === undefined) return undefined
  if (!text.trim()) {
    push(issues, field, '不能为空。')
    return undefined
  }
  return text
}

function read_positive_int(value: unknown, field: string, issues: ResultProtocolIssue[]): number | undefined {
  if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 1) return value
  push(issues, field, '必须是正整数。')
  return undefined
}

/** 实时事件里的步骤号必须落在后端主 Agent 决策上限内。 */
function read_step(value: unknown, field: string, issues: ResultProtocolIssue[]): number | undefined {
  const step = read_positive_int(value, field, issues)
  if (step === undefined) return undefined
  if (step > MAX_LIVE_STEPS) {
    push(issues, field, `必须不超过 ${MAX_LIVE_STEPS}。`)
    return undefined
  }
  return step
}

/** 只接受服务端固定知识标注；结构不符时整体拒绝，绝不把普通回答标成知识回答。 */
function read_knowledge_grounding(
  value: unknown,
  field: string,
  issues: ResultProtocolIssue[],
): MainKnowledgeGroundingProjection | null | undefined {
  if (value === null || value === undefined) return null
  const record = read_object(value, field, issues)
  if (record === undefined) return undefined
  const capability_id = read_nonempty_text(record.capability_id, `${field}.capability_id`, issues)
  const capability_version = read_positive_int(record.capability_version, `${field}.capability_version`, issues)
  const skill_id = read_nonempty_text(record.skill_id, `${field}.skill_id`, issues)
  const skill_version = read_positive_int(record.skill_version, `${field}.skill_version`, issues)
  if (record.data_access !== 'none') {
    push(issues, `${field}.data_access`, '知识辅助回答不得声明读取实时数据。')
    return undefined
  }
  if (record.note !== KNOWLEDGE_GROUNDING_NOTE) {
    push(issues, `${field}.note`, `知识标注必须固定为「${KNOWLEDGE_GROUNDING_NOTE}」。`)
    return undefined
  }
  if (capability_id === undefined || capability_version === undefined) return undefined
  if (skill_id === undefined || skill_version === undefined) return undefined
  return {
    capability_id,
    capability_version,
    data_access: 'none',
    note: KNOWLEDGE_GROUNDING_NOTE,
    skill_id,
    skill_version,
  }
}

function read_capability_use(
  value: unknown,
  field: string,
  issues: ResultProtocolIssue[],
): MainCapabilityUseProjection | undefined {
  const record = read_object(value, field, issues)
  if (record === undefined) return undefined
  const capability_id = read_nonempty_text(record.capability_id, `${field}.capability_id`, issues)
  const capability_version = read_positive_int(record.capability_version, `${field}.capability_version`, issues)
  const kind = read_enum(record.kind, CAPABILITY_KINDS, `${field}.kind`, issues)
  const status = read_enum(record.status, CAPABILITY_USE_STATUSES, `${field}.status`, issues)
  if (capability_id === undefined || capability_version === undefined) return undefined
  if (kind === undefined || status === undefined) return undefined
  return { capability_id, capability_version, kind, status }
}

function read_capability_uses(
  value: unknown,
  field: string,
  issues: ResultProtocolIssue[],
): MainCapabilityUseProjection[] | undefined {
  if (!Array.isArray(value)) {
    push(issues, field, '必须是数组。')
    return undefined
  }
  const items = value
    .map((item, index) => read_capability_use(item, `${field}[${index}]`, issues))
    .filter((item): item is MainCapabilityUseProjection => item !== undefined)
  return items.length === value.length ? items : undefined
}


function read_comparison(
  record: Record<string, unknown>,
  issues: ResultProtocolIssue[],
): MainComparisonDeliveryProjection | undefined {
  const capability_id = read_text(record.capability_id, 'capability_id', issues)
  if (capability_id !== undefined && capability_id !== COMPARISON_CAPABILITY_ID) {
    push(issues, 'capability_id', `必须是 ${COMPARISON_CAPABILITY_ID}。`)
    return undefined
  }
  const capability_version = typeof record.capability_version === 'number' ? record.capability_version : undefined
  if (capability_version === undefined) push(issues, 'capability_version', '必须是数值版本。')
  const rule_version = read_text(record.rule_version, 'rule_version', issues)
  if (rule_version !== undefined && rule_version !== LITERAL_RULE_VERSION) {
    push(issues, 'rule_version', `必须是 ${LITERAL_RULE_VERSION}。`)
    return undefined
  }
  const status = read_enum(record.status, COMPARISON_STATUSES, 'status', issues)
  const a_material_id = read_text(record.a_material_id, 'a_material_id', issues)
  const b_material_id = read_text(record.b_material_id, 'b_material_id', issues)
  const block_values = Array.isArray(record.blocks) ? record.blocks : undefined
  if (block_values === undefined) {
    push(issues, 'blocks', '必须是数组。')
    return undefined
  }
  const blocks = block_values
    .map((item, index) => read_diff_block(item, index, issues))
    .filter((item): item is MainTextDiffBlockProjection => item !== undefined)
  if (blocks.length !== block_values.length) return undefined
  if (capability_id === undefined || capability_version === undefined || rule_version === undefined) return undefined
  if (status === undefined || a_material_id === undefined || b_material_id === undefined) return undefined
  return {
    a_material_id,
    b_material_id,
    blocks,
    capability_id: COMPARISON_CAPABILITY_ID,
    capability_version,
    kind: 'comparison',
    rule_version: LITERAL_RULE_VERSION,
    status,
  }
}

function read_needs_input(
  record: Record<string, unknown>,
  issues: ResultProtocolIssue[],
): MainNeedsInputDeliveryProjection | undefined {
  const values = Array.isArray(record.missing) ? record.missing : undefined
  if (values === undefined) {
    push(issues, 'missing', '必须是缺失侧数组。')
    return undefined
  }
  const missing = values
    .map((item, index) => read_enum(item, MATERIAL_SIDES, `missing[${index}]`, issues))
    .filter((item): item is MainMaterialSide => item !== undefined)
  if (missing.length !== values.length) return undefined
  const prompt = read_text(record.prompt, 'prompt', issues)
  if (prompt === undefined) return undefined
  return { kind: 'needs_input', missing, prompt }
}

export function read_main_delivery(value: unknown): MainDeliveryReadResult {
  const issues: ResultProtocolIssue[] = []
  const record = read_object(value, 'delivery', issues)
  if (record === undefined) return { issues }
  const kind = read_enum(record.kind, DELIVERY_KINDS, 'delivery.kind', issues)
  if (kind === 'answer') {
    const text = read_text(record.text, 'delivery.text', issues)
    const knowledge_grounding = read_knowledge_grounding(
      record.knowledge_grounding,
      'delivery.knowledge_grounding',
      issues,
    )
    if (text === undefined || knowledge_grounding === undefined) return { issues }
    return { delivery: { knowledge_grounding, kind: 'answer', text }, issues }
  }
  if (kind === 'needs_input') {
    const delivery = read_needs_input(record, issues)
    return delivery ? { delivery, issues } : { issues }
  }
  if (kind === 'comparison') {
    const delivery = read_comparison(record, issues)
    return delivery ? { delivery, issues } : { issues }
  }
  return { issues }
}

function read_material(value: unknown, field: string, issues: ResultProtocolIssue[]): MainMaterialProjection | null | undefined {
  if (value === null || value === undefined) return null
  const record = read_object(value, field, issues)
  if (record === undefined) return undefined
  const material_id = read_text(record.material_id, `${field}.material_id`, issues)
  const original_text = read_text(record.original_text, `${field}.original_text`, issues)
  const content_sha256 = read_text(record.content_sha256, `${field}.content_sha256`, issues)
  if (material_id === undefined || original_text === undefined || content_sha256 === undefined) return undefined
  return { content_sha256, material_id, original_text }
}

export function read_main_input_snapshot(value: unknown): MainInputSnapshotReadResult {
  const issues: ResultProtocolIssue[] = []
  const record = read_object(value, 'input_snapshot', issues)
  if (record === undefined) return { issues }
  const query = read_text(record.query, 'input_snapshot.query', issues)
  const rule_version = read_text(record.rule_version, 'input_snapshot.rule_version', issues)
  if (rule_version !== undefined && rule_version !== LITERAL_RULE_VERSION) {
    push(issues, 'input_snapshot.rule_version', `必须是 ${LITERAL_RULE_VERSION}。`)
    return { issues }
  }
  const text_a = read_material(record.text_a, 'input_snapshot.text_a', issues)
  const text_b = read_material(record.text_b, 'input_snapshot.text_b', issues)
  if (query === undefined || rule_version === undefined || text_a === undefined || text_b === undefined) return { issues }
  return {
    issues,
    snapshot: { query, rule_version: LITERAL_RULE_VERSION, text_a, text_b },
  }
}

/**
 * 读取公开能力归属；`available` 下字段损坏按 `unavailable` 失败关闭，
 * 页面不会把半截数据渲染成"本次使用了某能力"。
 */
export function read_main_capabilities(value: unknown, status_value: unknown): MainCapabilitiesReadResult {
  const issues: ResultProtocolIssue[] = []
  const status = read_enum_or_undefined(status_value, CAPABILITIES_STATUSES)
  if (status === undefined) {
    if (status_value !== undefined && status_value !== null) {
      push(issues, 'main_capabilities_status', '能力归属状态不受支持。')
    }
    return { issues, status: undefined }
  }
  if (status === 'absent') return { issues, status }
  const empty: MainCapabilitiesProjection = { degraded: [], steps: null, used: [] }
  const record = read_object(value, 'main_capabilities', issues)
  if (record === undefined) {
    return status === 'unavailable' ? { capabilities: empty, issues: [], status } : { issues, status: 'unavailable' }
  }
  const used = read_capability_uses(record.used, 'main_capabilities.used', issues)
  const degraded = read_capability_uses(record.degraded, 'main_capabilities.degraded', issues)
  let steps: number | null | undefined = null
  if (record.steps !== null && record.steps !== undefined) {
    steps = read_positive_int(record.steps, 'main_capabilities.steps', issues)
  }
  if (used === undefined || degraded === undefined || steps === undefined) {
    return { capabilities: empty, issues, status: 'unavailable' }
  }
  if (used.some((item) => item.status === 'unavailable') || degraded.some((item) => item.status !== 'unavailable')) {
    push(issues, 'main_capabilities', '使用与降级列表的状态互相矛盾。')
    return { capabilities: empty, issues, status: 'unavailable' }
  }
  return { capabilities: { degraded, steps, used }, issues, status }
}

/** 读取知识接地；缺失返回空投影，结构不符返回问题并拒绝渲染徽标。 */
export function read_main_knowledge(value: unknown): MainKnowledgeReadResult {
  if (value === null || value === undefined) return { issues: [] }
  const issues: ResultProtocolIssue[] = []
  const grounding = read_knowledge_grounding(value, 'main_knowledge', issues)
  return grounding === undefined || grounding === null ? { issues } : { grounding, issues }
}

/**
 * 从实时 Run 事件流投影能力归属（Design §2.7）。
 *
 * 事件字段是公开 SSE 数据，仍按封闭枚举与标量类型严格校验；
 * 任一损坏字段都让整次投影失败关闭，不在实时态猜测能力身份。
 */
export function read_live_main_capabilities(events: readonly PersistedRunEvent[]): MainCapabilitiesReadResult {
  const issues: ResultProtocolIssue[] = []
  const used = new Map<string, MainCapabilityUseProjection>()
  const degraded = new Map<string, MainCapabilityUseProjection>()
  let steps: number | null = null
  let malformed = false

  for (const event of events) {
    const data = event.data
    if (event.type === 'route_decided') {
      const decision = data.decision
      const step = data.step
      const status = data.status
      if (
        typeof decision !== 'string'
        || !LIVE_DECISIONS.includes(decision as (typeof LIVE_DECISIONS)[number])
        || !read_step(step, 'route_decided.step', issues)
        || (status !== undefined && (typeof status !== 'string' || !['ok', 'unavailable'].includes(status)))
      ) {
        malformed = true
        break
      }
      const event_step = step as number
      steps = steps === null ? event_step : Math.max(steps, event_step)
      const capability_id = data.capability_id
      if (capability_id === undefined || capability_id === null) {
        if (data.capability_version != null || data.capability_kind != null) {
          malformed = true
          break
        }
        continue
      }
      const capability_version = read_positive_int(data.capability_version, 'route_decided.capability_version', issues)
      const kind = read_enum_or_undefined(data.capability_kind, CAPABILITY_KINDS)
      if (
        typeof capability_id !== 'string'
        || !capability_id
        || capability_version === undefined
        || kind === undefined
        || status === undefined
        || (status === 'ok' && decision !== 'load_skill' && decision !== 'invoke_capability')
      ) {
        malformed = true
        break
      }
      const item_status: MainCapabilityUseStatus =
        status === 'unavailable' ? 'unavailable' : decision === 'load_skill' ? 'loaded' : 'ok'
      const item: MainCapabilityUseProjection = {
        capability_id,
        capability_version,
        kind,
        status: item_status,
      }
      const key = `${capability_id}@${capability_version}`
      if (status === 'ok') used.set(key, item)
      else degraded.set(key, item)
    } else if (event.type === 'agent_done') {
      const event_steps = data.steps
      const outcome = data.outcome
      if (
        read_step(event_steps, 'agent_done.steps', issues) === undefined
        || typeof outcome !== 'string'
        || !AGENT_OUTCOMES.includes(outcome as (typeof AGENT_OUTCOMES)[number])
      ) {
        malformed = true
        break
      }
      steps = event_steps as number
    }
  }

  const empty: MainCapabilitiesProjection = { degraded: [], steps: null, used: [] }
  if (malformed) return { capabilities: empty, issues, status: 'unavailable' }
  if (used.size === 0 && degraded.size === 0) return { issues, status: 'absent' }
  for (const key of used.keys()) degraded.delete(key)
  return {
    capabilities: { degraded: [...degraded.values()], steps, used: [...used.values()] },
    issues,
    status: 'available',
  }
}
