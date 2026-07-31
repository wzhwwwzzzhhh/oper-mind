import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, List, Skeleton, Space, Tag, Typography } from 'antd'
import type { ReactElement } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type ServiceListResponse,
  type ServiceResponse,
} from '../../api/v1/client'
import {
  api_v1_query_keys,
  get_service_query,
  list_services_query,
} from '../../api/v1/queries'
import {
  read_items,
  read_page,
  read_record,
  resource_optional_string,
  resource_string,
  resource_value,
} from '../workbench/resource-readers'

const ORDERS_SLOW_QUERY_INTENT_ID = 'orders_slow_query.v1'

function ServiceLoading({ label }: { label: string }): ReactElement {
  return <Skeleton active aria-label={label} paragraph={{ rows: 5 }} title />
}

function ServiceErrorNotice({ error }: { error: unknown }): ReactElement {
  const description = error instanceof ApiClientError
    ? `服务中心未返回可用的受控事实（${error.code}）。页面不会以本地数据替代。`
    : '服务中心当前无法返回受控事实。请稍后手动刷新；页面不会以本地数据替代。'
  return <Alert description={description} showIcon title="暂时无法读取服务中心" type="error" />
}

function signal_color(value: string): string {
  if (['healthy', 'index_and_plan_confirmed', 'no_slow_query_detected', 'verified'].includes(value)) return 'green'
  if (['slow_query_detected', 'missing_index_seq_scan_detected', 'unhealthy', 'failed', 'blocked'].includes(value)) return 'red'
  if (['insufficient_data', 'unavailable', 'not_configured', 'pending_approval', 'approved'].includes(value)) return 'gold'
  return 'blue'
}

function label(value: string): string {
  const labels: Record<string, string> = {
    available: '可读取',
    unavailable: '不可用',
    not_configured: '未配置',
    healthy: '健康',
    unhealthy: '异常',
    slow_query_detected: '检测到慢查询信号',
    no_slow_query_detected: '未检测到慢查询信号',
    missing_index_seq_scan_detected: '检测到缺失索引 / 顺序扫描',
    index_and_plan_confirmed: '索引与计划已确认',
    insufficient_data: '证据不足',
    mock: '模拟快照',
    target: '受控靶场读取',
    disabled: '未启用',
    queued: '已排队',
    running: '调查中',
    succeeded: '调查完成',
    failed: '失败',
    cancelled: '已取消',
    pending_approval: '等待审批',
    approved: '已批准',
    executing: '执行中',
    verifying: '验证中',
    verified: '已验证',
    rejected: '已拒绝',
    expired: '已过期',
    blocked: '已阻断',
  }
  return labels[value] ?? value
}

function display_metric(value: unknown, suffix = ''): string {
  return typeof value === 'number' ? `${value}${suffix}` : '—'
}

function SnapshotSummary({ service }: { service: unknown }): ReactElement {
  const snapshot = read_record(resource_value(service, 'snapshot'))
  const metrics = read_record(snapshot?.server_metrics)
  const database = read_record(snapshot?.database)
  const availability = resource_string(snapshot, 'availability')
  const performance = resource_string(snapshot, 'performance_signal')
  const mode = resource_string(snapshot, 'mode')
  const database_signal = resource_string(database, 'signal')
  return (
    <div className="service-snapshot-summary">
      <Space wrap>
        <Tag color={signal_color(availability)}>{label(availability)}</Tag>
        <Tag color={signal_color(performance)}>{label(performance)}</Tag>
        <Tag>{label(mode)}</Tag>
      </Space>
      <Typography.Paragraph className="service-observed-at" type="secondary">
        最近快照：{resource_string(snapshot, 'observed_at')}
      </Typography.Paragraph>
      <div className="service-metric-grid">
        <span>P50：<strong>{display_metric(metrics?.p50_ms, ' ms')}</strong></span>
        <span>P95：<strong>{display_metric(metrics?.p95_ms, ' ms')}</strong></span>
        <span>窗口：<strong>{display_metric(metrics?.window_size)}</strong></span>
        <span>慢查询：<strong>{display_metric(metrics?.slow_query_count)}</strong></span>
        <span>超时：<strong>{display_metric(metrics?.timeout_count)}</strong></span>
      </div>
      <Typography.Text type="secondary">数据库状态：{label(database_signal)}</Typography.Text>
    </div>
  )
}

