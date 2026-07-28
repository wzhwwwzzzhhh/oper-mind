import { mutationOptions, queryOptions } from '@tanstack/react-query'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type ListSessionMessagesQuery,
  type ListSessionRunsQuery,
  type ListRunEventsQuery,
  type CreateRunOptions,
  type CreateRunRequest,
  type ListSessionsQuery,
} from './client'

export const api_v1_query_keys = {
  sessions: (query: ListSessionsQuery) => ['api-v1', 'sessions', query] as const,
  session: (session_id: string) => ['api-v1', 'session', session_id] as const,
  session_messages: (session_id: string, query: ListSessionMessagesQuery) =>
    ['api-v1', 'session-messages', session_id, query] as const,
  session_runs: (session_id: string, query: ListSessionRunsQuery) =>
    ['api-v1', 'session-runs', session_id, query] as const,
  run: (run_id: string) => ['api-v1', 'run', run_id] as const,
  run_events: (run_id: string, query: ListRunEventsQuery) => ['api-v1', 'run-events', run_id, query] as const,
}

export function list_sessions_query(query: ListSessionsQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.sessions(query),
    queryFn: ({ signal }) => api_v1_client.list_sessions(query, { signal }),
  })
}

export function get_session_query(session_id: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.session(session_id),
    queryFn: ({ signal }) => api_v1_client.get_session(session_id, { signal }),
  })
}

export function list_session_messages_query(
  session_id: string,
  query: ListSessionMessagesQuery = {},
) {
  return queryOptions({
    queryKey: api_v1_query_keys.session_messages(session_id, query),
    queryFn: ({ signal }) => api_v1_client.list_session_messages(session_id, query, { signal }),
  })
}

export function list_session_runs_query(session_id: string, query: ListSessionRunsQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.session_runs(session_id, query),
    queryFn: ({ signal }) => api_v1_client.list_session_runs(session_id, query, { signal }),
  })
}

export function get_run_query(run_id: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.run(run_id),
    queryFn: ({ signal }) => api_v1_client.get_run(run_id, { signal }),
  })
}


export function list_run_events_query(run_id: string, query: ListRunEventsQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.run_events(run_id, query),
    queryFn: ({ signal }) => api_v1_client.list_run_events(run_id, query, { signal }),
  })
}


export interface CreateRunMutationVariables {
  idempotency_key: string
  query: CreateRunRequest['query']
  session_id: string
}

export function create_run_mutation() {
  return mutationOptions({
    mutationFn: ({ session_id, query, idempotency_key }: CreateRunMutationVariables) =>
      api_v1_client.create_run(
        session_id,
        { query },
        { idempotency_key } satisfies CreateRunOptions,
      ),
  })
}

export const default_session_list_query: ListSessionsQuery = {
  limit: API_V1_DEFAULT_PAGE_SIZE,
  status: 'active',
}
