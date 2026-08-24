import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import { get_model_config_query } from '../../api/v1/queries'
import { Icon } from './Icon'

interface TopBarProps {
  on_theme: () => void
  on_share: () => void
  /** 当前页面标题，留空时不渲染。 */
  title?: string
}

/** 生效模型标识：只读展示后端真实生效配置，加载/失败如实降级，不写死模型名。 */
function EffectiveModelLabel(): ReactElement {
  const model_config_query = useQuery({ ...get_model_config_query() })
  const config = model_config_query.data?.data.config

  let label: string
  if (model_config_query.isPending) {
    label = '生效模型读取中…'
  } else if (model_config_query.isError || config === undefined) {
    label = '生效模型暂不可读'
  } else {
    const mode = config.mode === 'mock' ? 'Mock' : '真实'
    // real 已保存但无可用 Key 时后端实际回退确定性调用，如实标注"暂不可用"。
    const unavailable = config.mode === 'real' && !config.mode_available ? '（暂不可用）' : ''
    const model = config.diagnostic_model.status === 'configured' ? config.diagnostic_model.model : '未配置'
    label = `生效模型 ${model} · ${mode}${unavailable}`
  }

  return (
    <span aria-label="生效模型" className="effective-model" title="当前会话链路的真实生效模型（来自后端配置）">
      <Icon name="spark" size={13} />
      {label}
    </span>
  )
}

/** 主区顶栏：真实已连接操作（主题切换、分享通知）+ 生效模型只读标识。 */
export function TopBar({ on_theme, on_share, title }: TopBarProps): ReactElement {
  return (
    <header className="topbar">
      <div className="topbar-left">
        {title && <span className="topbar-title">{title}</span>}
      </div>
      <div className="topbar-right">
        <EffectiveModelLabel />
        <button aria-label="切换主题" className="top-action theme-button" onClick={on_theme} title="切换主题" type="button">
          <Icon name="contrast" size={15} />
          <span>主题</span>
        </button>
        <button aria-label="分享" className="top-action" onClick={on_share} title="分享" type="button">
          <Icon name="link" size={15} />
          <span>分享</span>
        </button>
      </div>
    </header>
  )
}
