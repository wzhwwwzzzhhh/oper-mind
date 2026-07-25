export type DiagnosisEventType =
  | 'route_decided'
  | 'agent_start'
  | 'agent_done'
  | 'conflict_checked'
  | 'debate_round'
  | 'report'
  | 'reflection'

export interface TraceEvent {
  type: DiagnosisEventType
  node: string
  detail: string
  timestamp: string
}

export interface DiagnoseResponse {
  result: string
  thinking?: string[] | null
  trace?: TraceEvent[] | null
  strategy: string
}

export interface HealthResponse {
  status: 'ok'
  mode: 'mock' | 'real'
  model: string
}
