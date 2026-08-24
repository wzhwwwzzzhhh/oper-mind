import type { ReactElement } from 'react'

interface WelcomePanelProps {
  on_prompt: (prompt: string) => void
  service_count?: number
  services?: Array<{ id: string; title: string }>
  selected_service_ids?: string[]
  on_service_change?: (service_ids: string[]) => void
  /** 服务列表读取状态：加载/失败时如实展示，不冒充"0 个服务"。 */
  services_loading?: boolean
  services_error?: boolean
}

const QUICK_PROMPTS: Array<{ title: string; note: string; prompt: string }> = [
  {
    title: '排查慢查询',
    note: '从数据库监控和执行计划开始',
    prompt: '帮我排查订单服务最近的慢查询，先从数据库只读调查开始。',
  },
  {
    title: '调查接口错误',
    note: '串联服务、日志和数据库证据',
    prompt: '检查支付服务 5xx 增多的可能原因，给我一个只读调查计划。',
  },
  {
    title: '发布前巡检',
    note: '并行查看关键服务健康状态',
    prompt: '帮我做一次发布前服务巡检，只读检查并列出风险。',
  },
  {
    title: '定位连接超时',
    note: '先确认事实，再给出可审批建议',
    prompt: 'Redis 连接池出现偶发超时，应该如何安全定位？',
  },
]

export function WelcomePanel({
  on_prompt,
  service_count = 0,
  services = [],
  selected_service_ids = [],
  on_service_change,
  services_loading = false,
  services_error = false,
}: WelcomePanelProps): ReactElement {
  // 服务数是"已接入（注册）"口径，不是在线数；加载/失败时不冒充 0 个服务。
  const service_count_text = services_loading
    ? '正在读取已接入服务…'
    : services_error
      ? '服务列表暂不可读'
      : `${service_count} 个服务已接入`
  return (
    <section className="welcome">
      <div className="welcome-mark">O</div>
      <h1>你好，我是 OperMind</h1>
      <p>面向研发与运维的会话式 Copilot。描述一个问题，我会基于已接入服务和受控工具，陪你一起定位根因。</p>
      <div className="state-strip">
        <span className="state-dot" />
        <span>{service_count_text} · 默认只读调查</span>
      </div>
      <fieldset className="service-selector">
        <span>调查目标服务</span>
        <div aria-label="调查目标服务" className="service-checkboxes">
          {services_loading && <span>正在读取服务列表…</span>}
          {!services_loading && services_error && <span>服务列表暂不可读，稍后可重试</span>}
          {!services_loading && !services_error && services.length === 0 && <span>暂无已接入服务</span>}
          {services.map((service) => (
            <label key={service.id}>
              <input
                checked={selected_service_ids.includes(service.id)}
                onChange={(event) => on_service_change?.(event.target.checked
                  ? [...selected_service_ids, service.id]
                  : selected_service_ids.filter((id) => id !== service.id))}
                type="checkbox"
              />
              {service.title}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="quick-grid">
        {QUICK_PROMPTS.map((item) => (
          <button className="quick-card" key={item.title} onClick={() => on_prompt(item.prompt)} type="button">
            <strong>{item.title}</strong>
            <span>{item.note}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
