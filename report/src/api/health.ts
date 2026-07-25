import type { HealthResponse } from '../types/api'

const API_PREFIX = '/api'

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) return false
  const payload = value as Record<string, unknown>
  return (
    payload.status === 'ok'
    && (payload.mode === 'mock' || payload.mode === 'real')
    && typeof payload.model === 'string'
  )
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_PREFIX}/health`, { signal })
  if (!response.ok) {
    throw new Error(`后端不可用（HTTP ${response.status}）`)
  }

  const payload: unknown = await response.json()
  if (!isHealthResponse(payload)) {
    throw new Error('后端健康检查响应不符合契约')
  }
  return payload
}
