export type ApiEnvelope<T> = {
  status: 'ok' | 'error'
  data: T | null
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  } | null
  meta?: {
    trace_id?: string | null
    project_key?: string | null
    pagination?: {
      page: number
      page_size: number
      total: number
      total_pages: number
    } | null
  }
}

export type HealthResponse = {
  status: string
  provider: string
  env: string
  runtime_mode?: RuntimeMode
  services?: Record<string, RuntimeServiceStatus>
  health_url?: string
  port_hints?: Record<string, number | string>
  missing_dependencies?: string[]
}

export type DeepHealthResponse = {
  status: string
  database?: string
  elasticsearch?: string
}

export type RuntimeMode = 'docker' | 'local' | 'mixed' | 'unknown'

export type RuntimeServiceStatus = {
  status?: string
  mode?: RuntimeMode
  provider?: string
  host?: string | null
  health_url?: string | null
  port_hint?: number | string | null
  missing_dependencies?: string[]
}

export type BusinessLineEvidenceMatrixLine = {
  line_key: string
  entrypoints?: unknown[]
  api_groups?: unknown[]
  current_gaps?: string[] | string | null
  next_remediation?: string[] | string | null
  verification_commands?: string[] | string | null
  [key: string]: unknown
}

export type BusinessLineScheduledMatrixDiagnostics = {
  source_lane?: string | null
  source_artifact?: string | null
  consumer_surface?: string | null
  recommended_display_order?: string[] | string | null
  required_fields?: string[] | string | null
  blocked_project_fields?: string[] | string | null
  classification_boundary?: string | Record<string, unknown> | null
  [key: string]: unknown
}

export type BusinessLineEvidenceMatrix = {
  contract_version: 'business_line.evidence_matrix.v1' | string
  lines: BusinessLineEvidenceMatrixLine[]
  batch_orchestration?: Record<string, unknown> | null
  matrix_diagnostics_guidance?: BusinessLineScheduledMatrixDiagnostics | null
  scheduled_matrix_diagnostics?: BusinessLineScheduledMatrixDiagnostics | null
  generated_at?: string | null
  [key: string]: unknown
}

export type BusinessLineScheduledMatrixArtifactDiagnostics = {
  runtime_preflight_status?: string | number | boolean | null
  matrix_exit_code?: string | number | boolean | null
  first_blocked_reason?: string | number | boolean | null
  [key: string]: unknown
}

export type BusinessLineScheduledMatrixArtifactSummary = {
  contract_version?: string | null
  source_checker?: string | null
  lane?: string | null
  status?: 'passed' | 'blocked' | 'checker_unavailable' | string | null
  lane_classification?: 'scheduled_run_evidence' | 'scheduled_run_blocked' | 'manual_dry_run' | 'missing' | 'checker_unavailable' | string | null
  reason?: string | null
  artifact_path?: string | null
  diagnostics?: BusinessLineScheduledMatrixArtifactDiagnostics | null
  summary?: Record<string, unknown> | string | null
  observed_at?: string | null
  recommended_command?: string | null
  completion_boundary?: Record<string, unknown> | string | null
  [key: string]: unknown
}

export type BusinessLineScheduledArtifactLaneSummary = {
  lane?: string | null
  status?: 'passed' | 'blocked' | string | null
  lane_classification?: 'scheduled_run_evidence' | 'scheduled_run_blocked' | 'manual_dry_run' | 'missing' | string | null
  reason?: string | null
  artifact_path?: string | null
  diagnostics?: BusinessLineScheduledMatrixArtifactDiagnostics | Record<string, unknown> | null
  observed_at?: string | null
  recommended_command?: string | null
  [key: string]: unknown
}

export type BusinessLineScheduledArtifactDrilldownArtifact = {
  artifact_path?: string | null
  classification?: 'scheduled_run_evidence' | 'scheduled_run_blocked' | 'manual_dry_run' | 'missing' | string | null
  scheduled_completion_proof?: boolean | null
  reason?: string | null
  freshness_rank?: number | null
  freshness_window_size?: number | null
  is_latest_for_lane?: boolean | null
  identity_matches_latest?: boolean | null
  identity_status?: string | null
  identity_warning?: string | null
  identity_warning_severity?: string | null
  identity_warning_message?: string | null
  latest_artifact_path?: string | null
  size_bytes?: number | null
  sha256?: string | null
  mtime?: string | number | null
  observed_at?: string | null
}

export type BusinessLineScheduledArtifactDrilldownLane = {
  lane?: string | null
  status?: 'passed' | 'blocked' | string | null
  lane_classification?: 'scheduled_run_evidence' | 'scheduled_run_blocked' | 'manual_dry_run' | 'missing' | string | null
  scheduled_completion_proof?: boolean | null
  reason?: string | null
  artifact_path?: string | null
  base_dir?: string | null
  artifact_count?: number | null
  identity_warning_count?: number | null
  identity_warning_types?: string[] | null
  identity_warning_severity_counts?: Record<string, number> | null
  identity_warning_severity_order?: string[] | null
  identity_warning_highest_severity?: string | null
  identity_warning_highest_severity_rank?: number | null
  identity_status_counts?: Record<string, number> | null
  artifacts?: BusinessLineScheduledArtifactDrilldownArtifact[] | null
  diagnostics?: BusinessLineScheduledMatrixArtifactDiagnostics | Record<string, unknown> | null
  recommended_command?: string | null
}

export type BusinessLineScheduledArtifactDrilldown = {
  contract_version?: string | null
  source_checker?: string | null
  status?: 'passed' | 'blocked' | 'checker_unavailable' | string | null
  observed_at?: string | null
  summary?: Record<string, unknown> | string | null
  lanes?: BusinessLineScheduledArtifactDrilldownLane[] | null
  completion_boundary?: Record<string, unknown> | string | null
  recommended_command?: string | null
}

export type BusinessLineScheduledArtifactSummaries = {
  contract_version?: string | null
  source_checker?: string | null
  status?: 'passed' | 'blocked' | 'checker_unavailable' | string | null
  summary?: Record<string, unknown> | string | null
  lanes?: BusinessLineScheduledArtifactLaneSummary[] | null
  observed_at?: string | null
  recommended_command?: string | null
  whitelisted_lanes?: string[] | string | null
  completion_boundary?: Record<string, unknown> | string | null
  [key: string]: unknown
}

export type ProjectItem = {
  id?: number
  project_key: string
  name?: string
  schema_name?: string
  enabled?: boolean
  is_active?: boolean
}

