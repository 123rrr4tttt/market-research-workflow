"""Registration projection for existing cross-application failure vocabularies.

Each family is a closed, read-only semantic registration.  This module does not
execute backend operations and does not introduce a second Failure primitive.
"""

from __future__ import annotations

# pyright: reportMissingTypeStubs=false

from typing import Literal, get_args

from functorial_kit import define_failure_family


IngestLongCycleContractFailureCode = Literal["required_text_empty"]
WritingRequestContractFailureCode = Literal["query_required"]
SuccessorRuntimeDtoContractFailureCode = Literal[
    "command_payload_kind_mismatch",
    "query_params_kind_mismatch",
    "successful_envelope_data_missing",
    "successful_envelope_error_present",
    "error_envelope_details_missing",
    "error_envelope_data_present",
    "non_error_envelope_details_present",
    "sse_event_not_after_cursor",
    "sse_events_not_strictly_ascending",
    "sse_next_seq_mismatch",
]
DatabaseSessionRetryFailureCode = Literal["operation_failed", "retry_exhausted"]
KeywordMemoryContractFailureCode = Literal["keyword_required"]
CodexInvocationFailureCode = Literal[
    "prompt_required",
    "cli_not_installed",
    "cli_auth_unavailable",
    "cli_command_failed",
    "home_preparation_failed",
    "process_start_failed",
    "endpoint_timeout",
    "server_event_error",
    "rpc_error",
    "thread_id_missing",
    "empty_output",
]
LlmReportRequestFailureCode = Literal[
    "invalid_export_token_format",
    "invalid_export_token_signature",
    "invalid_export_token_payload",
    "unsupported_export_token_contract",
    "export_token_markdown_hash_mismatch",
    "export_token_missing_gate",
    "export_token_missing_expiry",
    "export_token_expired",
    "export_token_actor_mismatch",
    "export_token_revoked",
    "export_token_already_used",
    "retention_days_invalid",
    "topic_required",
    "unsupported_export_format",
]
ProjectOperationFailureCode = Literal[
    "project_key_required",
    "project_binding_conflict",
    "schema_binding_conflict",
    "workflow_not_found",
    "workflow_handler_not_found",
    "prefix_required",
]
SourceLibraryContractFailureCode = Literal[
    "external_project_manifest_invalid",
    "external_project_evidence_insufficient",
    "external_project_execution_mode_unsupported",
    "channel_not_found",
    "channel_disabled",
    "required_params_missing",
    "crawler_project_required",
    "crawler_spider_required",
    "channel_credentials_missing",
    "channel_provider_unsupported",
    "policy_state_required",
    "market_keywords_required",
    "google_news_keywords_required",
    "url_routing_urls_required",
    "frontdoor_runtime_targets_invalid",
    "frontdoor_entrypoint_rejected",
    "source_item_disabled",
]
SourceLibraryLoaderFailureCode = Literal["yaml_parser_unavailable"]
SourceLibraryResolverFailureCode = Literal[
    "parallel_item_failed",
    "parallel_timeout",
]
ReportQueryContractFailureCode = Literal["date_format_invalid"]
RequestIdentityFailureCode = Literal[
    "actor_context_invalid",
    "authority_contract_invalid",
    "observation_type_invalid",
    "trusted_actor_required",
]
PromptTimeDensityRequestFailureCode = Literal[
    "bucket_invalid",
    "candidate_window_format_invalid",
    "smoothing_invalid",
    "date_range_invalid",
    "keyword_required",
    "peak_percentile_out_of_range",
    "uncertainty_out_of_range",
    "candidate_windows_required",
    "eta_negative",
    "delta_max_out_of_range",
    "tau_negative",
    "min_overlap_out_of_range",
    "target_overlap_out_of_range",
    "max_windows_not_positive",
]
TaskReadbackContractFailureCode = Literal["line_key_required"]
OnlineLotteryCompatibilityFailureCode = Literal["attribute_not_found"]


ingest_long_cycle_contract_failures = define_failure_family(
    "ingest.long_cycle.contract_failure",
    get_args(IngestLongCycleContractFailureCode),
)
writing_request_contract_failures = define_failure_family(
    "writing.request.contract_failure",
    get_args(WritingRequestContractFailureCode),
)
successor_runtime_dto_contract_failures = define_failure_family(
    "successor_runtime.dto.contract_failure",
    get_args(SuccessorRuntimeDtoContractFailureCode),
)
database_session_retry_failures = define_failure_family(
    "database.session_retry.failure",
    get_args(DatabaseSessionRetryFailureCode),
)
keyword_memory_contract_failures = define_failure_family(
    "keyword_memory.contract_failure",
    get_args(KeywordMemoryContractFailureCode),
)
codex_invocation_failures = define_failure_family(
    "codex.invocation.failure",
    get_args(CodexInvocationFailureCode),
)
llm_report_request_failures = define_failure_family(
    "llm.report.request.failure",
    get_args(LlmReportRequestFailureCode),
)
project_operation_failures = define_failure_family(
    "project.operation.failure",
    get_args(ProjectOperationFailureCode),
)
source_library_contract_failures = define_failure_family(
    "source_library.contract_failure",
    get_args(SourceLibraryContractFailureCode),
)
source_library_loader_failures = define_failure_family(
    "source_library.loader.failure",
    get_args(SourceLibraryLoaderFailureCode),
)
source_library_resolver_failures = define_failure_family(
    "source_library.resolver.failure",
    get_args(SourceLibraryResolverFailureCode),
)
report_query_contract_failures = define_failure_family(
    "report.query.contract_failure",
    get_args(ReportQueryContractFailureCode),
)
request_identity_failures = define_failure_family(
    "request_identity.failure",
    get_args(RequestIdentityFailureCode),
)
prompt_time_density_request_failures = define_failure_family(
    "prompt_time_density.request.failure",
    get_args(PromptTimeDensityRequestFailureCode),
)
task_readback_contract_failures = define_failure_family(
    "task.readback.contract_failure",
    get_args(TaskReadbackContractFailureCode),
)
online_lottery_compatibility_failures = define_failure_family(
    "online_lottery.compatibility.failure",
    get_args(OnlineLotteryCompatibilityFailureCode),
)


__all__ = [
    "CodexInvocationFailureCode",
    "DatabaseSessionRetryFailureCode",
    "IngestLongCycleContractFailureCode",
    "KeywordMemoryContractFailureCode",
    "LlmReportRequestFailureCode",
    "OnlineLotteryCompatibilityFailureCode",
    "ProjectOperationFailureCode",
    "PromptTimeDensityRequestFailureCode",
    "ReportQueryContractFailureCode",
    "RequestIdentityFailureCode",
    "SuccessorRuntimeDtoContractFailureCode",
    "SourceLibraryContractFailureCode",
    "SourceLibraryLoaderFailureCode",
    "SourceLibraryResolverFailureCode",
    "TaskReadbackContractFailureCode",
    "WritingRequestContractFailureCode",
    "codex_invocation_failures",
    "database_session_retry_failures",
    "ingest_long_cycle_contract_failures",
    "keyword_memory_contract_failures",
    "llm_report_request_failures",
    "online_lottery_compatibility_failures",
    "project_operation_failures",
    "prompt_time_density_request_failures",
    "report_query_contract_failures",
    "request_identity_failures",
    "source_library_contract_failures",
    "source_library_loader_failures",
    "source_library_resolver_failures",
    "successor_runtime_dto_contract_failures",
    "task_readback_contract_failures",
    "writing_request_contract_failures",
]
