"""Focused authority metadata for W03 ingest and provider-effect builders."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = REPO_ROOT / "main" / "backend" / "app" / "services"
WITNESS = "test:test_w03_ingest_ports_authority_metadata"

EXPECTED_METADATA: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "collect_runtime/adapters/source_library.py",
        "build_source_library_authority_output",
        "CollectJsonObject",
        "view",
        "terminal_output+frontdoor_ingress+postprocess_frontdoor+legacy_result",
    ),
    (
        "collect_runtime/adapters/source_library.py",
        "build_source_library_compat_projection",
        "CollectJsonObject",
        "view",
        "authority_output",
    ),
    ("collect_runtime/display_meta.py", "build_display_meta", "CollectJsonObject", "view", "request+result+summary"),
    (
        "ingest/canary_handoff.py",
        "build_single_url_canary_handoff",
        "dict[str, object]",
        "view",
        "ingress_envelope+postprocess_frontdoor+writer_result+metrics_payload+live_canary_evidence",
    ),
    (
        "ingest/canary_handoff_live.py",
        "build_production_like_handoff_evidence",
        "dict[str, object]",
        "generated_evidence",
        "repo_local_api_responses+db_readback",
    ),
    (
        "ingest/canary_metrics.py",
        "build_configured_provider_canary_boundary",
        "dict[str, object]",
        "external_claim",
        "live_canary_evidence+configured_provider_evidence",
    ),
    (
        "ingest/canary_metrics.py",
        "build_single_url_provider_evidence_boundary",
        "dict[str, object]",
        "external_claim",
        "provider_evidence+source_record",
    ),
    (
        "ingest/canary_metrics.py",
        "build_ingest_canary_metrics_readiness",
        "IngestCanaryMetricsReadinessReport",
        "preflight",
        "handoff+live_canary_evidence+metric_readback_evidence+contract_constants",
    ),
    (
        "ingest/canary_metrics_readback.py",
        "build_canary_metrics_readback_record",
        "dict[str, object]",
        "generated_evidence",
        "handoff+project_key+snapshot_digest_inputs",
    ),
    (
        "ingest/canary_strict_promotion.py",
        "build_strict_promotion_readiness",
        "StrictPromotionReadiness",
        "preflight",
        "live_canary_evidence+metrics_artifacts+ops_promotion_evidence+contract_constants",
    ),
    ("ingest/frontdoor_contract.py", "build_frontdoor_envelope", "dict[str, Any]", "view", "ingress_inputs+collection_payload+trace_contract"),
    ("ingest/frontdoor_ingress.py", "build_frontdoor_ingress_envelope", "FrontdoorIngressEnvelope", "view", "ingress_inputs+normalized_source_ref"),
    ("ingest/frontdoor_ingress.py", "build_source_library_ingress_envelope", "FrontdoorIngressEnvelope", "view", "terminal_output+legacy_result+frontdoor_route_inputs"),
    ("ingest/frontdoor_ingress.py", "build_raw_import_ingress_envelope", "FrontdoorIngressEnvelope", "view", "raw_import_payload+item"),
    ("ingest/frontdoor_ingress.py", "build_discovery_ingress_envelope", "FrontdoorIngressEnvelope", "view", "discovery_item"),
    ("ingest/frontdoor_router_contract.py", "build_frontdoor_fetch_router_contract", "dict[str, Any]", "view", "router_inputs+fallback_evidence+diagnostics+router_contract_constants"),
    ("ingest/frontdoor_slo.py", "build_frontdoor_slo_payload", "dict[str, object]", "view", "summary+tri_state_contract+latency_samples"),
    ("ingest/guardrail_rollout.py", "build_ingest_guardrail_rollout_readiness", "IngestGuardrailRolloutReadiness", "preflight", "rollout_inputs+visibility_fields+rollout_contract_constants"),
    ("ingest/light_filter.py", "build_light_filter_not_run", "dict[str, object]", "view", "filter_reason_input+light_filter_defaults"),
    ("ingest/meaningful_gate.py", "build_gateplus_snapshot", "dict[str, object]", "view", "url_gate+content_gate+provenance_gate"),
    ("ingest/metrics_payload.py", "build_metrics_payload_from_summary", "dict[str, object]", "view", "metrics_summary"),
    ("ingest/metrics_payload.py", "build_metrics_payload_for_result", "dict[str, object]", "view", "collect_result+job_meta"),
    ("ingest/retry_policy.py", "build_retry_observability", "RetryObservability", "view", "retry_payload+retry_reason_contract"),
    ("ingest/source_search_contract.py", "build_query_url_from_contract", "str", "view", "template_url+query_terms+search_contract"),
    ("ingest/structured_extraction.py", "build_structured_summary", "dict[str, object]", "view", "extracted_data+extraction_outcome_inputs"),
    ("ingest/terminal_normalizer.py", "build_terminal_ingest_payload", "dict[str, object]", "view", "document_candidate+ingress_envelope+extraction_outcome+terminal_context"),
    ("resource_pool/candidate_source_plan.py", "build_candidate_source_plan", "CandidateSourcePlan", "view", "entry_type+policy_category+search_feature_flags"),
    ("resource_pool/candidate_source_plan.py", "plan_to_metadata", "dict[str, Any]", "view", "candidate_source_plan"),
    ("resource_pool/search_capabilities.py", "build_capability_candidates", "list[SearchCapabilityCandidate]", "view", "strategy+raw_candidates+url_normalization"),
    ("resource_pool/search_result_parser_profiles.py", "build_search_result_parser_profile", "SearchResultParserProfile", "view", "entry_domain+requested_parser_profile+parser_profile_constants"),
    ("resource_pool/search_template_service.py", "build_search_template_urls", "tuple[list[str], int]", "view", "search_template+query_terms+pagination_params"),
)


def _return_annotation(path: Path, function_name: str) -> ast.Subscript:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    annotation = function.returns
    assert isinstance(annotation, ast.Subscript)
    assert ast.unparse(annotation.value) == "Annotated"
    assert isinstance(annotation.slice, ast.Tuple)
    return annotation


def test_w03_ingest_ports_authority_metadata() -> None:
    witness_name = WITNESS.removeprefix("test:")
    test_functions = {
        node.name
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    assert witness_name in test_functions
    seen: set[tuple[str, str]] = set()
    for relative_path, function_name, return_type, derived_as, fact_source in EXPECTED_METADATA:
        seen.add((relative_path, function_name))
        annotation = _return_annotation(APP_ROOT / relative_path, function_name)
        return_node, metadata_node = annotation.slice.elts
        assert ast.unparse(return_node) == return_type
        metadata = ast.literal_eval(metadata_node)
        assert metadata.startswith("kit:non-authoritative ")
        assert f"derived_as={derived_as} " in metadata
        assert f"fact_source={fact_source} " in metadata
        assert f"witness={WITNESS}" in metadata
    assert len(EXPECTED_METADATA) == 31
    assert len(seen) == 31
