from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.build_crawler_public_replay_shard_outputs import build_public_shard_outputs
from scripts.build_single_url_provider_credentials_evidence import (
    build_provider_credentials_evidence,
)
from scripts.build_time_semantics_configured_live_evidence import build_evidence
from scripts.c9_projection_rebuild import build_loss_profile
from scripts.check_source_time_production_readiness import build_check
from scripts.check_wave14_vectorization_provider_capability import build_contract
from scripts.cleanup_llm_report_export_token_state import build_cleanup_report
from scripts.flake_trend import build_summary
from scripts.remove_cn_policy_docs import build_query


METADATA = {
    build_public_shard_outputs: "kit:non-authoritative derived_as=generated_evidence",
    build_provider_credentials_evidence: "kit:non-authoritative derived_as=generated_evidence",
    build_evidence: "kit:non-authoritative derived_as=generated_evidence",
    build_loss_profile: "kit:non-authoritative derived_as=view",
    build_check: "kit:non-authoritative derived_as=generated_evidence",
    build_contract: "kit:non-authoritative derived_as=preflight",
    build_cleanup_report: "kit:non-authoritative derived_as=generated_evidence",
    build_summary: "kit:non-authoritative derived_as=view",
    build_query: "kit:prepared-command effect_boundary=sqlalchemy.session.query",
}

WORKFLOW_SMOKE_SOURCE = (
    Path(__file__).resolve().parents[2] / "scripts/workflow_graph_smoke_local.py"
)
FACT_SOURCES = {
    build_public_shard_outputs: "fact_source=manifest+source_output+shard_payloads",
    build_provider_credentials_evidence: "fact_source=env_file+env+live_probe",
    build_evidence: (
        "fact_source=prompt_time_policy_decision_logs+prompt_time_window_feedback"
    ),
    build_loss_profile: "fact_source=sink_loss_profile_catalog",
    build_check: "fact_source=runtime_contracts+live_evidence+repo_token_checks",
    build_contract: (
        "fact_source=wave10_contract+wave12_provider_readiness+repo_topics"
    ),
    build_cleanup_report: (
        "fact_source=prune_llm_report_export_token_states.summary"
    ),
    build_summary: "fact_source=junit_xml_history",
}


def test_c15_backend_misc_cli_report_metadata_preserves_abi() -> None:
    assert len(METADATA) == 9

    for function, expected_metadata in METADATA.items():
        return_type = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_type) is Annotated
        annotations = [value for value in get_args(return_type)[1:] if isinstance(value, str)]
        assert len(annotations) == 1
        metadata = annotations[0]
        assert metadata.startswith(expected_metadata)
        assert "witness=test:test_c15_backend_misc_cli_report_metadata_preserves_abi" in metadata
        if function in FACT_SOURCES:
            assert FACT_SOURCES[function] in metadata

    source = WORKFLOW_SMOKE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    build_cases = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_cases"
    )
    annotation_source = ast.get_source_segment(source, build_cases.returns)
    assert annotation_source is not None
    assert "kit:non-authoritative derived_as=simulation" in annotation_source
    assert "fact_source=local_smoke_fixture_cases" in annotation_source
    assert "witness=test:test_c15_backend_misc_cli_report_metadata_preserves_abi" in annotation_source
