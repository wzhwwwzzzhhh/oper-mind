import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type SessionResponse,
} from '../../api/v1/client'
import {
  api_v1_query_keys,
  delete_session_mutation,
  list_sessions_infinite_query,
  update_session_mutation,
} from '../../api/v1/queries'
import { Icon } from '../shell/Icon'
import { UiAlert, UiButton, UiModal } from '../workbench/ui'
import { use_session_navigation } from './SessionNavigationContext'

type SessionActionStatus = 'active' | 'archived' | 'unknown'

interface SessionActionsProps {
  session_id: string
  title: string
  status: SessionActionStatus
  on_archived?: () => void
}

function action_error_message(error: unknown): string {
  if (error instanceof ApiClientError) return `${error.code}：${error.message}`
  if (error instanceof Error) return error.message
  return '会话操作失败，请稍后重试。'
}

function session_state(
  response: ApiResponse<SessionResponse>,
  expected_session_id: string,
): 'active' | 'archived' | undefined {
  const value = response.data.session
  if (!value || typeof value !== 'object') return undefined
  const record = value as Record<string, unknown>
  if (record.id !== expected_session_id) return undefined
  return record.status === 'active' || record.status === 'archived' ? record.status : undefined
}

function is_explicit_rejection(error: unknown): boolean {
  return error instanceof ApiClientError
    && error.diagnostics.status >= 400
    && error.diagnostics.status < 500
}