export type CrawlerProjectItem = {
  id?: number
  project_key: string
  name?: string
  description?: string | null
  source_type?: string
  source_uri?: string | null
  provider?: string
  status?: string
  current_version?: string | null
  deployed_version?: string | null
  previous_version?: string | null
  import_payload?: Record<string, unknown> | null
  analysis_plan?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type CrawlerDeployRunItem = {
  id?: number
  crawler_project_id?: number
  crawler_project_key?: string
  action?: 'deploy' | 'rollback' | string
  status?: string
  requested_version?: string | null
  from_version?: string | null
  to_version?: string | null
  planner_mode?: string
  plan?: Record<string, unknown> | null
  external_provider?: string | null
  external_job_id?: string | null
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
}

export type CrawlerProjectImportPayload = {
  project_key?: string | null
  name?: string | null
  repo_url: string
  branch?: string | null
  provider_hint?: string | null
  description?: string | null
  enable_now?: boolean
}

export type CrawlerProjectDeployPayload = {
  requested_version?: string | null
  planner_mode?: string | null
  async_mode?: boolean
}

export type CrawlerProjectRollbackPayload = {
  to_version?: string | null
  planner_mode?: string | null
  async_mode?: boolean
}

export type AutoCreateProjectPayload = {
  project_name: string
  project_key?: string | null
  template_project_key?: string
  activate?: boolean
  copy_initial_data?: boolean
  llm_configs?: Array<{
    service_name: string
    user_prompt_template?: string
    description?: string
    system_prompt?: string
    model?: string
    temperature?: number
    max_tokens?: number
    top_p?: number
    presence_penalty?: number
    frequency_penalty?: number
    enabled?: boolean
  }>
}

export type InjectInitialProjectPayload = {
  project_key?: string | null
  name?: string | null
  source_project_key?: string
  overwrite?: boolean
  activate?: boolean
}

export type InjectInitialProjectResult = {
  project_key: string
  name?: string
  schema_name?: string
  source_project_key?: string
  activated?: boolean
  copied_counts?: Record<string, number>
}

export type AutoCreateProjectResult = {
  project_key: string
  name?: string
  schema_name?: string
  activated?: boolean
  template_project_key?: string
  created_mode?: 'inject_initial' | 'create_empty'
  llm_configs_applied?: number
}

export type EnvSettings = Record<string, string>

export type SourceLibraryScope = 'effective' | 'shared' | 'project'

export type SourceLibraryCapabilitySummary =
  | string
  | {
      capability_id?: string | null
      name?: string | null
      summary?: string | null
      execution_mode?: string | null
      source_mode?: string | null
      entry_type?: string | null
      runner_ref?: string | null
      enabled?: boolean | null
      status?: string | null
      [key: string]: unknown
    }

export type SourceLibraryItem = {
  id?: number
  item_key: string
  name?: string
  channel_key?: string
  description?: string | null
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string | null
  extends_item_key?: string | null
  enabled?: boolean
  extra?: Record<string, unknown>
  project_key?: string | null
  scope?: SourceLibraryScope
  execution_plan?: Record<string, unknown>
  item_type?: string
  managed_by?: string
  capability?: SourceLibraryCapabilitySummary | null
  capability_summary?: SourceLibraryCapabilitySummary | null
}

export type SourceLibraryChannel = {
  channel_key: string
  name?: string
  provider?: string
  kind?: string
  description?: string | null
  enabled?: boolean
  params_schema?: Record<string, unknown>
  extra?: Record<string, unknown>
}

export type SourceLibraryItemsGroupedResponse = {
  by_handler?: Record<string, SourceLibraryItem[]>
  scope?: SourceLibraryScope
  project_key?: string | null
}

export type SourceLibraryItemUpsertPayload = {
  item_key: string
  name: string
  channel_key: string
  description?: string
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string
  extends_item_key?: string
  enabled?: boolean
  extra?: Record<string, unknown>
}

export type SourceLibraryItemRefreshPayload = {
  incremental?: boolean
  max_site_entries?: number
}

export type ExternalProjectRegistrationPayload = {
  project_link: string
  item_key?: string
  name?: string
  description?: string
  tags?: string[]
  enabled?: boolean
  persist?: boolean
  hints?: Record<string, unknown>
}

export type ExternalProjectRegistrationResponse = {
  ok?: boolean
  persisted?: boolean
  project_key?: string
  item?: SourceLibraryItem
  registration_context?: {
    source?: string
    project_link?: string
    preferred_execution_modes?: string[]
    endpoint_candidates?: Array<{
      execution_mode?: string
      runner_ref?: string
      reason?: string
      confidence?: string
    }>
    evidence?: Array<Record<string, unknown>>
  }
}

export type SourceLibraryHandlerSyncPayload = {
  handlers?: string[]
  incremental?: boolean
  max_site_entries?: number
}

export type SourceLibraryHandlerSyncResult = {
  handler_key?: string
  item_key?: string
  expected_entry_type?: string
  incremental?: boolean
  domains?: string[]
  site_entry_tags?: string[]
  site_entries_before?: number
  site_entries_after?: number
  added?: number
}

export type SourceLibraryHandlerSyncResponse = {
  ok?: boolean
  project_key?: string
  handler_count?: number
  results?: SourceLibraryHandlerSyncResult[]
}

export type SiteEntryGroupedResponse = {
  by_entry_type?: Record<string, { count?: number; sample_urls?: string[] }>
}

export type IngestJobRow = {
  id?: string | number
  submission_id?: string | null
  idempotency_key?: string | null
  submission_status?: string | null
  task_id?: string
  task_name?: string
  job_type?: string
  status?: string
  source?: string | null
  submission_source?: string | null
  feedback_state?: string | Record<string, unknown> | null
  trace_id?: string | null
  trace_chain?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
  started_at?: string
  finished_at?: string
  rejected_count?: number | null
  rejection_breakdown?: Record<string, number> | null
  degradation_flags?: string[] | null
  quality_score?: number | null
  error?: string | null
  params?: Record<string, unknown> | null
}

export type AgentBatchItemSubmitPayload = {
  item_id?: string | null
  source_id?: string | null
  item_key?: string | null
  channel?: string | null
  query_terms?: string[]
  max_items?: number | null
  provider?: string | null
  language?: string | null
  days_back?: number | null
  contract_version?: string
  input?: Record<string, unknown> | string | null
  override_params?: Record<string, unknown>
}

export type AgentBatchSubmitPayload = {
  project_key?: string | null
  idempotency_key?: string | null
  priority?: number | null
  rule_set_id?: string | null
  rule_set?: Record<string, unknown>
  batch: {
    jobs: AgentBatchItemSubmitPayload[]
  }
}

export type AgentBatchSubmitResult = {
  job_id: string
  status: string
  accepted_count: number
  rejected_count: number
  accepted_job_items: Array<{
    index: number
    item_id: string
    task_id: string
    channel?: string
    item_key?: string
    query_terms?: string[]
    contract_version?: string
  }>
  rejected_job_items: Array<{
    index: number
    reason_code?: string
    reason?: string
    details?: Record<string, unknown>
  }>
  created_at?: string
  links?: Record<string, string>
  idempotency_reused?: boolean
  rule_set_id?: string | null
}

export type AgentBatchJobDetail = {
  job_id: string
  status: string
  phase?: string
  progress?: {
    total?: number
    succeeded?: number
    failed?: number
    running?: number
    queued?: number
  }
  started_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  retry_count?: number
  error?: string | null
  meta?: Record<string, unknown>
}

export type AgentBatchItemRow = {
  item_id: string
  task_id: string
  status?: string
  input?: Record<string, unknown>
  output?: unknown
  error?: unknown
  last_update_at?: string
}

export type AgentBatchItemsResult = {
  items: AgentBatchItemRow[]
  pagination?: {
    next_cursor?: string | null
    has_more?: boolean
  }
}

export type AgentBatchRetryPayload = {
  scope?: string
  item_ids?: string[]
  reason?: string | null
  max_retries?: number | null
}

export type AgentBatchRetryResult = {
  job_id: string
  retry_session_id: string
  status: string
  retry_count: number
  targets: string[]
}

export type AgentBatchEventRow = {
  id: string
  event_type: string
  ts: string
  item_id: string
  severity?: string
  message?: string
  payload?: Record<string, unknown>
}

export type AgentBatchEventsResult = {
  events: AgentBatchEventRow[]
  pagination?: {
    next_cursor?: string | null
    has_more?: boolean
  }
}

export type AgentBatchRuleSetValidatePayload = {
  rule_set_id?: string | null
  rule_set: Record<string, unknown>
  batch_schema_version?: string | null
  sample_items?: Array<Record<string, unknown>>
}

export type AgentBatchRuleSetValidateResult = {
  valid: boolean
  errors: Array<{ code: string; message: string }>
  warnings: Array<{ code: string; message: string }>
  normalized_rule_set?: Record<string, unknown>
  unsupported_fields?: string[]
}

export type AgentBatchNlCommandPayload = {
  command: string
  project_key?: string | null
  idempotency_key?: string | null
}

export type AgentBatchNlCommandResult = {
  command: string
  parsed?: Record<string, unknown>
  submit?: AgentBatchSubmitResult
  session_id?: string | null
  root_task_id?: string | null
  current_phase?: string | null
  compat_mode?: boolean | null
  compat_projection_version?: string | null
  session?: AgentSessionItem | null
}

export type AgentChatTurnPayload = {
  message: string
  project_key?: string | null
  session_id?: string | null
  idempotency_key?: string | null
  dry_run?: boolean | null
  enable_bounded_retry?: boolean | null
  enable_limited_branching?: boolean | null
  enable_model_tool_loop?: boolean | null
  require_high_risk_approval?: boolean | null
  runtime_variant?: 'agent_runtime_v2' | 'legacy_batch' | 'legacy' | 'v2' | string | null
  model?: string | null
  reasoning_effort?: string | null
}

export type CodexModelOption = {
  model: string
  display_name: string
  is_default: boolean
  supported_reasoning_efforts: string[]
}

export type CodexModelCatalog = {
  provider?: string | null
  current_model?: string | null
  current_reasoning_effort?: string | null
  items: CodexModelOption[]
}

export type AgentChatCapabilityCall = {
  call_id?: string | null
  capability_id?: string | null
  tool_name?: string | null
  protocol?: string | null
  stream_state?: string | null
  status?: string | null
  summary?: string | null
  approval_id?: string | null
  run_id?: string | null
  job_id?: string | null
  accepted_count?: number | null
  rejected_count?: number | null
  loop_id?: string | null
  result?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
  material_category?: {
    category?: string | null
    label?: string | null
  } | null
}

export type AgentChatCapabilityItem = {
  capability_id?: string | null
  name?: string | null
  description?: string | null
  domain?: string | null
  approval_level?: string | null
  concurrency_class?: string | null
  call_pattern?: string | null
  risk_level?: string | null
  tool_group?: string | null
  deferred?: boolean | null
  implemented?: boolean | null
  implementation_state?: string | null
  enabled?: boolean | null
  disabled_reason?: string | null
  configured?: boolean | null
  reachable?: boolean | null
  auth_ok?: boolean | null
  server_error?: string | null
  service_status?: string | null
  mounted_tool_count?: number | null
  mounted_tools?: string[] | null
  risks?: string[] | null
  required_input?: string[] | null
}

export type AgentChatToolPool = {
  tools?: AgentChatCapabilityItem[] | null
  groups?: Record<string, AgentChatCapabilityItem[] | null | undefined> | null
  counts?: Record<string, number> | null
  feature_flags?: Record<string, boolean> | null
  project_key?: string | null
  agent_mode?: string | null
}

export type AgentChatCapabilitiesResult = {
  items?: AgentChatCapabilityItem[] | null
  feature_flags?: Record<string, boolean> | null
  tool_pool?: AgentChatToolPool | null
}

export type AgentChatTurnResult = {
  contract_version?: string | null
  turn?: Record<string, unknown> | null
  session?: AgentSessionItem | null
  tasks?: AgentTaskItem[] | null
  messages?: AgentMessageItem[] | null
  events?: AgentEventItem[] | null
  artifacts?: AgentArtifactItem[] | null
  approvals?: AgentApprovalItem[] | null
  agent_mode?: string | null
  plan?: Record<string, unknown> | null
  capability_calls?: AgentChatCapabilityCall[] | null
  suggested_next_actions?: string[] | null
  loop_result?: AgentBatchNlCommandResult | Record<string, unknown> | null
  run_loop?: Record<string, unknown> | null
  approval_requests?: Record<string, unknown>[] | null
  stream?: {
    protocol_version?: string | null
    session_id?: string | null
    url?: string | null
    since_seq?: number | null
    event_format?: string | null
  } | null
  final_answer?: string | null
}

export type AgentChatApprovalContinuePayload = {
  approved_by?: string | null
  binding_payload_overrides?: Record<string, unknown> | null
}

export type AgentChatApprovalContinueResult = {
  contract_version?: string | null
  approval?: AgentApprovalItem | Record<string, unknown> | null
  session?: AgentSessionItem | null
  tasks?: AgentTaskItem[] | null
  messages?: AgentMessageItem[] | null
  events?: AgentEventItem[] | null
  artifacts?: AgentArtifactItem[] | null
  approvals?: AgentApprovalItem[] | null
  capability_call?: AgentChatCapabilityCall | Record<string, unknown> | null
  continued?: boolean | null
  stream?: Record<string, unknown> | null
  final_answer?: string | null
}

export type AgentSessionStatus = 'pending' | 'active' | 'blocked' | 'completed' | 'failed' | 'canceled' | string

export type AgentTaskStatus = 'pending' | 'claimed' | 'in_progress' | 'blocked' | 'completed' | 'failed' | 'canceled' | 'expired' | string

export type AgentTaskProgressSummary = {
  tool_use_count?: number | null
  token_usage?: number | null
  last_activity?: string | null
  recent_activities?: string[] | null
  summary_label?: string | null
  started_at?: string | null
  updated_at?: string | null
}

export type AgentSessionItem = {
  session_id: string
  project_key?: string | null
  source?: string | null
  goal?: string | null
  title?: string | null
  status?: AgentSessionStatus
  current_phase?: string | null
  compat_mode?: boolean | null
  compat_projection_version?: string | null
  root_task_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  task_count?: number | null
  event_count?: number | null
  artifact_count?: number | null
  metadata?: Record<string, unknown> | null
  progress?: AgentTaskProgressSummary | null
}

export type AgentTaskItem = {
  task_id: string
  session_id?: string | null
  parent_task_id?: string | null
  task_type?: string | null
  phase?: string | null
  subject?: string | null
  description?: string | null
  status?: AgentTaskStatus
  owner?: string | null
  blocked_by?: string[] | null
  blocks?: string[] | null
  priority?: number | null
  write_set?: string[] | null
  read_set?: string[] | null
  lease_until?: string | null
  result_summary?: string | null
  metadata?: Record<string, unknown> | null
  progress?: AgentTaskProgressSummary | null
  created_at?: string | null
  updated_at?: string | null
}

export type AgentEventItem = {
  event_id: string
  session_id?: string | null
  turn_id?: string | null
  call_id?: string | null
  seq?: number | null
  task_id?: string | null
  event_type?: string | null
  ts?: string | null
  severity?: string | null
  message?: string | null
  payload?: Record<string, unknown> | null
}

export type AgentSessionEventStreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

export type AgentArtifactItem = {
  artifact_id: string
  session_id?: string | null
  task_id?: string | null
  artifact_type?: string | null
  name?: string | null
  path?: string | null
  status?: string | null
  summary?: string | null
  content?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type AgentMessageItem = {
  session_id: string
  task_id?: string | null
  role?: string | null
  actor?: string | null
  content?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string | null
}

export type AgentApprovalItem = {
  approval_id: string
  session_id?: string | null
  task_id?: string | null
  requester_session_id?: string | null
  requester_task_id?: string | null
  requester_actor?: string | null
  binding_hash?: string | null
  status?: string | null
  requested_by?: string | null
  approved_by?: string | null
  approved_at?: string | null
  expires_at?: string | null
  audit_log?: string[] | null
  binding_payload?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
}

export type AgentSessionDetail = AgentSessionItem & {
  tasks?: AgentTaskItem[] | null
  messages?: AgentMessageItem[] | null
  events?: AgentEventItem[] | null
  artifacts?: AgentArtifactItem[] | null
  approvals?: AgentApprovalItem[] | null
}

export type AgentSessionListResult = {
  sessions: AgentSessionItem[]
}

export type AgentTaskListResult = {
  tasks: AgentTaskItem[]
}

export type AgentEventListResult = {
  events: AgentEventItem[]
}

export type AgentArtifactListResult = {
  artifacts: AgentArtifactItem[]
}

export type AgentMessageListResult = {
  messages: AgentMessageItem[]
}

export type AgentSessionCreatePayload = {
  project_key?: string | null
  source?: string | null
  goal: string
  entrypoint_type?: string | null
  initial_context?: Record<string, unknown> | null
  compat_mode?: boolean | null
}

export type AgentSessionTaskRetryPayload = {
  task_id: string
  reason?: string | null
}

export type AgentSessionCancelPayload = {
  reason?: string | null
}

export type AgentSessionMessageCreatePayload = {
  role?: string | null
  actor?: string | null
  task_id?: string | null
  content: string
  metadata?: Record<string, unknown> | null
}

export type AgentApprovalRequestPayload = {
  task_id: string
  requester_actor?: string | null
  binding_payload?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
}

export type AgentCoordinatorPassResult = {
  session?: AgentSessionItem | null
  decisions?: Record<string, unknown>[] | null
  messages?: AgentMessageItem[] | null
}

export type SkillInvokeMeta = {
  trace_id?: string | null
  consumer?: string | null
  actor_role?: string | null
  permissions?: string[] | null
  owner?: string | null
  execution_profile?: string | null
  concurrency_class?: 'read_only' | 'write_shared' | 'write_external' | 'privileged' | string | null
  approval_policy?: Record<string, unknown> | null
  artifact_contract?: Record<string, unknown> | null
  approval_request?: Record<string, unknown> | null
}

export type SkillInvokeResult = {
  skill_id: string
  result?: unknown
  skill_meta?: SkillInvokeMeta | null
}

export type AgentApprovalResolvePayload = {
  approved: boolean
  reason?: string | null
}

export type ProcessTaskItem = {
  task_id: string
  name: string
  status: string
  worker?: string | null
  started_at?: string | null
  updated_at?: string | null
  source?: string | null
  args?: unknown[]
  kwargs?: Record<string, unknown>
  progress?: Record<string, unknown> | null
  traceback?: string | null
  display_meta?: ProcessTaskMeta | null
}

export type ProcessTaskList = {
  tasks: ProcessTaskItem[]
  stats: {
    total_tasks?: number
    active_tasks?: number
    pending_tasks?: number
    workers?: number
  }
}

export type ProcessTaskStats = {
  active_tasks?: number
  scheduled_tasks?: number
  reserved_tasks?: number
  total_running?: number
  workers?: number
  worker_names?: string[]
}

export type ProcessHistoryResponse = {
  history?: Array<{
    id: number
    task_id?: string | null
    task_name?: string | null
    job_type?: string
    status?: string
    params?: Record<string, unknown>
    started_at?: string
    finished_at?: string
    duration_seconds?: number | null
    error?: string | null
    source?: string | null
    worker?: string | null
    display_meta?: ProcessTaskMeta | null
    inserted_valid?: number | null
    rejected_count?: number | null
    rejection_breakdown?: Record<string, number> | null
  }>
  total?: number
  status_stats?: Record<string, number>
}

export type DashboardStats = {
  documents?: {
    total?: number
    recent_today?: number
    recent_7d?: number
    extraction_rate?: number
    type_distribution?: Record<string, number>
    source_query?: DashboardStatsSourceQuery
    source_refs?: DashboardStatsSourceRef[]
  }
  sources?: {
    total?: number
    enabled?: number
    source_query?: DashboardStatsSourceQuery
    source_refs?: DashboardStatsSourceRef[]
  }
  market_stats?: {
    total?: number
    states_count?: number
    source_query?: DashboardStatsSourceQuery
    source_refs?: DashboardStatsSourceRef[]
  }
  search_history?: {
    total?: number
    source_query?: DashboardStatsSourceQuery
    source_refs?: DashboardStatsSourceRef[]
  }
  tasks?: {
    total?: number
    running?: number
    completed?: number
    failed?: number
    source_query?: DashboardStatsSourceQuery
    source_refs?: DashboardStatsSourceRef[]
    frontdoor_tri_state?: {
      states?: Array<'success' | 'degraded_success' | 'failed'>
      counts?: Partial<Record<'success' | 'degraded_success' | 'failed', number>>
      total?: number
      source?: string
      source_query?: DashboardStatsSourceQuery
      source_refs?: DashboardStatsSourceRef[]
    }
  }
  llm_report_quality?: DashboardLlmReportQuality
  pending_actions?: DashboardPendingAction[]
}

export type DashboardLlmReportQuality = {
  contract_version?: string
  trend_contract_version?: string
  summary?: {
    total?: number
    decisions?: Record<string, number>
    by_decision?: Record<string, number>
    readiness?: Record<string, number>
    project_keys?: Record<string, number>
    avg_citation_coverage?: number
    avg_evidence_coverage?: number
    export_events?: {
      total?: number
      success?: number
      blocked?: number
      token_invalid?: number
      failed?: number
      legacy?: number
      trusted?: number
      ui_read_only_context_included_count?: number
      by_format?: Record<string, number>
      by_integrity_mode?: Record<string, number>
    }
  }
  recent_records?: DashboardLlmReportQualityRecord[]
  recent_export_events?: DashboardLlmReportQualityRecord[]
  storage?: {
    contract_version?: string
    memory_count?: number
    persisted_count?: number
    persisted_degraded?: boolean
    database_count?: number
    database_degraded?: boolean
    job_log_count?: number
    job_log_degraded?: boolean
    merged_count?: number
  }
  actionability?: {
    has_blocked_exports?: boolean
    has_review_required_exports?: boolean
    next_action?: string
  }
  source_query?: DashboardStatsSourceQuery
  source_refs?: DashboardStatsSourceRef[]
}

export type DashboardLlmReportQualityRecord = {
  trace_id?: string | null
  request_id?: string | null
  project_key?: string | null
  decision?: string
  readiness?: string
  citation_coverage?: number
  evidence_coverage?: number
  source_count?: number
  missing_items_count?: number
  hard_failure_count?: number
  soft_failure_count?: number
  job_id?: number | string | null
  job_status?: string | null
  topic?: string | null
  recorded_at?: string | null
  record_source?: string | null
  next_action?: string | null
  event_type?: string | null
  source_trace_id?: string | null
  export_format?: string | null
  export_outcome?: string | null
  export_integrity_mode?: string | null
  export_integrity_trusted?: boolean | null
  artifact_id?: string | null
  artifact_sha256?: string | null
  filename?: string | null
  content_type?: string | null
  content_size_bytes?: number | null
  error_code?: string | null
  ui_read_only_context_included?: boolean | null
  ui_read_only_context_scope?: string | null
}

export type DashboardLlmReportDetailParams = {
  traceId: string
  projectKey?: string | null
}

export type DashboardLlmReportDetailResponse = {
  contract_version?: 'dashboard.llm_report_detail.v1' | string
  found?: boolean
  trace_id?: string | null
  request_id?: string | null
  project_key?: string | null
  source_refs?: Array<DashboardStatsSourceRef | string>
  source_query?: DashboardStatsSourceQuery | null
  report_artifact?: Record<string, unknown> | null
  artifact?: Record<string, unknown> | null
  quality_gate?: Record<string, unknown> | null
  report_quality_gate?: Record<string, unknown> | null
  repair_context?: Record<string, unknown> | null
  export_events?: Array<Record<string, unknown>>
  export_events_summary?: Record<string, unknown> | null
  export_audit?: {
    summary?: Record<string, unknown> | null
    events?: Array<Record<string, unknown>>
    storage?: Record<string, unknown>
    [key: string]: unknown
  } | null
  quality_record?: DashboardLlmReportQualityRecord | null
  [key: string]: unknown
}

export type DashboardStatsSourceQuery = {
  scope?: 'dashboard.stats' | string
  card?: string
  table?: string
  metrics?: string[]
  filters?: Record<string, unknown>
}

export type DashboardStatsSourceRef = {
  id?: string
  kind?: string
  table?: string
  columns?: string[]
  detail?: string
}

export type DashboardPendingAction = {
  id?: string
  type?: string
  status?: 'open' | 'resolved' | string
  severity?: 'low' | 'medium' | 'high' | string
  title?: string
  detail?: string
  source_metric?: string
  filters?: Record<string, unknown>
  suggested_action?: string | null
  source_refs?: string[]
}

export type DashboardDrilldownResponse = {
  metric?: string
  source_ref?: string
  filters?: Record<string, unknown>
  sample_rows?: Array<Record<string, unknown>>
  row_count?: number
  source_query?: DashboardStatsSourceQuery
  source_refs?: DashboardStatsSourceRef[]
}

export type DashboardReportFromFilterPayload = {
  request_type: 'report_from_dashboard_filter' | string
  project_key?: string
  dashboard: {
    variant?: string
    selected_label?: string | null
    selected_metric?: string | null
    selected_source_ref?: string | null
    pending_action_id?: string | null
    filters?: Record<string, unknown>
    action_filters?: Record<string, unknown>
    drilldown_filters?: Record<string, unknown>
    source_query?: DashboardStatsSourceQuery | null
    source_refs?: DashboardStatsSourceRef[]
    sample_rows?: Array<Record<string, unknown>>
    sample_row_count?: number
    reset_telemetry_boundary_context?: Record<string, unknown>
  }
  report_options?: {
    include_dashboard_sample_rows?: boolean
    preserve_source_refs?: boolean
    [key: string]: unknown
  }
}

export type DashboardReportFromFilterResponse = {
  contract_version?: string
  report_id?: string
  draft_id?: number
  document_id?: number
  title?: string
  status?: string
  filters?: Record<string, unknown>
  source_query?: DashboardStatsSourceQuery
  source_refs?: DashboardStatsSourceRef[]
  quality?: {
    status?: string
    quality_gate_mode?: string
    next_action?: string
    report_quality_gate?: Record<string, unknown>
    checklist?: Array<{
      id?: string
      status?: string
      detail?: string
    }>
  }
  report_quality_gate?: Record<string, unknown>
  export_artifact?: {
    artifact_id?: string
    artifact_token?: string
    artifact_sha256?: string
    markdown_sha256?: string
    gate_decision?: string
    gate_mode?: string
    trace_id?: string
    request_id?: string | null
    project_key?: string | null
    job_id?: number | null
    [key: string]: unknown
  }
  artifact?: {
    artifact_id?: string
    artifact_token?: string
    artifact_sha256?: string
    markdown_sha256?: string
    gate_decision?: string
    gate_mode?: string
    trace_id?: string
    request_id?: string | null
    project_key?: string | null
    job_id?: number | null
    [key: string]: unknown
  }
  draft?: {
    id?: number
    report_id?: string
    title?: string
    status?: string
    version?: number | null
  }
  evidence_metadata?: Record<string, unknown>
}

export type IngestFormState = {
  queryTerms: string
  topicFocus: '' | 'company' | 'product' | 'operation'
  languages: Array<'zh' | 'en'>
  provider: '' | 'serper' | 'google' | 'ddg' | 'serpstack' | 'serpapi' | 'auto'
  maxItems: number
  startOffset: string
  daysBack: string
  enableExtraction: boolean
  asyncMode: boolean
  socialPlatform: string
  baseSubreddits: string
  enableSubredditDiscovery: boolean
  commodityLimit: number
  ecomLimit: number
  sourceItemKey: string
  sourceHandlerKey: string
  singleUrl: string
  singleUrlStrictMode: boolean
  singleUrlSearchExpand: boolean
  singleUrlSearchExpandLimit: number
  singleUrlSearchProvider: 'auto' | 'google' | 'ddg_html'
  singleUrlSearchFallbackProvider: 'ddg_html'
  singleUrlFallbackOnInsufficient: boolean
  singleUrlAllowSearchSummaryWrite: boolean
  singleUrlMinResultsRequired: number
  singleUrlTargetCandidates: number
  singleUrlDecodeRedirectWrappers: boolean
  singleUrlFilterLowValueCandidates: boolean
  singleUrlLightFilterEnabled: boolean
  singleUrlLightFilterMinScore: number
  singleUrlLightFilterRejectStaticAssets: boolean
  singleUrlLightFilterRejectSearchNoiseDomain: boolean
}

export type RouteToken =
  | 'overviewTasks'
  | 'process-management'
  | 'overviewData'
  | 'admin'
  | 'dashboard'
  | 'dashboard-analysis'
  | 'dashboard-board'
  | 'data-dashboard'
  | 'market-data-visualization'
  | 'social-media-visualization'
  | 'policy-visualization'
  | 'graph'
  | 'graph-market'
  | 'graph-policy'
  | 'graph-social'
  | 'graph-company'
  | 'graph-product'
  | 'graph-operation'
  | 'graph-market-deep'
  | 'ingest'
  | 'ingest-specialized'
  | 'raw-data-processing'
  | 'resource-pool-management'
  | 'crawler-management'
  | 'project-management'
  | 'settings'
  | 'settings-llm-config'
  | 'backend-dashboard'
  | 'topic-dashboard'
  | 'topic-company'
  | 'topic-product'
  | 'topic-operation'

export type RouteHint = {
  mode: 'flowProcessing'
  variant?: 'rawData'
}

export type TaskPayload = {
  project_key?: string | null
  query_terms?: string[]
  keywords?: string[]
  base_keywords?: string[]
  max_items?: number
  max_results?: number
  url_count?: number
  limit?: number
  provider?: string
  search_provider?: string
  scope?: string
  state?: string
  item_key?: string | null
  resource_id?: string | null
  channel_key?: string | null
  platform?: string
  topic?: string
}

export type ProcessTaskMeta = {
  project_key?: string | null
  summary?: string | null
  chips?: string[]
  item_key?: string | null
  channel?: string | null
  query_terms_count?: number | null
  url_count?: number | null
  provider?: string | null
  limit?: number | null
  item?: string | null
  stage?: string | null
  state?: string | null
  [key: string]: unknown
}

export type ProcessTaskDetail = {
  task_id: string
  name: string
  status: string
  ready?: boolean | null
  successful?: boolean | null
  failed?: boolean | null
  result?: unknown
  progress?: Record<string, unknown> | null
  traceback?: string | null
  worker?: string | null
  started_at?: string | null
  args?: unknown[]
  kwargs?: Record<string, unknown>
  display_meta?: ProcessTaskMeta | null
  inserted_valid?: number | null
  rejected_count?: number | null
  rejection_breakdown?: Record<string, number> | null
}

export type ResourcePoolUrlItem = {
  id?: number
  url?: string
  domain?: string
  source?: string
  created_at?: string
}

export type SiteEntryItem = {
  id?: number
  site_url?: string
  domain?: string
  entry_type?: string
  source?: string
  enabled?: boolean
  scope?: SourceLibraryScope
  template?: string | null
  name?: string | null
  tags?: string[]
  source_ref?: Record<string, unknown>
  extra?: Record<string, unknown>
  lifecycle_state?: ResourcePoolSiteEntryLifecycleState | string
  lifecycle_summary?: ResourcePoolSiteEntryLifecycleSummary
  execution_plan_preview?: ResourcePoolSiteEntryExecutionPlanPreview
  review_closure?: ResourcePoolSiteEntryReviewClosure
  next_actions?: ResourcePoolSiteEntryNextAction[]
  evidence_binding?: ResourcePoolSiteEntryEvidenceBinding
  lifecycle_transition?: ResourcePoolSiteEntryLifecycleTransition
  single_source_guard?: ResourcePoolSiteEntrySingleSourceGuard
  execution_fact?: ResourcePoolSiteEntryExecutionFact
}

export type ResourcePoolSiteEntryLifecycleState =
  | 'accepted'
  | 'rejected'
  | 'needs_review'
  | 'disabled'
  | 'candidate'
  | 'active'

export type ResourcePoolSiteEntryLifecycleSummary = {
  state?: ResourcePoolSiteEntryLifecycleState | string
  enabled?: boolean
  scope?: string | null
  entry_type?: string | null
  source?: string | null
  state_source?: string | null
  [key: string]: unknown
}

export type ResourcePoolSiteEntryExecutionPlanPreview = {
  contract_version?: string
  site_entry_urls?: string[]
  expected_entry_type?: string
  route_bucket_counts?: Record<string, number>
  plan_meta?: Record<string, unknown>
  [key: string]: unknown
}

export type ResourcePoolSiteEntryEvidenceBinding = {
  contract_version?: string
  target?: string
  site_entry_url?: string
  source_ref?: Record<string, unknown>
  report_source_ref?: string
  report_refs?: string[]
  [key: string]: unknown
}

export type ResourcePoolSiteEntrySingleSourceGuard = {
  contract_version?: string
  strict_source?: boolean
  guarantee?: boolean
  status?: 'passed' | 'blocked' | string
  reason_code?: string | null
  source_ref?: Record<string, unknown>
  report_source_ref?: string
  allowed_urls?: string[]
  allowed_count?: number
  blocked_reason?: string | null
  runner_contract?: Record<string, unknown>
  [key: string]: unknown
}

export type ResourcePoolSiteEntryExecutionFact = {
  contract_version?: string
  fact_ref?: string
  reason_code?: string | null
  review_state?: ResourcePoolSiteEntryLifecycleState | string | null
  review_status?: string | null
  guard_status?: 'passed' | 'blocked' | string
  guard_reason_code?: string | null
  blocked?: boolean
  executable?: boolean
  source_refs?: Array<Record<string, unknown>>
  source_ref?: Record<string, unknown>
  report_source_ref?: string
  execution_plan_ref?: Record<string, unknown>
  next_actions?: ResourcePoolSiteEntryNextAction[]
  single_source_guard?: ResourcePoolSiteEntrySingleSourceGuard
  [key: string]: unknown
}

export type ResourcePoolSiteEntryLifecycleTransition = {
  contract_version?: string
  from_state?: ResourcePoolSiteEntryLifecycleState | string | null
  to_state?: ResourcePoolSiteEntryLifecycleState | string | null
  status?: string | null
  reason?: string | null
  reason_code?: string | null
  report_source_ref?: string | null
  trace_id?: string | null
  [key: string]: unknown
}

export type ResourcePoolSiteEntryNextAction = {
  action?: string
  enabled?: boolean
  blocked?: boolean
  block_reason?: string | null
  method?: string
  endpoint?: string
  handler_key?: string
  payload?: Record<string, unknown>
  report_source_ref?: string
  source_ref?: Record<string, unknown>
  strict_source?: ResourcePoolSiteEntrySingleSourceGuard
  single_source_guard?: ResourcePoolSiteEntrySingleSourceGuard
  [key: string]: unknown
}

export type ResourcePoolSiteEntryReviewClosure = {
  contract_version?: string
  status?: string
  state?: ResourcePoolSiteEntryLifecycleState | string
  enabled?: boolean
  executable?: boolean
  blocked?: boolean
  block_reason?: string | null
  site_entry_url?: string
  entry_type?: string
  report_source_ref?: string
  source_ref?: Record<string, unknown>
  evidence_binding?: ResourcePoolSiteEntryEvidenceBinding
  strict_source?: ResourcePoolSiteEntrySingleSourceGuard
  single_source_guard?: ResourcePoolSiteEntrySingleSourceGuard
  next_actions?: ResourcePoolSiteEntryNextAction[]
  [key: string]: unknown
}

export type WorkflowNode = {
  id: string
  name?: string
  module_key?: string
  type?: string
  handler?: string
  params?: Record<string, unknown>
  title?: string
  data_type?: string
}

export type WorkflowEdge = {
  id?: string
  source: string
  target: string
  mapping?: Record<string, unknown>
}

export type WorkflowBoardLayout = {
  layout?: string
  graph?: {
    nodes?: WorkflowNode[]
    edges?: WorkflowEdge[]
    [key: string]: unknown
  }
  edge_mappings?: Array<Record<string, unknown>>
  auto_interface?: boolean
  design?: {
    global_data_type?: string
    node_overrides?: Record<string, unknown>
    llm_policy?: string
    visualization_module?: string
  }
  data_flow?: string[]
  adapter_nodes?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type TopicItem = {
  id: number
  topic_name: string
  domains: string[]
  languages: string[]
  keywords_seed: string[]
  subreddits: string[]
  enabled: boolean
  description?: string | null
}

export type ProductItem = {
  id: number
  name: string
  category?: string | null
  source_name?: string | null
  source_uri?: string | null
  selector_hint?: string | null
  currency?: string | null
  enabled: boolean
}

export type PolicyItem = {
  id: number
  title?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  policy_type?: string | null
  uri?: string | null
}

export type PolicyDetail = {
  id: number
  title?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  effective_date?: string | null
  policy_type?: string | null
  key_points?: string[]
  summary?: string | null
  uri?: string | null
  content?: string | null
  source_id?: number | null
}

export type PolicyStats = {
  total_policies?: number
  state_distribution?: Array<{ state: string; count: number }>
  type_distribution?: Array<{ policy_type: string; count: number }>
  status_distribution?: Array<{ status: string; count: number }>
}

export type WorkflowTemplate = {
  workflow_name: string
  steps: Array<{
    handler: string
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  }>
  board_layout?: Record<string, unknown>
  boardLayout?: WorkflowBoardLayout
  meta?: Record<string, unknown>
}

export type WorkflowTemplatePayload = {
  project_key?: string
  steps: Array<{
    handler: string
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  }>
  board_layout?: WorkflowBoardLayout | Record<string, unknown>
}

export type WorkflowTemplateStageName = 'draft' | 'staging' | 'active'

export type WorkflowTemplateDiffStep = {
  index: number
  change_type: 'added' | 'removed' | 'modified' | string
  before?: {
    handler?: string | null
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  } | null
  after?: {
    handler?: string | null
    params?: Record<string, unknown>
    enabled?: boolean
    name?: string | null
  } | null
}

export type WorkflowTemplateDiffResponse = {
  project_key?: string
  workflow_name?: string
  config_key?: string
  changed?: boolean
  current_version?: number
  next_version?: number
  version_summary?: {
    active_version?: number
    draft_version?: number
    staging_version?: number | null
    stage?: string
    source?: string
    will_mutate?: boolean
    requires_publish?: boolean
    [key: string]: unknown
  }
  diff?: {
    steps?: WorkflowTemplateDiffStep[]
    step_count_before?: number
    step_count_after?: number
    board_layout_changed?: boolean
    [key: string]: unknown
  }
  current?: WorkflowTemplateResponse | Record<string, unknown>
  proposed?: WorkflowTemplatePayload | Record<string, unknown>
  [key: string]: unknown
}

export type WorkflowTemplateStageSummary = {
  has_draft?: boolean
  has_staging?: boolean
  has_active?: boolean
  active_version?: number | null
  draft_version?: number | null
  staging_version?: number | null
  [key: string]: unknown
}

export type WorkflowTemplateStageRecord = {
  stage: WorkflowTemplateStageName | string
  version?: number | null
  steps?: WorkflowTemplatePayload['steps']
  board_layout?: WorkflowBoardLayout | Record<string, unknown>
  requires_publish?: boolean
  promoted_from?: string | null
  [key: string]: unknown
}

export type WorkflowTemplateVersionListResponse = {
  project_key?: string
  workflow_name?: string
  config_key?: string
  current_version?: number
  items?: WorkflowTemplateStageRecord[]
  stage_summary?: WorkflowTemplateStageSummary
  [key: string]: unknown
}

export type WorkflowTemplateStagePayload = WorkflowTemplatePayload & {
  stage?: WorkflowTemplateStageName
}

export type WorkflowTemplatePromotePayload = {
  project_key?: string
  from_stage?: Extract<WorkflowTemplateStageName, 'draft' | 'staging'>
  to_stage?: Extract<WorkflowTemplateStageName, 'staging' | 'active'>
}

export type WorkflowTemplateRollbackPayload = {
  project_key?: string
  target_stage?: WorkflowTemplateStageName | string
  target_version?: number | null
  reason?: string
  actor?: string
  requested_by?: string
  trace_id?: string
}

export type WorkflowTemplateStageAuditEvent = {
  actor?: string | null
  requested_by?: string | null
  applied_by?: string | null
  action?: string
  from_stage?: string | null
  to_stage?: string | null
  version?: number | null
  created_at?: string | null
  trace_id?: string | null
  [key: string]: unknown
}

export type WorkflowTemplateRollbackPlan = {
  mode?: string
  can_execute?: boolean
  executable?: boolean
  will_mutate?: boolean
  reason?: string | null
  blocked_reason?: string | null
  from_stage?: string | null
  to_stage?: string | null
  target_version?: number | null
  target_stage_record?: WorkflowTemplateStageRecord | Record<string, unknown> | null
  apply_endpoint?: string | null
  requires_explicit_apply?: boolean
  risks?: string[]
  [key: string]: unknown
}

export type WorkflowTemplateStageMutationResponse = WorkflowTemplateMutationResponse & {
  promoted?: boolean
  stage?: WorkflowTemplateStageName | string
  from_stage?: string
  to_stage?: string
  current_version?: number
  next_version?: number
  version_summary?: NonNullable<WorkflowTemplateDiffResponse['version_summary']>
  stage_record?: WorkflowTemplateStageRecord
}

export type WorkflowTemplateRollbackResponse = WorkflowTemplateStageMutationResponse & {
  rollback_preview?: boolean
  rolled_back?: boolean
  applied?: boolean
  audit?: WorkflowTemplateStageAuditEvent
  history?: WorkflowTemplateStageAuditEvent[]
  rollback_plan?: WorkflowTemplateRollbackPlan
}

export type WorkflowRunResult = {
  task_id?: string
  task_name?: string
  status?: string
  started_at?: string
  params?: Record<string, unknown>
  workflow_name?: string
  dry_run?: boolean | null
  config_version?: number | string | null
  readiness?: boolean | string | Record<string, unknown> | null
  will_execute?: boolean | null
  writes_blocked?: boolean | null
  requires_publish?: boolean | null
  steps?: Array<Record<string, unknown>> | Record<string, unknown> | null
}

export type WorkflowTemplateMeta = {
  source?: 'builtin' | 'custom'
  [key: string]: unknown
}

export type WorkflowTemplateResponse = WorkflowTemplate & {
  project_key?: string
  meta?: WorkflowTemplateMeta
  board_layout?: WorkflowBoardLayout
}

export type ResourcePoolAction = {
  name?: string
  status?: string
  task_id?: string
  project_key?: string
  total?: number
  upserted?: number
  skipped?: number
  errors?: number
}

export type SettingTemplateConfig = {
  id?: number
  project_key?: string
  service_name: string
  description?: string | null
  system_prompt?: string | null
  user_prompt_template?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  top_p?: number | null
  presence_penalty?: number | null
  frequency_penalty?: number | null
  enabled: boolean
  updated_at?: string | null
}

export type LlmTemplatePayload = Omit<SettingTemplateConfig, 'id' | 'updated_at' | 'project_key'>

export type RawImportPayload = {
  items: Array<{
    title?: string
    uri?: string | null
    uris?: string[]
    text: string
    summary?: string | null
    doc_type?: string | null
    publish_date?: string | null
    state?: string | null
  }>
  source_name: string
  source_kind?: string
  infer_from_links: boolean
  enable_extraction: boolean
  default_doc_type: 'market_info' | 'policy' | 'social_sentiment' | 'news' | 'raw_note'
  extraction_mode: 'auto' | 'market' | 'policy' | 'social'
  overwrite_on_uri: boolean
  chunk_size: number
  chunk_overlap: number
  max_chunks: number
}

export type RawImportResult = {
  inserted?: number
  updated?: number
  skipped?: number
  error_count?: number
  errors?: Array<Record<string, unknown>>
  items?: Array<Record<string, unknown>>
}

export type SourceLibraryItemPayload = {
  item_key: string
  name?: string
  channel_key?: string
  description?: string
  params?: Record<string, unknown>
  tags?: string[]
  schedule?: string
  extends_item_key?: string
  enabled?: boolean
  extra?: Record<string, unknown>
  project_key?: string
}

export type SourceLibraryRunResult = {
  task_id?: string
  trace_id?: string | null
  async?: boolean
  item_key?: string
  project_key?: string
  ok?: boolean
  status?: string
  contract_version?: string
  source_mode?: 'protocol_search' | 'provider_harvest' | 'site_search' | 'url_execution' | string
  item?: {
    item_key?: string
    item_type?: string | null
    managed_by?: string | null
  }
  request?: {
    project_key?: string | null
    query_terms?: string[]
    time_window?: {
      days_back?: number | null
      start_time?: string | null
      end_time?: string | null
    }
    paging?: {
      page?: number | null
      start_offset?: number | null
      cursor?: string | null
    }
    limits?: {
      limit?: number | null
      max_items?: number | null
      per_keyword_limit?: number | null
      max_candidates?: number | null
      ingest_limit?: number | null
    }
  }
  results?: {
    records?: Array<Record<string, unknown>>
    stats?: {
      fetched?: number
      normalized?: number
      dropped?: number
      errors?: number
    }
  }
  errors?: Array<Record<string, unknown>>
  single_source_guard?: ResourcePoolSiteEntrySingleSourceGuard
  strict_source?: ResourcePoolSiteEntrySingleSourceGuard
  execution_fact?: ResourcePoolSiteEntryExecutionFact
  trace_chain?: Record<string, unknown> | null
  meta?: {
    reason_code?: string
    retryable?: boolean
    provider?: string | null
    provider_job_id?: string | null
    trace_id?: string | null
    warnings?: string[]
    raw_result_keys?: string[]
  }
  raw_snapshot?: Record<string, unknown>
}

export type SearchRetrievalRunReadback = {
  retrieval_run_id?: string
  retrieval_run?: Record<string, unknown>
  source_query?: Record<string, unknown> | null
  source_refs?: Array<Record<string, unknown> | string>
  provider_trace?: Record<string, unknown> | null
  index_freshness?: Record<string, unknown> | null
  retrieval_run_readback?: Record<string, unknown> | null
  readback?: Record<string, unknown> | null
  known_limitations?: string[]
  trace_chain?: Record<string, unknown> | null
}

export type ProcessTaskCancelResult = {
  success?: boolean
  message?: string
  task_id?: string
}

export type ProcessTaskLogsResponse = {
  task_id?: string
  tail?: number
  filtered?: boolean
  text?: string
  log_file?: string
}

export type AdminDocumentListPayload = {
  page?: number
  page_size?: number
  state?: string | null
  doc_type?: string | null
  has_extracted_data?: boolean | null
  search?: string | null
  sort_by?: 'created_at' | 'publish_date' | 'id'
  sort_order?: 'asc' | 'desc'
}

export type AdminDocumentItem = {
  id: number
  title?: string | null
  doc_type?: string | null
  state?: string | null
  source_id?: number
  created_at?: string | null
  updated_at?: string | null
  publish_date?: string | null
  has_extracted_data?: boolean
}

export type AdminDocumentListResponse = {
  items: AdminDocumentItem[]
  total: number
  page: number
  page_size: number
}

export type DocumentItem = {
  id: number
  title?: string | null
  doc_type?: string | null
  state?: string | null
  status?: string | null
  publish_date?: string | null
  content?: string | null
  summary?: string | null
  uri?: string | null
  source_id?: number | null
  created_at?: string | null
  updated_at?: string | null
  extracted_data?: Record<string, unknown> | null
}

export type DocumentExtractedPayload = {
  mode: 'replace' | 'merge'
  extracted_data: unknown
}

export type DocumentBulkExtractedPayload = {
  doc_ids: number[]
  mode: 'replace' | 'merge'
  extracted_data: unknown
  preview?: boolean
}

export type AdminEvidenceSourceRef = Record<string, unknown> | string

export type AdminEvidencePreview = {
  execution_result_available?: boolean
  affected_count?: number
  sample_rows?: Array<Record<string, unknown>>
  limitations?: string[]
  [key: string]: unknown
}

export type AdminActionResponse = {
  preview?: boolean
  schema_version?: string
  action?: string
  action_kind?: string
  audit_event?: Record<string, unknown> | null
  audit_trail?: Record<string, unknown> | Array<Record<string, unknown>> | null
  execution_result?: Record<string, unknown> | null
  rollback_hint?: Record<string, unknown> | string | null
  rollback_recommendation?: Record<string, unknown> | string | null
  would_affect_count?: number
  samples?: Array<Record<string, unknown>>
  risk_tags?: string[]
  risk_labels?: string[]
  source_query?: Record<string, unknown> | string | null
  source_refs?: AdminEvidenceSourceRef[]
  trace_chain?: Record<string, unknown> | null
  evidence_preview?: AdminEvidencePreview | null
  requires_confirmation?: boolean
  requested?: number
  updated?: number
  skipped?: number
  missing?: number[]
  total?: number
  success?: number
  error?: number
  skipped_count?: number
}

export type AdminDeleteDocumentsPayload = {
  ids: number[]
  preview?: boolean
}

export type AdminReExtractPayload = {
  doc_ids?: number[]
  force?: boolean
  fetch_missing_content?: boolean
  batch_size?: number
  limit?: number
  treat_empty_er_as_missing?: boolean
  preview?: boolean
}

export type AdminTopicExtractPayload = {
  topics?: Array<'company' | 'product' | 'operation'>
  doc_ids?: number[]
  doc_types?: string[]
  force?: boolean
  fetch_missing_content?: boolean
  batch_size?: number
  limit?: number
  candidate_mode?: 'rules_then_llm' | string
}

export type AdminTopicExtractResponse = {
  total?: number
  success?: number
  error?: number
  skipped?: number
  topic_hits?: Partial<Record<'company' | 'product' | 'operation', number>> & Record<string, number>
  [key: string]: unknown
}

export type GraphExportResponse = {
  nodes?: Array<Record<string, unknown>>
  edges?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type WorkflowTemplateMutationResponse = {
  project_key?: string
  workflow_name?: string
  saved?: boolean
  deleted?: boolean
  config_key?: string
  config?: Record<string, unknown>
}

export type WorkflowGraphTemplateItem = {
  template_id: string
  name?: string | null
  description?: string | null
  graph_id?: string | null
  active_version?: string | null
  latest_version?: string | null
  created_at?: string | null
  updated_at?: string | null
  meta?: Record<string, unknown> | null
}

export type WorkflowGraphTemplatePayload = {
  template_id: string
  name?: string | null
  description?: string | null
  dsl: Record<string, unknown>
  base_version?: string | null
  meta?: Record<string, unknown>
}

export type WorkflowGraphTemplateUpdatePayload = {
  name?: string | null
  description?: string | null
  dsl?: Record<string, unknown>
  base_version?: string | null
  meta?: Record<string, unknown>
}

export type WorkflowGraphTemplateListResponse = {
  items?: WorkflowGraphTemplateItem[]
  total?: number
}

export type WorkflowGraphTemplateMutationResponse = {
  template_id?: string
  created?: boolean
  updated?: boolean
  deleted?: boolean
  template?: WorkflowGraphTemplateItem
}

export type WorkflowGraphTemplateVersionItem = {
  template_id?: string
  version_id: string
  version?: string
  status?: string | null
  graph_id?: string | null
  checksum?: string | null
  created_at?: string | null
  updated_at?: string | null
  created_by?: string | null
  note?: string | null
  base_version?: string | null
  dsl?: Record<string, unknown> | null
  meta?: Record<string, unknown> | null
}

export type WorkflowGraphTemplateVersionPayload = {
  version_id?: string
  dsl?: Record<string, unknown>
  base_version?: string | null
  note?: string | null
  meta?: Record<string, unknown>
}

export type WorkflowGraphTemplateVersionListResponse = {
  items?: WorkflowGraphTemplateVersionItem[]
  total?: number
}

export type WorkflowGraphTemplateVersionMutationResponse = {
  template_id?: string
  version_id?: string
  created?: boolean
  activated?: boolean
  version?: WorkflowGraphTemplateVersionItem
}

export type ResourcePoolRecommendationPayload = {
  project_key?: string | null
  site_url: string
  entry_type?: string | null
  template?: string | null
  use_llm?: boolean
}

export type ResourcePoolRecommendationItem = {
  index?: number
  site_url?: string
  entry_type?: string | null
  channel_key?: string | null
  template?: string | null
  validated?: boolean
  source?: string
  capabilities?: Record<string, unknown>
  symbol_suggestion?: Record<string, unknown> | null
}

export type ResourcePoolRecommendationResponse = {
  channel_key?: string | null
  entry_type?: string | null
  template?: string | null
  validated?: boolean
  source?: string
  capabilities?: Record<string, unknown>
}

export type ResourcePoolBatchRecommendationPayload = {
  project_key?: string | null
  entries: Array<{
    site_url: string
    entry_type?: string | null
    template?: string | null
  }>
  use_llm?: boolean
  llm_batch_size?: number
}

export type ResourcePoolBatchRecommendationResponse = {
  items?: ResourcePoolRecommendationItem[]
  count?: number
}

export type ResourcePoolUpsertSiteEntryPayload = {
  project_key?: string
  scope?: 'project' | 'shared'
  site_url: string
  entry_type?: string
  template?: string | null
  name?: string | null
  domain?: string | null
  tags?: string[]
  enabled?: boolean
  capabilities?: Record<string, unknown>
  source?: string
  source_ref?: Record<string, unknown>
  extra?: Record<string, unknown>
}

export type ResourcePoolSiteEntryLifecyclePatchPayload = {
  project_key?: string | null
  scope?: 'project' | 'shared'
  site_url: string
  lifecycle_state: ResourcePoolSiteEntryLifecycleState
  reviewer?: string | null
  review_note?: string | null
  review_reason?: string | null
  enabled?: boolean | null
  extra_patch?: Record<string, unknown> | null
}

export type ResourcePoolDiscoverPayload = {
  project_key?: string
  url_scope?: 'project' | 'shared' | 'effective' | string
  target_scope?: 'project' | 'shared'
  limit_domains?: number
  probe_timeout?: number
  dry_run?: boolean
  write?: boolean
  async_mode?: boolean
}

export type ResourcePoolDiscoverResponse = {
  task_id?: string
  candidates?: number
  written?: number
  inserted?: number
  updated?: number
  skipped?: number
  errors?: number
  [key: string]: unknown
}

export type LlmProjectTemplatesResponse = {
  project_key?: string
  items?: LlmServiceConfigItem[]
}

export type LlmTemplateUpdatePayload = {
  description?: string | null
  system_prompt?: string | null
  user_prompt_template?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  top_p?: number | null
  presence_penalty?: number | null
  frequency_penalty?: number | null
  enabled?: boolean | null
}

export type LlmTemplateUpdateResponse = {
  project_key?: string
  item?: LlmServiceConfigItem
}

export type LlmTemplateCopyPayload = {
  source_project_key: string
  overwrite?: boolean
}

export type LlmTemplateCopyResponse = {
  source_project_key?: string
  target_project_key?: string
  copied?: number
  skipped?: number
  overwrite?: boolean
}

export type LlmServiceConfigItem = {
  id: number
  service_name: string
  description?: string | null
  model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  enabled: boolean
  updated_at?: string
}

export type AdminStats = {
  documents?: {
    total?: number
    recent_today?: number
  }
  social_data?: {
    total?: number
    recent_today?: number
  }
  sources?: {
    total?: number
  }
  market_stats?: {
    total?: number
  }
  search_history?: {
    total?: number
  }
}

export type SearchHistoryItem = {
  id: number
  topic?: string | null
  last_search_time?: string | null
}

export type GraphNodeRef = {
  type: string
  id: string | number
}

export type GraphNodeItem = {
  id: string | number
  type: string
  entry_id?: string | number
  title?: string
  name?: string
  text?: string
  canonical_name?: string
  [key: string]: unknown
}

export type GraphEdgeItem = {
  type?: string
  predicate?: string
  predicate_raw?: string
  relation_class?: string
  from: GraphNodeRef
  to: GraphNodeRef
  [key: string]: unknown
}

export type GraphResponse = {
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
}

export type GraphConfigResponse = {
  graph_doc_types?: Record<string, string[]>
  graph_type_labels?: Record<string, string>
  graph_node_types?: Record<string, string[]>
  graph_node_labels?: Record<string, string>
  graph_topic_scope_entities?: Record<string, string[]>
  graph_field_labels?: Record<string, string>
  graph_edge_types?: Record<string, string[]>
  graph_relation_labels?: Record<string, string>
}

export type GraphStructuredSelectedNode = {
  type: string
  id: string
  entry_id: string
  label: string
  topic_focus?: 'company' | 'product' | 'operation' | 'general'
}

export type GraphStructuredSelectedEdge = {
  source_entry_id?: string
  target_entry_id?: string
  relation?: string
  label?: string
}

export type GraphStructuredDashboardParams = {
  language: string
  provider: string
  max_items: number
  start_offset: number | null
  days_back: number | null
  enable_extraction: boolean
  async_mode: boolean
  platforms: string[]
  enable_subreddit_discovery: boolean
  base_subreddits: string[] | null
  source_item_keys?: string[]
  project_key?: string | null
}

export type GraphStructuredSearchRequest = {
  selected_nodes: GraphStructuredSelectedNode[]
  selected_edges?: GraphStructuredSelectedEdge[]
  dashboard: GraphStructuredDashboardParams
  llm_assist: boolean
  flow_type: 'collect' | 'source_collect'
  intent_mode: 'keyword' | 'keyword_llm'
}

export type GraphStructuredSearchBatch = {
  batch_name?: string
  task_id?: string
  type?: string
  [key: string]: unknown
}

export type GraphStructuredSearchResponse = {
  flow_type?: string
  intent_mode?: string
  batches?: GraphStructuredSearchBatch[]
  summary?: {
    accepted?: number
    queued?: number
    failed?: number
    [key: string]: unknown
  }
  [key: string]: unknown
}
