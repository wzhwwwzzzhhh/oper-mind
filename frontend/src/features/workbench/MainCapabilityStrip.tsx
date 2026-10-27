import type { ReactElement } from 'react'

import {
  read_main_capabilities,
  read_main_knowledge,
  type MainCapabilitiesStatus,
  type MainCapabilityUseProjection,
} from './main-delivery-readers'

const KIND_LABELS: Record<MainCapabilityUseProjection['kind'], string> = {
  execution: '执行',
  knowledge: '知识',
}

const USE_STATUS_LABELS: Record<MainCapabilityUseProjection['status'], string> = {
  loaded: '已装载',
  ok: '已调用',
  unavailable: '不可用',
}

function capability_chip(item: MainCapabilityUseProjection): ReactElement {
  const identity = `${item.capability_id}@${item.capability_version}`
  const label = item.status === 'unavailable'
    ? `${identity} · ${USE_STATUS_LABELS[item.status]}`
    : `${KIND_LABELS[item.kind]} · ${identity} · ${USE_STATUS_LABELS[item.status]}`
  return (
    <span
      className={`main-capability-strip__chip main-capability-strip__chip--${item.kind}${
        item.status === 'unavailable' ? ' main-capability-strip__chip--degraded' : ''
      }`}
      key={`${identity}:${item.status}`}
    >
      {label}
    </span>
  )
}

/**
 * 公示一次主 Agent Run 的能力归属与知识标注。
 *
 * 只渲染服务端公开投影：没有字段就不渲染，损坏或不可用就如实提示；
 * 知识辅助回答的标注由服务端接地声明驱动，前端不自行升级成"已校验"。
 */
export function MainCapabilityStrip({
  capabilities,
  knowledge,
  status,
}: {
  capabilities: unknown
  knowledge?: unknown
  status?: MainCapabilitiesStatus | string
}): ReactElement | null {
  const read = read_main_capabilities(capabilities, status)
  const knowledge_read = read_main_knowledge(knowledge)
  if (read.status === undefined || read.status === 'absent') return null

  const body = read.status === 'unavailable' || read.capabilities === undefined
    ? <span className="main-capability-strip__note">能力归属不可用，页面不猜测本次使用了哪些能力。</span>
    : (
      <>
        {read.capabilities.steps !== null
          ? <span className="main-capability-strip__note">共 {read.capabilities.steps} 步</span>
          : <span className="main-capability-strip__note">步骤未知</span>}
        {read.capabilities.used.map(capability_chip)}
        {read.capabilities.degraded.map(capability_chip)}
        {read.capabilities.used.length === 0 && read.capabilities.degraded.length === 0 && (
          <span className="main-capability-strip__note">未使用外部能力</span>
        )}
      </>
    )

  return (
    <section
      aria-label="本次能力归属"
      className={`main-capability-strip${read.status === 'unavailable' ? ' main-capability-strip--unavailable' : ''}`}
    >
      <div className="main-capability-strip__row">
        <strong className="main-capability-strip__title">能力归属</strong>
        {body}
      </div>
      {knowledge_read.grounding !== undefined && (
        <span className="main-capability-strip__knowledge">
          {knowledge_read.grounding.note}
        </span>
      )}
      {knowledge_read.issues.length > 0 && (
        <span className="main-capability-strip__note main-capability-strip__note--warning">
          知识标注数据异常，页面不将其视为知识辅助回答。
        </span>
      )}
    </section>
  )
}
