import type { ReactElement } from 'react'

import { resource_optional_string, resource_string } from '../workbench/resource-readers'
import type { UtilityKey } from './UtilityRail'

interface UtilityModalProps {
  open: boolean
  utility: UtilityKey | null
  services: unknown[]
  on_close: () => void
}

const UTILITY_TEXT: Record<UtilityKey, { title: string; text: string }> = {
  connections: {
    title: '服务连接',
    text: '统一管理已接入的外部服务与授权边界。前端不直接连接用户服务，所有访问都由受控 Connector 执行。',
  },
  monitoring: {
    title: '服务监控',
    text: '从这里快速查看服务健康状态，再回到会话中发起只读调查。',
  },
  models: {
    title: '模型设置',
    text: '选择会话使用的推理模型，并查看当前运行策略。高风险工具始终需要人工审批。',
  },
  documents: {
    title: '文档添加',
    text: '添加运行手册、架构说明和服务知识，让 Agent 在调查时获得经过授权的上下文。',
  },
}

const STATIC_ROWS: Partial<Record<UtilityKey, Array<[string, string]>>> = {
  models: [['当前模型', 'OperMind-Reasoner'], ['响应策略', '稳定优先'], ['工具模式', '受控调用']],
  documents: [['已接入文档', '12 份'], ['支持格式', 'PDF · Markdown · TXT'], ['索引状态', '已就绪']],
}

export function UtilityModal({ open, utility, services, on_close }: UtilityModalProps): ReactElement {
  const content = utility ? UTILITY_TEXT[utility] : undefined

  let rows: Array<[string, string]> = []
  if (utility === 'connections' || utility === 'monitoring') {
    rows = services.map((service) => {
      const name = resource_string(service, 'name', '未命名服务')
      const service_id = resource_optional_string(service, 'id')
      return [name, service_id ? '已连接' : '—']
    })
    if (rows.length === 0) rows = [['暂无服务', '—']]
  } else if (utility) {
    rows = STATIC_ROWS[utility] ?? []
  }

  return (
    <div aria-modal="true" className={`utility-modal${open && content ? ' open' : ''}`} onClick={on_close} role="dialog">
      <div className="utility-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="utility-dialog-head">
          <strong>{content?.title ?? '工作台设置'}</strong>
          <button aria-label="关闭" className="icon-btn" onClick={on_close} type="button">
            ×
          </button>
        </div>
        <div className="utility-dialog-body">
          {content && (
            <>
              <p>{content.text}</p>
              <ul className="dialog-list">
                {rows.map(([label, value]) => (
                  <li key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
        <div className="dialog-footer">
          <button className="dialog-action" onClick={on_close} type="button">
            稍后设置
          </button>
          <button className="dialog-action primary" onClick={on_close} type="button">
            打开设置
          </button>
        </div>
      </div>
    </div>
  )
}
