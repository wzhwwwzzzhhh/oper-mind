import { mutationOptions, queryOptions } from '@tanstack/react-query'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type GetModelUsageQuery,
  type ListActionProposalsQuery,
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
  type ListRunsQuery,
  type ListServiceActivitiesQuery,
  type ListAuditActivitiesQuery,
  type CreateServiceRequest,
  type UpdateServiceRequest,
  type SendPlainMessageRequest,
} from './client'

export const api_v1_query_keys = {
  model_config: () => ['api-v1', 'model-config'] as const,
  model_providers: () => ['api-v1', 'model-providers'] as const,
  model_usage: (query: GetModelUsageQuery = {}) => ['api-v1', 'model-usage', query] as const,
  services: () => ['api-v1', 'services'] as const,
  service: (service_id: string) => ['api-v1', 'service', service_id] as const,
  monitor_overview: () => ['api-v1', 'monitor-overview'] as const,
  service_monitor_history: (service_id: string) => ['api-v1', 'service-monitor-history', service_id] as const,
  service_activities: (service_id: string, query: ListServiceActivitiesQuery) =>
    ['api-v1', 'service-activities', service_id, query] as const,
  audit_activities: (query: ListAuditActivitiesQuery) =>
    ['api-v1', 'audit-activities', query] as const,
  sessions: (query: ListSessionsQuery) => ['api-v1', 'sessions', query] as const,
  session: (session_id: string) => ['api-v1', 'session', session_id] as const,
  session_messages: (session_id: string, query: ListSessionMessagesQuery) =>
    ['api-v1', 'session-messages', session_id, query] as const,
  session_runs: (session_id: string, query: ListSessionRunsQuery) =>
    ['api-v1', 'session-runs', session_id, query] as const,
  runs: (query: ListRunsQuery) => ['api-v1', 'runs', query] as const,
  run: (run_id: string) => ['api-v1', 'run', run_id] as const,
  run_events: (run_id: string, query: ListRunEventsQuery) => ['api-v1', 'run-events', run_id, query] as const,
  action_proposals: (query: ListActionProposalsQuery) => ['api-v1', 'action-proposals', query] as const,
  action_proposal: (proposal_id: string) => ['api-v1', 'action-proposal', proposal_id] as const,
  knowledge_documents: (limit: number) => ['api-v1', 'knowledge-documents', limit] as const,
  knowledge_search: (query: string) => ['api-v1', 'knowledge-search', query] as const,
  knowledge_document: (document_path: string) => ['api-v1', 'knowledge-document', document_path] as const,
}

export function get_model_config_query() {
  return queryOptions({
    queryKey: api_v1_query_keys.model_config(),
    queryFn: ({ signal }) => api_v1_client.get_model_config({ signal }),
  })
}

export interface UpdateModelModeMutationVariables {
  mode: 'mock' | 'real'
}

export function update_model_mode_mutation() {
  return mutationOptions({
    mutationFn: ({ mode }: UpdateModelModeMutationVariables) => api_v1_client.update_model_mode({ mode }),
  })
}

export interface UpdateModelParamsMutationVariables {
  temperature: number | null
  max_tokens: number | null
}

