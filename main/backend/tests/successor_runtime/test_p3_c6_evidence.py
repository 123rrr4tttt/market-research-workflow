"""Normalized P3 C6 evidence generator determinism and root-schema tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.checksum import content_digest

pytestmark = pytest.mark.unit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c6_fragment.py"
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_FRAGMENT = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C6.json"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c6_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fragment_root_schema_and_cells_are_normalized() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    assert fragment["schema"] == "mrw.functorial_successor.p3_fragment.v1"
    assert fragment["phase"] == "P3"
    assert fragment["family"] == "C6"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert fragment["fragment_id"] == "p3-c6-family-local-implementation"
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C6.1",
        "C6.2",
        "C6.3",
    ]
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots


def test_cells_have_required_binding_fields() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    required_cell_fields = {
        "cell_id",
        "p1_cell_digest",
        "operation_bindings",
        "owner_capability_id",
        "program_digest",
        "plan_digest",
        "legacy_observation",
        "successor_observation",
        "rollback_observation",
        "provider_calls",
        "postgres_requirement",
    }
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert len(cell["p1_cell_digest"]) == 64
        assert {"value", "reason"} == set(cell["program_digest"])
        assert {"value", "reason"} == set(cell["plan_digest"])
        assert cell["provider_calls"] == 0
        assert cell["operation_bindings"][0]["contract_digest"]
        canary = cell["successor_observation"]["runtime_node_canary"]
        assert canary["state"] == "COMMITTED"
        assert canary["disposition"] == "SUCCEEDED"
        assert canary["provider_calls"] == 0
        assert canary["sentinel_scan_passed"] is True
        assert canary["rollback_future_owner"] == "legacy"
    assert fragment["cells"][0]["postgres_requirement"] == "not_required"
    assert fragment["cells"][1]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c6_worker_test"
    )
    assert fragment["cells"][2]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c6_worker_test"
    )
    c6_1 = fragment["cells"][0]
    assert c6_1["legacy_observation"]["tool_result_statuses"] == ["completed"]
    assert len(c6_1["legacy_observation"]["observation_digest"]) == 64
    assert c6_1["successor_observation"]["tool_result_statuses"] == ["completed"]
    c6_3 = fragment["cells"][2]
    assert c6_3["legacy_observation"]["same_program_shadow_parity"] is True
    assert c6_3["successor_observation"]["same_program_shadow_parity"] is True
    assert (
        c6_3["legacy_observation"]["binding_digest"]
        != c6_3["successor_observation"]["binding_digest"]
    )


def test_bindings_are_exact_and_authority_is_false() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    for binding in (
        *fragment["source_bindings"],
        *fragment["implementation_bindings"],
        *fragment["test_bindings"],
    ):
        assert set(binding) == {"path", "sha256", "bytes", "lines", "role"}
        assert len(binding["sha256"]) == 64
        assert binding["bytes"] > 0
        assert binding["lines"] > 0
        data = (_REPOSITORY_ROOT / binding["path"]).read_bytes()
        assert binding["sha256"] == hashlib.sha256(data).hexdigest()
        assert binding["bytes"] == len(data)
    assert all(not value for value in fragment["authority"].values())
    assert fragment["open_findings"]
    finding_ids = {finding["id"] for finding in fragment["open_findings"]}
    assert "P3_AUTHORITY_RECORD_DIVERGENCE" not in finding_ids
    assert "P3C6_DEPENDENCY_LINT_NOT_GLOBALLY_GREEN" not in finding_ids
    live_finding = next(
        finding
        for finding in fragment["open_findings"]
        if finding["id"] == "C6_2_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN"
    )
    assert live_finding["severity"] == "P1"
    assert "no live-provider claim" in live_finding["description"]


def test_generator_is_deterministic_and_digest_self_tests() -> None:
    module = _load_generator()
    first = module.build_fragment()
    second = module.build_fragment()
    assert module._canonical_json(first) == module._canonical_json(second)
    digest = content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    module._self_test(first)
    persisted = json.loads(module.FRAGMENT_PATH.read_text())
    assert persisted["schema"] == module.FRAGMENT_SCHEMA
    assert persisted["family"] == "C6"
    assert persisted["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert persisted["content_digest"] == digest
    assert module._canonical_json(persisted) == module._canonical_json(first)


def test_generator_check_is_read_only_and_bytes_stable() -> None:
    before_stat = _FRAGMENT.stat()
    before_bytes = _FRAGMENT.read_bytes()
    completed = subprocess.run(
        [sys.executable, str(_GENERATOR), "--check"],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    after_stat = _FRAGMENT.stat()
    after_bytes = _FRAGMENT.read_bytes()
    assert after_bytes == before_bytes
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


def test_generator_check_drift_returns_1_without_write(tmp_path: Path) -> None:
    module = _load_generator()
    drifted = tmp_path / "C6.json"
    drifted.write_text("{}", encoding="utf-8")
    before_ns = drifted.stat().st_mtime_ns
    original_path = module.FRAGMENT_PATH
    module.FRAGMENT_PATH = drifted
    try:
        code = module.main(["--check"])
        assert code == 1
        assert drifted.read_text(encoding="utf-8") == "{}"
        assert drifted.stat().st_mtime_ns == before_ns
    finally:
        module.FRAGMENT_PATH = original_path


def test_generator_unknown_argument_rejected() -> None:
    completed = subprocess.run(
        [sys.executable, str(_GENERATOR), "--bogus"],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "bogus" in completed.stderr