function ServicesList(): ReactElement {
  const navigate = useNavigate()
  const services_query = useQuery(list_services_query())

  return (
    <section className="workbench-page service-center-page" aria-labelledby="services-title">
      <div className="page-eyebrow">SERVICE CENTER · CONTROLLED DEMO</div>
      <Typography.Title id="services-title" level={2}>服务中心</Typography.Title>
      <Typography.Paragraph className="page-description">
        先确认正在管理的受控服务与当前有限事实，再进入会话调查。这里不是实时监控平台，也不提供动态接入或自动修复。
      </Typography.Paragraph>
      {services_query.isPending && <ServiceLoading label="正在读取服务中心" />}
      {services_query.isError && <ServiceErrorNotice error={services_query.error} />}
      {services_query.isSuccess && (
        <List
          className="service-list"
          dataSource={read_items((services_query.data as ApiResponse<ServiceListResponse>).data)}
          locale={{ emptyText: <Empty description="暂无已注册服务" /> }}
          renderItem={(service) => (
            <List.Item>
              <Card className="service-card" title={resource_string(service, 'title')}>
                <Typography.Paragraph type="secondary">
                  类型：{resource_string(service, 'kind')} · 仅限受控靶场
                </Typography.Paragraph>
                <SnapshotSummary service={service} />
                <Button
                  onClick={() => navigate(`/services/${resource_string(service, 'id')}`)}
                  type="primary"
                >
                  查看服务详情
                </Button>
              </Card>
            </List.Item>
          )}
        />
      )}
    </section>
  )
}

