import type { ReactElement } from 'react'

interface WelcomePanelProps {
  on_prompt: (prompt: string) => void
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

export function WelcomePanel({ on_prompt }: WelcomePanelProps): ReactElement {
  return (
    <section className="welcome">
      <div className="welcome-mark">O</div>
      <h1>你好，我是 OperMind</h1>
      <p>面向研发与运维的会话式 Copilot。描述一个问题，我会基于已接入服务和受控工具，陪你一起定位根因。</p>
      <div className="state-strip">
        <span className="state-dot" />
        <span>3 个服务在线 · 默认只读调查</span>
      </div>
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
