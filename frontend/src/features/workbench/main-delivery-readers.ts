import { read_record, read_string } from './resource-readers'
import type { ResultProtocolIssue } from './result-readers'

const DELIVERY_KINDS = ['answer', 'needs_input', 'comparison'] as const
const DIFF_BLOCK_KINDS = ['added', 'deleted', 'modified'] as const
const COMPARISON_STATUSES = ['no_difference', 'has_difference'] as const
const MATERIAL_SIDES = ['text_a', 'text_b'] as const
const COMPARISON_CAPABILITY_ID = 'text.literal_compare'
const LITERAL_RULE_VERSION = 'literal-lines@1'

export type MainDeliveryKind = (typeof DELIVERY_KINDS)[number]
export type MainDiffBlockKind = (typeof DIFF_BLOCK_KINDS)[number]
export type MainComparisonStatus = (typeof COMPARISON_STATUSES)[number]
export type MainMaterialSide = (typeof MATERIAL_SIDES)[number]

export interface MainAnswerDeliveryProjection {
  kind: 'answer'
  text: string
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
    if (text === undefined) return { issues }
    return { delivery: { kind: 'answer', text }, issues }
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