export function update_model_params_mutation() {
  return mutationOptions({
    mutationFn: ({ temperature, max_tokens }: UpdateModelParamsMutationVariables) =>
      api_v1_client.update_model_params({ temperature, max_tokens }),
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

export function get_monitor_overview_query() {
  return queryOptions({
    queryKey: api_v1_query_keys.monitor_overview(),
    queryFn: ({ signal }) => api_v1_client.get_monitor_overview({ signal }),
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


export function list_audit_activities_query(query: ListAuditActivitiesQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.audit_activities(query),
    queryFn: ({ signal }) => api_v1_client.list_audit_activities(query, { signal }),
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

export function list_runs_query(query: ListRunsQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.runs(query),
    queryFn: ({ signal }) => api_v1_client.list_runs(query, { signal }),
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

export function list_action_proposals_query(query: ListActionProposalsQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.action_proposals(query),
    queryFn: ({ signal }) => api_v1_client.list_action_proposals(query, { signal }),
  })
}

export function get_action_proposal_query(proposal_id: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.action_proposal(proposal_id),
    queryFn: ({ signal }) => api_v1_client.get_action_proposal(proposal_id, { signal }),
  })
}

export interface SendPlainMessageMutationVariables {
  content: SendPlainMessageRequest['content']
  session_id: string
}

export function send_plain_message_mutation() {
  return mutationOptions({
    mutationFn: ({ session_id, content }: SendPlainMessageMutationVariables) =>
      api_v1_client.send_plain_message(session_id, { content }),
  })
}

export function cancel_run_mutation() {
  return mutationOptions({
    mutationFn: (run_id: string) => api_v1_client.cancel_run(run_id),
  })
}


export interface RerunRunMutationVariables {
  idempotency_key: string
  run_id: string
}

export function rerun_run_mutation() {
  return mutationOptions({
    mutationFn: ({ run_id, idempotency_key }: RerunRunMutationVariables) =>
      api_v1_client.rerun_run(run_id, { idempotency_key } satisfies CreateRunOptions),
  })
}


export interface CreateRunMutationVariables {
  idempotency_key: string
  query: CreateRunRequest['query']
  service_id?: CreateRunRequest['service_id']
  session_id: string
}

export function create_run_mutation() {
  return mutationOptions({
    mutationFn: ({ session_id, query, service_id, idempotency_key }: CreateRunMutationVariables) =>
      api_v1_client.create_run(
        session_id,
        { query, service_id },
        { idempotency_key } satisfies CreateRunOptions,
      ),
  })
}

export interface CreateSessionMutationVariables {
  title: CreateSessionRequest['title']
  service_id?: CreateSessionRequest['service_id']
  service_ids?: CreateSessionRequest['service_ids']
}

export function create_session_mutation() {
  return mutationOptions({
    mutationFn: ({ title, service_id, service_ids }: CreateSessionMutationVariables) =>
      api_v1_client.create_session({ title, service_id, service_ids }),
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

export function get_model_usage_query(query: GetModelUsageQuery = {}) {
  return queryOptions({
    queryKey: api_v1_query_keys.model_usage(query),
    queryFn: ({ signal }) => api_v1_client.get_model_usage(query, { signal }),
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

export function list_provider_models_mutation() {
  return mutationOptions({
    mutationFn: (provider_id: string) => api_v1_client.list_model_provider_models(provider_id),
  })
}

export function delete_model_provider_mutation() {
  return mutationOptions({
    mutationFn: (provider_id: string) => api_v1_client.delete_model_provider(provider_id),
  })
}

export interface CreateServiceMutationVariables {
  kind: CreateServiceRequest['kind']
  instance_id: CreateServiceRequest['instance_id']
  title: CreateServiceRequest['title']
  dsn: CreateServiceRequest['dsn']
}

export function create_service_mutation() {
  return mutationOptions({
    mutationFn: ({ kind, instance_id, title, dsn }: CreateServiceMutationVariables) =>
      api_v1_client.register_service({ kind, instance_id, title, dsn }),
  })
}

export interface UpdateServiceMutationVariables {
  service_id: string
  title: UpdateServiceRequest['title']
  dsn?: UpdateServiceRequest['dsn']
}

export function update_service_mutation() {
  return mutationOptions({
    mutationFn: ({ service_id, title, dsn }: UpdateServiceMutationVariables) =>
      api_v1_client.update_service(service_id, { title, dsn }),
  })
}

export function delete_service_mutation() {
  return mutationOptions({
    mutationFn: (service_id: string) => api_v1_client.delete_service(service_id),
  })
}

export function test_service_connection_mutation() {
  return mutationOptions({
    mutationFn: (service_id: string) => api_v1_client.test_service_connection(service_id),
  })
}

export function search_knowledge_query(query: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.knowledge_search(query),
    queryFn: ({ signal }) => api_v1_client.search_knowledge(query, 5, { signal }),
  })
}

export function get_knowledge_document_query(document_path: string) {
  return queryOptions({
    queryKey: api_v1_query_keys.knowledge_document(document_path),
    queryFn: ({ signal }) => api_v1_client.get_knowledge_document(document_path, { signal }),
  })
}
