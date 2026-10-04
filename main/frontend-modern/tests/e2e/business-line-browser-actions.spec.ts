import { expect, test, type Page, type Route } from '@playwright/test'

type ProjectRow = {
  project_key: string
  name: string
  enabled: boolean
  is_active?: boolean
  schema_name?: string
}

const MOCK_PROJECT_KEY = 'mocked_rail_58'

type ResetTelemetryBoundaryContext = {
  scope: string
  source: string
  lines: string[]
  not_report_proof: boolean
  not_scheduled_run_evidence_proof: boolean
  scheduled_evidence_write: string
  scheduled_completion_proof: string
}

function expectResetTelemetryBoundaryContext(context: ResetTelemetryBoundaryContext) {
  expect(context).toMatchObject({
    scope: 'ui_read_only_evidence_context',
    source: 'business_lines.evidence_matrix.ui_boundary.reset_telemetry',
    not_report_proof: true,
    not_scheduled_run_evidence_proof: true,
    scheduled_evidence_write: 'none',
    scheduled_completion_proof: 'unchanged',
  })
}

function apiEnvelope(data: unknown) {
  return {
    status: 'ok',
    data,
    error: null,
    meta: {
      trace_id: 'mocked-business-line-browser-actions-not-real-backend-proof',
      mock: true,
      real_backend_proof: false,
    },
  }
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

function agentCoreEvent(eventType: string, seq: number, payload: Record<string, unknown>, callId?: string) {
  return {
    event_id: `mocked-agent-event-${seq}`,
    session_id: 'mocked-session-58',
    seq,
    event_type: eventType,
    call_id: callId || null,
    severity: 'info',
    payload,
    ts: '2026-05-24T18:08:00Z',
  }
}

function agentCoreSse(event: ReturnType<typeof agentCoreEvent>) {
  return `event: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`
}

function typedKnowledgeWritingContextPayload() {
  return {
    project_key: MOCK_PROJECT_KEY,
    route_path: '/api/v1/typed-knowledge/writing-context',
    live_db_backed: true,
    typed_knowledge_context: {
      contract_version: 'writing.typed_knowledge_context.v1',
      source: 'typed_knowledge',
      consumer: 'writing.keyword_card',
      boundary: {
        scope: 'business-line-browser-actions',
        source: 'mocked typed knowledge context readback',
        not_real_backend_proof: true,
      },
      handoffs: [
        {
          contract_version: 'typed_knowledge.writing_handoff.v1',
          knowledge_item_key: 'tk-mocked-58',
          project_key: MOCK_PROJECT_KEY,
          canonical_statement: 'Typed knowledge handoff is visible in the writing workbench.',
          primary_type_node_key: 'type:market_signal',
          topic_cluster_keys: ['topic:browser-rail'],
          booklet_keys: ['booklet:p1-agent-knowledge-event-model'],
          review_state: 'pending',
          quality_grade: 'A',
          locale: 'zh-CN',
          evidence_refs: ['typed-knowledge:evidence:58'],
          visibility_scope: 'project',
          selection_hash: 'sha256:mocked-typed-knowledge-58',
          selection_text: 'typed knowledge writing context',
          facets: { line_key: 'writing_knowledge_graph_agent' },
        },
      ],
    },
  }
}

function mockedAgentReadbackEvents() {
  return [
    agentCoreEvent('agent_core.tool_call_requested', 1, {
      tool_call: { tool_name: 'agent_session.read', call_id: 'call-agent-session-read' },
      status: 'requested',
    }, 'call-agent-session-read'),
    agentCoreEvent('agent_core.tool_result', 2, {
      tool_name: 'agent_session.read',
      status: 'completed',
      model_summary: 'session readback returned mocked-session-58',
      structured_content: {
        session_id: 'mocked-session-58',
        readback_status: 'passed',
      },
    }, 'call-agent-session-read'),
    agentCoreEvent('agent_core.tool_result', 3, {
      tool_name: 'writing.document.insert_paragraph',
      status: 'completed',
      model_summary: 'typed knowledge writing context stayed attached to the Agent session',
      structured_content: {
        doc_id: 5804,
        operation: 'append',
        diff: { added_lines: 1, removed_lines: 0 },
      },
    }, 'call-writing-readback'),
  ]
}

function healthPayload() {
  return {
    status: 'ok',
    provider: 'mocked-browser-rail-not-real-backend',
    env: 'mocked',
    runtime_mode: 'mocked',
    services: {
      api: {
        status: 'ok',
        mode: 'mocked',
        health_port_hint: 'route-mock',
        missing_dependencies: [],
      },
      database: {
        status: 'ok',
        mode: 'mocked',
        health_port_hint: 'route-mock',
        missing_dependencies: [],
      },
      queue: {
        status: 'ok',
        mode: 'mocked',
        health_port_hint: 'route-mock',
        missing_dependencies: [],
      },
    },
  }
}

function deepHealthPayload() {
  return {
    status: 'ok',
    database: 'ok',
    elasticsearch: 'ok',
    runtime_mode: 'mocked',
    services: healthPayload().services,
  }
}

function businessLineEvidenceMatrixPayload() {
  const lines = [
    {
      line_key: 'ingest',
      label: '采集 / 入库',
      entrypoints: ['IngestPage'],
      api_groups: ['/api/v1/ingest/*'],
      current_gaps: ['submission/task/index closure must be proven inside batch 66'],
      next_remediation: 'Close ingest evidence in the same batch; not a next batch leak.',
      verification_commands: ['pytest main/backend/tests/core_business/test_ingest_core_contract.py -q'],
    },
    {
      line_key: 'search_discovery_index',
      label: '检索 / 发现 / 索引',
      entrypoints: ['DashboardPage', 'CatalogPage'],
      api_groups: ['/api/v1/search', '/api/v1/discovery/*'],
      current_gaps: ['retrieval run readback and index freshness must stay visible'],
      next_remediation: 'Keep search readback covered by the same evidence matrix.',
      verification_commands: ['pytest main/backend/tests/core_business/test_search_core_contract.py -q'],
    },
    {
      line_key: 'resource_source_library',
      label: '资源池 / 来源库',
      entrypoints: ['ResourcePage', 'CatalogPage'],
      api_groups: ['/api/v1/resource_pool/*', '/api/v1/source_library/*'],
      current_gaps: ['source refs, lifecycle, and next actions need same-batch evidence'],
      next_remediation: 'Cover source-library remediation without pushing it to a later batch.',
      verification_commands: ['pytest main/backend/tests/core_business/test_resource_pool_core_contract.py -q'],
    },
    {
      line_key: 'projects_config_workflow',
      label: '项目 / 配置 / 工作流',
      entrypoints: ['ProjectsPage', 'SettingsPage', 'ProcessPage'],
      api_groups: ['/api/v1/projects/*', '/api/v1/project-customization/*'],
      current_gaps: ['readiness and workflow impact must stay connected to user actions'],
      next_remediation: 'Keep projects and workflow actions in the batch 66 rail.',
      verification_commands: ['pytest main/backend/tests/core_business/test_project_customization_core_contract.py -q'],
    },
    {
      line_key: 'dashboard_admin_governance',
      label: '报告 / 仪表盘 / 后台治理',
      entrypoints: ['DashboardPage', 'OpsPage'],
      api_groups: ['/api/v1/dashboard/*', '/api/v1/admin/*'],
      current_gaps: ['report detail and admin governance evidence must not split across batches'],
      next_remediation: 'Keep dashboard/admin evidence inside the same mocked rail.',
      verification_commands: ['pytest main/backend/tests/core_business/test_admin_dashboard_process_core_contract.py -q'],
    },
    {
      line_key: 'writing_knowledge_graph_agent',
      label: '写作 / 知识 / 图谱 / Agent',
      entrypoints: ['WritingWorkbenchPage', 'GraphPage', 'CodexAgentPage'],
      api_groups: ['/api/v1/writing/*', '/api/v1/workflow_graph/*', '/api/v1/agent-batch/*'],
      current_gaps: ['graph and agent evidence need a visible same-batch coverage row'],
      next_remediation: 'Track graph/agent coverage explicitly instead of relying on follow-up batches.',
      verification_commands: ['pytest main/backend/tests/integration/test_workflow_graph_api_unittest.py -q'],
    },
    {
      line_key: 'runtime_ops',
      label: '运维 / 启动器 / 运行环境',
      entrypoints: ['OpsPage'],
      api_groups: ['/api/v1/health', '/api/v1/health/deep'],
      current_gaps: ['runtime diagnostics and recovery visibility must remain same-batch evidence'],
      next_remediation: 'Close ops runtime evidence in the batch 66 matrix; not next batch leak.',
      verification_commands: ['python3 scripts/runtime_health_matrix.py --help'],
    },
  ]
  return {
    contract_version: 'business_line.evidence_matrix.v2',
    vocabulary_version: 'business_line.vocabulary.current.v1',
    matrix_diagnostics_guidance: {
      source_lane: 'business_line_worker_readback_project_matrix_nightly',
      source_artifact: 'nightly-manifest.json:matrix_diagnostics',
      consumer_surface: 'OpsPage:/api/v1/business-lines/evidence-matrix',
      recommended_display_order: [
        'runtime_preflight_status',
        'matrix_exit_code',
        'project_keys',
        'summary_total',
        'first_blocked_reason',
        'reason_counts',
        'blocked_projects',
        'failed_projects',
      ],
      required_fields: [
        'runtime_preflight_status',
        'matrix_exit_code',
        'project_keys',
        'summary_total',
        'first_blocked_reason',
        'reason_counts',
      ],
      blocked_project_fields: [
        'project_key',
        'status',
        'reason',
        'stopped_at',
        'exit_code',
        'trigger_smoke_status',
      ],
      classification_boundary: {
        scheduled_run_blocked: 'scheduled_run_blocked is not completion proof',
        scheduled_run_evidence: 'Only scheduled_run_evidence can close scheduled evidence',
        completion_claim: 'does_not_claim_real_scheduler_run',
      },
    },
    coverage: {
      covered_line_count: lines.length,
      covered_line_keys: lines.map((line) => line.line_key),
      not_admin_only: true,
    },
    worker_readback: {
      contract_version: 'business_line.worker_readback_contract.v2',
      covered_line_keys: ['ingest', 'search_discovery_index', 'writing_knowledge_graph_agent'],
      completion_claim: 'not_observed_without_live_worker_readback',
    },
    scheduled_observation: {
      observation_status: 'not_observed',
      scheduled_run_evidence: 'not_observed',
      install_status: 'unknown',
      codex_retirement_status: 'not_observed',
      completion_claim: 'not_observed',
    },
    ui_boundary: {
      reset_telemetry: {
        event_name: 'reset_empty_warning_view',
        event_scope: 'ui_event_log_only',
        filter_transition: { from: 'warning_only', to: 'all' },
        sort_behavior: 'unchanged',
        api_payload_behavior: 'unchanged',
        scheduled_evidence_write: 'none',
        scheduled_completion_proof: false,
        scheduled_evidence_controller: 'scheduled_run_evidence',
      },
      read_only_context: {
        not_report_proof: true,
        not_quality_gate_input: true,
        not_scheduled_run_evidence_proof: true,
        scheduled_evidence_write: 'none',
        scheduled_completion_proof_behavior: 'unchanged',
        audit_outcome_behavior: 'unchanged',
        observation_status: 'not_applicable_ui_boundary',
        boundary: 'UI-only read-only context is not report proof, quality gate input, or scheduled_run_evidence proof.',
      },
    },
    lines,
  }
}

function businessLineEvidenceMatrixWithoutResetTelemetryPayload() {
  const payload = businessLineEvidenceMatrixPayload()
  const uiBoundary = payload.ui_boundary as {
    reset_telemetry?: unknown
    read_only_context: typeof payload.ui_boundary.read_only_context
  }
  delete uiBoundary.reset_telemetry
  payload.ui_boundary = uiBoundary
  return payload
}

function scheduledMatrixArtifactSummaryPayload() {
  return {
    contract_version: 'business_line.scheduled_matrix_artifact_summary.v1',
    source_checker: 'check_scheduled_automation_artifacts',
    lane: 'business_line_worker_readback_project_matrix_nightly',
    status: 'missing',
    lane_classification: 'missing',
    reason: 'no expected nightly artifact files were found',
    artifact_path: null,
    diagnostics: {
      runtime_preflight_status: 'passed',
      matrix_exit_code: null,
      first_blocked_reason: 'no expected nightly artifact files were found',
    },
    summary: {
      expected_artifact_kind: 'scheduled_run_evidence',
      observed_artifact_count: 0,
      missing_artifact_count: 1,
    },
    observed_at: '2026-05-25T08:30:00Z',
    recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane business_line_worker_readback_project_matrix_nightly',
    completion_boundary: {
      scheduled_run_evidence: 'Only scheduled_run_evidence can close scheduled evidence',
      scheduled_run_blocked: 'scheduled_run_blocked is not completion proof',
      completion_claim: 'does_not_claim_real_scheduler_run',
    },
  }
}

function scheduledArtifactSummariesPayload() {
  return {
    contract_version: 'business_line.scheduled_artifact_summaries.v1',
    source_checker: 'scripts/check_scheduled_automation_artifacts.py',
    status: 'blocked',
    summary: {
      lane_count: 3,
      scheduled_run_evidence_count: 0,
      scheduled_run_blocked_count: 0,
      manual_dry_run_count: 2,
      missing_count: 1,
    },
    lanes: [
      {
        lane: 'performance_capacity_baseline_nightly',
        status: 'blocked',
        lane_classification: 'manual_dry_run',
        reason: 'latest artifact is a manual dry run and is not completion proof',
        artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
        diagnostics: {
          runtime_preflight_status: 'passed',
        },
        observed_at: '2026-05-25T08:29:00Z',
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane performance_capacity_baseline_nightly',
      },
      {
        lane: 'llm_report_token_state_retention_nightly',
        status: 'blocked',
        lane_classification: 'manual_dry_run',
        reason: 'latest artifact is a manual dry run and is not completion proof',
        artifact_path: 'artifacts/llm_report_token_state_retention_nightly/latest.json',
        diagnostics: {
          runtime_preflight_status: 'passed',
          first_blocked_reason: 'manual dry run is not scheduled evidence',
        },
        observed_at: '2026-05-25T08:30:00Z',
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane llm_report_token_state_retention_nightly',
      },
      {
        lane: 'business_line_worker_readback_project_matrix_nightly',
        status: 'blocked',
        lane_classification: 'missing',
        reason: 'no expected nightly artifact files were found',
        artifact_path: null,
        diagnostics: {
          runtime_preflight_status: 'passed',
          matrix_exit_code: null,
          first_blocked_reason: 'no expected nightly artifact files were found',
        },
        observed_at: '2026-05-25T08:30:00Z',
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane business_line_worker_readback_project_matrix_nightly',
      },
    ],
    observed_at: '2026-05-25T08:30:00Z',
    recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --all-scheduled-lanes',
    whitelisted_lanes: [
      'performance_capacity_baseline_nightly',
      'llm_report_token_state_retention_nightly',
      'business_line_worker_readback_project_matrix_nightly',
    ],
    completion_boundary: {
      scheduled_run_evidence: 'Only scheduled_run_evidence can close scheduled evidence',
      scheduled_run_blocked: 'scheduled_run_blocked is not completion proof',
      manual_dry_run: 'manual_dry_run is not completion proof',
      missing: 'missing is not completion proof',
      completion_claim: 'does_not_claim_real_scheduler_run',
    },
  }
}

function scheduledArtifactDrilldownPayload() {
  return {
    contract_version: 'business_line.scheduled_artifact_drilldown.v1',
    source_checker: 'scripts/check_scheduled_automation_artifacts.py',
    status: 'blocked',
    observed_at: '2026-05-25T08:31:00Z',
    summary: {
      lane_count: 3,
      artifact_count: 4,
      scheduled_run_evidence_count: 0,
      scheduled_run_blocked_count: 1,
      manual_dry_run_count: 1,
      missing_count: 1,
    },
    lanes: [
      {
        lane: 'llm_report_token_state_retention_nightly',
        status: 'blocked',
        lane_classification: 'scheduled_run_blocked',
        scheduled_completion_proof: false,
        reason: 'scheduled_run_blocked artifact records a failed scheduler attempt but does not close evidence',
        artifact_path: 'artifacts/llm_report_token_state_retention_nightly/blocked.json',
        base_dir: 'artifacts/llm_report_token_state_retention_nightly',
        artifact_count: 1,
        identity_warning_count: 0,
        identity_warning_types: [],
        identity_warning_severity_counts: {},
        identity_warning_severity_order: null,
        identity_warning_highest_severity: null,
        identity_warning_highest_severity_rank: null,
        identity_status_counts: {
          latest: 1,
        },
        artifacts: [
          {
            artifact_path: 'artifacts/llm_report_token_state_retention_nightly/blocked.json',
            classification: 'scheduled_run_blocked',
            scheduled_completion_proof: false,
            reason: 'retention scheduler blocked on token-state preflight',
            freshness_rank: 1,
            freshness_window_size: 1,
            is_latest_for_lane: true,
            identity_matches_latest: true,
            identity_status: 'latest',
            identity_warning: null,
            identity_warning_severity: null,
            identity_warning_message: null,
            latest_artifact_path: 'artifacts/llm_report_token_state_retention_nightly/blocked.json',
            size_bytes: 512,
            sha256: 'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210',
            mtime: '2026-05-25T08:12:00Z',
            observed_at: '2026-05-25T08:31:00Z',
          },
        ],
        diagnostics: {
          runtime_preflight_status: 'passed',
          first_blocked_reason: 'retention scheduler blocked on token-state preflight',
          artifact_count: 1,
        },
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane llm_report_token_state_retention_nightly',
      },
      {
        lane: 'performance_capacity_baseline_nightly',
        status: 'blocked',
        lane_classification: 'manual_dry_run',
        scheduled_completion_proof: false,
        reason: 'manual_dry_run artifact exists but is not scheduled_run_evidence',
        artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
        base_dir: 'artifacts/performance_capacity_baseline_nightly',
        artifact_count: 3,
        identity_warning_count: 1,
        identity_warning_types: ['artifact_identity_differs_from_latest'],
        identity_warning_severity_counts: {
          warning: 1,
        },
        identity_warning_severity_order: ['warning'],
        identity_warning_highest_severity: 'warning',
        identity_warning_highest_severity_rank: 1,
        identity_status_counts: {
          latest: 1,
          differs_from_latest: 1,
          same_as_latest: 1,
        },
        artifacts: [
          {
            artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
            classification: 'manual_dry_run',
            scheduled_completion_proof: false,
            reason: 'manual_dry_run is not completion proof',
            freshness_rank: 1,
            freshness_window_size: 3,
            is_latest_for_lane: true,
            identity_matches_latest: true,
            identity_status: 'latest',
            identity_warning: null,
            identity_warning_severity: null,
            identity_warning_message: null,
            latest_artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
            size_bytes: 2048,
            sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            mtime: '2026-05-25T08:10:00Z',
            observed_at: '2026-05-25T08:31:00Z',
          },
          {
            artifact_path: 'artifacts/performance_capacity_baseline_nightly/manual-dry-run.json',
            classification: 'manual_dry_run',
            scheduled_completion_proof: false,
            reason: 'manual dry-run evidence only',
            freshness_rank: 2,
            freshness_window_size: 3,
            is_latest_for_lane: false,
            identity_matches_latest: false,
            identity_status: 'differs_from_latest',
            identity_warning: 'artifact_identity_differs_from_latest',
            identity_warning_severity: 'warning',
            identity_warning_message: 'artifact identity differs from latest artifact for this lane',
            latest_artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
            size_bytes: 1536,
            sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
            mtime: '2026-05-25T08:09:00Z',
            observed_at: '2026-05-25T08:31:00Z',
          },
          {
            artifact_path: 'artifacts/performance_capacity_baseline_nightly/manual-dry-run-copy.json',
            classification: 'manual_dry_run',
            scheduled_completion_proof: false,
            reason: 'manual dry-run copy matches latest identity and is not completion proof',
            freshness_rank: 3,
            freshness_window_size: 3,
            is_latest_for_lane: false,
            identity_matches_latest: true,
            identity_status: 'same_as_latest',
            identity_warning: null,
            identity_warning_severity: null,
            identity_warning_message: null,
            latest_artifact_path: 'artifacts/performance_capacity_baseline_nightly/latest.json',
            size_bytes: 2048,
            sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            mtime: '2026-05-25T08:08:00Z',
            observed_at: '2026-05-25T08:31:00Z',
          },
        ],
        diagnostics: {
          runtime_preflight_status: 'passed',
          first_blocked_reason: 'manual dry run is not scheduled evidence',
          artifact_count: 3,
        },
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane performance_capacity_baseline_nightly',
      },
      {
        lane: 'business_line_worker_readback_project_matrix_nightly',
        status: 'blocked',
        lane_classification: 'missing',
        scheduled_completion_proof: false,
        reason: 'no matrix scheduled artifact was found',
        artifact_path: null,
        base_dir: 'artifacts/business_line_worker_readback_project_matrix_nightly',
        artifact_count: 0,
        identity_warning_count: 0,
        identity_warning_types: [],
        identity_warning_severity_counts: {},
        identity_warning_severity_order: null,
        identity_warning_highest_severity: null,
        identity_warning_highest_severity_rank: null,
        identity_status_counts: {},
        artifacts: [],
        diagnostics: {
          runtime_preflight_status: 'passed',
          matrix_exit_code: null,
          first_blocked_reason: 'no matrix scheduled artifact was found',
          artifact_count: 0,
        },
        recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --lane business_line_worker_readback_project_matrix_nightly',
      },
    ],
    completion_boundary: {
      scheduled_run_evidence: 'Only scheduled_run_evidence can close scheduled evidence',
      scheduled_run_blocked: 'scheduled_run_blocked is not completion proof',
      manual_dry_run: 'manual_dry_run is not completion proof',
      missing: 'missing is not completion proof',
      completion_claim: 'does_not_claim_real_scheduler_run',
    },
    recommended_command: 'python3 scripts/check_scheduled_automation_artifacts.py --all-scheduled-lanes --drilldown',
  }
}

type ScheduledArtifactDrilldownFixture = ReturnType<typeof scheduledArtifactDrilldownPayload>

function scheduledArtifactDrilldownNoWarningPayload(): ScheduledArtifactDrilldownFixture {
  const payload = scheduledArtifactDrilldownPayload()
  return {
    ...payload,
    lanes: payload.lanes.map((lane) => ({
      ...lane,
      identity_warning_count: 0,
      identity_warning_types: [],
      identity_warning_severity_counts: {},
      identity_warning_severity_order: null,
      identity_warning_highest_severity: null,
      identity_warning_highest_severity_rank: null,
      artifacts: lane.artifacts.map((artifact) => ({
        ...artifact,
        identity_warning: null,
        identity_warning_severity: null,
        identity_warning_message: null,
      })),
    })),
  }
}

function adminPreviewPayload(actionKind: string, requestPayload: Record<string, unknown>) {
  const ids = Array.isArray(requestPayload.ids)
    ? requestPayload.ids
    : Array.isArray(requestPayload.doc_ids)
      ? requestPayload.doc_ids
      : []
  return {
    preview: true,
    schema_version: 'ops.admin.preview_evidence_package.v1',
    action_kind: actionKind,
    risk_labels: actionKind === 'delete_documents' ? ['destructive', 'admin_write'] : ['write', 'admin_write'],
    source_query: {
      scope: 'admin.documents',
      project_key: MOCK_PROJECT_KEY,
      ids,
      preview: true,
    },
    source_refs: [
      { id: 'admin.documents:5801', type: 'document', table: 'documents' },
      { id: `admin.preview:${actionKind}:mocked`, type: 'admin_preview', action_kind: actionKind },
    ],
    trace_chain: {
      contract_version: 'ops.admin.preview.trace_chain.v1',
      trace_id: `trace-admin-preview-${actionKind}`,
      action_kind: actionKind,
      preview: true,
    },
    evidence_preview: {
      execution_result_available: false,
      affected_count: ids.length,
      sample_rows: [{ id: 5801, title: 'Mocked Rail Ops Document' }],
      limitations: ['mocked_preview_not_real_backend_proof'],
    },
    would_affect_count: ids.length,
    requires_confirmation: true,
  }
}

function adminExecutionPayload(actionKind: string, requestPayload: Record<string, unknown>) {
  const ids = Array.isArray(requestPayload.ids)
    ? requestPayload.ids
    : Array.isArray(requestPayload.doc_ids)
      ? requestPayload.doc_ids
      : []
  return {
    preview: false,
    schema_version: 'ops.admin.governance_execution_readback.v1',
    action_kind: actionKind,
    risk_labels: actionKind === 'delete_documents' ? ['destructive', 'admin_write'] : ['write', 'admin_write'],
    source_query: {
      scope: 'admin.documents.execution',
      project_key: MOCK_PROJECT_KEY,
      ids,
      preview: false,
    },
    source_refs: [
      { id: 'admin.documents:5801', type: 'document', table: 'documents' },
      { id: `admin.execution:${actionKind}:mocked`, type: 'admin_execution', action_kind: actionKind },
    ],
    trace_chain: {
      contract_version: 'ops.admin.execution.trace_chain.v1',
      trace_id: `trace-admin-execution-${actionKind}`,
      action_kind: actionKind,
      preview: false,
      status: 'executed',
    },
    evidence_preview: {
      execution_result_available: true,
      affected_count: ids.length,
      sample_rows: [{ id: 5801, title: 'Mocked Rail Ops Document' }],
      limitations: ['mocked_execution_not_real_backend_proof'],
    },
    execution_result: {
      execution_result_available: true,
      affected_count: ids.length,
      status: 'executed',
      missing_ids: [],
    },
    audit_event: {
      trace_id: `trace-admin-execution-${actionKind}`,
      action_kind: actionKind,
      project_key: MOCK_PROJECT_KEY,
      requested_count: ids.length,
      affected_count: ids.length,
      status: 'recorded_in_response_only',
    },
    rollback_hint: {
      supported: false,
      reason: 'mocked browser rail does not mutate backend state',
    },
    updated: actionKind === 'bulk_structured_write' ? ids.length : undefined,
    deleted: actionKind === 'delete_documents' ? ids.length : undefined,
  }
}

async function setupMockedBusinessLineRail(
  page: Page,
  options: {
    scheduledArtifactDrilldownFixture?: () => ScheduledArtifactDrilldownFixture
    businessLineEvidenceMatrixFixture?: typeof businessLineEvidenceMatrixPayload
  } = {},
) {
  const scheduledArtifactDrilldownFixture = options.scheduledArtifactDrilldownFixture || scheduledArtifactDrilldownPayload
  const businessLineEvidenceMatrixFixture = options.businessLineEvidenceMatrixFixture || businessLineEvidenceMatrixPayload
  let activeProjectKey = MOCK_PROJECT_KEY
  let projects: ProjectRow[] = [
    {
      project_key: MOCK_PROJECT_KEY,
      name: 'Mocked Rail 58 Project',
      schema_name: 'mocked_rail_58_schema',
      enabled: true,
      is_active: true,
    },
    {
      project_key: 'demo_proj',
      name: 'Demo Template Project',
      schema_name: 'demo_schema',
      enabled: true,
      is_active: false,
    },
  ]
  const hits = {
    dashboardStats: 0,
    dashboardReportDetail: 0,
    topologyDiscovery: 0,
    topologyRead: 0,
    graphConfig: 0,
    ingestSingleUrl: 0,
    searchRetrievalRun: 0,
    marketGraph: 0,
    siteEntries: 0,
    sourceLibraryRun: 0,
    opsHealth: 0,
    adminDeletePreview: 0,
    adminBulkWritePreview: 0,
    adminDeleteExecute: 0,
    adminBulkWriteExecute: 0,
    businessLineEvidenceMatrix: 0,
    scheduledMatrixArtifactSummary: 0,
    scheduledArtifactSummaries: 0,
    scheduledArtifactDrilldown: 0,
    dashboardReportFromFilter: 0,
    dashboardReportFromFilterPayloads: [] as Array<Record<string, unknown>>,
    writingMarkdownExports: 0,
    typedKnowledgeWritingContext: 0,
    typedKnowledgeReviewState: 0,
    agentChatTurn: 0,
    agentSessionDetail: 0,
    agentSessionTasks: 0,
    agentSessionEvents: 0,
    agentSessionArtifacts: 0,
    llmReportFileExportPayloads: [] as Array<{
      format: 'pdf' | 'docx'
      payload: Record<string, unknown>
    }>,
  }

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    const method = request.method()

    if (pathname === '/api/v1/health') {
      hits.opsHealth += 1
      await fulfillJson(route, healthPayload())
      return
    }

    if (pathname === '/api/v1/health/deep') {
      await fulfillJson(route, deepHealthPayload())
      return
    }

    if (pathname === '/api/v1/business-lines/evidence-matrix') {
      hits.businessLineEvidenceMatrix += 1
      await fulfillJson(route, businessLineEvidenceMatrixFixture())
      return
    }

    if (pathname === '/api/v1/business-lines/scheduled-matrix-artifact-summary') {
      hits.scheduledMatrixArtifactSummary += 1
      await fulfillJson(route, scheduledMatrixArtifactSummaryPayload())
      return
    }

    if (pathname === '/api/v1/business-lines/scheduled-artifact-summaries') {
      hits.scheduledArtifactSummaries += 1
      await fulfillJson(route, scheduledArtifactSummariesPayload())
      return
    }

    if (pathname === '/api/v1/business-lines/scheduled-artifact-drilldown') {
      hits.scheduledArtifactDrilldown += 1
      await fulfillJson(route, scheduledArtifactDrilldownFixture())
      return
    }

    if (pathname === '/api/v1/config/env') {
      await fulfillJson(route, {
        OPENAI_API_KEY: 'mocked-key-present',
        DATABASE_URL: 'mocked://database',
        SERPAPI_KEY: 'mocked-search-key',
        NEWS_API_KEY: 'mocked-news-key',
      })
      return
    }

    if (pathname === '/api/v1/codex-auth/status') {
      await fulfillJson(route, {
        authenticated: true,
        token_sink_authenticated: true,
        codex_oauth_enabled: false,
      })
      return
    }

    if (pathname === '/api/v1/projects' && method === 'GET') {
      await fulfillJson(route, projects.map((item) => ({
        ...item,
        is_active: item.project_key === activeProjectKey,
      })))
      return
    }

    if (pathname === '/api/v1/projects' && method === 'POST') {
      const payload = request.postDataJSON() as Partial<ProjectRow>
      const nextProject = {
        project_key: String(payload.project_key || 'mocked_created_project'),
        name: String(payload.name || 'Mocked Created Project'),
        schema_name: `${String(payload.project_key || 'mocked_created_project')}_schema`,
        enabled: payload.enabled !== false,
        is_active: false,
      }
      projects = [nextProject, ...projects.filter((item) => item.project_key !== nextProject.project_key)]
      await fulfillJson(route, nextProject)
      return
    }

    const projectActivateMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)\/activate$/)
    if (projectActivateMatch) {
      activeProjectKey = decodeURIComponent(projectActivateMatch[1] || MOCK_PROJECT_KEY)
      projects = projects.map((item) => ({ ...item, is_active: item.project_key === activeProjectKey }))
      await fulfillJson(route, { project_key: activeProjectKey, activated: true })
      return
    }

    const projectPatchMatch = pathname.match(/^\/api\/v1\/projects\/([^/]+)$/)
    if (projectPatchMatch && method === 'PATCH') {
      const key = decodeURIComponent(projectPatchMatch[1] || '')
      const payload = request.postDataJSON() as Partial<ProjectRow>
      projects = projects.map((item) => (item.project_key === key ? { ...item, ...payload } : item))
      await fulfillJson(route, { project_key: key, updated: true })
      return
    }

    if (pathname === '/api/v1/dashboard/stats') {
      hits.dashboardStats += 1
      await fulfillJson(route, {
        documents: {
          total: 58,
          recent_today: 4,
          recent_7d: 18,
          extraction_rate: 0.91,
          type_distribution: { mocked_report: 8, browser_note: 2 },
          source_refs: [{ id: 'mocked-dashboard-documents-source', table: 'documents' }],
        },
        sources: {
          total: 7,
          enabled: 6,
          source_refs: [{ id: 'mocked-dashboard-sources-source', table: 'source_library' }],
        },
        market_stats: {
          total: 12,
          states_count: 3,
          source_refs: [{ id: 'mocked-dashboard-market-source', table: 'market_stats' }],
        },
        tasks: {
          total: 9,
          running: 1,
          completed: 7,
          failed: 1,
          source_refs: [{ id: 'mocked-dashboard-tasks-source', table: 'process_tasks' }],
          frontdoor_tri_state: {
            states: ['success', 'degraded_success', 'failed'],
            counts: { success: 7, degraded_success: 1, failed: 1 },
            source_refs: [{ id: 'mocked-dashboard-frontdoor-source', table: 'ingest_registry' }],
          },
        },
        llm_report_quality: {
          summary: {
            total: 1,
            by_decision: { pass: 1 },
            readiness: { ready: 1 },
            avg_citation_coverage: 0.95,
            avg_evidence_coverage: 0.9,
            export_events: {
              total: 1,
              success: 1,
              trusted: 1,
              ui_read_only_context_included_count: 1,
              by_format: { pdf: 1 },
              by_integrity_mode: { artifact_token: 1 },
            },
          },
          actionability: { next_action: 'Mocked browser rail report detail is available.' },
          source_refs: [{ id: 'mocked-llm-report-source', table: 'llm_report_quality' }],
          recent_records: [
            {
              trace_id: 'trace-mocked-rail-58',
              request_id: 'req-mocked-rail-58',
              project_key: MOCK_PROJECT_KEY,
              decision: 'pass',
              readiness: 'ready',
              citation_coverage: 0.95,
              evidence_coverage: 0.9,
              job_id: 5801,
              job_status: 'completed',
              recorded_at: '2026-05-24T18:00:00Z',
              next_action: 'Open mocked report detail',
            },
          ],
          recent_export_events: [
            {
              trace_id: 'export-trace-mocked-rail-58',
              source_trace_id: 'trace-mocked-rail-58',
              request_id: 'req-mocked-rail-export-58',
              project_key: MOCK_PROJECT_KEY,
              export_format: 'pdf',
              export_outcome: 'success',
              export_integrity_mode: 'artifact_token',
              export_integrity_trusted: true,
              artifact_id: 'mocked-artifact-58',
              filename: 'mocked-rail-report-58.pdf',
              content_type: 'application/pdf',
              content_size_bytes: 2048,
              error_code: null,
              recorded_at: '2026-05-24T18:01:00Z',
              ui_read_only_context_included: true,
              ui_read_only_context_scope: 'ui_read_only_evidence_context',
            },
          ],
        },
        pending_actions: [
          {
            id: 'mocked-action-58',
            type: 'browser_rail_review',
            status: 'open',
            severity: 'low',
            title: 'Mocked rail action is not real-backend proof',
            source_metric: 'documents.total',
            source_refs: ['mocked-dashboard-documents-source'],
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/dashboard/drilldown') {
      await fulfillJson(route, {
        metric: url.searchParams.get('metric') || 'documents.total',
        source_ref: 'mocked-dashboard-documents-source',
        filters: { project_key: MOCK_PROJECT_KEY },
        row_count: 1,
        source_query: { scope: 'dashboard.stats', table: 'documents' },
        source_refs: [{ id: 'mocked-dashboard-documents-source', table: 'documents' }],
        sample_rows: [
          {
            id: 58,
            title: 'Mocked rail dashboard sample row',
            source_ref: 'mocked-dashboard-documents-source',
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/dashboard/report-from-filter') {
      hits.dashboardReportFromFilter += 1
      hits.dashboardReportFromFilterPayloads.push(request.postDataJSON() as Record<string, unknown>)
      await fulfillJson(route, {
        contract_version: 'dashboard.report_from_filter.v1',
        report_id: 'mocked-rail-report-58',
        draft_id: 5802,
        document_id: 5802,
        title: 'Mocked Rail 58 Report Draft',
        status: 'draft',
        quality: {
          status: 'ready',
          quality_gate_mode: 'mocked',
          checklist: [{ id: 'mocked', status: 'pass', detail: 'mocked browser rail only' }],
        },
        export_artifact: {
          artifact_id: 'mocked-artifact-58',
          artifact_token: 'mocked-token-58',
          artifact_sha256: 'mocked-sha256-58',
        },
      })
      return
    }

    if (pathname === '/api/v1/writing/export/markdown') {
      hits.writingMarkdownExports += 1
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown; charset=utf-8',
        headers: {
          'content-disposition': 'attachment; filename=mocked-rail-report-58.md',
        },
        body: '# Mocked Rail 58 Report Draft\n\nMocked markdown export for file renderer.',
      })
      return
    }

    if (pathname === '/api/v1/typed-knowledge/writing-context') {
      hits.typedKnowledgeWritingContext += 1
      await fulfillJson(route, typedKnowledgeWritingContextPayload())
      return
    }

    if (pathname === '/api/v1/typed-knowledge/governance/review-state') {
      hits.typedKnowledgeReviewState += 1
      const payload = request.postDataJSON() as Record<string, unknown>
      await fulfillJson(route, {
        contract_version: 'typed_knowledge.governance_review_state_mutation.v1',
        route_path: '/api/v1/typed-knowledge/governance/review-state',
        project_key: payload.project_key || MOCK_PROJECT_KEY,
        identity_ref: 'typed_knowledge:tk-mocked-58',
        object_type: payload.object_type || 'knowledge_item',
        object_key: payload.object_key || 'tk-mocked-58',
        previous: { review_state: 'pending' },
        current: { review_state: payload.review_state || 'human_confirmed' },
        actor: { actor_type: payload.actor_type || 'human', actor_id: payload.actor_id || 'writing-workbench' },
        live_db_write: false,
        readback: { status: 'mocked', not_real_backend_proof: true },
      })
      return
    }

    if (pathname === '/api/v1/writing/documents' && method === 'GET') {
      await fulfillJson(route, {
        items: [
          {
            id: 5804,
            project_key: MOCK_PROJECT_KEY,
            title: 'Mocked Typed Knowledge Draft',
            body_md: '## Mocked typed knowledge\n\nTyped knowledge writing context is attached.',
            status: 'draft',
            version: 3,
            etag: 'mocked-writing-etag-58',
            updated_at: '2026-05-24T18:08:00Z',
            metadata_json: {
              source: 'business-line-browser-actions',
              typed_knowledge_context: typedKnowledgeWritingContextPayload().typed_knowledge_context,
            },
          },
        ],
        total: 1,
      })
      return
    }

    if (pathname === '/api/v1/writing/documents/5804') {
      await fulfillJson(route, {
        id: 5804,
        project_key: MOCK_PROJECT_KEY,
        title: 'Mocked Typed Knowledge Draft',
        body_md: '## Mocked typed knowledge\n\nTyped knowledge writing context is attached.',
        status: 'draft',
        version: 3,
        etag: 'mocked-writing-etag-58',
        updated_at: '2026-05-24T18:08:00Z',
        metadata_json: {
          source: 'business-line-browser-actions',
          typed_knowledge_context: typedKnowledgeWritingContextPayload().typed_knowledge_context,
        },
      })
      return
    }

    if (pathname === '/api/v1/writing/documents/5804/citations') {
      await fulfillJson(route, { items: [], total: 0 })
      return
    }

    if (pathname === '/api/v1/writing/templates') {
      await fulfillJson(route, { items: [], total: 0 })
      return
    }

    if (pathname === '/api/v1/writing/keyword-cards') {
      const payload = request.postDataJSON() as Record<string, unknown>
      await fulfillJson(route, {
        cards: [
          {
            card_id: 'typed-knowledge-card-58',
            source_type: 'graph',
            title: 'Typed Knowledge Card 58',
            snippet: 'Mocked typed knowledge context card.',
            score: 0.91,
            relevance_tags: ['typed_knowledge'],
            quick_actions: [],
            extra: {
              received_typed_knowledge_context: Boolean((payload.context as Record<string, unknown> | undefined)?.typed_knowledge_context),
            },
          },
        ],
        selection_hash: 'sha256:mocked-selection-58',
        context_boundary: { contract_version: 'writing.context_boundary.e3.v1' },
      })
      return
    }

    const llmReportFileExportMatch = pathname.match(/^\/api\/v1\/llm-report\/export\/(pdf|docx)$/)
    if (llmReportFileExportMatch && method === 'POST') {
      const format = llmReportFileExportMatch[1] as 'pdf' | 'docx'
      hits.llmReportFileExportPayloads.push({
        format,
        payload: request.postDataJSON() as Record<string, unknown>,
      })
      await route.fulfill({
        status: 200,
        contentType: format === 'pdf'
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers: {
          'content-disposition': `attachment; filename=mocked-rail-report-58.${format}`,
          'x-llm-report-export-readiness': 'mocked-ready',
        },
        body: format === 'pdf' ? '%PDF-1.4 mocked' : 'PK mocked docx',
      })
      return
    }

    if (pathname === '/api/v1/dashboard/llm-report-detail') {
      hits.dashboardReportDetail += 1
      await fulfillJson(route, {
        contract_version: 'dashboard.llm_report_detail.v1',
        found: true,
        trace_id: url.searchParams.get('trace_id') || 'trace-mocked-rail-58',
        request_id: 'req-mocked-rail-58',
        project_key: MOCK_PROJECT_KEY,
        source_refs: [{ id: 'mocked-dashboard-documents-source', table: 'documents' }],
        source_query: { scope: 'dashboard.stats', table: 'documents' },
        report_artifact: { artifact_id: 'mocked-artifact-58', artifact_sha256: 'mocked-sha256-58' },
        quality_gate: { decision: 'pass', status: 'ready' },
        repair_context: { trace_id: 'trace-mocked-rail-58', real_backend_proof: false },
        export_events: [
          {
            export_format: 'pdf',
            export_outcome: 'mocked',
            ui_read_only_context_included: true,
            ui_read_only_context_scope: 'ui_read_only_evidence_context',
          },
        ],
        export_events_summary: {
          contract_version: 'dashboard.llm_report_detail.export_events_summary.v1',
          total: 1,
          ui_read_only_context_included_count: 1,
          read_only_context_semantics: (
            'ui_read_only_context_included_count is detail observability only; '
            + 'not proof, not quality gate input, not scheduled_run_evidence proof'
          ),
        },
      })
      return
    }

    if (pathname === '/api/v1/information-topology/topologies' && method === 'GET') {
      hits.topologyDiscovery += 1
      await fulfillJson(route, { items: [], total: 0 })
      return
    }

    if (pathname === '/api/v1/information-topology/topologies/read' && method === 'POST') {
      hits.topologyRead += 1
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { status: 'error', error: { code: 'NOT_FOUND', message: 'topology state was not found' } },
        }),
      })
      return
    }

    if (pathname === '/api/v1/project-customization/graph-config') {
      hits.graphConfig += 1
      await fulfillJson(route, {
        graph_node_types: {
          market: ['product', 'company', 'policy'],
          company: ['company'],
          product: ['product'],
          operation: ['operation'],
        },
        graph_node_labels: {
          product: '商品',
          company: '公司',
          policy: '政策',
          operation: '运营',
        },
        graph_relation_labels: {
          supplies: '供给',
          regulated_by: '监管',
        },
        graph_doc_types: {
          market: ['mocked_report'],
        },
      })
      return
    }

    if (pathname === '/api/v1/admin/market-graph') {
      hits.marketGraph += 1
      await fulfillJson(route, {
        nodes: [
          { id: 'mocked-product', type: 'product', name: 'Mocked Rail Product' },
          { id: 'mocked-company', type: 'company', name: 'Mocked Rail Company' },
          { id: 'mocked-policy', type: 'policy', name: 'Mocked Rail Policy' },
        ],
        edges: [
          {
            type: 'supplies',
            from: { type: 'company', id: 'mocked-company' },
            to: { type: 'product', id: 'mocked-product' },
          },
          {
            type: 'regulated_by',
            from: { type: 'product', id: 'mocked-product' },
            to: { type: 'policy', id: 'mocked-policy' },
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/admin/policy-graph' || pathname === '/api/v1/admin/content-graph') {
      await fulfillJson(route, { nodes: [], edges: [] })
      return
    }

    if (pathname === '/api/v1/workflow-graph/templates') {
      await fulfillJson(route, { items: [], total: 0 })
      return
    }

    if (pathname === '/api/v1/ingest/history') {
      await fulfillJson(route, [
        {
          id: 5803,
          task_id: 'mocked-ingest-history-58',
          task_name: 'single_url',
          status: 'completed',
          created_at: '2026-05-24T18:03:00Z',
          finished_at: '2026-05-24T18:04:00Z',
          degradation_flags: ['no_real_index_timestamp'],
          params: { trace_id: 'trace-mocked-ingest-history-58' },
        },
      ])
      return
    }

    if (pathname === '/api/v1/ingest/url/single') {
      hits.ingestSingleUrl += 1
      await fulfillJson(route, {
        task_id: 'mocked-ingest-task-58',
        status: 'queued',
        async: true,
        trace_id: 'trace-mocked-ingest-58',
        trace_chain: {
          contract_version: 'ingest_search.trace_chain.v1',
          trace_id: 'trace-mocked-ingest-58',
          submission_id: 'mocked-submission-58',
          task_id: 'mocked-ingest-task-58',
          retrieval_run_id: 'mocked-retrieval-run-58',
          provider_trace: { provider: 'route_mock' },
          fallback: { used: false },
          index_freshness: { backend: 'mocked-index' },
          known_limitations: ['not_real_backend_proof'],
        },
      })
      return
    }

    const retrievalRunMatch = pathname.match(/^\/api\/v1\/search\/runs\/([^/]+)$/)
    if (retrievalRunMatch) {
      hits.searchRetrievalRun += 1
      const runId = decodeURIComponent(retrievalRunMatch[1] || '')
      await fulfillJson(route, {
        retrieval_run_id: runId,
        retrieval_run: {
          run_id: runId,
          query: 'mocked single url',
          retrieval_family: 'main_search',
        },
        source_query: {
          scope: 'search.retrieval_run',
          query: 'mocked single url',
          project_key: MOCK_PROJECT_KEY,
        },
        source_refs: [
          { id: `search.retrieval_run:${runId}`, type: 'search_retrieval_run', retrieval_run_id: runId },
          { id: `search.evidence_hit:${runId}:1`, type: 'search_evidence_hit', source_id: 'mocked-source-a' },
        ],
        provider_trace: { status: 'mocked', provider: 'route_mock', retrieval_run_id: runId },
        index_freshness: { status: 'mocked', backend: 'mocked-index', freshness_state: 'available' },
        retrieval_run_readback: { status: 'passed', readback_available: true },
        known_limitations: ['not_real_backend_proof'],
      })
      return
    }

    if (pathname === '/api/v1/source_library/items') {
      await fulfillJson(route, [
        {
          item_key: 'mocked_source_item',
          name: 'Mocked Source Item',
          channel_key: 'browser_rail',
          scope: 'project',
          item_type: 'website',
          enabled: true,
          tags: ['mocked'],
          params: { site_entries: ['https://mocked.example.com'] },
          extra: { managed_by: 'browser_rail_mock' },
        },
      ])
      return
    }

    if (pathname === '/api/v1/source_library/items/grouped') {
      await fulfillJson(route, {
        by_handler: {
          browser_rail: [
            {
              item_key: 'mocked_source_item',
              name: 'Mocked Source Item',
              channel_key: 'browser_rail',
              enabled: true,
              tags: ['mocked'],
            },
          ],
        },
      })
      return
    }

    if (pathname === '/api/v1/source_library/channels') {
      await fulfillJson(route, [{ channel_key: 'browser_rail', name: 'Browser Rail', enabled: true }])
      return
    }

    if (pathname === '/api/v1/ingest/source-library/run') {
      hits.sourceLibraryRun += 1
      const payload = request.postDataJSON() as Record<string, unknown>
      const overrideParams = (payload.override_params || {}) as Record<string, unknown>
      const guard = (overrideParams.single_source_guard || {}) as Record<string, unknown>
      await fulfillJson(route, {
        task_id: 'mocked-source-library-task-58',
        trace_id: 'trace-source-library-run-58',
        status: 'queued',
        async: true,
        handler_key: payload.handler_key || 'domain_root',
        single_source_guard: guard,
        strict_source: guard,
        execution_fact: {
          contract_version: 'source_library.execution_fact.v1',
          reason_code: 'single_source_guard_passed',
          guard_status: guard.status || 'passed',
          report_source_ref: guard.report_source_ref || overrideParams.report_source_ref,
          single_source_guard: guard,
        },
        meta: {
          trace_id: 'trace-source-library-run-58',
        },
      })
      return
    }

    if (pathname === '/api/v1/resource_pool/urls') {
      await fulfillJson(route, [
        {
          id: 5801,
          url: 'https://mocked.example.com/report',
          domain: 'mocked.example.com',
          source: 'mocked-browser-rail',
          created_at: '2026-05-24T18:01:00Z',
        },
      ])
      return
    }

    if (pathname === '/api/v1/resource_pool/site_entries') {
      hits.siteEntries += 1
      if (method === 'POST') {
        await fulfillJson(route, {
          site_url: 'https://created.mocked.example.com',
          domain: 'created.mocked.example.com',
          entry_type: 'domain_root',
          source: 'manual',
          enabled: true,
        })
        return
      }
      const acceptedGuard = {
        contract_version: 'resource_pool.site_entry.single_source_guard.v1',
        strict_source: true,
        guarantee: true,
        status: 'passed',
        reason_code: null,
        source_ref: {
          tool: 'resource_pool.site_entry_review',
          site_entry_url: 'https://mocked.example.com',
          project_key: MOCK_PROJECT_KEY,
        },
        report_source_ref: 'resource_pool.site_entry:project:5802',
        allowed_urls: ['https://mocked.example.com'],
        allowed_count: 1,
        blocked_reason: null,
        runner_contract: {
          entrypoint: 'ingest.source_library.run',
          guard_field: 'override_params.site_entries',
        },
      }
      const blockedGuard = {
        ...acceptedGuard,
        guarantee: false,
        status: 'blocked',
        reason_code: 'review_rejected',
        report_source_ref: 'resource_pool.site_entry:project:5803',
        blocked_reason: 'review_rejected',
      }
      await fulfillJson(route, [
        {
          id: 5802,
          site_url: 'https://mocked.example.com',
          domain: 'mocked.example.com',
          entry_type: 'domain_root',
          source: 'mocked-browser-rail',
          lifecycle_state: 'accepted',
          lifecycle_transition: {
            contract_version: 'resource_pool.site_entry.lifecycle_transition.v1',
            from_state: 'candidate',
            to_state: 'accepted',
            status: 'accepted',
            reason: 'mocked_frontend_acceptance',
            report_source_ref: 'resource_pool.site_entry:project:5802',
          },
          enabled: true,
          source_ref: {
            kind: 'route_mock',
            note: 'not real-backend proof',
          },
          execution_plan_preview: {
            contract_version: 'source_library.item_execution_plan.v1',
            expected_entry_type: 'domain_root',
            site_entry_urls: ['https://mocked.example.com'],
            route_bucket_counts: { total: 1, domain_root: 1 },
            plan_meta: { preview_source: 'resource_pool.site_entry' },
          },
          review_closure: {
            contract_version: 'resource_pool.site_entry.review_closure.v1',
            status: 'ready_to_collect',
            reason_code: 'ready_to_collect',
            state: 'accepted',
            enabled: true,
            executable: true,
            blocked: false,
            block_reason: null,
            site_entry_url: 'https://mocked.example.com',
            entry_type: 'domain_root',
            report_source_ref: 'resource_pool.site_entry:project:5802',
            source_ref: acceptedGuard.source_ref,
            single_source_guard: acceptedGuard,
            evidence_binding: {
              contract_version: 'resource_pool.site_entry.evidence_binding.v1',
              target: 'evidence.resource_pool.site_entry:5802',
              site_entry_url: 'https://mocked.example.com',
              source_ref: acceptedGuard.source_ref,
              report_source_ref: 'resource_pool.site_entry:project:5802',
              report_refs: ['resource_pool.site_entry:project:5802', 'https://mocked.example.com'],
            },
            next_actions: [
              {
                action: 'collect_source_library_run',
                enabled: true,
                blocked: false,
                block_reason: null,
                method: 'POST',
                endpoint: '/api/v1/ingest/source-library/run',
                handler_key: 'domain_root',
                single_source_guard: acceptedGuard,
                payload: {
                  handler_key: 'domain_root',
                  async_mode: true,
                  override_params: {
                    site_entries: ['https://mocked.example.com'],
                    source_ref: acceptedGuard.source_ref,
                    report_source_ref: 'resource_pool.site_entry:project:5802',
                    review_state: 'accepted',
                    single_source_guard: acceptedGuard,
                  },
                },
              },
              {
                action: 'copy_report_source_ref',
                enabled: true,
                blocked: false,
                report_source_ref: 'resource_pool.site_entry:project:5802',
                source_ref: acceptedGuard.source_ref,
              },
            ],
          },
          evidence_binding: {
            contract_version: 'resource_pool.site_entry.evidence_binding.v1',
            target: 'evidence.resource_pool.site_entry:5802',
            site_entry_url: 'https://mocked.example.com',
            source_ref: acceptedGuard.source_ref,
            report_source_ref: 'resource_pool.site_entry:project:5802',
            report_refs: ['resource_pool.site_entry:project:5802', 'https://mocked.example.com'],
          },
          execution_fact: {
            contract_version: 'resource.execution_fact.v1',
            fact_ref: 'resource.execution_fact:resource_pool.site_entry:project:5802',
            reason_code: 'ready_to_collect',
            review_state: 'accepted',
            review_status: 'ready_to_collect',
            guard_status: 'passed',
            guard_reason_code: null,
            blocked: false,
            executable: true,
            report_source_ref: 'resource_pool.site_entry:project:5802',
            source_refs: [{ report_source_ref: 'resource_pool.site_entry:project:5802' }],
            single_source_guard: acceptedGuard,
          },
        },
        {
          id: 5803,
          site_url: 'https://blocked.mocked.example.com',
          domain: 'blocked.mocked.example.com',
          entry_type: 'domain_root',
          source: 'mocked-browser-rail',
          lifecycle_state: 'rejected',
          lifecycle_transition: {
            to_state: 'rejected',
            status: 'blocked',
            reason_code: 'review_rejected',
            report_source_ref: 'resource_pool.site_entry:project:5803',
          },
          enabled: true,
          review_closure: {
            status: 'blocked',
            reason_code: 'review_rejected',
            state: 'rejected',
            enabled: true,
            executable: false,
            blocked: true,
            block_reason: 'review_rejected',
            site_entry_url: 'https://blocked.mocked.example.com',
            entry_type: 'domain_root',
            report_source_ref: 'resource_pool.site_entry:project:5803',
            single_source_guard: blockedGuard,
            next_actions: [
              {
                action: 'collect_source_library_run',
                enabled: false,
                blocked: true,
                block_reason: 'review_rejected',
                handler_key: 'domain_root',
                single_source_guard: blockedGuard,
                payload: {
                  handler_key: 'domain_root',
                  async_mode: true,
                  override_params: {
                    site_entries: ['https://blocked.mocked.example.com'],
                    report_source_ref: 'resource_pool.site_entry:project:5803',
                    single_source_guard: blockedGuard,
                  },
                },
              },
            ],
          },
          evidence_binding: {
            report_source_ref: 'resource_pool.site_entry:project:5803',
            site_entry_url: 'https://blocked.mocked.example.com',
          },
          execution_fact: {
            reason_code: 'review_rejected',
            review_state: 'rejected',
            review_status: 'blocked',
            guard_status: 'blocked',
            guard_reason_code: 'review_rejected',
            report_source_ref: 'resource_pool.site_entry:project:5803',
            single_source_guard: blockedGuard,
          },
        },
      ])
      return
    }

    if (pathname === '/api/v1/resource_pool/site_entries/grouped') {
      await fulfillJson(route, {
        by_entry_type: {
          domain_root: [
            {
              site_url: 'https://mocked.example.com',
              domain: 'mocked.example.com',
              entry_type: 'domain_root',
              source: 'mocked-browser-rail',
            },
          ],
        },
      })
      return
    }

    if (pathname === '/api/v1/resource_pool/site_entries/lifecycle') {
      await fulfillJson(route, {
        site_url: 'https://mocked.example.com',
        domain: 'mocked.example.com',
        entry_type: 'domain_root',
        lifecycle_state: 'accepted',
        lifecycle_transition: {
          to_state: 'accepted',
          status: 'accepted',
          reason: 'mocked_frontend_acceptance',
          report_source_ref: 'resource_pool.site_entry:project:5802',
        },
        enabled: true,
        review_closure: {
          status: 'ready_to_collect',
          reason_code: 'ready_to_collect',
          report_source_ref: 'resource_pool.site_entry:project:5802',
        },
        evidence_binding: {
          report_source_ref: 'resource_pool.site_entry:project:5802',
        },
      })
      return
    }

    if (
      pathname === '/api/v1/resource_pool/extract/from-documents'
      || pathname === '/api/v1/resource_pool/discover/site-entries'
      || pathname === '/api/v1/resource_pool/site_entries/simplify'
    ) {
      await fulfillJson(route, {
        task_id: 'mocked-resource-task-58',
        status: 'queued',
        async: true,
        created: 1,
      })
      return
    }

    if (pathname === '/api/v1/admin/stats') {
      await fulfillJson(route, {
        documents: { total: 58, recent_today: 5 },
        social_data: { total: 12, recent_today: 2 },
        sources: { total: 7 },
        search_history: { total: 3 },
      })
      return
    }

    if (pathname === '/api/v1/admin/search-history') {
      await fulfillJson(route, [
        { id: 5801, topic: 'mocked rail search', last_search_time: '2026-05-24T18:05:00Z' },
      ])
      return
    }

    if (pathname === '/api/v1/admin/documents/list') {
      await fulfillJson(route, {
        items: [
          {
            id: 5801,
            title: 'Mocked Rail Ops Document',
            doc_type: 'mocked_report',
            state: 'ready',
            has_extracted_data: true,
            updated_at: '2026-05-24T18:06:00Z',
            extracted_data: { company: ['Mocked Rail Company'] },
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      })
      return
    }

    if (pathname === '/api/v1/admin/documents/bulk/extracted-data') {
      const payload = request.postDataJSON() as Record<string, unknown>
      if (payload.preview === true) {
        hits.adminBulkWritePreview += 1
        await fulfillJson(route, adminPreviewPayload('bulk_structured_write', payload))
        return
      }
      hits.adminBulkWriteExecute += 1
      await fulfillJson(route, adminExecutionPayload('bulk_structured_write', payload))
      return
    }

    if (pathname === '/api/v1/admin/documents/delete') {
      const payload = request.postDataJSON() as Record<string, unknown>
      if (payload.preview === true) {
        hits.adminDeletePreview += 1
        await fulfillJson(route, adminPreviewPayload('delete_documents', payload))
        return
      }
      hits.adminDeleteExecute += 1
      await fulfillJson(route, adminExecutionPayload('delete_documents', payload))
      return
    }

    if (pathname === '/api/v1/admin/export-graph') {
      await fulfillJson(route, {
        nodes: [{ id: 'mocked-company', type: 'company', name: 'Mocked Rail Company' }],
        edges: [],
      })
      return
    }

    if (pathname === '/api/v1/agent-chat/capabilities') {
      await fulfillJson(route, {
        tool_pool: {
          groups: {
            core: [
              {
                capability_id: 'agent_session.read',
                approval_level: 'none',
                concurrency_class: 'readonly',
                implemented: true,
                implementation_state: 'ready',
                enabled: true,
              },
            ],
            deferred: [],
            external_boundary: [],
          },
        },
      })
      return
    }

    if (pathname === '/api/v1/agent-chat/turn/stream') {
      hits.agentChatTurn += 1
      const events = mockedAgentReadbackEvents()
      const result = {
        final_answer: 'Agent session/event readback is visible for mocked-session-58.',
        agent_mode: 'core',
        contract_version: 'agent_core.turn.v1',
        runtime_variant: 'agent_core_v3',
        session: {
          session_id: 'mocked-session-58',
          current_phase: 'verification',
          status: 'completed',
          root_task_id: 'mocked-root-task-58',
          compat_mode: false,
        },
        tasks: [
          {
            task_id: 'mocked-agent-task-58',
            subject: 'Agent session/event readback',
            description: 'Read session and events for P1 frontend boundary.',
            status: 'completed',
            phase: 'verification',
            priority: 1,
            result_summary: 'agent session and events read back',
            read_set: ['agent_sessions', 'agent_events'],
            write_set: [],
          },
        ],
        events,
        capability_calls: [
          {
            capability_id: 'agent_session.read',
            tool_name: 'agent_session.read',
            status: 'completed',
            summary: 'session readback returned mocked-session-58',
          },
        ],
        artifacts: [],
        approvals: [],
        suggested_next_actions: [],
        stream: { url: '/api/v1/agent-sessions/mocked-session-58/stream' },
      }
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: `${events.map(agentCoreSse).join('')}event: agent_core.final_answer\ndata: ${JSON.stringify(result)}\n\n`,
      })
      return
    }

    if (pathname === '/api/v1/agent-sessions') {
      await fulfillJson(route, {
        sessions: [
          {
            session_id: 'mocked-session-58',
            project_key: MOCK_PROJECT_KEY,
            status: 'completed',
            goal: 'Mocked browser rail session',
            current_phase: 'verification',
            root_task_id: 'mocked-root-task-58',
            created_at: '2026-05-24T18:07:00Z',
            updated_at: '2026-05-24T18:08:00Z',
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/agent-sessions/mocked-session-58/tasks') {
      hits.agentSessionTasks += 1
      await fulfillJson(route, {
        tasks: [
          {
            task_id: 'mocked-agent-task-58',
            session_id: 'mocked-session-58',
            subject: 'Agent session/event readback',
            description: 'Read session and events for P1 frontend boundary.',
            status: 'completed',
            phase: 'verification',
            priority: 1,
            result_summary: 'agent session and events read back',
            read_set: ['agent_sessions', 'agent_events'],
            write_set: [],
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/agent-sessions/mocked-session-58/events') {
      hits.agentSessionEvents += 1
      await fulfillJson(route, { events: mockedAgentReadbackEvents() })
      return
    }

    if (pathname === '/api/v1/agent-sessions/mocked-session-58/artifacts') {
      hits.agentSessionArtifacts += 1
      await fulfillJson(route, {
        artifacts: [{ artifact_id: 'artifact-agent-readback-58', name: 'agent-readback.json', content: 'mocked rail memory' }],
      })
      return
    }

    if (pathname === '/api/v1/agent-sessions/mocked-session-58/stream') {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: 'event: agent_session.keepalive\ndata: {"event_type":"agent_session.keepalive","seq":4}\n\n',
      })
      return
    }

    if (pathname === '/api/v1/agent-sessions/mocked-session-58') {
      hits.agentSessionDetail += 1
      await fulfillJson(route, {
        session_id: 'mocked-session-58',
        project_key: MOCK_PROJECT_KEY,
        status: 'completed',
        goal: 'Mocked browser rail session',
        current_phase: 'verification',
        root_task_id: 'mocked-root-task-58',
        tasks: [
          {
            task_id: 'mocked-agent-task-58',
            session_id: 'mocked-session-58',
            subject: 'Agent session/event readback',
            status: 'completed',
            phase: 'verification',
            result_summary: 'agent session and events read back',
          },
        ],
        events: mockedAgentReadbackEvents(),
        messages: [],
        artifacts: [{ name: 'memory.md', content: 'mocked rail memory' }],
        approvals: [],
      })
      return
    }

    await fulfillJson(route, { items: [], total: 0 })
  })

  return hits
}

async function bootstrapMockedRail(page: Page) {
  await page.addInitScript((projectKey) => {
    window.localStorage.setItem('market_project_key', projectKey)
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  }, MOCK_PROJECT_KEY)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], {
    origin: `http://127.0.0.1:${process.env.FRONTEND_E2E_PORT || '4173'}`,
  })
}

test('batch 58 Dashboard -> Projects -> Graph -> Ingest/Search -> Resource -> Ops mocked browser rail (not real-backend proof)', async ({ page }) => {
  const hits = await setupMockedBusinessLineRail(page)
  await bootstrapMockedRail(page)

  await page.goto('/#/visual/dashboard')
  await expect(page.getByRole('heading', { name: '数据仪表盘' })).toBeVisible()
  await expect(page.getByText('Mocked rail action is not real-backend proof')).toBeVisible()
  const dashboardResetTelemetryBoundary = page.getByTestId('dashboard-scheduled-artifact-reset-telemetry-boundary')
  await expect(dashboardResetTelemetryBoundary).toBeVisible()
  await expect(dashboardResetTelemetryBoundary).toContainText('scheduled artifact reset telemetry boundary')
  await expect(dashboardResetTelemetryBoundary).toContainText('reset_empty_warning_view')
  await expect(dashboardResetTelemetryBoundary).toContainText('ui_event_log_only')
  await expect(dashboardResetTelemetryBoundary).toContainText('filter=warning_only->all')
  await expect(dashboardResetTelemetryBoundary).toContainText('sort=unchanged')
  await expect(dashboardResetTelemetryBoundary).toContainText('api_payload=unchanged')
  await expect(dashboardResetTelemetryBoundary).toContainText('scheduled_evidence_write=none')
  await expect(dashboardResetTelemetryBoundary).toContainText('scheduled_completion_proof=false')
  await expect(dashboardResetTelemetryBoundary).toContainText('scheduled_evidence_controller=scheduled_run_evidence')
  await expect(dashboardResetTelemetryBoundary).toContainText('scheduled_completion_proof unchanged')
  await expect(dashboardResetTelemetryBoundary).toContainText('not scheduled_run_evidence proof')
  await expect(dashboardResetTelemetryBoundary).not.toContainText('reset telemetry metadata unavailable')
  await expect(dashboardResetTelemetryBoundary).not.toContainText('fallback boundary:')
  await expect(page.getByRole('columnheader', { name: '只读上下文 trace 覆盖' })).toBeVisible()
  const exportAuditReadOnlyContextTrace = page.getByTestId('dashboard-export-audit-read-only-context-trace')
  await expect(exportAuditReadOnlyContextTrace).toBeVisible()
  await expect(exportAuditReadOnlyContextTrace).toContainText('ui_read_only_context_included=true')
  await expect(exportAuditReadOnlyContextTrace).toContainText('scope=ui_read_only_evidence_context')
  const exportEventsReadOnlyContextIncluded = page.getByTestId('dashboard-export-events-read-only-context-included')
  await expect(exportEventsReadOnlyContextIncluded).toBeVisible()
  await expect(exportEventsReadOnlyContextIncluded).toContainText('ui read-only context included 1')
  await expect(exportEventsReadOnlyContextIncluded).toContainText('trace coverage')
  await expect(exportEventsReadOnlyContextIncluded).toContainText('非 proof/trusted/success')
  await page.getByRole('button', { name: 'mocked-dashboard-documents-source' }).first().click()
  await expect(page.getByRole('cell', { name: 'Mocked rail dashboard sample row' })).toBeVisible()
  await page.getByRole('button', { name: '打开报告详情' }).first().click()
  await expect(page.getByText('当前报告详情 trace: trace-mocked-rail-58')).toBeVisible()
  const dashboardReportDetailResetTelemetryBoundary = page.getByTestId('dashboard-report-detail-reset-telemetry-boundary')
  await expect(dashboardReportDetailResetTelemetryBoundary).toBeVisible()
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('report detail reset telemetry boundary')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('reset_empty_warning_view')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('ui_event_log_only')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('filter=warning_only->all')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('sort=unchanged')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('api_payload=unchanged')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('scheduled_evidence_write=none')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('scheduled_completion_proof=false')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('scheduled_evidence_controller=scheduled_run_evidence')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('scheduled_completion_proof unchanged')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('not scheduled_run_evidence proof')
  await expect(dashboardReportDetailResetTelemetryBoundary).not.toContainText('reset telemetry metadata unavailable')
  await expect(dashboardReportDetailResetTelemetryBoundary).not.toContainText('fallback boundary:')
  const reportDetailExportEventsSummary = page.getByTestId('dashboard-report-detail-export-events-summary')
  await expect(reportDetailExportEventsSummary).toContainText('"ui_read_only_context_included_count": 1')
  await expect(reportDetailExportEventsSummary).toContainText('detail observability only')
  await expect(reportDetailExportEventsSummary).toContainText('not scheduled_run_evidence proof')
  const reportPayload = JSON.parse(await page.getByTestId('dashboard-report-payload').inputValue()) as {
    reset_telemetry_boundary_context?: unknown
    dashboard: {
      reset_telemetry_boundary_context: ResetTelemetryBoundaryContext
    }
    report_options: Record<string, unknown>
  }
  const resetTelemetryBoundaryContext = reportPayload.dashboard.reset_telemetry_boundary_context
  expectResetTelemetryBoundaryContext(resetTelemetryBoundaryContext)
  expect(resetTelemetryBoundaryContext.lines).toEqual(expect.arrayContaining([
    'reset_empty_warning_view',
    'ui_event_log_only',
    'filter=warning_only->all',
    'sort=unchanged',
    'api_payload=unchanged',
    'scheduled_evidence_write=none',
    'scheduled_completion_proof=false',
    'scheduled_evidence_controller=scheduled_run_evidence',
    'scheduled_completion_proof unchanged',
    'not scheduled_run_evidence proof',
  ]))
  expect(reportPayload.report_options.include_reset_telemetry_boundary_context).toBe(true)
  expect(reportPayload.reset_telemetry_boundary_context).toBeUndefined()
  await page.getByRole('button', { name: '复制报告请求' }).click()
  const copiedReportPayload = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))
  expect(copiedReportPayload).toEqual(reportPayload)
  await page.getByTestId('dashboard-generate-report-draft').click()
  await expect.poll(() => hits.dashboardReportFromFilterPayloads.length).toBe(1)
  expect(hits.dashboardReportFromFilterPayloads[0]).toEqual(reportPayload)
  await page.getByTestId('dashboard-export-pdf').click()
  await expect.poll(() => hits.llmReportFileExportPayloads.length).toBe(1)
  await expect(page.getByText('文件已导出: mocked-rail-report-58.pdf')).toBeVisible()
  await page.getByTestId('dashboard-export-docx').click()
  await expect.poll(() => hits.llmReportFileExportPayloads.length).toBe(2)
  await expect(page.getByText('文件已导出: mocked-rail-report-58.docx')).toBeVisible()
  expect(hits.writingMarkdownExports).toBe(2)
  const pdfExportPayload = hits.llmReportFileExportPayloads.find((item) => item.format === 'pdf')?.payload
  const docxExportPayload = hits.llmReportFileExportPayloads.find((item) => item.format === 'docx')?.payload
  expect(pdfExportPayload).toBeTruthy()
  expect(docxExportPayload).toBeTruthy()
  expectResetTelemetryBoundaryContext(
    pdfExportPayload?.reset_telemetry_boundary_context as ResetTelemetryBoundaryContext,
  )
  expectResetTelemetryBoundaryContext(
    docxExportPayload?.reset_telemetry_boundary_context as ResetTelemetryBoundaryContext,
  )
  expect(pdfExportPayload?.reset_telemetry_boundary_context).toEqual(resetTelemetryBoundaryContext)
  expect(docxExportPayload?.reset_telemetry_boundary_context).toEqual(resetTelemetryBoundaryContext)
  expect(hits.dashboardReportFromFilterPayloads[0]).toEqual(reportPayload)
  expect(hits.dashboardStats).toBeGreaterThanOrEqual(1)
  expect(hits.dashboardReportDetail).toBeGreaterThanOrEqual(1)
  expect(hits.dashboardReportFromFilter).toBe(1)

  await page.goto('/#/admin/projects')
  await expect(page.getByRole('heading', { name: '项目与模板' })).toBeVisible()
  await expect(page.getByTestId('projects-list')).toContainText(MOCK_PROJECT_KEY)
  await expect(page.getByTestId('projects-readiness-action-card')).toBeVisible()
  await expect(page.getByTestId('projects-readiness-action-label')).toContainText('可以提交任务')
  await page.getByTestId('projects-readiness-copy-action').click()
  await expect(page.getByTestId('projects-readiness-action-status')).toContainText('项目处置上下文已复制')
  const projectReadinessClipboard = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))
  expect(projectReadinessClipboard).toMatchObject({
    schema_version: 'projects.readiness.quick_action.v1',
    project_key: MOCK_PROJECT_KEY,
    readiness: 'ready',
    action_priority: 'low',
  })
  await page.getByTestId('projects-readiness-open-target').click()
  await expect(page.getByTestId('projects-readiness-action-status')).toContainText('已定位到处置目标')
  await page.getByTestId('projects-readiness-refresh-status').click()
  await expect(page.getByTestId('projects-readiness-action-status')).toContainText('项目 readiness 已刷新')
  await page.getByPlaceholder('demo_proj_2').fill('mocked_created_58')
  await page.getByPlaceholder('演示项目 2').fill('Mocked Created 58')
  await page.getByRole('button', { name: /^创建$/ }).click()
  await expect(page.getByTestId('projects-list')).toContainText('mocked_created_58')

  await page.goto('/#/visual/graph/market')
  await expect(page.getByRole('heading', { name: '市场图谱' })).toBeVisible()
  await expect(page.getByTestId('graph-chart-2d')).toBeVisible()
  await page.getByRole('button', { name: '刷新' }).last().click()
  await expect.poll(() => hits.marketGraph).toBeGreaterThanOrEqual(2)
  expect(hits.topologyDiscovery).toBeGreaterThanOrEqual(1)
  expect(hits.topologyRead).toBeGreaterThanOrEqual(1)
  expect(hits.graphConfig).toBeGreaterThanOrEqual(1)

  await page.goto('/#writing-workbench.html')
  await expect(page.getByTestId('writing-workbench-page')).toBeVisible()
  const typedKnowledgeContext = page.getByTestId('writing-typed-knowledge-context')
  await expect(typedKnowledgeContext).toBeVisible()
  await expect(typedKnowledgeContext).toContainText('知识上下文 1 条')
  await expect(typedKnowledgeContext).toContainText('tk-mocked-58')
  await expect(typedKnowledgeContext).toContainText('pending')
  await expect(typedKnowledgeContext).toContainText('live=true')
  await expect(page.getByTestId('writing-typed-knowledge-governance')).toBeEnabled()
  await page.getByTestId('writing-typed-knowledge-governance').click()
  await expect(page.getByText('资料已确认')).toBeVisible()
  expect(hits.typedKnowledgeWritingContext).toBeGreaterThanOrEqual(1)
  expect(hits.typedKnowledgeReviewState).toBe(1)

  // Agent Chat is now the Codex WebUI surface. Keep this browser rail focused
  // on the canonical host route and its iframe boundary; chat/session details
  // are owned by the embedded Codex application rather than MRW DOM selectors.
  const agentResponse = await page.goto('/#/workbench/agent')
  if (agentResponse) expect(agentResponse.ok()).toBeTruthy()
  await expect(page.getByTestId('codex-agent-page')).toBeVisible()
  await expect(page.getByTestId('codex-agent-frame')).toHaveAttribute('src', '/codex/')

  await page.goto('/#/workbench/ingest/specialized')
  await expect(page.getByRole('heading', { name: '单 URL 入库' })).toBeVisible()
  await page.getByPlaceholder('https://example.com/article').fill('https://mocked.example.com/report')
  await page.getByRole('button', { name: '执行单 URL 入库' }).click()
  await expect(page.getByTestId('ingest-action-status')).toContainText('证据链: ingest_search.trace_chain.v1')
  await expect(page.getByTestId('ingest-action-status')).toContainText('检索运行: mocked-retrieval-run-58')
  await expect(page.getByTestId('ingest-action-status')).toContainText('提供方: route_mock')
  await expect(page.getByTestId('ingest-action-status')).toContainText('索引后端: mocked-index')
  await expect(page.getByTestId('ingest-action-status')).toContainText('已知限制: not_real_backend_proof')
  await page.getByRole('button', { name: '加载检索运行详情' }).click()
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('来源引用: 2')
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('Provider trace: mocked')
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('索引新鲜度: mocked')
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('回读状态: passed')
  await expect(page.getByTestId('ingest-retrieval-readback')).toContainText('not_real_backend_proof')
  expect(hits.ingestSingleUrl).toBe(1)
  expect(hits.searchRetrievalRun).toBe(1)

  await page.goto('/#/admin/resources')
  await expect(page.getByRole('heading', { name: '信息资源库管理' }).first()).toBeVisible()
  await expect(page.getByText('https://mocked.example.com/report')).toBeVisible()
  await expect(page.getByText('https://mocked.example.com').first()).toBeVisible()
  await expect(page.getByText('transition:accepted').first()).toBeVisible()
  await expect(page.getByText('review_closure:ready_to_collect').first()).toBeVisible()
  await expect(page.getByText('source_ref:resource_pool.site_entry:project:5802').first()).toBeVisible()
  await expect(page.getByText('guard_status:passed').first()).toBeVisible()
  await expect(page.getByText('allowed_count:1').first()).toBeVisible()
  await expect(page.getByText('review_rejected').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '采纳后采集' }).first()).toBeEnabled()
  await expect(page.getByRole('button', { name: '采纳后采集' }).nth(1)).toBeDisabled()
  await page.getByRole('button', { name: '采纳后采集' }).first().click()
  await expect(page.getByText('trace_id=trace-source-library-run-58').first()).toBeVisible()
  await expect(page.getByText('guard_status=passed').first()).toBeVisible()
  expect(hits.sourceLibraryRun).toBe(1)
  await page.getByRole('textbox', { name: 'domain', exact: true }).fill('mocked.example.com')
  await page.getByRole('button', { name: '刷新列表' }).click()
  await expect.poll(() => hits.siteEntries).toBeGreaterThanOrEqual(2)

  await page.goto('/#/admin/ops')
  await expect(page.getByRole('heading', { name: '运行态状态' })).toBeVisible()
  await expect(page.getByText('mode mocked')).toBeVisible()
  await page.getByTestId('ops-technical-toggle').getByRole('button').click()
  await expect(page.getByRole('cell', { name: 'api', exact: true })).toBeVisible()
  const evidenceMatrix = page.getByTestId('ops-business-line-evidence-matrix')
  await expect(evidenceMatrix).toBeVisible()
  await expect(evidenceMatrix).toContainText('business_line.evidence_matrix.v2')
  await expect(evidenceMatrix).toContainText('覆盖所有条线')
  await expect(evidenceMatrix).toContainText('not_admin_only=true')
  await expect(evidenceMatrix).toContainText('business_line.vocabulary.current.v1')
  await expect(evidenceMatrix).toContainText('not_observed_without_live_worker_readback')
  const scheduledArtifactSummary = page.getByTestId('ops-business-line-scheduled-matrix-artifact-summary')
  await expect(scheduledArtifactSummary).toBeVisible()
  await expect(scheduledArtifactSummary).toContainText('missing')
  await expect(scheduledArtifactSummary).toContainText('no expected nightly artifact files were found')
  await expect(scheduledArtifactSummary).toContainText('scheduled_run_evidence')
  const scheduledArtifactSummaries = page.getByTestId('ops-business-line-scheduled-artifact-summaries')
  await expect(scheduledArtifactSummaries).toBeVisible()
  await expect(scheduledArtifactSummaries).toContainText('performance_capacity_baseline_nightly')
  await expect(scheduledArtifactSummaries).toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactSummaries).toContainText('business_line_worker_readback_project_matrix_nightly')
  await expect(scheduledArtifactSummaries).toContainText('missing')
  const scheduledArtifactDrilldown = page.getByTestId('ops-business-line-scheduled-artifact-drilldown')
  await expect(scheduledArtifactDrilldown).toBeVisible()
  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: all')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: source_order')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: source order from API payload; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 3/3')
  await expect(scheduledArtifactDrilldown).toContainText('performance_capacity_baseline_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('business_line_worker_readback_project_matrix_nightly')
  const laneSummaryRows = scheduledArtifactDrilldown.locator('table').first().locator('tbody tr')
  await expect(laneSummaryRows.nth(0)).toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('manual_dry_run')
  await expect(scheduledArtifactDrilldown).toContainText('missing')
  await expect(scheduledArtifactDrilldown).toContainText('artifact_count')
  await expect(scheduledArtifactDrilldown).toContainText('warning_count')
  await expect(scheduledArtifactDrilldown).toContainText('warning types')
  await expect(scheduledArtifactDrilldown).toContainText('severity counts')
  await expect(scheduledArtifactDrilldown).toContainText('highest severity')
  await expect(scheduledArtifactDrilldown).toContainText('severity rank')
  await expect(scheduledArtifactDrilldown).toContainText('severity order')
  await expect(scheduledArtifactDrilldown).toContainText('status counts')
  await expect(scheduledArtifactDrilldown).toContainText('artifact_identity_differs_from_latest')
  await expect(scheduledArtifactDrilldown).toContainText('warning: 1')
  await expect(scheduledArtifactDrilldown).toContainText('highest severity: warning')
  await expect(scheduledArtifactDrilldown).toContainText('severity rank: 1')
  await expect(scheduledArtifactDrilldown).toContainText('differs_from_latest: 1')
  await expect(scheduledArtifactDrilldown).toContainText('same_as_latest: 1')
  await expect(scheduledArtifactDrilldown).toContainText('not completion proof')
  await expect(scheduledArtifactDrilldown).toContainText('artifacts/performance_capacity_baseline_nightly/latest.json')
  await expect(scheduledArtifactDrilldown).toContainText('freshness')
  await expect(scheduledArtifactDrilldown).toContainText('rank 1/3')
  await expect(scheduledArtifactDrilldown).toContainText('latest')
  await expect(scheduledArtifactDrilldown).toContainText('stale')
  await expect(scheduledArtifactDrilldown).toContainText('identity match')
  await expect(scheduledArtifactDrilldown).toContainText('identity mismatch')
  await expect(scheduledArtifactDrilldown).toContainText('identity status: differs_from_latest')
  await expect(scheduledArtifactDrilldown).toContainText('identity status: same_as_latest')
  await expect(scheduledArtifactDrilldown).toContainText('identity warning: artifact_identity_differs_from_latest')
  await expect(scheduledArtifactDrilldown).toContainText('identity warning severity: warning')
  await expect(scheduledArtifactDrilldown).toContainText('artifact identity differs from latest artifact for this lane')
  const sameAsLatestArtifactRow = scheduledArtifactDrilldown.getByRole('row').filter({
    hasText: 'manual-dry-run-copy.json',
  })
  await expect(sameAsLatestArtifactRow).toContainText('identity status: same_as_latest')
  await expect(sameAsLatestArtifactRow).toContainText('identity match')
  await expect(sameAsLatestArtifactRow).toContainText('not completion proof')
  await expect(sameAsLatestArtifactRow).not.toContainText('identity warning:')
  await expect(sameAsLatestArtifactRow).not.toContainText('identity warning severity:')
  await expect(sameAsLatestArtifactRow).not.toContainText('scheduled_run_evidence')
  const missingMatrixLaneRows = scheduledArtifactDrilldown.getByRole('row').filter({
    hasText: 'business_line_worker_readback_project_matrix_nightly',
  }).filter({
    hasText: '<missing>',
  })
  await expect(missingMatrixLaneRows).toContainText('missing')
  await expect(missingMatrixLaneRows).toContainText('not completion proof')
  await expect(missingMatrixLaneRows).not.toContainText('scheduled_run_evidence')
  await expect(scheduledArtifactDrilldown).toContainText('size_bytes')
  await expect(scheduledArtifactDrilldown).toContainText('2.0 KiB')
  await expect(scheduledArtifactDrilldown).toContainText('sha256')
  await expect(scheduledArtifactDrilldown).toContainText('sha256: 0123456789ab...89abcdef')
  await expect(scheduledArtifactDrilldown).not.toContainText('absolute_path')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'sort warning priority' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by highest severity rank desc, warning count desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(laneSummaryRows.nth(0)).toContainText('performance_capacity_baseline_nightly')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'show warning lanes' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: warning_only')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by highest severity rank desc, warning count desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 1/3')
  await expect(laneSummaryRows.nth(0)).toContainText('performance_capacity_baseline_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('performance_capacity_baseline_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('not completion proof')
  await expect(scheduledArtifactDrilldown).not.toContainText('empty warning diagnostics:')
  await expect(scheduledArtifactDrilldown).not.toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactDrilldown).not.toContainText('business_line_worker_readback_project_matrix_nightly')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'show all lanes' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: all')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by highest severity rank desc, warning count desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 3/3')
  await expect(laneSummaryRows.nth(0)).toContainText('performance_capacity_baseline_nightly')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'sort warning count' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_count')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by warning count desc, severity rank desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(laneSummaryRows.nth(0)).toContainText('performance_capacity_baseline_nightly')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'sort artifact count' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: artifact_count')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by artifact count desc, warning count desc, severity rank desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(laneSummaryRows.nth(0)).toContainText('performance_capacity_baseline_nightly')
  await scheduledArtifactDrilldown.getByRole('button', { name: 'sort source order' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: source_order')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: source order from API payload; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(laneSummaryRows.nth(0)).toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('llm_report_token_state_retention_nightly')
  await expect(scheduledArtifactDrilldown).toContainText('business_line_worker_readback_project_matrix_nightly')
  const matrixDiagnosticsGuidance = page.getByTestId('ops-business-line-matrix-diagnostics-guidance')
  await expect(matrixDiagnosticsGuidance).toBeVisible()
  await expect(matrixDiagnosticsGuidance).toContainText('nightly-manifest.json:matrix_diagnostics')
  await expect(matrixDiagnosticsGuidance).toContainText('runtime_preflight_status')
  await expect(matrixDiagnosticsGuidance).toContainText('first_blocked_reason')
  await expect(matrixDiagnosticsGuidance).toContainText('scheduled_run_blocked')
  await expect(matrixDiagnosticsGuidance).toContainText('not completion proof')
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-ingest')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-search_discovery_index')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-resource_source_library')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-projects_config_workflow')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-dashboard_admin_governance')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-writing_knowledge_graph_agent')).toBeVisible()
  await expect(page.getByTestId('ops-business-line-evidence-matrix-line-runtime_ops')).toBeVisible()
  await expect(page.getByText('Mocked Rail Ops Document')).toBeVisible()
  await page.getByRole('button', { name: '选择当前页' }).click()
  await page.getByRole('button', { name: '预览删除' }).click()
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('preview evidence')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('delete_documents')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('执行结果可用')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('false')
  await page.getByTestId('ops-copy-preview-evidence-package').click()
  const previewClipboard = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))
  expect(previewClipboard).toMatchObject({
    action_kind: 'delete_documents',
    evidence_preview: { execution_result_available: false },
  })
  await page.getByRole('button', { name: '删除文档' }).click()
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('execution evidence')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('trace-admin-execution-delete_documents')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('recorded_in_response_only')
  await expect(page.getByTestId('ops-document-governance-preview')).toContainText('mocked browser rail does not mutate backend state')
  await page.getByTestId('ops-copy-preview-evidence-package').click()
  const executionClipboard = JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))
  expect(executionClipboard).toMatchObject({
    schema_version: 'ops.admin.governance_execution_readback.v1',
    action_kind: 'delete_documents',
    execution_result: { execution_result_available: true, affected_count: 1 },
    audit_event: { status: 'recorded_in_response_only' },
  })
  await page.getByRole('button', { name: '复制诊断包' }).click()
  await expect(page.getByText('运行态诊断包已复制')).toBeVisible()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(JSON.parse(clipboard)).toMatchObject({
    project_key: MOCK_PROJECT_KEY,
    runtime_mode: 'mocked',
  })
  expect(hits.opsHealth).toBeGreaterThanOrEqual(1)
  expect(hits.adminDeletePreview).toBe(1)
  expect(hits.adminDeleteExecute).toBe(1)
  expect(hits.businessLineEvidenceMatrix).toBeGreaterThanOrEqual(1)
  expect(hits.scheduledMatrixArtifactSummary).toBeGreaterThanOrEqual(1)
  expect(hits.scheduledArtifactSummaries).toBeGreaterThanOrEqual(1)
  expect(hits.scheduledArtifactDrilldown).toBeGreaterThanOrEqual(1)
})

test('batch 114 Dashboard reset telemetry fallback keeps missing metadata as not proof', async ({ page }) => {
  const hits = await setupMockedBusinessLineRail(page, {
    businessLineEvidenceMatrixFixture: businessLineEvidenceMatrixWithoutResetTelemetryPayload,
  })
  await bootstrapMockedRail(page)

  await page.goto('/#/visual/dashboard')
  await expect(page.getByRole('heading', { name: '数据仪表盘' })).toBeVisible()
  const dashboardResetTelemetryBoundary = page.getByTestId('dashboard-scheduled-artifact-reset-telemetry-boundary')
  await expect(dashboardResetTelemetryBoundary).toBeVisible()
  await expect(dashboardResetTelemetryBoundary).toContainText('reset telemetry metadata unavailable')
  await expect(dashboardResetTelemetryBoundary).toContainText('fallback boundary: not scheduled_run_evidence proof')
  await expect(dashboardResetTelemetryBoundary).toContainText('fallback boundary: scheduled_evidence_write=none')
  await expect(dashboardResetTelemetryBoundary).toContainText('fallback boundary: scheduled_completion_proof unchanged')
  await expect(dashboardResetTelemetryBoundary).not.toContainText('reset_empty_warning_view')
  await expect(dashboardResetTelemetryBoundary).not.toContainText('ui_event_log_only')
  const fallbackReportPayload = JSON.parse(await page.locator('textarea[readonly]').inputValue()) as {
    dashboard: {
      reset_telemetry_boundary_context: {
        scope: string
        source: string
        lines: string[]
        not_report_proof: boolean
        not_scheduled_run_evidence_proof: boolean
        scheduled_evidence_write: string
        scheduled_completion_proof: string
      }
    }
    report_options: Record<string, unknown>
  }
  const fallbackResetTelemetryBoundaryContext = fallbackReportPayload.dashboard.reset_telemetry_boundary_context
  expect(fallbackResetTelemetryBoundaryContext).toMatchObject({
    scope: 'ui_read_only_evidence_context',
    source: 'business_lines.evidence_matrix.ui_boundary.reset_telemetry',
    not_report_proof: true,
    not_scheduled_run_evidence_proof: true,
    scheduled_evidence_write: 'none',
    scheduled_completion_proof: 'unchanged',
  })
  expect(fallbackResetTelemetryBoundaryContext.lines).toEqual([
    'reset telemetry metadata unavailable',
    'fallback boundary: not scheduled_run_evidence proof',
    'fallback boundary: scheduled_evidence_write=none',
    'fallback boundary: scheduled_completion_proof unchanged',
  ])
  expect(fallbackResetTelemetryBoundaryContext.lines.join('\n')).not.toContain('reset_empty_warning_view')
  expect(fallbackResetTelemetryBoundaryContext.lines.join('\n')).not.toContain('ui_event_log_only')
  expect(fallbackReportPayload.report_options.include_reset_telemetry_boundary_context).toBe(true)

  await page.getByRole('button', { name: '打开报告详情' }).first().click()
  await expect(page.getByText('当前报告详情 trace: trace-mocked-rail-58')).toBeVisible()
  const dashboardReportDetailResetTelemetryBoundary = page.getByTestId('dashboard-report-detail-reset-telemetry-boundary')
  await expect(dashboardReportDetailResetTelemetryBoundary).toBeVisible()
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('reset telemetry metadata unavailable')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('fallback boundary: not scheduled_run_evidence proof')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('fallback boundary: scheduled_evidence_write=none')
  await expect(dashboardReportDetailResetTelemetryBoundary).toContainText('fallback boundary: scheduled_completion_proof unchanged')
  await expect(dashboardReportDetailResetTelemetryBoundary).not.toContainText('reset_empty_warning_view')
  await expect(dashboardReportDetailResetTelemetryBoundary).not.toContainText('ui_event_log_only')
  expect(hits.businessLineEvidenceMatrix).toBeGreaterThanOrEqual(1)
  expect(hits.dashboardReportDetail).toBeGreaterThanOrEqual(1)
})

