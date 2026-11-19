import { useMutation, useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useState } from 'react'

import { ApiClientError } from '../../api/v1/client'
import { create_main_agent_run_mutation, list_services_query } from '../../api/v1/queries'
import { Composer } from '../shell/Composer'
import { read_items, read_record, read_string, resource_value } from './resource-readers'
import { UiAlert, UiButton, UiCollapse } from './ui'

/** 可被主 Agent 选择的服务：只列真正可用的 PostgreSQL 实例，不做兜底猜测。 */
interface PickableService {
  id: string
  title: string
}

/** 从公开服务列表里窄化出可选项；字段在 generated 里是 unknown，必须逐项判型。 */
function pickable_services(value: unknown): PickableService[] {
  const picked: PickableService[] = []
  for (const item of read_items(value)) {
    const id = read_string(resource_value(item, 'id'))
    const kind = read_string(resource_value(item, 'kind'))
    const title = read_string(resource_value(item, 'title'))
    // 后端受理期只接受 kind='postgres' 且已配置 DSN 的服务，前端不展示注定被拒的选项。
    if (id === undefined || title === undefined) continue
    if (kind !== 'postgres') continue
    if (read_record(item)?.has_dsn !== true) continue
    picked.push({ id, title })
  }
  return picked
}

interface MainAgentComposerProps {
  disabled?: boolean
  loading?: boolean
  /** 提交成功后的回调；由父级刷新权威会话记录，本组件不本地拼接时间线。 */
  on_submitted: () => void
  session_id: string
}

/** V2 主 Agent 录入：目标 + 可选两段文本材料；受理只走 create_run(main_agent)，本地不伪造结果。 */
export function MainAgentComposer({
  disabled,
  loading = false,
  on_submitted,
  session_id,
}: MainAgentComposerProps): ReactElement {
  const [query, set_query] = useState('')
  const [text_a, set_text_a] = useState('')
  const [text_b, set_text_b] = useState('')
  // 「未提供」与「提供了空文本」是两种不同输入，不能靠留空塌缩：勾选即显式提供该侧，未勾选提交 null。
  const [a_provided, set_a_provided] = useState(false)
  const [b_provided, set_b_provided] = useState(false)
  const [notice, set_notice] = useState<string | undefined>()
  const [service_id, set_service_id] = useState<string | undefined>()
  const create_run = useMutation({ ...create_main_agent_run_mutation() })
  // 自持查询：WorkbenchPage 的 services_query 以会话 service_ids 为 enabled 条件，
  // V2 会话通常不带 service_ids，复用会让选择器在主场景恒为空。
  const services_query = useQuery({ ...list_services_query() })
  const pickable = services_query.data === undefined ? [] : pickable_services(services_query.data.data)

  const submit = (): void => {
    const trimmed = query.trim()
    if (!trimmed || create_run.isPending) return
    set_notice(undefined)
    create_run.mutate(
      {
        session_id,
        query: trimmed,
        // 每次点击一个新幂等键：V2 首闭环不做本地重放恢复，双击不得重复受理。
        idempotency_key: globalThis.crypto.randomUUID(),
        text_a: a_provided ? text_a : null,
        text_b: b_provided ? text_b : null,
        service_id,
      },
      {
        onSuccess: () => {
          set_query('')
          on_submitted()
        },
        onError: (error) => {
          if (!(error instanceof ApiClientError)) return
          if (error.code === 'MAIN_AGENT_INPUT_REJECTED') {
            set_notice('输入包含凭据等不允许的内容，请移除后重新发起。')
            return
          }
          if (error.code === 'VALIDATION_ERROR') {
            set_notice(`${error.message}（目标不超过 200 字，每段材料不超过 2000 字、100 行）`)
            return
          }
          if (error.code === 'MAIN_AGENT_SERVICE_UNAVAILABLE') {
            set_notice('所选服务当前不可用，请重新选择。')
          }
        },
      },
    )
  }

  return (
    <div className="main-agent-composer">
      {notice !== undefined && (
        <UiAlert className="main-agent-composer__notice" description={notice} showIcon title="本次请求未受理" type="warning" />
      )}
      {create_run.isError && notice === undefined && (
        <UiAlert
          className="main-agent-composer__notice"
          description={create_run.error instanceof ApiClientError ? create_run.error.message : '请求未能提交到服务端。'}
          showIcon
          title="本次请求未受理"
          type="error"
        />
      )}
      <p className="main-agent-composer__hint">
        可直接询问只读排查步骤；知识辅助回答不会读取实时数据。
      </p>
      <div className="main-agent-composer__service">
        <label className="main-agent-composer__field">
          <span>目标服务（可选）</span>
          <select
            aria-label="目标服务"
            disabled={disabled || loading || pickable.length === 0}
            onChange={(event) => set_service_id(event.target.value === '' ? undefined : event.target.value)}
            value={service_id ?? ''}
          >
            <option value="">不指定服务</option>
            {pickable.map((service) => (
              <option key={service.id} value={service.id}>{service.title}</option>
            ))}
          </select>
        </label>
        {services_query.isPending && (
          <p className="main-agent-composer__service-note">正在读取服务列表…</p>
        )}
        {!services_query.isPending && services_query.isError && (
          <p className="main-agent-composer__service-note">服务列表读取失败，请稍后重试。</p>
        )}
        {!services_query.isPending && !services_query.isError && pickable.length === 0 && (
          <p className="main-agent-composer__service-note">没有可用的 PostgreSQL 服务。</p>
        )}
        {!services_query.isPending && !services_query.isError && pickable.length > 0 && (
          <p className="main-agent-composer__service-note">
            服务选择将在后续版本用于健康摘要与日志扫描（本片未启用）；服务在本次请求内冻结。
          </p>
        )}
      </div>
      <UiCollapse
        className="main-agent-composer__materials"
        items={[
          {
            key: 'materials',
            label: '附加文本材料（比较两段文本时填写）',
            children: (
              <div className="main-agent-composer__fields">
                <label className="main-agent-composer__field">
                  <span>
                    <input
                      aria-label="提供文本 A"
                      checked={a_provided}
                      disabled={disabled || loading}
                      onChange={(event) => set_a_provided(event.target.checked)}
                      type="checkbox"
                    />
                    提供文本 A（旧）
                  </span>
                  <textarea
                    aria-label="文本 A"
                    disabled={disabled || loading || !a_provided}
                    onChange={(event) => set_text_a(event.target.value)}
                    rows={6}
                    value={text_a}
                  />
                </label>
                <label className="main-agent-composer__field">
                  <span>
                    <input
                      aria-label="提供文本 B"
                      checked={b_provided}
                      disabled={disabled || loading}
                      onChange={(event) => set_b_provided(event.target.checked)}
                      type="checkbox"
                    />
                    提供文本 B（新）
                  </span>
                  <textarea
                    aria-label="文本 B"
                    disabled={disabled || loading || !b_provided}
                    onChange={(event) => set_text_b(event.target.value)}
                    rows={6}
                    value={text_b}
                  />
                </label>
                <UiButton disabled={disabled || loading} onClick={submit} type="primary">
                  提交比较
                </UiButton>
              </div>
            ),
          },
        ]}
      />
      <Composer
        disabled={disabled}
        label="主 Agent 请求"
        loading={loading || create_run.isPending}
        loading_label="正在提交请求"
        onChange={set_query}
        onSubmit={submit}
        placeholder="给 OperMind 主 Agent 发送消息，例如比较两段文本的差异…"
        value={query}
      />
    </div>
  )
}
