import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { ReactElement } from 'react'

import { ApiClientError } from '../../api/v1/client'
import { api_v1_query_keys, delete_session_mutation, update_session_mutation } from '../../api/v1/queries'
import { Icon } from '../shell/Icon'
import { UiAlert, UiModal } from '../workbench/ui'

interface SessionActionsProps {
  session_id: string
  title: string
  status: 'active' | 'archived'
  on_archived?: () => void
}

function action_error_message(error: unknown): string {
  if (error instanceof ApiClientError) return `${error.code}：${error.message}`
  return '会话操作失败，请稍后重试。'
}

export function SessionActions({ session_id, title, status, on_archived }: SessionActionsProps): ReactElement | null {
  const query_client = useQueryClient()
  const [menu_open, set_menu_open] = useState(false)
  const [rename_open, set_rename_open] = useState(false)
  const [archive_open, set_archive_open] = useState(false)
  const [draft_title, set_draft_title] = useState(title)
  const [validation_error, set_validation_error] = useState<string | null>(null)
  const [success_message, set_success_message] = useState<string | null>(null)

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

  if (status === 'archived') return null

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
        <p>如果有进行中的调查，调查会继续执行；归档后本会话只读，当前版本不能恢复。</p>
      </UiModal>
    </div>
  )
}
