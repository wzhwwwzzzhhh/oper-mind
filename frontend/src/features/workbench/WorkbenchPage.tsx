import type { ReactElement } from 'react'
import { Empty, Tag, Typography } from 'antd'

export function WorkbenchPage(): ReactElement {
  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">OPERATIONS DIAGNOSIS</div>
      <Typography.Title id="workbench-title" level={2}>
        诊断工作台
      </Typography.Title>
      <Typography.Paragraph className="page-description">
        P3.1 已建立主产品外壳。会话、Run、结构化结果与持久化事件将在后续切片通过
        <code> /api/v1 </code>
        接入。
      </Typography.Paragraph>
      <Empty
        className="workbench-empty"
        description={
          <span>
            <strong>尚未接入会话数据</strong>
            <br />
            请选择或创建会话的真实入口将在 P3.2 接入；当前不会伪造 Session、Run 或诊断结果。
          </span>
        }
      />
      <div className="honest-status" aria-label="阶段能力状态">
        <Tag color="blue">会话与诊断：P3.2 起接入</Tag>
        <Tag>环境与数据源：待 P4</Tag>
        <Tag>告警与审批：待 P5</Tag>
        <Tag>报告与导出：待 P6</Tag>
      </div>
    </section>
  )
}