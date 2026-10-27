import { describe, expect, it } from 'vitest'

import {
  KNOWLEDGE_GROUNDING_NOTE,
  read_live_main_capabilities,
  read_main_capabilities,
  read_main_delivery,
  read_main_input_snapshot,
  read_main_knowledge,
} from './main-delivery-readers'
import type { PersistedRunEvent, RunEventType } from './run-events'

const ANSWER = { kind: 'answer', text: '两份文本的第三行不同。' }
const GROUNDING = {
  capability_id: 'ops.readonly_playbook',
  capability_version: 1,
  data_access: 'none',
  note: KNOWLEDGE_GROUNDING_NOTE,
  skill_id: 'ops.readonly_playbook',
  skill_version: 1,
}
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
    expect(read_main_delivery(ANSWER).delivery).toEqual({ knowledge_grounding: null, kind: 'answer', text: ANSWER.text })
    expect(read_main_delivery(NEEDS_INPUT).delivery).toEqual(NEEDS_INPUT)
  })

  it('知识辅助回答只接受固定接地声明，不把缺失或伪造标注当成知识回答', () => {
    const grounded = { ...ANSWER, knowledge_grounding: GROUNDING }
    expect(read_main_delivery(grounded).delivery).toEqual({
      knowledge_grounding: GROUNDING,
      kind: 'answer',
      text: ANSWER.text,
    })
    expect(read_main_delivery({ ...ANSWER, knowledge_grounding: { ...GROUNDING, data_access: 'read' } }).delivery).toBeUndefined()
    expect(read_main_delivery({ ...ANSWER, knowledge_grounding: { ...GROUNDING, note: '已读取实时数据' } }).delivery).toBeUndefined()
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

describe('read_main_capabilities', () => {
  const USED = {
    capability_id: 'text.literal_compare',
    capability_version: 1,
    kind: 'execution',
    status: 'ok',
  }
  const DEGRADED = {
    capability_id: 'ops.readonly_playbook',
    capability_version: 1,
    kind: 'knowledge',
    status: 'unavailable',
  }

  it('投影 used／degraded／steps 与可用状态', () => {
    const read = read_main_capabilities(
      { degraded: [DEGRADED], steps: 2, used: [USED] },
      'available',
    )
    expect(read.issues).toEqual([])
    expect(read.status).toBe('available')
    expect(read.capabilities).toEqual({ degraded: [DEGRADED], steps: 2, used: [USED] })
  })

  it('absent 表示没有能力归属，不伪造空数据', () => {
    const read = read_main_capabilities(undefined, 'absent')
    expect(read).toEqual({ issues: [], status: 'absent' })
    expect(read_main_capabilities(undefined, undefined).status).toBeUndefined()
  })

  it('unavailable 或损坏字段一律诚实降级，不部分渲染', () => {
    const unavailable = read_main_capabilities({ degraded: [], steps: null, used: [] }, 'unavailable')
    expect(unavailable.status).toBe('unavailable')
    expect(unavailable.capabilities).toEqual({ degraded: [], steps: null, used: [] })

    const malformed = read_main_capabilities(
      { degraded: [{ ...DEGRADED, status: 'ok' }], steps: 1, used: [] },
      'available',
    )
    expect(malformed.status).toBe('unavailable')
    expect(malformed.issues.length).toBeGreaterThan(0)
  })
})

describe('read_main_knowledge', () => {
  it('只接受固定知识标注；缺失时返回空投影', () => {
    expect(read_main_knowledge(GROUNDING).grounding).toEqual(GROUNDING)
    expect(read_main_knowledge(null)).toEqual({ issues: [] })
    expect(read_main_knowledge({ ...GROUNDING, capability_id: '' }).grounding).toBeUndefined()
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

function live_event(type: RunEventType, data: Record<string, unknown>, sequence = 1): PersistedRunEvent {
  return {
    data,
    id: `event-${sequence}`,
    occurred_at: '2026-10-27T00:00:00.000Z',
    run_id: 'run-live',
    sequence,
    type,
  }
}

describe('read_live_main_capabilities', () => {
  it('从实时事件投影知识装载、执行调用与步数', () => {
    const result = read_live_main_capabilities([
      live_event('route_decided', {
        capability_id: 'ops.readonly_playbook',
        capability_kind: 'knowledge',
        capability_version: 1,
        decision: 'load_skill',
        status: 'ok',
        step: 1,
      }),
      live_event('route_decided', {
        capability_id: 'text.literal_compare',
        capability_kind: 'execution',
        capability_version: 1,
        decision: 'invoke_capability',
        status: 'ok',
        step: 2,
      }, 2),
      live_event('agent_done', { outcome: 'comparison', steps: 2 }, 3),
    ])

    expect(result.status).toBe('available')
    expect(result.capabilities).toEqual({
      degraded: [],
      steps: 2,
      used: [
        { capability_id: 'ops.readonly_playbook', capability_version: 1, kind: 'knowledge', status: 'loaded' },
        { capability_id: 'text.literal_compare', capability_version: 1, kind: 'execution', status: 'ok' },
      ],
    })
  })

  it('降级能力进入 degraded，直答没有能力使用时为 absent', () => {
    const degraded = read_live_main_capabilities([
      live_event('route_decided', {
        capability_id: 'ops.readonly_playbook',
        capability_kind: 'knowledge',
        capability_version: 1,
        decision: 'load_skill',
        status: 'unavailable',
        step: 1,
      }),
    ])
    expect(degraded.status).toBe('available')
    expect(degraded.capabilities?.degraded).toEqual([
      { capability_id: 'ops.readonly_playbook', capability_version: 1, kind: 'knowledge', status: 'unavailable' },
    ])

    const plain = read_live_main_capabilities([
      live_event('route_decided', { decision: 'answer', status: 'ok', step: 1 }),
      live_event('agent_done', { outcome: 'answer', steps: 1 }, 2),
    ])
    expect(plain).toEqual({ issues: [], status: 'absent' })
  })

  it('预算耗尽与失败决策按后端语义处理，不误判为损坏事件', () => {
    const budget = read_live_main_capabilities([
      live_event('route_decided', {
        capability_id: 'text.literal_compare',
        capability_kind: 'execution',
        capability_version: 1,
        decision: 'budget_exhausted',
        status: 'unavailable',
        step: 2,
      }),
    ])
    expect(budget.status).toBe('available')
    expect(budget.capabilities?.degraded).toEqual([
      { capability_id: 'text.literal_compare', capability_version: 1, kind: 'execution', status: 'unavailable' },
    ])

    const failed = read_live_main_capabilities([
      live_event('route_decided', { decision: 'failed', status: 'unavailable', step: 1 }),
    ])
    expect(failed.status).toBe('absent')
  })

  it('超过决策上限的步骤号失败关闭', () => {
    const result = read_live_main_capabilities([
      live_event('route_decided', {
        capability_id: 'ops.readonly_playbook',
        capability_kind: 'knowledge',
        capability_version: 1,
        decision: 'load_skill',
        status: 'ok',
        step: 99,
      }),
    ])
    expect(result.status).toBe('unavailable')
  })

  it('非标量或未知事件字段失败关闭，不猜测能力身份', () => {
    const corrupted = read_live_main_capabilities([
      live_event('route_decided', { decision: [], step: 1 }),
    ])
    expect(corrupted.status).toBe('unavailable')
    expect(corrupted.capabilities).toEqual({ degraded: [], steps: null, used: [] })

    const bad_outcome = read_live_main_capabilities([
      live_event('agent_done', { outcome: [], steps: 1 }),
    ])
    expect(bad_outcome.status).toBe('unavailable')
  })
})
