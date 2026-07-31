import type { components, operations } from './generated'

export const API_V1_DEFAULT_PAGE_SIZE = 20

export type SessionResource = components['schemas']['SessionResource']
export type MessageResource = components['schemas']['MessageResource']
export type DiagnosisRunResource = components['schemas']['DiagnosisRunResource']
export type DiagnosisResultResource = components['schemas']['DiagnosisResultResource']
export type SessionResponse = components['schemas']['SessionResponse']
export type SessionListResponse = components['schemas']['SessionListResponse']
export type MessageListResponse = components['schemas']['MessageListResponse']
export type DiagnosisRunListResponse = components['schemas']['DiagnosisRunListResponse']
export type RunResponse = components['schemas']['RunResponse']
export type RunEventResource = components['schemas']['RunEventResource']
export type RunEventListResponse = components['schemas']['RunEventListResponse']
export type CreateRunRequest = components['schemas']['CreateRunRequest']
export type ActionApprovalRequest = components['schemas']['ActionApprovalRequest']
export type ActionExecutionRequest = components['schemas']['ActionExecutionRequest']
export type RunActionProposalResponse = components['schemas']['RunActionProposalResponse']
export type ActionProposalResponse = components['schemas']['ActionProposalResponse']
export type ActionEventListResponse = components['schemas']['ActionEventListResponse']
export type ActionExecutionResponse = components['schemas']['ActionExecutionResponse']
export type ServiceResource = components['schemas']['ServiceResource']
export type ServiceResponse = components['schemas']['ServiceResponse']
export type ServiceListResponse = components['schemas']['ServiceListResponse']
export type ServiceActivityResource = components['schemas']['ServiceActivityResource']
export type ServiceActivityListResponse = components['schemas']['ServiceActivityListResponse']

export type ListSessionsQuery = NonNullable<
  operations['list_sessions_api_v1_sessions_get']['parameters']['query']
>
export type ListSessionMessagesQuery = NonNullable<
  operations['list_messages_api_v1_sessions__session_id__messages_get']['parameters']['query']
>
export type ListSessionRunsQuery = NonNullable<
  operations['list_session_runs_api_v1_sessions__session_id__runs_get']['parameters']['query']
>
export type ListRunEventsQuery = NonNullable<
  operations['list_run_events_api_v1_runs__run_id__events_get']['parameters']['query']
>
export type ListActionEventsQuery = NonNullable<
  operations['list_action_events_api_v1_action_proposals__proposal_id__events_get']['parameters']['query']
>
export type ListServiceActivitiesQuery = NonNullable<
  operations['list_service_activities_api_v1_services__service_id__activities_get']['parameters']['query']
>

export interface ApiRequestDiagnostics {
  request_id: string
  response_request_id?: string
  response_trace_id?: string
  meta_request_id?: string
  meta_trace_id?: string
  status: number
  protocol_issues: ApiProtocolIssue[]
}

export type ApiProtocolIssue =
  | 'missing_response_request_id'
  | 'request_id_mismatch'
  | 'request_id_header_meta_mismatch'
  | 'trace_id_header_meta_mismatch'

export interface ApiResponse<TData> {
  data: TData
  diagnostics: ApiRequestDiagnostics
}

export interface ApiRequestOptions {
  signal?: AbortSignal
}

export interface CreateRunOptions extends ApiRequestOptions {
  idempotency_key: string
}

export interface ActionMutationOptions extends ApiRequestOptions {
  idempotency_key: string
}

export interface ApiClientOptions {
  base_url?: string
  fetch_impl?: typeof fetch
  request_id_factory?: () => string
}

interface ApiErrorPayload {
  error?: {
    code?: unknown
    message?: unknown
    details?: unknown
  }
}

interface ResponseMeta {
  request_id?: unknown
  trace_id?: unknown
}

export class ApiClientError extends Error {
  readonly code: string
  readonly details: unknown
  readonly diagnostics: ApiRequestDiagnostics

  constructor(
    code: string,
    message: string,
    details: unknown,
    diagnostics: ApiRequestDiagnostics,
  ) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.details = details
    this.diagnostics = diagnostics
  }
}

