import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MainCapabilityStrip } from './MainCapabilityStrip'

const USED_EXECUTION = {
  capability_id: 'text.literal_compare',
  capability_version: 1,
  kind: 'execution',
  status: 'ok',
}
const USED_KNOWLEDGE = {
  capability_id: 'ops.readonly_playbook',
  capability_version: 1,
  kind: 'knowledge',
  status: 'loaded',
}
const DEGRADED = {
  capability_id: 'ops.readonly_playbook',
  capability_version: 1,
  kind: 'knowledge',
  status: 'unavailable',
}
const KNOWLEDGE = {
  capability_id: 'ops.readonly_playbook',
  capability_version: 1,
  data_access: 'none',
  note: '知识辅助回答 · 未读取实时数据',
  skill_id: 'ops.readonly_playbook',
  skill_version: 1,
}

describe('MainCapabilityStrip', () => {
  it('展示本次使用、降级的能力与步数', () => {
    render(
      <MainCapabilityStrip
        capabilities={{ degraded: [DEGRADED], steps: 2, used: [USED_KNOWLEDGE, USED_EXECUTION] }}
        status="available"
      />,
    )

    expect(screen.getByText('知识 · ops.readonly_playbook@1 · 已装载')).toBeInTheDocument()
    expect(screen.getByText('执行 · text.literal_compare@1 · 已调用')).toBeInTheDocument()
    expect(screen.getByText('ops.readonly_playbook@1 · 不可用')).toBeInTheDocument()
    expect(screen.getByText('共 2 步')).toBeInTheDocument()
  })

  it('没有使用外部能力时如实说明', () => {
    render(<MainCapabilityStrip capabilities={{ degraded: [], steps: 1, used: [] }} status="available" />)

    expect(screen.getByText('未使用外部能力')).toBeInTheDocument()
    expect(screen.getByText('共 1 步')).toBeInTheDocument()
  })

  it('步数读不出时显示步骤未知，不伪造 0', () => {
    render(<MainCapabilityStrip capabilities={{ degraded: [], steps: null, used: [USED_EXECUTION] }} status="available" />)

    expect(screen.getByText('步骤未知')).toBeInTheDocument()
    expect(screen.queryByText('共 0 步')).not.toBeInTheDocument()
  })

  it('能力归属不可用时只报安全不可用，不猜能力', () => {
    render(<MainCapabilityStrip capabilities={{ degraded: [], steps: null, used: [] }} status="unavailable" />)

    expect(screen.getByText('能力归属不可用，页面不猜测本次使用了哪些能力。')).toBeInTheDocument()
    expect(screen.queryByText(/text\.literal_compare/)).not.toBeInTheDocument()
  })

  it('没有能力归属字段时不渲染，不伪造空状态', () => {
    const { container } = render(<MainCapabilityStrip capabilities={null} status="absent" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('知识辅助回答只使用固定标注，不出现已校验／已读取／已诊断', () => {
    render(
      <MainCapabilityStrip
        capabilities={{ degraded: [], steps: 2, used: [USED_KNOWLEDGE] }}
        knowledge={KNOWLEDGE}
        status="available"
      />,
    )

    expect(screen.getByText('知识辅助回答 · 未读取实时数据')).toBeInTheDocument()
    expect(screen.queryByText(/已校验/)).not.toBeInTheDocument()
    expect(screen.queryByText(/已读取/)).not.toBeInTheDocument()
    expect(screen.queryByText(/已诊断/)).not.toBeInTheDocument()
  })

  it('知识标注结构不符时拒绝背书，只报数据异常', () => {
    render(
      <MainCapabilityStrip
        capabilities={{ degraded: [], steps: 1, used: [] }}
        knowledge={{ ...KNOWLEDGE, note: '已读取实时数据' }}
        status="available"
      />,
    )

    expect(screen.queryByText('知识辅助回答 · 未读取实时数据')).not.toBeInTheDocument()
    expect(screen.getByText('知识标注数据异常，页面不将其视为知识辅助回答。')).toBeInTheDocument()
  })
})
