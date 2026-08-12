import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { list_sessions_query } from '../../api/v1/queries'
import { read_items, resource_optional_string, resource_string } from '../workbench/resource-readers'
import { Icon } from './Icon'

interface SidebarProps {
  collapsed: boolean
  on_collapse: () => void
}

/** 第二栏（会话模式）：品牌 + 新建会话 + 会话搜索（Ctrl K）+ 最近会话列表（接真实 API）；运维中心走最左侧全局导航。 */
export function Sidebar({ collapsed, on_collapse }: SidebarProps): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const current_session_id = location.pathname.match(/\/sessions\/([^/]+)/)?.[1]
  const search_ref = useRef<HTMLInputElement | null>(null)
  const search_timer = useRef<number | null>(null)
  const [search_value, set_search_value] = useState('')
  const [search_query, set_search_query] = useState('')

  // 输入 300ms debounce 后走服务端标题搜索；清空立即恢复默认最近会话列表。
  function handle_search_change(value: string): void {
    set_search_value(value)
    if (search_timer.current !== null) {
      window.clearTimeout(search_timer.current)
      search_timer.current = null
    }
    const trimmed = value.trim()
    if (!trimmed) {
      set_search_query('')
      return
    }
    search_timer.current = window.setTimeout(() => set_search_query(trimmed), 300)
  }

  // Ctrl K 聚焦搜索框（真实键盘监听，替代完善清单 P1-12 假提示）；Esc 清空搜索。
  useEffect(() => {
    function on_keydown(event: KeyboardEvent): void {
      if (event.ctrlKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        event.stopPropagation()
        search_ref.current?.focus()
        search_ref.current?.select()
      }
    }
    document.addEventListener('keydown', on_keydown)
    return () => document.removeEventListener('keydown', on_keydown)
  }, [])

  const sessions_query = useQuery({
    ...list_sessions_query(
      search_query ? { limit: 20, status: 'active', q: search_query } : { limit: 20, status: 'active' },
    ),
  })
  const sessions = sessions_query.data ? read_items(sessions_query.data.data) : []
  const searching = search_query !== ''

  return (
    <aside aria-label="会话导航" className={`second chat-side${collapsed ? ' collapsed' : ''}`}>
      <div className="brand-row">
        <a aria-label="OperMind 首页" className="brand" href="/workbench">
          <span className="brand-mark">O</span>
          <span className="brand-copy">
            OperMind
            <small>DEVOPS COPILOT</small>
          </span>
        </a>
        <button aria-label="收起侧栏" className="icon-btn" id="collapse-btn" onClick={on_collapse} type="button">
          <Icon className="icon" name="chevron-left" size={15} />
        </button>
      </div>

      <button className="new-chat" onClick={() => navigate('/workbench')} type="button">
        <span className="plus">＋</span>
        <span className="new-chat-label">新建会话</span>
      </button>

      <div className="history-search-wrap">
        <Icon className="history-search-icon" name="search" size={14} />
        <input
          aria-label="搜索会话"
          className="history-search"
          onChange={(event) => handle_search_change(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              set_search_value('')
              set_search_query('')
              search_ref.current?.blur()
            }
          }}
          placeholder="搜索会话（Ctrl K）"
          ref={search_ref}
          value={search_value}
        />
        {search_value !== '' && (
          <button
            aria-label="清空搜索"
            className="history-search-clear"
            onClick={() => {
              set_search_value('')
              set_search_query('')
            }}
            type="button"
          >
            <Icon className="icon" name="x" size={13} />
          </button>
        )}
      </div>

      <div className="history-heading">
        <span>{searching ? '搜索结果' : '最近会话'}</span>
      </div>
      <nav className="history-list">
        {sessions_query.isPending && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>正在加载会话…</span>
        )}
        {sessions_query.isSuccess && sessions.length === 0 && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            {searching ? '无匹配会话' : '还没有会话'}
          </span>
        )}
        {sessions_query.isError && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            {searching ? '会话搜索暂不可用' : '会话列表暂不可读'}
          </span>
        )}
        {sessions.map((session) => {
          const session_id = resource_optional_string(session, 'id')
          const title = resource_string(session, 'title', '未命名会话')
          const active = session_id != null && session_id === current_session_id
          return (
            <button
              aria-current={active ? 'true' : undefined}
              className={`history-item${active ? ' active' : ''}`}
              disabled={!session_id}
              key={session_id ?? title}
              onClick={() => session_id && navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)}
              type="button"
            >
              {title}
            </button>
          )
        })}
      </nav>
      <button className="approvals-entry" onClick={() => navigate('/workbench/runs')} type="button">
        <Icon className="icon" name="clock" size={15} />
        <span>最近调查</span>
      </button>
      <button className="approvals-entry" onClick={() => navigate('/workbench/approvals')} type="button">
        <Icon className="icon" name="stack" size={15} />
        <span>待审批</span>
      </button>
    </aside>
  )
}
