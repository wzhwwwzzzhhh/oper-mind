import { useInfiniteQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { API_V1_DEFAULT_PAGE_SIZE } from '../../api/v1/client'
import { list_sessions_infinite_query } from '../../api/v1/queries'
import { SessionActions } from '../session/SessionActions'
import { use_session_navigation } from '../session/SessionNavigationContext'
import { read_items, resource_optional_string, resource_string } from '../workbench/resource-readers'
import { Icon } from './Icon'

interface SidebarProps {
  collapsed: boolean
  on_collapse: () => void
}

/** 第二栏（会话模式）：会话双视图、标题搜索、分页与生命周期入口。 */
export function Sidebar({ collapsed, on_collapse }: SidebarProps): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const navigation = use_session_navigation()
  const current_session_id = location.pathname.match(/\/sessions\/([^/]+)/)?.[1]
  const search_ref = useRef<HTMLInputElement | null>(null)
  const search_timer = useRef<number | null>(null)

  function cancel_search_timer(): void {
    if (search_timer.current === null) return
    window.clearTimeout(search_timer.current)
    search_timer.current = null
  }

  function clear_search(): void {
    cancel_search_timer()
    navigation.set_search_value('')
    navigation.set_search_query('')
  }

  function handle_search_change(value: string): void {
    navigation.set_search_value(value)
    cancel_search_timer()
    const trimmed = value.trim()
    if (!trimmed) {
      navigation.set_search_query('')
      return
    }
    search_timer.current = window.setTimeout(() => navigation.set_search_query(trimmed), 300)
  }

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

  useEffect(() => () => {
    cancel_search_timer()
  }, [])

  const sessions_query = useInfiniteQuery(list_sessions_infinite_query({
    limit: API_V1_DEFAULT_PAGE_SIZE,
    q: navigation.search_query || undefined,
    status: navigation.view,
  }))
  const sessions = sessions_query.data?.pages.flatMap((page) => read_items(page.data)) ?? []
  const searching = navigation.search_query !== ''
  const archived_view = navigation.view === 'archived'

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

      <div aria-label="会话视图" className="session-view-switch">
        <button
          aria-pressed={navigation.view === 'active'}
          className={navigation.view === 'active' ? 'active' : ''}
          onClick={() => navigation.set_view('active')}
          type="button"
        >
          最近会话
        </button>
        <button
          aria-pressed={archived_view}
          className={archived_view ? 'active' : ''}
          onClick={() => navigation.set_view('archived')}
          type="button"
        >
          已归档
        </button>
      </div>

      <div className="history-search-wrap">
        <Icon className="history-search-icon" name="search" size={14} />
        <input
          aria-label="搜索会话"
          className="history-search"
          maxLength={100}
          onChange={(event) => handle_search_change(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              clear_search()
              search_ref.current?.blur()
            }
          }}
          placeholder="搜索会话（Ctrl K）"
          ref={search_ref}
          value={navigation.search_value}
        />
        {navigation.search_value !== '' && (
          <button
            aria-label="清空搜索"
            className="history-search-clear"
            onClick={clear_search}
            type="button"
          >
            <Icon className="icon" name="x" size={13} />
          </button>
        )}
      </div>

      {navigation.lifecycle_notice && (
        <div aria-live="polite" className="session-lifecycle-notice" role="status">
          {navigation.lifecycle_notice}
        </div>
      )}

      <div className="history-heading">
        <span>{searching ? '搜索结果' : archived_view ? '已归档' : '最近会话'}</span>
      </div>
      <nav className="history-list">
        {sessions_query.isPending && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            {archived_view ? '正在加载归档会话…' : '正在加载会话…'}
          </span>
        )}
        {sessions_query.isSuccess && sessions.length === 0 && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            {searching
              ? archived_view ? '无匹配归档会话' : '无匹配会话'
              : archived_view ? '还没有归档会话' : '还没有会话'}
          </span>
        )}
        {sessions_query.isError && sessions.length === 0 && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            {archived_view ? '归档会话暂不可读' : searching ? '会话搜索暂不可用' : '会话列表暂不可读'}
          </span>
        )}
        {sessions.map((session) => {
          const session_id = resource_optional_string(session, 'id')
          const title = resource_string(session, 'title', '未命名会话')
          const status = resource_optional_string(session, 'status') === 'archived' ? 'archived' : 'active'
          const active = session_id != null && session_id === current_session_id
          return (
            <div className={`history-item-row${active ? ' active' : ''}`} key={session_id ?? title}>
              <button
                aria-current={active ? 'true' : undefined}
                className={`history-item${active ? ' active' : ''}`}
                disabled={!session_id}
                onClick={() => session_id && navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)}
                type="button"
              >
                <span>{title}</span>
                {status === 'archived' && <small className="archived-session-label">已归档</small>}
              </button>
              {session_id && (
                <SessionActions
                  on_archived={active ? () => navigate('/workbench') : undefined}
                  session_id={session_id}
                  status={status}
                  title={title}
                />
              )}
            </div>
          )
        })}
        {sessions_query.hasNextPage && (
          <button
            className="history-load-more"
            disabled={sessions_query.isFetchingNextPage}
            onClick={() => void sessions_query.fetchNextPage()}
            type="button"
          >
            {sessions_query.isFetchingNextPage ? '正在加载…' : '加载更多会话'}
          </button>
        )}
        {sessions_query.isFetchNextPageError && (
          <div className="history-page-error">
            <span>加载更多失败</span>
            <button onClick={() => void sessions_query.fetchNextPage()} type="button">重试</button>
          </div>
        )}
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
