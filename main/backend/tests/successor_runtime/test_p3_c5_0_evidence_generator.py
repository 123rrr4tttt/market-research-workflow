"""P3 C5 evidence generator determinism and normalized-root schema tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.successor_runtime.capabilities.checksum import content_digest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c5_fragment.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GENERATOR), *args],
        capture_output=True,
        text=True,
        cwd=_BACKEND_ROOT,
        check=False,
    )


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c5_fragment", _GENERATOR
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
    assert fragment["family"] == "C5"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert fragment["fragment_id"] == "p3-c5-family-local-implementation"
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
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
        "resolved_findings",
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
    for index in (0, 1, 2):
        assert fragment["cells"][index]["postgres_requirement"] == (
            "required_and_verified_mrw_p3_c5_worker_test"
        )
    assert fragment["cells"][3]["postgres_requirement"] == "not_required"


def test_p1_digests_bind_frozen_eligibility_cells() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    p1_cells = module._p1_cells()
    for cell in fragment["cells"]:
        assert cell["p1_cell_digest"] == content_digest(p1_cells[cell["cell_id"]])


def test_bindings_are_exact_authority_false_and_blocker_preserved() -> None:
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
    assert all(not value for value in fragment["authority"].values())
    open_finding_ids = {item["id"] for item in fragment["open_findings"]}
    assert "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED" not in open_finding_ids
    resolved = {item["id"]: item for item in fragment["resolved_findings"]}
    blocker = resolved["C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED"]
    assert blocker["severity"] == "P0"
    assert blocker["state"] == "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE"
    assert blocker["disposition"] == "NO_ADDITIVE_AMENDMENT_REQUIRED"
    assert blocker["evidence_ref"]["content_digest"] == (
        "1b2209a7cc55be719a4470575579a66b744171aadea52eae9e30e075e81b9b0d"
    )


def test_adjudication_artifact_content_is_validated_deterministically() -> None:
    module = _load_generator()
    assert module.ADJUDICATION_PATH.is_file()
    artifact = json.loads(module.ADJUDICATION_PATH.read_bytes())
    assert artifact["schema"] == "mrw.functorial_successor.c5_4_locator_adjudication.v1"
    assert artifact["status"] == "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE"
    assert artifact["disposition"] == "NO_ADDITIVE_AMENDMENT_REQUIRED"
    assert artifact["blocker"] == "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED"
    assert artifact["content_digest"] == module.ADJUDICATION_CONTENT_DIGEST
    assert artifact["normative_donor_locators"] == list(module.NORMATIVE_DONOR_LOCATORS)
    assert artifact["supplementary_read_only_evidence"] == list(
        module.SUPPLEMENTARY_READ_ONLY_EVIDENCE
    )


def test_source_dirty_path_is_never_bound_or_adopted() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    prohibited = module.PROHIBITED_DIRTY_SOURCE
    all_bindings = (
        *fragment["source_bindings"],
        *fragment["implementation_bindings"],
        *fragment["test_bindings"],
    )
    assert all(binding["path"] != prohibited for binding in all_bindings)
    artifact = json.loads(module.ADJUDICATION_PATH.read_bytes())
    dirty = artifact["path_observations"]["source_checkout_dirty"]
    assert dirty["path"] == prohibited
    assert dirty["adopted"] is False
    resolved = {item["id"]: item for item in fragment["resolved_findings"]}
    blocker = resolved["C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED"]
    assert blocker["source_dirty_excluded"] == {
        "path": prohibited,
        "adopted": False,
    }


def test_c5_4_donor_surface_roles_are_normative_and_supplementary() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    roles = {
        binding["path"]: binding["role"] for binding in fragment["source_bindings"]
    }
    for path in module.NORMATIVE_DONOR_LOCATORS:
        if path.endswith((".py", "agent_sessions")):
            bound = [key for key in roles if key.startswith(path)]
            assert bound, f"normative locator {path} is not bound"
    assert roles["main/backend/app/services/tasks.py"] == (
        "legacy_donor_c5_4_normative"
    )
    assert roles["main/backend/app/celery_app.py"] == ("legacy_donor_c5_4_normative")
    assert roles["main/backend/app/api/process.py"] == (
        "legacy_donor_c5_4_supplementary"
    )
    assert roles["main/backend/app/api/agent_batch.py"] == (
        "legacy_donor_c5_4_supplementary"
    )


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
    assert persisted["content_digest"] == digest


def test_cli_check_matches_persisted_fragment_without_write() -> None:
    module = _load_generator()
    fragment_path = module.FRAGMENT_PATH
    before_bytes = fragment_path.read_bytes()
    before_mtime_ns = fragment_path.stat().st_mtime_ns

    result = _run_cli("--check")

    assert result.returncode == 0, result.stderr
    assert "check ok" in result.stdout
    assert fragment_path.read_bytes() == before_bytes
    assert fragment_path.stat().st_mtime_ns == before_mtime_ns


def test_cli_check_drift_returns_1_without_write() -> None:
    module = _load_generator()
    fragment_path = module.FRAGMENT_PATH
    original = fragment_path.read_bytes()
    tampered = original.replace(b'"family":"C5"', b'"family":"C5X"')
    assert tampered != original
    fragment_path.write_bytes(tampered)
    try:
        result = _run_cli("--check")
        assert result.returncode == 1
        assert "drift" in result.stderr
        assert fragment_path.read_bytes() == tampered
    finally:
        fragment_path.write_bytes(original)


def test_cli_unknown_argument_returns_2_without_write() -> None:
    module = _load_generator()
    fragment_path = module.FRAGMENT_PATH
    before_bytes = fragment_path.read_bytes()
    before_mtime_ns = fragment_path.stat().st_mtime_ns

    result = _run_cli("--unknown-option")

    assert result.returncode == 2
    assert fragment_path.read_bytes() == before_bytes
    assert fragment_path.stat().st_mtime_ns == before_mtime_ns


def test_cli_default_write_returns_0() -> None:
    result = _run_cli()
    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout
