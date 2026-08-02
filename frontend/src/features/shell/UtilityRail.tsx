import type { ReactElement } from 'react'

interface UtilityRailProps {
  collapsed: boolean
  on_collapse: () => void
  on_open_utility: (key: UtilityKey) => void
}

export type UtilityKey = 'connections' | 'monitoring' | 'models' | 'documents'

const UTILITIES: Array<{ key: UtilityKey; icon: string; tone: '' | 'green' | 'orange' | 'purple'; title: string; note: string }> = [
  { key: 'connections', icon: '⌘', tone: '', title: '服务连接', note: '3 个服务已接入' },
  { key: 'monitoring', icon: '⌁', tone: 'green', title: '服务监控', note: '3 个在线 · 0 条告警' },
  { key: 'models', icon: '✦', tone: 'purple', title: '模型设置', note: 'OperMind-Reasoner · 温度 0' },
  { key: 'documents', icon: '＋', tone: 'orange', title: '文档添加', note: '知识库已就绪' },
]

export function UtilityRail({ collapsed, on_collapse, on_open_utility }: UtilityRailProps): ReactElement {
  return (
    <aside aria-label="工作台功能" className={`right-rail${collapsed ? ' collapsed' : ''}`}>
      <div className="right-rail-heading">
        <strong>工作台</strong>
        <span>快捷入口</span>
        <button aria-label="收起右侧栏" className="icon-btn" id="rail-collapse" onClick={on_collapse} type="button">
          ›
        </button>
      </div>

      <div className="utility-group">
        <p className="utility-group-title">服务状态</p>
        <div className="utility-list">
          {UTILITIES.slice(0, 2).map((item) => (
            <button className="utility-card" key={item.key} onClick={() => on_open_utility(item.key)} type="button">
              <span className={`utility-icon${item.tone ? ` ${item.tone}` : ''}`}>{item.icon}</span>
              <span className="utility-copy">
                <strong>{item.title}</strong>
                <span>{item.note}</span>
              </span>
              <span className="utility-arrow">›</span>
            </button>
          ))}
        </div>
      </div>

      <div className="utility-group">
        <p className="utility-group-title">工作台设置</p>
        <div className="utility-list">
          {UTILITIES.slice(2).map((item) => (
            <button className="utility-card" key={item.key} onClick={() => on_open_utility(item.key)} type="button">
              <span className={`utility-icon${item.tone ? ` ${item.tone}` : ''}`}>{item.icon}</span>
              <span className="utility-copy">
                <strong>{item.title}</strong>
                <span>{item.note}</span>
              </span>
              <span className="utility-arrow">›</span>
            </button>
          ))}
        </div>
      </div>

      <hr className="rail-divider" />
      <p className="rail-section-title">当前环境</p>
      <div className="rail-status">
        <div className="rail-status-summary">
          <span className="alert-dot" />
          <span>
            <span className="status-count">3</span> 个服务在线
          </span>
        </div>
        <div className="rail-status-row">
          <span>当前告警</span>
          <strong className="status-ok">0 条</strong>
        </div>
        <div className="rail-status-row">
          <span>调查权限</span>
          <strong className="status-ok">只读</strong>
        </div>
        <div className="rail-status-row">
          <span>外部连接</span>
          <strong className="status-ok">已保护</strong>
        </div>
        <div className="rail-status-row">
          <span>审批策略</span>
          <strong>人工确认</strong>
        </div>
      </div>
    </aside>
  )
}
