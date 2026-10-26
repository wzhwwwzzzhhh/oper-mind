import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MainDeliveryPanel } from './MainDeliveryPanel'

const MATERIAL = { content_sha256: 'b'.repeat(64), material_id: 'material-a', original_text: 'alpha\nbeta' }

function comparison(blocks: unknown[], status = 'has_difference') {
  return {
    a_material_id: 'material-a',
    b_material_id: 'material-b',
    blocks,
    capability_id: 'text.literal_compare',
    capability_version: 1,
    kind: 'comparison',
    rule_version: 'literal-lines@1',
    status,
  }
}

describe('MainDeliveryPanel', () => {
  it('渲染差异块、行号与逐字引文', () => {
    render(
      <MainDeliveryPanel
        delivery={comparison([
          { a_end: 2, a_quote: 'beta', a_start: 2, b_end: 2, b_quote: 'gamma', b_start: 2, kind: 'modified' },
        ])}
      />,
    )

    expect(screen.getByText('存在差异')).toBeInTheDocument()
    expect(screen.getByText('修改')).toBeInTheDocument()
    expect(screen.getByText('A 第 2 行')).toBeInTheDocument()
    expect(screen.getByText('beta')).toBeInTheDocument()
    expect(screen.getByText('gamma')).toBeInTheDocument()
    expect(screen.getByText(/literal-lines@1/)).toBeInTheDocument()
  })

  it('无差异时如实说明，不编造差异块', () => {
    render(<MainDeliveryPanel delivery={comparison([], 'no_difference')} />)

    expect(screen.getByText('逐行一致')).toBeInTheDocument()
    expect(screen.getByText('两份文本按行完全一致，未发现差异。')).toBeInTheDocument()
  })

  it('行号倒挂时整体不渲染差异内容，只报协议问题', () => {
    render(
      <MainDeliveryPanel
        delivery={comparison([
          { a_end: 1, a_quote: 'beta', a_start: 2, b_end: 2, b_quote: 'gamma', b_start: 2, kind: 'modified' },
        ])}
      />,
    )

    expect(screen.getByText('交付数据异常')).toBeInTheDocument()
    expect(screen.queryByText('gamma')).not.toBeInTheDocument()
  })

  it('answer 交付不重复渲染正文，冻结输入可展开查看', () => {
    render(
      <MainDeliveryPanel
        delivery={{ kind: 'answer', text: '我需要对 B 侧做一次只读比较。' }}
        input_snapshot={{ query: '比较这两段文本', rule_version: 'literal-lines@1', text_a: MATERIAL, text_b: null }}
      />,
    )

    expect(screen.queryByText('我需要对 B 侧做一次只读比较。')).not.toBeInTheDocument()
    expect(screen.getByText('展开本次输入')).toBeInTheDocument()
    expect(screen.getByText('比较这两段文本')).toBeInTheDocument()
    expect(screen.getByText('未提供')).toBeInTheDocument()
  })
})
