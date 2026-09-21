from __future__ import annotations

import ast
import importlib.util
import shlex
import sys
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[2]
WITNESS = "test:test_INVARIANT__c16_business_cli_authority_metadata"
CASES = (
    ("scripts/build_business_line_async_readiness_artifact.py", "build_line", "derived"),
    ("scripts/build_business_line_async_readiness_artifact.py", "build_artifact", "derived"),
    ("scripts/build_business_line_async_task_readback_artifact.py", "build_line", "derived"),
    ("scripts/build_business_line_async_task_readback_artifact.py", "build_artifact", "derived"),
    ("scripts/build_business_line_real_backend_browser_artifact.py", "build_artifact", "derived"),
    ("scripts/build_business_line_task_readback_manifest_from_runtime.py", "build_candidate_sample", "derived"),
    ("scripts/build_business_line_task_readback_manifest_from_runtime.py", "build_manifest_candidate", "derived"),
    ("scripts/build_business_line_task_readback_manifest_from_runtime.py", "build_url", "prepared"),
    ("scripts/check_business_line_async_readiness_artifact.py", "build_report", "derived"),
    ("scripts/check_business_line_async_task_readback_artifact.py", "build_manifest_index", "derived"),
    ("scripts/check_business_line_async_task_readback_artifact.py", "build_report", "derived"),
    ("scripts/check_business_line_batch_coverage.py", "build_report", "derived"),
    ("scripts/check_business_line_real_backend_browser_artifact.py", "build_report", "derived"),
    ("scripts/check_business_line_task_readback_manifest.py", "build_report", "derived"),
    ("scripts/check_business_line_trace_baseline_artifact.py", "build_report", "derived"),
    ("scripts/check_business_line_user_flow_smoke_artifact.py", "build_report", "derived"),
    ("scripts/check_business_line_worker_project_schema_preflight.py", "build_url", "prepared"),
    ("scripts/check_business_trace_readback_contract.py", "build_report", "derived"),
    ("scripts/run_business_line_async_task_readback_live_samples.py", "build_live_samples", "derived"),
    ("scripts/run_business_line_async_task_readback_live_samples.py", "build_probe_url", "prepared"),
    ("scripts/run_business_line_async_task_readback_live_samples.py", "build_url", "prepared"),
    ("scripts/run_business_line_trace_baseline_live.py", "build_matrix_blocked_report", "derived"),
    ("scripts/run_business_line_trace_baseline_live.py", "build_url", "prepared"),
    ("scripts/run_business_line_user_flow_smoke.py", "build_feedback_loop_blocked", "derived"),
    ("scripts/run_business_line_user_flow_smoke.py", "build_matrix_blocked_report", "derived"),
    ("scripts/run_business_line_user_flow_smoke.py", "build_summary", "derived"),
    ("scripts/run_business_line_user_flow_smoke.py", "build_url", "prepared"),
    ("scripts/run_business_line_worker_readback_evidence_chain.py", "build_report", "derived"),
    ("scripts/run_business_line_worker_readback_evidence_chain.py", "build_url", "prepared"),
    ("scripts/run_business_line_worker_readback_project_matrix.py", "build_chain_command", "prepared"),
    ("scripts/run_business_line_worker_readback_project_matrix.py", "build_report", "derived"),
    ("scripts/run_business_line_worker_readback_smoke_triggers.py", "build_artifact", "derived"),
    ("scripts/run_business_line_worker_readback_smoke_triggers.py", "build_url", "prepared"),
)


def _function(file_name: str, function_name: str):
    path = REPO_ROOT / file_name
    module_name = file_name.removesuffix(".py").replace("/", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, function_name)


def test_INVARIANT__c16_business_cli_authority_metadata() -> None:
    assert len(CASES) == len(set(CASES)) == 33
    for file_name, function_name, kind in CASES:
        source = (REPO_ROOT / file_name).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=file_name)
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        )
        assert isinstance(function.returns, ast.Subscript), f"{file_name}:{function_name}"
        assert isinstance(function.returns.value, ast.Name), f"{file_name}:{function_name}"
        assert function.returns.value.id == "Annotated", f"{file_name}:{function_name}"

        function_object = _function(file_name, function_name)
        return_hint = get_type_hints(function_object, include_extras=True)["return"]
        assert get_origin(return_hint) is Annotated, f"{file_name}:{function_name}"
        _, annotation = get_args(return_hint)
        tokens = shlex.split(annotation)
        if kind == "derived":
            assert tokens[0] == "kit:non-authoritative", f"{file_name}:{function_name}"
            assert tokens[1] in {"derived_as=view", "derived_as=preflight", "derived_as=generated_evidence"}, f"{file_name}:{function_name}"
            assert tokens[2].startswith("fact_source=") and tokens[2] != "fact_source=", f"{file_name}:{function_name}"
            assert tokens[3] == f"witness={WITNESS}", f"{file_name}:{function_name}"
            assert len(tokens) == 4, f"{file_name}:{function_name}"
        else:
            assert tokens[0] == "kit:prepared-command", f"{file_name}:{function_name}"
            assert tokens[1].startswith("effect_boundary="), f"{file_name}:{function_name}"
            assert tokens[1] != "effect_boundary=", f"{file_name}:{function_name}"
            assert tokens[2] == f"witness={WITNESS}", f"{file_name}:{function_name}"
            assert len(tokens) == 3, f"{file_name}:{function_name}"
