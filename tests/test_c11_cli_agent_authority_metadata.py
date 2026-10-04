from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
WITNESS = "test:test_c11_cli_agent_authority_metadata"

CASES: dict[str, tuple[str, str, str]] = {
    "derived-marked|main/backend/scripts/check_admin_dashboard_consumer_boundary.py|"
    "build_check returns an unmarked derived value": (
        "check_admin_dashboard_consumer_boundary",
        "build_check",
        "kit:non-authoritative derived_as=preflight fact_source=repository_source_files",
    ),
    "derived-marked|main/backend/scripts/check_agent_batch_quality_promotion_readback.py|"
    "build_contract returns an unmarked derived value": (
        "check_agent_batch_quality_promotion_readback",
        "build_contract",
        "kit:non-authoritative derived_as=preflight fact_source=app.services.agent_core.batch_search",
    ),
    "derived-marked|main/backend/scripts/check_agent_symbolic_provider_quality_readiness.py|"
    "build_contract returns an unmarked derived value": (
        "check_agent_symbolic_provider_quality_readiness",
        "build_contract",
        "kit:non-authoritative derived_as=preflight fact_source=app.services.source_library.provider_quality",
    ),
    "derived-marked|main/backend/scripts/check_agent_symbolic_search_quality_replay.py|"
    "build_contract returns an unmarked derived value": (
        "check_agent_symbolic_search_quality_replay",
        "build_contract",
        "kit:non-authoritative derived_as=preflight fact_source=app.services.source_library.provider_quality_replay",
    ),
    "derived-marked|main/backend/scripts/check_consumer_side_facade_contract.py|"
    "build_check returns an unmarked derived value": (
        "check_consumer_side_facade_contract",
        "build_check",
        "kit:non-authoritative derived_as=preflight fact_source=repository_source_files",
    ),
    "derived-marked|main/backend/scripts/check_consumer_sql_predicate_facade.py|"
    "build_check returns an unmarked derived value": (
        "check_consumer_sql_predicate_facade",
        "build_check",
        "kit:non-authoritative derived_as=preflight fact_source=repository_source_files",
    ),
    "derived-marked|main/backend/scripts/check_single_url_external_blocker_closure.py|"
    "build_check returns an unmarked derived value": (
        "check_single_url_external_blocker_closure",
        "build_check",
        "kit:non-authoritative derived_as=preflight fact_source=single_url_repo_local_gate_evidence",
    ),
    "derived-marked|main/backend/scripts/check_single_url_official_api_provider_maturity.py|"
    "build_report returns an unmarked derived value": (
        "check_single_url_official_api_provider_maturity",
        "build_report",
        "kit:non-authoritative derived_as=preflight fact_source=single_url_official_api_probe_results",
    ),
    "derived-marked|main/backend/scripts/check_single_url_wave29_blocker_alignment.py|"
    "build_report returns an unmarked derived value": (
        "check_single_url_wave29_blocker_alignment",
        "build_report",
        "kit:non-authoritative derived_as=preflight fact_source=repository_source_files",
    ),
    "derived-marked|main/backend/scripts/check_symbolic_live_quality_threshold.py|"
    "build_contract returns an unmarked derived value": (
        "check_symbolic_live_quality_threshold",
        "build_contract",
        "kit:non-authoritative derived_as=preflight fact_source=app.services.agent_batch.search_quality_replay",
    ),
    "derived-marked|main/backend/scripts/check_symbolic_quality_regression_evaluator.py|"
    "build_contract returns an unmarked derived value": (
        "check_symbolic_quality_regression_evaluator",
        "build_contract",
        "kit:non-authoritative derived_as=preflight fact_source=app.services.agent_batch.quality_regression",
    ),
}


def _function(module_name: str, function_name: str):
    module = importlib.import_module(f"main.backend.scripts.{module_name}")
    return getattr(module, function_name)


def test_c11_cli_agent_authority_metadata() -> None:
    assert len(CASES) == 11

    for baseline_key, (module_name, function_name, expected_authority) in CASES.items():
        function = _function(module_name, function_name)
        return_hint = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_hint) is Annotated
        value, annotation = get_args(return_hint)
        assert value is not None
        assert isinstance(annotation, str)
        assert annotation.startswith(expected_authority)
        assert f"witness={WITNESS}" in annotation
        assert baseline_key.startswith("derived-marked|main/backend/scripts/")

        if annotation.startswith("kit:non-authoritative"):
            kind = re.search(r"derived_as=([a-z_]+)", annotation)
            fact_source = re.search(r"fact_source=([^ ]+)", annotation)
            assert kind is not None and kind.group(1) in {
                "view",
                "preflight",
                "simulation",
                "external_claim",
                "generated_evidence",
            }
            assert fact_source is not None and fact_source.group(1)
        else:
            owner = re.search(r"canonical_owner=([^ ]+)", annotation)
            assert owner is not None and owner.group(1).startswith("app.services.")