test('batch 108 Ops scheduled artifact drilldown warning-only empty state is not completion proof', async ({ page }) => {
  const hits = await setupMockedBusinessLineRail(page, {
    scheduledArtifactDrilldownFixture: scheduledArtifactDrilldownNoWarningPayload,
  })

  await page.goto('/#/admin/ops')
  await page.getByTestId('ops-technical-toggle').getByRole('button').click()
  const scheduledArtifactDrilldown = page.getByTestId('ops-business-line-scheduled-artifact-drilldown')
  await expect(scheduledArtifactDrilldown).toBeVisible()
  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: all')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 3/3')

  await scheduledArtifactDrilldown.getByRole('button', { name: 'sort warning priority' }).click()
  await scheduledArtifactDrilldown.getByRole('button', { name: 'show warning lanes' }).click()

  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: warning_only')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 0/3')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning view: no lanes match the current warning-only filter and lane sort')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning view is not scheduled evidence passed')
  await expect(scheduledArtifactDrilldown).toContainText('scheduled_completion_proof unchanged')
  await expect(scheduledArtifactDrilldown).toContainText('only scheduled_run_evidence can close scheduled evidence')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning diagnostics: filter=warning_only')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning diagnostics: sort=warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning diagnostics: total_lanes=3')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning diagnostics: visible_lanes=0')
  await expect(scheduledArtifactDrilldown).toContainText('empty warning diagnostics: warning_lanes=0')

  const laneSummaryBody = scheduledArtifactDrilldown.locator('table').first().locator('tbody')
  const laneSummaryRows = laneSummaryBody.locator('tr')
  await expect(laneSummaryRows).toHaveCount(1)
  await expect(laneSummaryRows.first()).toContainText('empty warning view: no lanes match the current warning-only filter and lane sort')
  await expect(laneSummaryRows.first()).not.toContainText('scheduled_run_evidence')

  const artifactBody = scheduledArtifactDrilldown.locator('table').nth(1).locator('tbody')
  const artifactRows = artifactBody.locator('tr')
  await expect(artifactRows).toHaveCount(1)
  await expect(artifactRows.first()).toContainText('empty warning view: no lanes match the current warning-only filter and lane sort')
  await expect(artifactRows.first()).not.toContainText('scheduled_run_evidence')

  const scheduledArtifactDrilldownHitsBeforeReset = hits.scheduledArtifactDrilldown
  await scheduledArtifactDrilldown.getByRole('button', { name: 'reset empty warning view: show all lanes' }).click()
  await expect(scheduledArtifactDrilldown).toContainText('warning lane filter: all')
  await expect(scheduledArtifactDrilldown).toContainText('visible lanes: 3/3')
  await expect(scheduledArtifactDrilldown).not.toContainText('empty warning view: no lanes match the current warning-only filter and lane sort')
  await expect(scheduledArtifactDrilldown).not.toContainText('empty warning diagnostics:')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort: warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('lane sort explanation: sorted by highest severity rank desc, warning count desc, artifact count desc, lane asc; display order only; scheduled_completion_proof unchanged; not proof')
  await expect(scheduledArtifactDrilldown).toContainText('scheduled artifact UI event log')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: reset_empty_warning_view')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: from=warning_only')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: to=all')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: sort=warning_priority')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: api_payload=unchanged')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: scheduled_evidence_write=none')
  await expect(scheduledArtifactDrilldown).toContainText('ui telemetry event: scheduled_completion_proof=unchanged')
  expect(hits.scheduledArtifactDrilldown).toBe(scheduledArtifactDrilldownHitsBeforeReset)
  await expect(laneSummaryRows).toHaveCount(3)
  const laneProofTexts = await laneSummaryRows.locator('td:nth-child(12)').allTextContents()
  expect(laneProofTexts.map((text) => text.trim())).toEqual([
    'not completion proof',
    'not completion proof',
    'not completion proof',
  ])
  const artifactProofTexts = await artifactRows.locator('td:nth-child(4)').allTextContents()
  expect(artifactProofTexts.length).toBeGreaterThan(0)
  expect(artifactProofTexts.every((text) => text.trim() === 'not completion proof')).toBe(true)

  expect(hits.scheduledArtifactDrilldown).toBeGreaterThanOrEqual(1)
})
