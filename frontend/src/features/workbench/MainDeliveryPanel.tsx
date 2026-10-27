import type { ReactElement } from 'react'

import {
  read_main_delivery,
  read_main_input_snapshot,
  type MainComparisonDeliveryProjection,
  type MainInputSnapshotProjection,
  type MainMaterialProjection,
  type MainMaterialSide,
  type MainTextDiffBlockProjection,
} from './main-delivery-readers'

const SIDE_LABELS: Record<MainMaterialSide, string> = { text_a: '文本 A', text_b: '文本 B' }

const BLOCK_LABELS: Record<MainTextDiffBlockProjection['kind'], string> = {
  added: '新增',
  deleted: '删除',
  modified: '修改',
}

function line_range(start: number | null, end: number | null): string {
  if (start === null) return '无对应行'
  return start === end ? `第 ${start} 行` : `第 ${start}–${end} 行`
}

function DiffBlock({ block }: { block: MainTextDiffBlockProjection }): ReactElement {
  return (
    <li className="main-delivery-panel__block">
      <div className="main-delivery-panel__block-head">
        <span className={`main-delivery-panel__tag main-delivery-panel__tag--${block.kind}`}>{BLOCK_LABELS[block.kind]}</span>
        <span className="main-delivery-panel__meta">A {line_range(block.a_start, block.a_end)}</span>
        <span className="main-delivery-panel__meta">B {line_range(block.b_start, block.b_end)}</span>
      </div>
      {block.a_quote !== null && <pre className="main-delivery-panel__quote main-delivery-panel__quote--removed">{block.a_quote}</pre>}
      {block.b_quote !== null && <pre className="main-delivery-panel__quote main-delivery-panel__quote--added">{block.b_quote}</pre>}
    </li>
  )
}

function ComparisonBody({ comparison }: { comparison: MainComparisonDeliveryProjection }): ReactElement {
  return (
    <>
      <div className="main-delivery-panel__meta-row">
        <span className={`main-delivery-panel__tag${comparison.status === 'has_difference' ? ' main-delivery-panel__tag--modified' : ' main-delivery-panel__tag--same'}`}>
          {comparison.status === 'has_difference' ? '存在差异' : '逐行一致'}
        </span>
        <span className="main-delivery-panel__meta">
          能力 {comparison.capability_id}@{comparison.capability_version} · 规则 {comparison.rule_version} · 差异块 {comparison.blocks.length} 个
        </span>
      </div>
      {comparison.blocks.length === 0
        ? <p className="main-delivery-panel__copy">两份文本按行完全一致，未发现差异。</p>
        : <ul className="main-delivery-panel__blocks">{comparison.blocks.map((block, index) => <DiffBlock block={block} key={index} />)}</ul>}
    </>
  )
}

function MaterialBlock({ material, side }: { material: MainMaterialProjection | null; side: MainMaterialSide }): ReactElement {
  return (
    <div className="main-delivery-panel__material">
      <span className="main-delivery-panel__material-label">{SIDE_LABELS[side]}</span>
      {material === null
        ? <p className="main-delivery-panel__copy main-delivery-panel__copy--muted">未提供</p>
        : (
          <>
            <pre className="main-delivery-panel__raw">{material.original_text}</pre>
            <p className="main-delivery-panel__meta">摘要 {material.content_sha256.slice(0, 12)}…</p>
          </>
        )}
    </div>
  )
}

function InputSnapshotBody({ snapshot }: { snapshot: MainInputSnapshotProjection }): ReactElement {
  return (
    <>
      <div className="main-delivery-panel__material">
        <span className="main-delivery-panel__material-label">本次目标</span>
        <pre className="main-delivery-panel__raw">{snapshot.query}</pre>
      </div>
      <MaterialBlock material={snapshot.text_a} side="text_a" />
      <MaterialBlock material={snapshot.text_b} side="text_b" />
    </>
  )
}

function ProtocolNotice({ detail, title }: { detail: string; title: string }): ReactElement {
  return (
    <div className="main-delivery-panel__notice">
      <strong className="main-delivery-panel__notice-title">{title}</strong>
      <p className="main-delivery-panel__copy">{detail}</p>
    </div>
  )
}

/**
 * 渲染一次 V2 主 Agent 交付的结构化补充：比较差异块与本次冻结输入。
 *
 * `answer`／`needs_input` 的正文由服务端写入助手消息后在气泡里呈现，本面板不重复渲染；
 * 投影不符合公开契约时只报协议问题，不做猜测性渲染。
 */
export function MainDeliveryPanel({
  delivery,
  input_snapshot,
}: {
  delivery: unknown
  input_snapshot?: unknown
}): ReactElement {
  const delivery_read = read_main_delivery(delivery)
  const snapshot_read =
    input_snapshot === null || input_snapshot === undefined ? undefined : read_main_input_snapshot(input_snapshot)
  // 只要投影报出协议问题就整体不渲染：宁可少显示，也不显示半截的行号或材料。
  const delivery_ok = delivery_read.delivery !== undefined && delivery_read.issues.length === 0
  const answer_knowledge =
    delivery_ok && delivery_read.delivery?.kind === 'answer'
      ? delivery_read.delivery.knowledge_grounding
      : null

  return (
    <article className="main-delivery-panel">
      {delivery_ok
        ? (delivery_read.delivery?.kind === 'comparison' ? <ComparisonBody comparison={delivery_read.delivery} /> : null)
        : <ProtocolNotice detail={delivery_read.issues[0]?.message ?? '服务端交付不符合公开契约。'} title="交付数据异常" />}
      {answer_knowledge !== null && (
        <div className="main-delivery-panel__knowledge">
          <span className="main-delivery-panel__knowledge-badge">{answer_knowledge.note}</span>
          <p className="main-delivery-panel__copy">
            来源：内置只读排查手册 {answer_knowledge.capability_id}@{answer_knowledge.capability_version}（未检索、未联网）
          </p>
        </div>
      )}
      {snapshot_read && snapshot_read.snapshot && snapshot_read.issues.length === 0 && (
        <details className="main-delivery-panel__snapshot">
          <summary>展开本次输入</summary>
          <InputSnapshotBody snapshot={snapshot_read.snapshot} />
        </details>
      )}
      {snapshot_read && !snapshot_read.snapshot && (
        <ProtocolNotice detail={snapshot_read.issues[0]?.message ?? '服务端冻结输入不符合公开契约。'} title="输入数据异常" />
      )}
    </article>
  )
}
