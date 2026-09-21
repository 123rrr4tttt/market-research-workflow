"""Focused authority metadata witnesses for W12 runtime/misc CLI builders."""

from __future__ import annotations

import ast
import importlib
import json
import shlex
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = REPO_ROOT / "docs/governance/functorial-debt-zero-baseline-packets.v1.json"
WITNESS = "test:test_w12_runtime_misc_laws"

# (file, function, semantic tag, baseline key suffix)
CASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "scripts/performance_capacity_baseline.py",
        "build_fixture",
        "kit:non-authoritative",
        "build_fixture returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_index",
        "kit:non-authoritative",
        "build_index returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_fail_fast_decision",
        "kit:non-authoritative",
        "build_fail_fast_decision returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_probe_latency",
        "kit:non-authoritative",
        "build_probe_latency returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_service_degradation",
        "kit:non-authoritative",
        "build_service_degradation returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_trend_record",
        "kit:non-authoritative",
        "build_trend_record returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_diagnostic_package",
        "kit:non-authoritative",
        "build_diagnostic_package returns an unmarked derived value",
    ),
    (
        "scripts/performance_capacity_baseline.py",
        "build_artifact",
        "kit:non-authoritative",
        "build_artifact returns an unmarked derived value",
    ),
    (
        "scripts/run_agent_knowledge_event_model_smoke.py",
        "build_artifact",
        "kit:non-authoritative",
        "build_artifact returns an unmarked derived value",
    ),
    (
        "scripts/run_agent_knowledge_event_model_smoke.py",
        "build_summary",
        "kit:non-authoritative",
        "build_summary returns an unmarked derived value",
    ),
    (
        "scripts/run_agent_knowledge_event_model_smoke.py",
        "build_url",
        "kit:prepared-command",
        "build_url returns an unmarked derived value",
    ),
    (
        "scripts/run_agent_knowledge_event_model_smoke.py",
        "build_workflow_graph_dsl",
        "kit:prepared-command",
        "build_workflow_graph_dsl returns an unmarked derived value",
    ),
    (
        "scripts/run_dashboard_report_closure_smoke.py",
        "build_artifact",
        "kit:non-authoritative",
        "build_artifact returns an unmarked derived value",
    ),
    (
        "scripts/run_dashboard_report_closure_smoke.py",
        "build_summary",
        "kit:non-authoritative",
        "build_summary returns an unmarked derived value",
    ),
    (
        "scripts/run_dashboard_report_closure_smoke.py",
        "build_url",
        "kit:prepared-command",
        "build_url returns an unmarked derived value",
    ),
    (
        "scripts/run_project_config_workflow_dry_run_smoke.py",
        "build_artifact",
        "kit:non-authoritative",
        "build_artifact returns an unmarked derived value",
    ),
    (
        "scripts/run_project_config_workflow_dry_run_smoke.py",
        "build_summary",
        "kit:non-authoritative",
        "build_summary returns an unmarked derived value",
    ),
    (
        "scripts/run_project_config_workflow_dry_run_smoke.py",
        "build_url",
        "kit:prepared-command",
        "build_url returns an unmarked derived value",
    ),
    (
        "scripts/run_resource_source_lifecycle_smoke.py",
        "build_artifact",
        "kit:non-authoritative",
        "build_artifact returns an unmarked derived value",
    ),
    (
        "scripts/run_resource_source_lifecycle_smoke.py",
        "build_summary",
        "kit:non-authoritative",
        "build_summary returns an unmarked derived value",
    ),
    (
        "scripts/run_resource_source_lifecycle_smoke.py",
        "build_url",
        "kit:prepared-command",
        "build_url returns an unmarked derived value",
    ),
    (
        "scripts/runtime_health_matrix.py",
        "build_matrix",
        "kit:non-authoritative",
        "build_matrix returns an unmarked derived value",
    ),
    (
        "scripts/runtime_health_matrix.py",
        "build_mode_specs",
        "kit:prepared-command",
        "build_mode_specs returns an unmarked derived value",
    ),
)


def _annotation_metadata(file_name: str, function_name: str) -> str:
    source = (REPO_ROOT / file_name).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=file_name)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )

    assert isinstance(function.returns, ast.Subscript)
    assert isinstance(function.returns.value, ast.Name)
    assert function.returns.value.id == "Annotated"

    module = importlib.import_module(file_name.removesuffix(".py").replace("/", "."))
    runtime_function = getattr(module, function_name)
    return_type = get_type_hints(runtime_function, include_extras=True)["return"]
    assert get_origin(return_type) is Annotated
    base_type, annotation = get_args(return_type)
    assert base_type is not None
    assert isinstance(annotation, str)
    return annotation


def test_w12_runtime_misc_laws() -> None:
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    w12 = next(packet_row for packet_row in packet["packets"] if packet_row["id"] == "W12")
    packet_keys = {row["key"] for row in w12["input_rows"]}

    assert len(CASES) == 23
    assert len({(file_name, function_name) for file_name, function_name, _, _ in CASES}) == 23

    for file_name, function_name, semantic_tag, key_suffix in CASES:
        baseline_key = f"derived-marked|{file_name}|{key_suffix}"
        assert baseline_key in packet_keys

        annotation = _annotation_metadata(file_name, function_name)
        assert not annotation.startswith("NonAuthoritative")
        assert "NonAuthoritativePreparedCommand" not in annotation
        assert annotation.startswith(f"{semantic_tag} ")
        assert f"witness={WITNESS}" in annotation

        tokens = shlex.split(annotation)
        assert tokens[0] == semantic_tag
        fields = dict(token.split("=", 1) for token in tokens[1:] if "=" in token)
        if semantic_tag == "kit:non-authoritative":
            assert set(fields) == {"derived_as", "fact_source", "witness"}
            assert fields["derived_as"] in {"view", "preflight", "generated_evidence"}
            assert fields["fact_source"]
        else:
            assert semantic_tag == "kit:prepared-command"
            assert set(fields) == {"effect_boundary", "witness"}
            assert fields["effect_boundary"]
        assert fields["witness"] == WITNESS
