import { describe, expect, it } from 'vitest'

import { read_main_delivery, read_main_input_snapshot } from './main-delivery-readers'

const ANSWER = { kind: 'answer', text: '两份文本的第三行不同。' }
const NEEDS_INPUT = { kind: 'needs_input', missing: ['text_b'], prompt: '请补充文本 B。' }
const BLOCK = {
  a_end: 2,
  a_quote: 'beta',
  a_start: 2,
  b_end: 2,
  b_quote: 'gamma',
  b_start: 2,
  kind: 'modified',
}
const COMPARISON = {
  a_material_id: 'material-a',
  b_material_id: 'material-b',
  blocks: [BLOCK],
  capability_id: 'text.literal_compare',
  capability_version: 1,
  kind: 'comparison',
  rule_version: 'literal-lines@1',
  status: 'has_difference',
}

describe('read_main_delivery', () => {
  it('投影 answer 与 needs_input 交付', () => {
    expect(read_main_delivery(ANSWER).delivery).toEqual({ kind: 'answer', text: ANSWER.text })
    expect(read_main_delivery(NEEDS_INPUT).delivery).toEqual(NEEDS_INPUT)
  })

  it('投影 comparison 的差异块与规则版本', () => {
    const read = read_main_delivery(COMPARISON)
    expect(read.issues).toEqual([])
    expect(read.delivery).toEqual(COMPARISON)
  })

  it('未知交付类型或非法能力标识只报协议问题，不猜测渲染', () => {
    expect(read_main_delivery({ kind: 'unknown' }).delivery).toBeUndefined()
    expect(read_main_delivery({ ...COMPARISON, capability_id: 'text.other' }).delivery).toBeUndefined()
    expect(read_main_delivery(null).issues.length).toBeGreaterThan(0)
  })

  it('行号倒挂或非正整数行号视为契约违规', () => {
    const reversed = { ...COMPARISON, blocks: [{ ...BLOCK, a_end: 1 }] }
    expect(read_main_delivery(reversed).delivery).toBeUndefined()
    const zero_start = { ...COMPARISON, blocks: [{ ...BLOCK, a_start: 0 }] }
    expect(read_main_delivery(zero_start).delivery).toBeUndefined()
  })

  it('新增块可以没有 A 侧行号与引文', () => {
    const added = {
      ...COMPARISON,
      blocks: [{ ...BLOCK, a_end: null, a_quote: null, a_start: null, kind: 'added' }],
    }
    expect(read_main_delivery(added).delivery).toEqual(added)
  })
})

describe('read_main_input_snapshot', () => {
  const material = { content_sha256: 'a'.repeat(64), material_id: 'material-a', original_text: 'alpha\nbeta' }

  it('投影目标与两段材料', () => {
    const snapshot = { query: '比较这两段文本', rule_version: 'literal-lines@1', text_a: material, text_b: material }
    expect(read_main_input_snapshot(snapshot).snapshot).toEqual(snapshot)
  })

  it('缺失一侧保持 null，但规则版本不符时拒绝投影', () => {
    const partial = { query: '比较', rule_version: 'literal-lines@1', text_a: material, text_b: null }
    expect(read_main_input_snapshot(partial).snapshot).toEqual(partial)
    expect(read_main_input_snapshot({ ...partial, rule_version: 'other@1' }).snapshot).toBeUndefined()
  })

  it('材料缺少原文时按协议问题处理，不用空字符串代替', () => {
    const broken = { query: '比较', rule_version: 'literal-lines@1', text_a: { ...material, original_text: 42 }, text_b: null }
    expect(read_main_input_snapshot(broken).snapshot).toBeUndefined()
  })
})
