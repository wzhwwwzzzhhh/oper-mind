import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DiagnosisResultPanel } from './DiagnosisResultPanel'
import { read_diagnosis_result } from './result-readers'

const RUN_ID = '33333333-3333-4333-8333-333333333333'

function complete_result() {
  return {
    agent_summary: [{ agent: 'server', duration_ms: 120, status: 'completed', summary: '已完成服务侧摘要。' }],
    confidence: 0.92,
    created_at: '2026-07-28T08:00:00.000Z',
    evidence: [{
      attributes: { count: 12, healthy: false, note: null },
      id: 'evidence-1',
      locator: 'nginx/upstream',
      observed_at: '2026-07-28T07:59:00.000Z',
      source_name: 'nginx-access',
      source_type: 'log',
      summary: '上游连接池耗尽。',
      title: 'Nginx 错误日志',
    }],
    id: '77777777-7777-4777-8777-777777777777',
    impact: { affected_scope: '支付入口', affected_services: ['gateway'], summary: '支付请求受影响。' },
    recommendations: [{
      description: '扩容连接池。', evidence_ids: ['evidence-1'], id: 'recommendation-1', priority: 'p1', requires_approval: true, risk_level: 'medium', title: '调整连接池',
    }],
    report_markdown: '# 补充诊断报告\n\n- 已核对结构化证据',
    requires_approval: true,
    risks: [{ id: 'risk-1', level: 'medium', mitigation: '分批发布。', summary: '扩容可能影响连接数。' }],
    root_causes: [{ confidence: 0.88, evidence_ids: ['evidence-1'], id: 'root-cause-1', summary: '连接池长期耗尽。', title: '上游连接池不足' }],
    run_id: RUN_ID,
    severity: 'high',
    summary: 'Nginx 上游连接池已耗尽。',
  }
}

describe('read_diagnosis_result', () => {
  it('投影完整且合法的 P2 结构化结果', () => {
    const read = read_diagnosis_result(complete_result(), RUN_ID)

    expect(read.issues).toEqual([])
    expect(read.result?.severity).toBe('high')
    expect(read.result?.evidence[0]?.attributes).toEqual({ count: 12, healthy: false, note: null })
  })

  it('接受契约允许的空字符串，而不把它们误判为缺失字段', () => {
    const result = complete_result()
    result.summary = ''
    result.root_causes[0].summary = ''

    const read = read_diagnosis_result(result, RUN_ID)

    expect(read.issues).toEqual([])
    expect(read.result?.summary).toBe('')
    expect(read.result?.root_causes[0]?.summary).toBe('')
  })

  it.each([
    ['run_id 不匹配', (result: Record<string, unknown>) => ({ ...result, run_id: 'other-run' }), 'run_id'],
    ['缺少 created_at', (result: Record<string, unknown>) => { const { created_at: _created_at, ...without_created_at } = result; return without_created_at }, 'created_at'],
    ['未知严重度', (result: Record<string, unknown>) => ({ ...result, severity: 'urgent' }), 'severity'],
    ['越界置信度', (result: Record<string, unknown>) => ({ ...result, confidence: 1.2 }), 'confidence'],
    ['非 UTC Z 时间', (result: Record<string, unknown>) => ({ ...result, created_at: '2026-07-28T08:00:00+08:00' }), 'created_at'],
  ])('拒绝%s', (_label, mutate, expected_field) => {
    const read = read_diagnosis_result(mutate(complete_result()), RUN_ID)

    expect(read.result).toBeUndefined()
    expect(read.issues.some((issue) => issue.field === expected_field)).toBe(true)
  })
})