/** active 会话操作与 archived 恢复入口；unknown/refreshing 时不暴露生命周期动作。 */
export function SessionActions({ session_id, title, status, on_archived }: SessionActionsProps): ReactElement | null {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const navigation = use_session_navigation()
  const [menu_open, set_menu_open] = useState(false)
  const [rename_open, set_rename_open] = useState(false)
  const [archive_open, set_archive_open] = useState(false)
  const [restore_open, set_restore_open] = useState(false)
  const [draft_title, set_draft_title] = useState(title)
  const [validation_error, set_validation_error] = useState<string | null>(null)
  const [success_message, set_success_message] = useState<string | null>(null)
  const restore_in_flight = useRef(false)

  const invalidate_session = async (): Promise<void> => {
    await Promise.all([
      query_client.invalidateQueries({ queryKey: ['api-v1', 'sessions'] }),
      query_client.invalidateQueries({ queryKey: api_v1_query_keys.session(session_id) }),
    ])
  }

  const update_mutation = useMutation({
    ...update_session_mutation(),
    onSuccess: async () => {
      await invalidate_session()
      set_rename_open(false)
      set_validation_error(null)
      set_success_message('会话标题已更新')
    },
  })

  const delete_mutation = useMutation({
    ...delete_session_mutation(),
    onSuccess: async () => {
      await invalidate_session()
      set_archive_open(false)
      set_success_message('会话已归档')
      on_archived?.()
    },
  })

  const restore_mutation = useMutation({
    mutationFn: async (): Promise<ApiResponse<SessionResponse>> => {
      let uncertain_error: unknown
      try {
        const response = await api_v1_client.update_session(session_id, { status: 'active' })
        if (session_state(response, session_id) === 'active') return response
        uncertain_error = new Error('恢复响应与请求的会话状态不一致。')
      } catch (error) {
        if (is_explicit_rejection(error)) throw error
        uncertain_error = error
      }

      await query_client.cancelQueries({ queryKey: api_v1_query_keys.session(session_id), exact: true })
      try {
        const response = await api_v1_client.get_session(session_id)
        const state = session_state(response, session_id)
        if (state === 'active') return response
        if (state === 'archived') throw uncertain_error
        throw new Error('服务器返回了不匹配的会话资源。')
      } catch (read_error) {
        if (read_error === uncertain_error) throw read_error
        if (read_error instanceof ApiClientError && read_error.code === 'SESSION_NOT_FOUND') throw read_error
        throw new Error('恢复结果尚未确认，请刷新会话状态后重试。')
      }
    },
    onSuccess: async (response) => {
      const detail_key = api_v1_query_keys.session(session_id)
      await query_client.cancelQueries({ queryKey: detail_key, exact: true })
      query_client.setQueryData(detail_key, response)

      const list_prefix = ['api-v1', 'sessions'] as const
      await query_client.cancelQueries({ queryKey: list_prefix })
      query_client.removeQueries({ queryKey: list_prefix, type: 'inactive' })
      await query_client.resetQueries({ queryKey: list_prefix, type: 'active' }).catch(() => undefined)
      await query_client.prefetchInfiniteQuery(list_sessions_infinite_query({
        limit: API_V1_DEFAULT_PAGE_SIZE,
        q: navigation.search_query || undefined,
        status: 'active',
      })).catch(() => undefined)

      navigation.set_view('active')
      navigation.set_lifecycle_notice('会话已恢复')
      set_restore_open(false)
      navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)
      void query_client.invalidateQueries({ queryKey: list_prefix })
    },
  })

  const submit_restore = (): void => {
    if (restore_in_flight.current) return
    restore_in_flight.current = true
    restore_mutation.mutate(undefined, {
      onSettled: () => {
        restore_in_flight.current = false
      },
    })
  }

  if (status === 'unknown') return null

  const open_rename = (): void => {
    set_menu_open(false)
    set_draft_title(title)
    set_validation_error(null)
    set_rename_open(true)
  }

  const save_title = (): void => {
    const normalized_title = draft_title.trim()
    if (!normalized_title) {
      set_validation_error('会话标题不能为空')
      return
    }
    set_validation_error(null)
    update_mutation.mutate({ session_id, payload: { title: normalized_title } })
  }

  const open_archive = (): void => {
    set_menu_open(false)
    set_archive_open(true)
  }

  if (status === 'archived') {
    return (
      <div className="session-actions session-actions--restore">
        <UiButton
          className="session-actions__restore"
          disabled={restore_mutation.isPending}
          loading={restore_mutation.isPending}
          onClick={() => set_restore_open(true)}
          type="link"
        >
          恢复会话
        </UiButton>
        {restore_mutation.isError && (
          <UiAlert
            className="session-actions__notice"
            description={action_error_message(restore_mutation.error)}
            type="error"
          />
        )}
        <UiModal
          cancelText="取消"
          confirmLoading={restore_mutation.isPending}
          onCancel={() => set_restore_open(false)}
          onOk={submit_restore}
          okText="确认恢复"
          open={restore_open}
          title="恢复会话"
        >
          <p>恢复后会话将回到最近会话，并重新提供消息与调查录入。</p>
          <p>恢复不会复制历史内容，也不会创建或启动调查。</p>
        </UiModal>
      </div>
    )
  }

  return (
    <div className="session-actions">
      <button
        aria-expanded={menu_open}
        aria-haspopup="menu"
        aria-label={`会话操作：${title}`}
        className="session-actions__trigger"
        onClick={() => set_menu_open((current) => !current)}
        type="button"
      >
        <Icon name="chevron-down" size={13} />
      </button>
      {menu_open && (
        <div className="session-actions__menu" role="menu">
          <button className="session-actions__menu-item" onClick={open_rename} role="menuitem" type="button">
            重命名
          </button>
          <button className="session-actions__menu-item danger" onClick={open_archive} role="menuitem" type="button">
            归档
          </button>
        </div>
      )}
      {success_message && <UiAlert className="session-actions__notice" description={success_message} type="success" />}
      {update_mutation.isError && (
        <UiAlert className="session-actions__notice" description={action_error_message(update_mutation.error)} type="error" />
      )}
      {delete_mutation.isError && (
        <UiAlert className="session-actions__notice" description={action_error_message(delete_mutation.error)} type="error" />
      )}
      <UiModal
        cancelText="取消"
        confirmLoading={update_mutation.isPending}
        onCancel={() => {
          set_rename_open(false)
          set_validation_error(null)
        }}
        onOk={save_title}
        okText="保存标题"
        open={rename_open}
        title="重命名会话"
      >
        <label className="session-actions__field">
          <span>会话标题</span>
          <input
            aria-label="会话标题"
            autoFocus
            onChange={(event) => set_draft_title(event.target.value)}
            value={draft_title}
          />
        </label>
        {validation_error && <UiAlert description={validation_error} type="error" />}
      </UiModal>
      <UiModal
        cancelText="取消"
        confirmLoading={delete_mutation.isPending}
        okButtonProps={{ danger: true }}
        onCancel={() => set_archive_open(false)}
        onOk={() => delete_mutation.mutate(session_id)}
        okText="确认归档"
        open={archive_open}
        title="归档会话"
      >
        <p>归档后会话将从最近会话中隐藏，历史内容仍可查看。</p>
        <p>如果有进行中的调查，调查会继续执行；你可以稍后在“已归档”中找回并恢复会话。</p>
      </UiModal>
    </div>
  )
}
