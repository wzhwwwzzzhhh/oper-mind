/**
 * P8 普通消息的「待发送意图」恢复机制。
 * 用户在欢迎页输入普通消息并创建会话后，把消息暂存到 sessionStorage，
 * 会话页加载后自动发送；发送成功或明确失败后清除。
 * 只服务于普通消息（run_id 为空），与 send-intent.ts（Run 幂等链路）互不干扰。
 */

export interface PendingPlainMessage {
  created_at: string
  query: string
}

const STORAGE_PREFIX = 'opermind:p8:plain-message-intent:'

function storage_key(session_id: string): string {
  return `${STORAGE_PREFIX}${session_id}`
}

function is_uuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}

function is_pending(value: unknown): value is PendingPlainMessage {
  if (typeof value !== 'object' || value === null) return false
  const pending = value as Partial<PendingPlainMessage>
  return typeof pending.query === 'string' && pending.query.trim().length > 0
    && typeof pending.created_at === 'string' && pending.created_at.endsWith('Z')
}

export function save_pending_plain_message(
  storage: Storage,
  session_id: string,
  query: string,
): void {
  if (!is_uuid(session_id) || !query.trim()) {
    throw new Error('普通消息待发送意图需要合法的会话标识与内容。')
  }
  storage.setItem(
    storage_key(session_id),
    JSON.stringify({ query, created_at: new Date().toISOString() }),
  )
}

export function load_pending_plain_message(
  storage: Storage,
  session_id: string,
): PendingPlainMessage | undefined {
  const serialized = storage.getItem(storage_key(session_id))
  if (!serialized) return undefined
  try {
    const parsed: unknown = JSON.parse(serialized)
    return is_pending(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

export function clear_pending_plain_message(storage: Storage, session_id: string): void {
  storage.removeItem(storage_key(session_id))
}
