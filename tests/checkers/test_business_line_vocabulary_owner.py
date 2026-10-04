"""Independent oracle for the current business-line vocabulary owner."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from mrw_functorial_kit import business_line_vocabulary as vocabulary


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
)
EXPECTED_WORKER_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)
SCRIPT_ALIASES = {
    "build_business_line_async_readiness_artifact.py": {"REQUIRED_LINE_KEYS"},
    "build_business_line_async_task_readback_artifact.py": {
        "REQUIRED_LINE_KEYS",
        "WORKER_REQUIRED_LINE_KEYS",
    },
    "build_business_line_real_backend_browser_artifact.py": {"REQUIRED_LINE_KEYS"},
    "build_business_line_task_readback_manifest_from_runtime.py": {
        "CANONICAL_LINE_KEYS",
        "WORKER_REQUIRED_LINE_KEYS",
    },
    "check_business_line_async_readiness_artifact.py": {"REQUIRED_LINE_KEYS"},
    "check_business_line_async_task_readback_artifact.py": {
        "REQUIRED_LINE_KEYS",
        "WORKER_REQUIRED_LINE_KEYS",
    },
    "check_business_line_batch_coverage.py": {"REQUIRED_LINE_KEYS"},
    "check_business_line_real_backend_browser_artifact.py": {"REQUIRED_LINE_KEYS"},
    "check_business_line_task_readback_manifest.py": {"REQUIRED_LINE_KEYS"},
    "check_business_line_trace_baseline_artifact.py": {"REQUIRED_LINE_KEYS"},
    "check_business_line_user_flow_smoke_artifact.py": {"REQUIRED_LINE_KEYS"},
    "run_business_line_async_task_readback_live_samples.py": {
        "EXPECTED_LINE_KEYS",
        "WORKER_REQUIRED_LINE_KEYS",
    },
    "run_business_line_trace_baseline_live.py": {"EXPECTED_LINE_KEYS"},
    "run_business_line_user_flow_smoke.py": {"EXPECTED_LINE_KEYS"},
    "run_business_line_worker_readback_smoke_triggers.py": {
        "WORKER_REQUIRED_LINE_KEYS",
    },
}


def _load_script(filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(
        f"business_line_vocabulary_consumer_{path.stem}", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_vocabulary_is_fixed_and_subset_is_explicit() -> None:
    assert vocabulary.BUSINESS_LINE_VOCABULARY_VERSION == "business_line.vocabulary.current.v1"
    assert vocabulary.BUSINESS_LINE_KEYS == EXPECTED_LINE_KEYS
    assert vocabulary.WORKER_REQUIRED_BUSINESS_LINE_KEYS == EXPECTED_WORKER_LINE_KEYS
    assert set(vocabulary.WORKER_REQUIRED_BUSINESS_LINE_KEYS) < set(vocabulary.BUSINESS_LINE_KEYS)
    assert vocabulary.is_business_line_key("Search Discovery Index") is True
    assert vocabulary.is_worker_required_business_line_key("runtime-ops") is False


def test_fifteen_script_consumers_share_the_owner_identity() -> None:
    for filename, aliases in SCRIPT_ALIASES.items():
        module = _load_script(filename)
        for alias in aliases:
            is_worker_alias = alias == "WORKER_REQUIRED_LINE_KEYS" or filename == (
                "check_business_line_task_readback_manifest.py"
            )
            expected = (
                vocabulary.WORKER_REQUIRED_BUSINESS_LINE_KEYS
                if is_worker_alias
                else vocabulary.BUSINESS_LINE_KEYS
            )
            assert getattr(module, alias) == expected


def test_absolute_script_import_uses_script_bootstrap_without_repo_root_on_path() -> None:
    script = ROOT / "scripts" / "check_business_line_batch_coverage.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
