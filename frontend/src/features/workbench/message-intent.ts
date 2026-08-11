/**
 * 前端意图快速预判（与服务端 `requires_database_context` 保持一致的关键词集合）。
 * 仅用于 UX 快速分流：服务端 `POST /sessions/{id}/messages` 仍权威判定，
 * 调查意图会返回 409 INVESTIGATION_REQUIRED 由前端回退到 Run 主链路。
 */
const DATABASE_KEYWORDS = [
  'select', 'sql', 'explain', '索引', '慢查询', '数据库', 'postgres',
  '连接池', 'pg_stat', 'schema',
] as const

const DATABASE_OR_QUERY_KEYWORDS = [...DATABASE_KEYWORDS, '查询', '表'] as const

const LOG_KEYWORDS = ['日志', 'log', '错误', '异常', '报错', '超时'] as const

export function is_investigation_message(text: string): boolean {
  const lowered = text.toLowerCase()
  if (LOG_KEYWORDS.some((keyword) => lowered.includes(keyword))) {
    return DATABASE_KEYWORDS.some((keyword) => lowered.includes(keyword))
  }
  return DATABASE_OR_QUERY_KEYWORDS.some((keyword) => lowered.includes(keyword))
}
