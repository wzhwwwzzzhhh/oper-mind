import { useState } from 'react'
import type { FormEvent, ReactElement } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  get_knowledge_document_query,
  list_knowledge_documents_query,
  search_knowledge_query,
} from '../../api/v1/queries'
import type { KnowledgeDocumentResource, KnowledgeSearchHitResource } from '../../api/v1/client'

function list_empty_text(status: string | undefined): string | null {
  if (status === 'not_configured') return '知识库未配置：请配置 OPERMIND_KNOWLEDGE_DIR 后使用。'
  if (status === 'empty') return '暂无文档：受管知识目录内还没有 Markdown 文档。'
  return null
}

function search_empty_text(status: string | undefined): string | null {
  if (status === 'not_configured') return '知识库未配置：请配置 OPERMIND_KNOWLEDGE_DIR 后使用。'
  if (status === 'empty') return '暂无文档：受管知识目录内还没有 Markdown 文档。'
  if (status === 'no_match') return '无匹配文档：请尝试更换检索词。'
  return null
}

/** 文档知识库页：受管知识目录的列表浏览 / 页面内检索 / 文档详情三视图，全程只读。 */
export function KnowledgePage(): ReactElement {
  const [search_params, set_search_params] = useSearchParams()
  const opened_path = search_params.get('doc')
  const [query, set_query] = useState('')

  const list_query = useQuery({ ...list_knowledge_documents_query() })
  const document_query = useQuery({
    ...get_knowledge_document_query(opened_path ?? ''),
    enabled: opened_path != null && opened_path !== '',
  })
  const search_query = useQuery({
    ...search_knowledge_query(query),
    enabled: query !== '',
  })

  const open_document = (relative_path: string): void => {
    set_search_params({ doc: relative_path })
  }

  const close_document = (): void => {
    set_search_params({})
  }

  const submit_search = (event: FormEvent): void => {
    event.preventDefault()
    void search_query.refetch()
  }

  const items: KnowledgeDocumentResource[] = list_query.data?.data.items ?? []
  const hits: KnowledgeSearchHitResource[] = search_query.data?.data.items ?? []

  if (opened_path != null && opened_path !== '') {
    if (document_query.isPending) {
      return (
        <div className="knowledge-page">
          <div className="knowledge-breadcrumb"><button onClick={close_document} type="button">← 返回文档列表</button></div>
          <div className="knowledge-inline-state">正在读取文档…</div>
        </div>
      )
    }
    if (document_query.isError) {
      return (
        <div className="knowledge-page">
          <div className="knowledge-breadcrumb"><button onClick={close_document} type="button">← 返回文档列表</button></div>
          <div className="knowledge-inline-state error">读取文档失败，请稍后重试。</div>
        </div>
      )
    }
    const document = document_query.data?.data.document
    if (document == null) {
      return (
        <div className="knowledge-page">
          <div className="knowledge-breadcrumb"><button onClick={close_document} type="button">← 返回文档列表</button></div>
          <div className="knowledge-inline-state">文档不存在或不可访问。</div>
        </div>
      )
    }
    return (
      <div className="knowledge-page">
        <div className="knowledge-breadcrumb"><button onClick={close_document} type="button">← 返回文档列表</button><span>/</span><strong>{document.title}</strong></div>
        <section className="knowledge-detail-head">
          <div><div className="knowledge-eyebrow">受管知识目录 · 只读</div><h1>{document.title}</h1><p>{document.relative_path}</p></div>
        </section>
        <section className="knowledge-detail-body">
          <pre>{document.content}</pre>
        </section>
      </div>
    )
  }

  return (
    <div className="knowledge-page">
      <div className="knowledge-breadcrumb"><button onClick={() => { window.history.replaceState({}, '', '/knowledge') }} type="button">会话工作台</button><span>/</span><strong>文档知识库</strong></div>

      <section className="knowledge-page-head">
        <div><div className="knowledge-eyebrow">知识库</div><h1>文档知识库</h1><p>浏览受管知识目录内的运维文档 / SOP / 排障记录，并在页面内直接检索。</p></div>
        <div className="knowledge-source-badge">受管知识目录 · 只读</div>
      </section>

      <form className="knowledge-search" onSubmit={submit_search}>
        <input
          aria-label="检索知识文档"
          placeholder="输入关键词检索知识文档，如「kill 慢查询」"
          value={query}
          onChange={(event) => set_query(event.target.value)}
          type="search"
        />
        <button className="knowledge-button" type="submit" disabled={query.trim() === ''}>检索</button>
      </form>

      {list_query.isPending && <div className="knowledge-inline-state">正在读取知识目录…</div>}
      {list_query.isError && (
        <div className="knowledge-inline-state error">读取知识库失败，请稍后重试。
          <button className="knowledge-link" onClick={() => void list_query.refetch()} type="button">重试</button>
        </div>
      )}

      {search_query.isEnabled && search_query.isError && (
        <div className="knowledge-inline-state error">检索失败，请稍后重试。
          <button className="knowledge-link" onClick={() => void search_query.refetch()} type="button">重试</button>
        </div>
      )}

      {search_query.isEnabled && search_query.isSuccess && (
        <section className="knowledge-section">
          <div className="knowledge-section-head"><div><h2>检索结果</h2><p>来源：受管知识目录 · 确定性检索</p></div></div>
          {hits.length === 0 && <div className="knowledge-empty">{search_empty_text(search_query.data?.data.status)}</div>}
          <div className="knowledge-doc-list">{hits.map((hit) => (
            <button className="knowledge-doc" key={hit.relative_path} onClick={() => open_document(hit.relative_path)} type="button">
              <strong>{hit.title}</strong>
              <span>{hit.relative_path}</span>
              {hit.snippets.map((snippet, index) => <p key={index}>… {snippet} …</p>)}
            </button>
          ))}</div>
        </section>
      )}

      <section className="knowledge-section">
        <div className="knowledge-section-head"><div><h2>全部文档</h2><p>来源：受管知识目录 · 只读</p></div></div>
        {list_query.isSuccess && items.length === 0 && <div className="knowledge-empty">{list_empty_text(list_query.data?.data.status) ?? '知识库为空。'}</div>}
        <div className="knowledge-doc-list">{items.map((item) => (
          <button className="knowledge-doc" key={item.relative_path} onClick={() => open_document(item.relative_path)} type="button">
            <strong>{item.title}</strong>
            <span>{item.relative_path}</span>
          </button>
        ))}</div>
      </section>
    </div>
  )
}