export interface ApiV1Client {
  list_services(options?: ApiRequestOptions): Promise<ApiResponse<ServiceListResponse>>
  get_service(service_id: string, options?: ApiRequestOptions): Promise<ApiResponse<ServiceResponse>>
  list_service_activities(
    service_id: string,
    query?: ListServiceActivitiesQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<ServiceActivityListResponse>>
  create_service_session(
    service_id: string,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<SessionResponse>>
  list_sessions(
    query?: ListSessionsQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<SessionListResponse>>
  get_session(
    session_id: string,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<SessionResponse>>
  list_session_messages(
    session_id: string,
    query?: ListSessionMessagesQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<MessageListResponse>>
  list_session_runs(
    session_id: string,
    query?: ListSessionRunsQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<DiagnosisRunListResponse>>
  get_run(run_id: string, options?: ApiRequestOptions): Promise<ApiResponse<RunResponse>>
  list_run_events(
    run_id: string,
    query?: ListRunEventsQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<RunEventListResponse>>
  create_run(
    session_id: string,
    payload: CreateRunRequest,
    options: CreateRunOptions,
  ): Promise<ApiResponse<RunResponse>>
  get_run_action_proposal(
    run_id: string,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<RunActionProposalResponse>>
  get_action_proposal(
    proposal_id: string,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<ActionProposalResponse>>
  list_action_events(
    proposal_id: string,
    query?: ListActionEventsQuery,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<ActionEventListResponse>>
  decide_action_proposal(
    proposal_id: string,
    payload: ActionApprovalRequest,
    options: ActionMutationOptions,
  ): Promise<ApiResponse<ActionProposalResponse>>
  request_action_execution(
    proposal_id: string,
    payload: ActionExecutionRequest,
    options: ActionMutationOptions,
  ): Promise<ApiResponse<ActionExecutionResponse>>
}

function create_request_id(): string {
  return globalThis.crypto.randomUUID()
}

function is_record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function read_response_meta(payload: unknown): ResponseMeta {
  if (!is_record(payload) || !is_record(payload.meta)) {
    return {}
  }

  return payload.meta
}

function read_safe_error(payload: unknown): ApiErrorPayload['error'] {
  if (!is_record(payload) || !is_record(payload.error)) {
    return undefined
  }

  return payload.error
}

function append_query<TQuery>(path: string, query: TQuery | undefined): string {
  if (!query) {
    return path
  }

  const search_params = new URLSearchParams()
  for (const [key, value] of Object.entries(query as Record<string, unknown>)) {
    if (value !== undefined && value !== null) {
      search_params.set(key, String(value))
    }
  }

  const serialized_query = search_params.toString()
  return serialized_query ? `${path}?${serialized_query}` : path
}

function resolve_url(base_url: string, path: string): string {
  if (base_url) {
    return new URL(path, base_url).toString()
  }

  if (typeof window !== 'undefined') {
    return new URL(path, window.location.origin).toString()
  }

  return path
}

function build_diagnostics(
  request_id: string,
  response: Response,
  payload: unknown,
): ApiRequestDiagnostics {
  const response_request_id = response.headers.get('X-Request-Id') ?? undefined
  const response_trace_id = response.headers.get('X-Trace-Id') ?? undefined
  const meta = read_response_meta(payload)
  const meta_request_id = typeof meta.request_id === 'string' ? meta.request_id : undefined
  const meta_trace_id = typeof meta.trace_id === 'string' ? meta.trace_id : undefined
  const protocol_issues: ApiProtocolIssue[] = []

  if (!response_request_id) {
    protocol_issues.push('missing_response_request_id')
  } else if (response_request_id !== request_id) {
    protocol_issues.push('request_id_mismatch')
  }

  if (response_request_id && meta_request_id && response_request_id !== meta_request_id) {
    protocol_issues.push('request_id_header_meta_mismatch')
  }

  if (response_trace_id && meta_trace_id && response_trace_id !== meta_trace_id) {
    protocol_issues.push('trace_id_header_meta_mismatch')
  }

  return {
    request_id,
    response_request_id,
    response_trace_id,
    meta_request_id,
    meta_trace_id,
    status: response.status,
    protocol_issues,
  }
}

async function parse_json_response(response: Response): Promise<unknown> {
  const content_type = response.headers.get('content-type') ?? ''
  if (!content_type.toLowerCase().includes('application/json')) {
    throw new Error('non_json')
  }

  return response.json() as Promise<unknown>
}

interface JsonRequestOptions {
  body?: unknown
  idempotency_key?: string
  method?: 'GET' | 'POST'
}

async function request_json<TData>(
  fetch_impl: typeof fetch,
  request_id_factory: () => string,
  base_url: string,
  path: string,
  options?: ApiRequestOptions,
  request_options: JsonRequestOptions = {},
): Promise<ApiResponse<TData>> {
  const request_id = request_id_factory()
  let response: Response
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Request-Id': request_id,
  }
  if (request_options.idempotency_key) {
    headers['Idempotency-Key'] = request_options.idempotency_key
  }
  if (request_options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  try {
    response = await fetch_impl(resolve_url(base_url, path), {
      method: request_options.method ?? 'GET',
      headers,
      body: request_options.body === undefined ? undefined : JSON.stringify(request_options.body),
      signal: options?.signal,
    })
  } catch (error) {
    const aborted = options?.signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')
    throw new ApiClientError(
      aborted ? 'REQUEST_ABORTED' : 'NETWORK_ERROR',
      aborted ? '请求已取消。' : '无法连接到服务。',
      undefined,
      { request_id, status: 0, protocol_issues: [] },
    )
  }

  let payload: unknown
  try {
    payload = await parse_json_response(response)
  } catch {
    throw new ApiClientError(
      'INVALID_API_RESPONSE',
      '服务返回了无法解析的 JSON 响应。',
      undefined,
      { request_id, status: response.status, protocol_issues: [] },
    )
  }

  const diagnostics = build_diagnostics(request_id, response, payload)
  if (!response.ok) {
    const safe_error = read_safe_error(payload)
    throw new ApiClientError(
      typeof safe_error?.code === 'string' ? safe_error.code : 'HTTP_ERROR',
      typeof safe_error?.message === 'string' ? safe_error.message : '服务请求失败。',
      safe_error?.details,
      diagnostics,
    )
  }

  return { data: payload as TData, diagnostics }
}

export function create_api_v1_client(options: ApiClientOptions = {}): ApiV1Client {
  const fetch_impl = options.fetch_impl
  const request_id_factory = options.request_id_factory ?? create_request_id
  const base_url = options.base_url ?? ''

  return {
    list_services: (request_options) =>
      request_json<ServiceListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        '/api/v1/services',
        request_options,
      ),
    get_service: (service_id, request_options) =>
      request_json<ServiceResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/services/${encodeURIComponent(service_id)}`,
        request_options,
      ),
    list_service_activities: (service_id, query = {}, request_options) =>
      request_json<ServiceActivityListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query(`/api/v1/services/${encodeURIComponent(service_id)}/activities`, query),
        request_options,
      ),
    create_service_session: (service_id, request_options) =>
      request_json<SessionResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/services/${encodeURIComponent(service_id)}/sessions`,
        request_options,
        { method: 'POST' },
      ),
    list_sessions: (query = {}, request_options) =>
      request_json<SessionListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query('/api/v1/sessions', query),
        request_options,
      ),
    get_session: (session_id, request_options) =>
      request_json<SessionResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/sessions/${encodeURIComponent(session_id)}`,
        request_options,
      ),
    list_session_messages: (session_id, query = {}, request_options) =>
      request_json<MessageListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query(`/api/v1/sessions/${encodeURIComponent(session_id)}/messages`, query),
        request_options,
      ),
    list_session_runs: (session_id, query = {}, request_options) =>
      request_json<DiagnosisRunListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query(`/api/v1/sessions/${encodeURIComponent(session_id)}/runs`, query),
        request_options,
      ),
    get_run: (run_id, request_options) =>
      request_json<RunResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/runs/${encodeURIComponent(run_id)}`,
        request_options,
      ),
    list_run_events: (run_id, query = {}, request_options) =>
      request_json<RunEventListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query(`/api/v1/runs/${encodeURIComponent(run_id)}/events`, query),
        request_options,
      ),
    create_run: (session_id, payload, request_options) =>
      request_json<RunResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/sessions/${encodeURIComponent(session_id)}/runs`,
        request_options,
        {
          body: payload,
          idempotency_key: request_options.idempotency_key,
          method: 'POST',
        },
      ),
    get_run_action_proposal: (run_id, request_options) =>
      request_json<RunActionProposalResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/runs/${encodeURIComponent(run_id)}/action-proposal`,
        request_options,
      ),
    get_action_proposal: (proposal_id, request_options) =>
      request_json<ActionProposalResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/action-proposals/${encodeURIComponent(proposal_id)}`,
        request_options,
      ),
    list_action_events: (proposal_id, query = {}, request_options) =>
      request_json<ActionEventListResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        append_query(`/api/v1/action-proposals/${encodeURIComponent(proposal_id)}/events`, query),
        request_options,
      ),
    decide_action_proposal: (proposal_id, payload, request_options) =>
      request_json<ActionProposalResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/action-proposals/${encodeURIComponent(proposal_id)}/approval`,
        request_options,
        {
          body: payload,
          idempotency_key: request_options.idempotency_key,
          method: 'POST',
        },
      ),
    request_action_execution: (proposal_id, payload, request_options) =>
      request_json<ActionExecutionResponse>(
        fetch_impl ?? globalThis.fetch,
        request_id_factory,
        base_url,
        `/api/v1/action-proposals/${encodeURIComponent(proposal_id)}/executions`,
        request_options,
        {
          body: payload,
          idempotency_key: request_options.idempotency_key,
          method: 'POST',
        },
      ),
  }
}

export const api_v1_client = create_api_v1_client()