describe('DiagnosisResultPanel', () => {
  it('呈现只读结构化区域，并在折叠区安全渲染完整报告 Markdown', () => {
    const read = read_diagnosis_result(complete_result(), RUN_ID)
    if (!read.result) throw new Error('测试夹具必须通过 Result reader')

    render(<DiagnosisResultPanel result={read.result} />)

    expect(screen.getByLabelText('诊断结果摘要')).toHaveTextContent('Nginx 上游连接池已耗尽。')
    expect(screen.getByText('上游连接池不足')).toBeInTheDocument()
    expect(screen.getByText('Nginx 错误日志')).toBeInTheDocument()
    expect(screen.getByText('定位信息：nginx/upstream')).toBeInTheDocument()
    // 根因与处置建议都会引用同一条证据，因此这里断言"至少出现一次"而不是唯一命中。
    expect(screen.getAllByText('证据 evidence-1').length).toBeGreaterThan(0)
    expect(screen.getByText('调查角色摘要')).toBeInTheDocument()
    expect(screen.getByText('已完成服务侧摘要。')).toBeInTheDocument()
    expect(screen.getByText('调查范围与风险')).toBeInTheDocument()
    expect(screen.getByText('扩容可能影响连接数。')).toBeInTheDocument()
    expect(screen.getByText('完整诊断报告')).toBeInTheDocument()
    fireEvent.click(screen.getByText('完整诊断报告'))
    expect(screen.getByRole('heading', { name: '补充诊断报告' })).toBeInTheDocument()
    expect(screen.getByText('已核对结构化证据')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('渲染后端已返回的影响面与处置建议，包含优先级、风险与审批要求', () => {
    const read = read_diagnosis_result(complete_result(), RUN_ID)
    if (!read.result) throw new Error('测试夹具必须通过 Result reader')

    render(<DiagnosisResultPanel result={read.result} />)

    expect(screen.getByText('支付请求受影响。')).toBeInTheDocument()
    expect(screen.getByText('影响范围：支付入口')).toBeInTheDocument()
    expect(screen.getByText('gateway')).toBeInTheDocument()
    expect(screen.getByText('调整连接池')).toBeInTheDocument()
    expect(screen.getByText('扩容连接池。')).toBeInTheDocument()
    expect(screen.getByText('P1 尽快处理')).toBeInTheDocument()
    // 建议的残留风险和风险清单都会写"中风险"，所以断言"至少出现一次"。
    expect(screen.getAllByText('中风险').length).toBeGreaterThan(0)
    expect(screen.getByText('需人工审批后执行')).toBeInTheDocument()
    expect(screen.getByText('整体需人工审批')).toBeInTheDocument()
  })

  it('风险清单用中文等级和存在样式规则的视觉等级类名，不泄露英文枚举值', () => {
    const read = read_diagnosis_result(complete_result(), RUN_ID)
    if (!read.result) throw new Error('测试夹具必须通过 Result reader')

    render(<DiagnosisResultPanel result={read.result} />)

    // 风险清单里的那一条：中风险 → warning，而不是没有规则的 --medium。
    const risk_tag = screen
      .getAllByText('中风险')
      .find((node) => node.parentElement?.textContent?.includes('扩容可能影响连接数。'))
    expect(risk_tag?.className).toContain('diagnosis-result-panel__tag--warning')
    expect(risk_tag?.className).not.toContain('--medium')
    // 英文枚举值不出现在用户可见文案里。
    expect(screen.queryByText('风险 medium')).not.toBeInTheDocument()
  })

  it('部分字段缺失时隐藏对应板块，不刷逐字段占位噪音', () => {
    const result = complete_result()
    result.impact = null as unknown as typeof result.impact
    result.recommendations = []
    const read = read_diagnosis_result(result, RUN_ID)
    if (!read.result) throw new Error('impact 为 null、建议为空数组都是合法 Result')

    render(<DiagnosisResultPanel result={read.result} />)

    expect(screen.queryByText('影响面')).not.toBeInTheDocument()
    expect(screen.queryByText('处置建议')).not.toBeInTheDocument()
    expect(screen.queryByText(/服务未返回/)).not.toBeInTheDocument()
  })

  it('在根因引用缺失证据时显示安全页内标记，不跳转外部资源', () => {
    const result = complete_result()
    result.root_causes[0].evidence_ids = ['missing-evidence']
    const read = read_diagnosis_result(result, RUN_ID)
    if (!read.result) throw new Error('证据引用缺失不是 Result 协议错误')

    render(<DiagnosisResultPanel result={read.result} />)

    expect(screen.getByText('关联证据不可用')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('结构化字段整体为空时只显示一个诚实空态', () => {
    const result = complete_result()
    result.root_causes = []
    result.evidence = []
    result.impact = null as unknown as typeof result.impact
    result.recommendations = []
    result.agent_summary = []
    result.risks = []
    const read = read_diagnosis_result(result, RUN_ID)
    if (!read.result) throw new Error('空数组是合法 Result')

    render(<DiagnosisResultPanel result={read.result} />)

    expect(screen.getByText('只读调查未产生可展示的结构化证据')).toBeInTheDocument()
    expect(screen.queryByText(/服务未返回/)).not.toBeInTheDocument()
    expect(screen.queryByText('可能根因')).not.toBeInTheDocument()
    expect(screen.queryByText('结构化证据')).not.toBeInTheDocument()
    expect(screen.getByLabelText('诊断结果摘要')).toHaveTextContent('Nginx 上游连接池已耗尽。')
  })
})
