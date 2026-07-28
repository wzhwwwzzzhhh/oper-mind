import { Card, Descriptions, Empty, List, Space, Tag, Typography } from 'antd'
import type { ReactElement } from 'react'

import type { DiagnosisEvidence, DiagnosisResultProjection, DiagnosisRootCause } from './result-readers'

const SEVERITY_COLORS: Record<DiagnosisResultProjection['severity'], string> = {
  critical: 'magenta',
  high: 'red',
  info: 'blue',
  low: 'green',
  medium: 'orange',
}

function EvidenceReferences({ evidence_ids, evidence_by_id }: { evidence_ids: string[]; evidence_by_id: ReadonlyMap<string, DiagnosisEvidence> }): ReactElement {
  if (evidence_ids.length === 0) return <Typography.Text type="secondary">未关联结构化证据</Typography.Text>

  return (
    <Space size={[4, 4]} wrap>
      {evidence_ids.map((evidence_id) => (
        evidence_by_id.has(evidence_id)
          ? <Tag key={evidence_id}>证据 {evidence_id}</Tag>
          : <Tag color="warning" key={evidence_id}>关联证据不可用</Tag>
      ))}
    </Space>
  )
}

function RootCauseItem({ root_cause, evidence_by_id }: { root_cause: DiagnosisRootCause; evidence_by_id: ReadonlyMap<string, DiagnosisEvidence> }): ReactElement {
  return (
    <List.Item>
      <Space direction="vertical" size={4}>
        <Typography.Text strong>{root_cause.title}</Typography.Text>
        <Typography.Paragraph>{root_cause.summary}</Typography.Paragraph>
        <Space size="small" wrap>
          <Tag color="cyan">置信度 {(root_cause.confidence * 100).toFixed(0)}%</Tag>
          <EvidenceReferences evidence_by_id={evidence_by_id} evidence_ids={root_cause.evidence_ids} />
        </Space>
      </Space>
    </List.Item>
  )
}

function attribute_text(attributes: DiagnosisEvidence['attributes']): string {
  return Object.entries(attributes).map(([key, value]) => `${key}: ${value === null ? 'null' : String(value)}`).join('；')
}

function EvidenceItem({ evidence }: { evidence: DiagnosisEvidence }): ReactElement {
  const attributes = attribute_text(evidence.attributes)
  return (
    <List.Item>
      <Space direction="vertical" size={4}>
        <Space size="small" wrap>
          <Typography.Text strong>{evidence.title}</Typography.Text>
          <Tag>{evidence.source_type}</Tag>
          <Tag color="default">{evidence.source_name}</Tag>
        </Space>
        <Typography.Paragraph>{evidence.summary}</Typography.Paragraph>
        <Space direction="vertical" size={2}>
          {evidence.observed_at && <Typography.Text type="secondary">观察时间：{evidence.observed_at}</Typography.Text>}
          {evidence.locator && <Typography.Text type="secondary">定位信息：{evidence.locator}</Typography.Text>}
          {attributes && <Typography.Text type="secondary">属性：{attributes}</Typography.Text>}
        </Space>
      </Space>
    </List.Item>
  )
}

/**
 * 仅渲染已通过运行时校验的 P2 结构化结果；不解析 Markdown 或跳转 Trace。
 */
export function DiagnosisResultPanel({ result }: { result: DiagnosisResultProjection }): ReactElement {
  const evidence_by_id = new Map(result.evidence.map((evidence) => [evidence.id, evidence]))

  return (
    <Card className="diagnosis-result-panel" title="结构化诊断结果">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space size="small" wrap>
          <Tag color={SEVERITY_COLORS[result.severity]}>严重度 {result.severity}</Tag>
          <Tag color="cyan">置信度 {(result.confidence * 100).toFixed(0)}%</Tag>
          <Tag>结果时间 {result.created_at}</Tag>
        </Space>
        <Typography.Paragraph aria-label="诊断结果摘要" strong>{result.summary}</Typography.Paragraph>

        <section aria-labelledby="root-causes-heading">
          <Typography.Title id="root-causes-heading" level={5}>可能根因</Typography.Title>
          {result.root_causes.length === 0
            ? <Empty description="服务未返回结构化根因" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            : <List dataSource={result.root_causes} renderItem={(root_cause) => <RootCauseItem evidence_by_id={evidence_by_id} key={root_cause.id} root_cause={root_cause} />} />}
        </section>

        <section aria-labelledby="evidence-heading">
          <Typography.Title id="evidence-heading" level={5}>结构化证据</Typography.Title>
          {result.evidence.length === 0
            ? <Empty description="服务未返回结构化证据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            : <List dataSource={result.evidence} renderItem={(evidence) => <EvidenceItem evidence={evidence} key={evidence.id} />} />}
        </section>

        <Descriptions column={1} size="small" title="结果关联">
          <Descriptions.Item label="结果 ID">{result.id}</Descriptions.Item>
          <Descriptions.Item label="Run ID">{result.run_id}</Descriptions.Item>
        </Descriptions>
      </Space>
    </Card>
  )
}
