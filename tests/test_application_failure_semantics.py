from __future__ import annotations

import ast
from pathlib import Path

# pyright: reportMissingTypeStubs=false
from functorial_kit import Failure, FailureFamily
import pytest

from mrw_functorial_kit.core.application_failure_semantics import (
    codex_invocation_failures,
    database_session_retry_failures,
    ingest_long_cycle_contract_failures,
    keyword_memory_contract_failures,
    llm_report_request_failures,
    online_lottery_compatibility_failures,
    project_operation_failures,
    prompt_time_density_request_failures,
    report_query_contract_failures,
    request_identity_failures,
    successor_runtime_dto_contract_failures,
    source_library_contract_failures,
    source_library_loader_failures,
    source_library_resolver_failures,
    task_readback_contract_failures,
    writing_request_contract_failures,
)


ROOT = Path(__file__).resolve().parents[1]
LLM_EXPORT_SOURCE = ROOT / "main/backend/app/services/llm_report_export.py"

EXPECTED_FAMILIES: tuple[tuple[FailureFamily, str, tuple[str, ...]], ...] = (
    (
        ingest_long_cycle_contract_failures,
        "ingest.long_cycle.contract_failure",
        ("required_text_empty",),
    ),
    (
        writing_request_contract_failures,
        "writing.request.contract_failure",
        ("query_required",),
    ),
    (
        successor_runtime_dto_contract_failures,
        "successor_runtime.dto.contract_failure",
        (
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
        ),
    ),
    (
        database_session_retry_failures,
        "database.session_retry.failure",
        ("operation_failed", "retry_exhausted"),
    ),
    (
        keyword_memory_contract_failures,
        "keyword_memory.contract_failure",
        ("keyword_required",),
    ),
    (
        codex_invocation_failures,
        "codex.invocation.failure",
        (
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
        ),
    ),
    (
        llm_report_request_failures,
        "llm.report.request.failure",
        (
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
        ),
    ),
    (
        project_operation_failures,
        "project.operation.failure",
        (
            "project_key_required",
            "project_binding_conflict",
            "schema_binding_conflict",
            "workflow_not_found",
            "workflow_handler_not_found",
            "prefix_required",
        ),
    ),
    (
        source_library_contract_failures,
        "source_library.contract_failure",
        (
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
        ),
    ),
    (
        source_library_loader_failures,
        "source_library.loader.failure",
        ("yaml_parser_unavailable",),
    ),
    (
        source_library_resolver_failures,
        "source_library.resolver.failure",
        ("parallel_item_failed", "parallel_timeout"),
    ),
    (
        report_query_contract_failures,
        "report.query.contract_failure",
        ("date_format_invalid",),
    ),
    (
        request_identity_failures,
        "request_identity.failure",
        (
            "actor_context_invalid",
            "authority_contract_invalid",
            "observation_type_invalid",
            "trusted_actor_required",
        ),
    ),
    (
        prompt_time_density_request_failures,
        "prompt_time_density.request.failure",
        (
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
        ),
    ),
    (
        task_readback_contract_failures,
        "task.readback.contract_failure",
        ("line_key_required",),
    ),
    (
        online_lottery_compatibility_failures,
        "online_lottery.compatibility.failure",
        ("attribute_not_found",),
    ),
)


def _llm_report_export_token_failure_sites() -> dict[str, tuple[str, ...]]:
    module = ast.parse(LLM_EXPORT_SOURCE.read_text(encoding="utf-8"))
    sites_by_code: dict[str, list[str]] = {}
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "_report_export_failure"):
            continue
        assert node.args and isinstance(node.args[0], ast.Constant), (
            "_report_export_failure call does not use one literal code"
        )
        code = node.args[0].value
        assert isinstance(code, str), "_report_export_failure code is not a string literal"
        site = next(
            (
                keyword.value.value
                for keyword in node.keywords
                if keyword.arg == "site" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str)
            ),
            None,
        )
        assert site, f"_report_export_failure({code!r}) has no literal source site witness"
        sites_by_code.setdefault(code, []).append(site)
    return {code: tuple(sites) for code, sites in sites_by_code.items()}


@pytest.mark.parametrize(("family", "expected_name", "expected_codes"), EXPECTED_FAMILIES)
def test_INVARIANT__application_failure_families_are_exact(
    family: FailureFamily,
    expected_name: str,
    expected_codes: tuple[str, ...],
) -> None:
    assert family.name == expected_name
    assert family.codes == expected_codes
    assert len(set(expected_codes)) == len(expected_codes)


def test_INVARIANT__llm_token_codes_are_existing_source_strings() -> None:
    token_codes = llm_report_request_failures.codes[:11]
    failure_sites = _llm_report_export_token_failure_sites()
    assert set(token_codes) <= set(failure_sites)
    assert all(failure_sites[code] for code in token_codes)
    assert set(failure_sites) == {*token_codes, "unsupported_export_format"}
    assert llm_report_request_failures.codes[11:] == (
        "retention_days_invalid",
        "topic_required",
        "unsupported_export_format",
    )


@pytest.mark.parametrize(("family", "_expected_name", "expected_codes"), EXPECTED_FAMILIES)
def test_INVARIANT__application_families_reject_unknown_codes(
    family: FailureFamily,
    _expected_name: str,
    expected_codes: tuple[str, ...],
) -> None:
    unknown_code = "UNREGISTERED_APPLICATION_FAILURE_CODE"
    with pytest.raises(ValueError, match=f"failure family {family.name}: unknown code '{unknown_code}'"):
        family.fail(unknown_code, "outside the closed family")

    assert all(family.fail(code, "inside the closed family") for code in expected_codes)


@pytest.mark.parametrize(("family", "_expected_name", "expected_codes"), EXPECTED_FAMILIES)
def test_INVARIANT__application_failure_values_use_kit_failure_structure(
    family: FailureFamily,
    _expected_name: str,
    expected_codes: tuple[str, ...],
) -> None:
    code = expected_codes[0]
    context = {"representative_code": code}
    failure = family.fail(code, "registered application failure", context)

    assert isinstance(failure, Failure)
    assert family.matches(failure)
    assert failure.family == family.name
    assert failure.code == code
    assert failure.message == "registered application failure"
    assert failure.context == context
    assert failure.failure is True
