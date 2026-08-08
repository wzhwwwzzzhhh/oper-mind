import { mutationOptions, queryOptions } from '@tanstack/react-query'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type ListSessionMessagesQuery,
  type ListSessionRunsQuery,
  type ListRunEventsQuery,
  type CreateRunOptions,
  type CreateRunRequest,
  type CreateSessionRequest,
  type CreateModelProviderRequest,
  type ActivateModelProviderRequest,
  type ProviderCreateOptions,
  type ListSessionsQuery,
  type ListServiceActivitiesQuery,
} from './client'

export const api_v1_query_keys = {
  model_config: () => ['api-v1', 'model-config'] as const,
  model_providers: () => ['api-v1', 'model-providers'] as const,
  services: () => ['api-v1', 'services'] as const,
  service: (service_id: string) => ['api-v1', 'service', service_id] as const,
  service_monitor_history: (service_id: string) => ['api-v1', 'service-monitor-history', service_id] as const,
  service_activities: (service_id: string, query: ListServiceActivitiesQuery) =>
    ['api-v1', 'service-activities', service_id, query] as const,
  sessions: (query: ListSessionsQuery) => ['api-v1', 'sessions', query] as const,
  session: (session_id: string) => ['api-v1', 'session', session_id] as const,
  session_messages: (session_id: string, query: ListSessionMessagesQuery) =>
    ['api-v1', 'session-messages', session_id, query] as const,
  session_runs: (session_id: string, query: ListSessionRunsQuery) =>
    ['api-v1', 'session-runs', session_id, query] as const,
  run: (run_id: string) => ['api-v1', 'run', run_id] as const,
  run_events: (run_id: string, query: ListRunEventsQuery) => ['api-v1', 'run-events', run_id, query] as const,
}

export function get_model_config_query() {
  return queryOptions({
    queryKey: api_v1_query_keys.model_config(),
    queryFn: ({ signal }) => api_v1_client.get_model_config({ signal }),
  })
}

export function list_services_query() {
  return queryOptions({
    queryKey: api_v1_query_keys.services(),
    queryFn: ({ signal }) => api_v1_client.list_services({ signal }),
  })
}

export function get_service_query(service_id: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.service(service_id),
    queryFn: ({ signal }) => api_v1_client.get_service(service_id, { signal }),
  })
}

export function get_service_monitor_history_query(service_id: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.service_monitor_history(service_id),
    queryFn: ({ signal }) => api_v1_client.get_service_monitor_history(service_id, {}, { signal }),
  })
}

export function list_service_activities_query(
  service_id: string,
  query: ListServiceActivitiesQuery = {},
) {
  return queryOptions({
    queryKey: api_v1_query_keys.service_activities(service_id, query),
    queryFn: ({ signal }) => api_v1_client.list_service_activities(service_id, query, { signal }),
  })
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

export interface CreateSessionMutationVariables {
  title: CreateSessionRequest['title']
  service_id?: CreateSessionRequest['service_id']
}

export function create_session_mutation() {
  return mutationOptions({
    mutationFn: ({ title, service_id }: CreateSessionMutationVariables) =>
      api_v1_client.create_session({ title, service_id }),
  })
}

export const default_session_list_query: ListSessionsQuery = {
  limit: API_V1_DEFAULT_PAGE_SIZE,
  status: 'active',
}

export function list_model_providers_query() {
  return queryOptions({
    queryKey: api_v1_query_keys.model_providers(),
    queryFn: ({ signal }) => api_v1_client.list_model_providers({ signal }),
  })
}

export interface CreateModelProviderMutationVariables {
  name: CreateModelProviderRequest['name']
  base_url: CreateModelProviderRequest['base_url']
  model: CreateModelProviderRequest['model']
  api_key: CreateModelProviderRequest['api_key']
  idempotency_key: string
}

export function create_model_provider_mutation() {
  return mutationOptions({
    mutationFn: ({
      name,
      base_url,
      model,
      api_key,
      idempotency_key,
    }: CreateModelProviderMutationVariables) =>
      api_v1_client.create_model_provider(
        { name, base_url, model, api_key },
        { idempotency_key } satisfies ProviderCreateOptions,
      ),
  })
}

export interface UpdateModelProviderMutationVariables {
  provider_id: string
  name: CreateModelProviderRequest['name']
  base_url: CreateModelProviderRequest['base_url']
  model: CreateModelProviderRequest['model']
  api_key: CreateModelProviderRequest['api_key']
}

export function update_model_provider_mutation() {
  return mutationOptions({
    mutationFn: ({ provider_id, name, base_url, model, api_key }: UpdateModelProviderMutationVariables) =>
      api_v1_client.update_model_provider(provider_id, { name, base_url, model, api_key }),
  })
}

export interface ActivateModelProviderMutationVariables {
  provider_id: string
  endpoint: ActivateModelProviderRequest['endpoint']
}

export function activate_model_provider_mutation() {
  return mutationOptions({
    mutationFn: ({ provider_id, endpoint }: ActivateModelProviderMutationVariables) =>
      api_v1_client.activate_model_provider(provider_id, { endpoint }),
  })
}

export function verify_model_provider_mutation() {
  return mutationOptions({
    mutationFn: (provider_id: string) => api_v1_client.verify_model_provider(provider_id),
  })
}

export function delete_model_provider_mutation() {
  return mutationOptions({
    mutationFn: (provider_id: string) => api_v1_client.delete_model_provider(provider_id),
  })
}