function ActivityList({ service_id }: { service_id: string }): ReactElement {
  const navigate = useNavigate()
  const activities_query = useInfiniteQuery({
    queryKey: api_v1_query_keys.service_activities(service_id, { limit: API_V1_DEFAULT_PAGE_SIZE }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => api_v1_client.list_service_activities(
      service_id,
      { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE },
      { signal },
    ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const items = activities_query.data?.pages.flatMap((page) => read_items(page.data)) ?? []

  if (activities_query.isPending) return <ServiceLoading label="正在读取最近调查与修复留痕" />
  if (activities_query.isError) return <ServiceErrorNotice error={activities_query.error} />
  if (items.length === 0) {
    return <Empty description="尚无从此服务入口发起的调查。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <>
      <List
        className="service-activity-list"
        dataSource={items}
        renderItem={(item) => {
          const session_id = resource_optional_string(item, 'session_id')
          const run_id = resource_optional_string(item, 'run_id')
          const run_status = resource_string(item, 'run_status')
          const proposal_status = resource_optional_string(item, 'proposal_status')
          const verification_status = resource_optional_string(item, 'verification_status')
          return (
            <List.Item
              actions={session_id ? [
                <Button
                  key="open"
                  onClick={() => navigate(`/workbench/sessions/${session_id}${run_id ? `/runs/${run_id}` : ''}`)}
                  type="link"
                >
                  查看会话
                </Button>,
              ] : []}
            >
              <List.Item.Meta
                description={resource_optional_string(item, 'summary') ?? '调查尚未形成可展示结论。'}
                title={resource_string(item, 'session_title')}
              />
              <Space wrap>
                <Tag color={signal_color(run_status)}>{label(run_status)}</Tag>
                {proposal_status && <Tag color={signal_color(proposal_status)}>提案：{label(proposal_status)}</Tag>}
                {verification_status && <Tag color={signal_color(verification_status)}>验证：{label(verification_status)}</Tag>}
              </Space>
            </List.Item>
          )
        }}
      />
      {activities_query.hasNextPage && (
        <Button
          disabled={activities_query.isFetchingNextPage}
          onClick={() => void activities_query.fetchNextPage()}
          type="link"
        >
          {activities_query.isFetchingNextPage ? '正在加载…' : '加载更多留痕'}
        </Button>
      )}
    </>
  )
}

function ServiceDetail({ service_id }: { service_id: string }): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const service_query = useQuery({
    ...get_service_query(service_id),
    refetchInterval: () => (typeof document !== 'undefined' && document.visibilityState === 'visible' ? 15_000 : false),
  })
  const create_session = useMutation({
    mutationFn: () => api_v1_client.create_service_session(service_id),
    onSuccess: (response) => {
      const session = read_record(response.data.session)
      const session_id = resource_optional_string(session, 'id')
      if (!session_id) return
      void query_client.invalidateQueries({ queryKey: api_v1_query_keys.sessions({ limit: API_V1_DEFAULT_PAGE_SIZE, status: 'active' }) })
      navigate(`/workbench/sessions/${session_id}?intent=${ORDERS_SLOW_QUERY_INTENT_ID}`)
    },
  })

  if (service_query.isPending) {
    return <section className="workbench-page service-center-page"><ServiceLoading label="正在读取服务详情" /></section>
  }
  if (service_query.isError) {
    return <section className="workbench-page service-center-page"><ServiceErrorNotice error={service_query.error} /></section>
  }

  const service = (service_query.data as ApiResponse<ServiceResponse>).data.service
  const supported_investigations = resource_value(service, 'supported_investigations')
  const investigations = Array.isArray(supported_investigations) ? supported_investigations : []
  const supports_slow_query = investigations.some((item) => resource_optional_string(item, 'id') === ORDERS_SLOW_QUERY_INTENT_ID)
  return (
    <section className="workbench-page service-center-page" aria-labelledby="service-detail-title">
      <div className="page-eyebrow">REGISTERED SERVICE · LIMITED SNAPSHOT</div>
      <Space align="center" className="workbench-title-row" wrap>
        <Typography.Title id="service-detail-title" level={2}>{resource_string(service, 'title')}</Typography.Title>
        <Tag>{resource_string(service, 'kind')}</Tag>
      </Space>
      <Typography.Paragraph className="page-description">
        当前页面仅在可见时最多每 15 秒读取一次受控快照；它不是实时监控、告警或自动修复平台。
      </Typography.Paragraph>
      <Card className="service-detail-card" title="当前有限快照">
        <SnapshotSummary service={service} />
        <Button onClick={() => void service_query.refetch()} type="default">手动刷新</Button>
      </Card>
      <Card className="service-detail-card" title="支持的调查与动作边界">
        {investigations.map((investigation) => (
          <div className="service-capability" key={resource_string(investigation, 'id')}>
            <Typography.Text strong>{resource_string(investigation, 'title')}</Typography.Text>
            <Typography.Paragraph type="secondary">{resource_string(investigation, 'description')}</Typography.Paragraph>
          </div>
        ))}
        <Alert description={resource_string(service, 'action_boundary')} showIcon title="动作边界" type="info" />
      </Card>
      <Card className="service-detail-card" title="发起调查">
        <Typography.Paragraph type="secondary">
          创建后只会进入带服务上下文的会话并预填固定问题，尚未开始调查。请在工作台确认后点击“开始调查”。
        </Typography.Paragraph>
        <Button
          disabled={!supports_slow_query || create_session.isPending}
          loading={create_session.isPending}
          onClick={() => create_session.mutate()}
          type="primary"
        >
          创建订单慢查询调查会话
        </Button>
        {create_session.isError && <div className="service-mutation-error"><ServiceErrorNotice error={create_session.error} /></div>}
      </Card>
      <Card className="service-detail-card" title="最近调查与修复留痕">
        <ActivityList service_id={service_id} />
      </Card>
    </section>
  )
}

export function ServiceCenterPage(): ReactElement {
  const { service_id } = useParams<{ service_id: string }>()
  if (service_id) return <ServiceDetail service_id={service_id} />
  return <ServicesList />
}
