"""P4 C7 evidence generator determinism and normalized-root schema tests."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.specification import c7_p4
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    fragment_bytes,
)

_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c7_fragment.py"
_SHARED_GENERATOR = _BACKEND_ROOT / "scripts/generate_family_fragment_shared.py"
_FROZEN_CANONICAL_SHA256 = (
    "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c7_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _legacy_generator_bytes(module) -> bytes:
    fragment = module.build_fragment()
    fragment["content_digest"] = module.content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    return module._canonical_json(fragment).encode("utf-8") + b"\n"


def _shared_generator_bytes() -> bytes:
    return fragment_bytes(c7_p4.CONFIG, build_fragment(c7_p4.CONFIG, _REPOSITORY_ROOT))


def _file_snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): _file_snapshot(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_fragment_root_schema_cells_and_status_are_normalized() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["phase"] == "P4"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fragment["lifecycle_state"] == "P4_NOT_STARTED"
    assert fragment["fragment_id"]
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
    ]
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "lifecycle_state",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots


def test_cells_have_required_fields_and_zero_provider_calls() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    required_cell_fields = {
        "cell_id",
        "p1_locators",
        "contract_ids",
        "legacy_observation",
        "successor_observation",
        "rollback_observation",
        "provider_calls",
        "postgres_requirement",
    }
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert cell["provider_calls"] == 0
        assert cell["p1_locators"]["locator_paths"]
    assert fragment["cells"][0]["successor_observation"]["admission_implied"] is False
    assert fragment["cells"][0]["successor_observation"]["step_kinds"] == [
        "EFFECT",
        "ADMISSION",
    ]
    assert fragment["cells"][0]["successor_observation"]["execution_class"] == (
        "EFFECTFUL"
    )
    assert (
        fragment["cells"][0]["successor_observation"]["document_write_boundary"]
        is False
    )
    closure = fragment["cells"][0]["successor_observation"][
        "runtime_assignment_closure"
    ]
    assert set(closure) == {
        "program_digest",
        "plan_digest",
        "step_id",
        "step_role",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    }
    for digest_key in (
        "program_digest",
        "plan_digest",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    ):
        assert len(closure[digest_key]) == 64
    assert closure["step_role"] == "EFFECT"
    assert fragment["cells"][1]["successor_observation"]["document_write"] is False
    assert fragment["cells"][2]["successor_observation"]["declared_loss"]
    assert fragment["cells"][3]["successor_observation"]["new_attempt_allowed"] is False


def test_bindings_are_exact_authority_false_and_shared_identities_bound() -> None:
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
    assert fragment["open_findings"]
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C7_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED" in finding_ids
    assert "C7_P4_NOT_STARTED" in finding_ids
    assert "C7_SHARED_RUNTIME_MODULES_ABSENT_IN_WORKTREE" not in finding_ids
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert "shared_program_spec" in source_roles
    assert "shared_compiler" in source_roles
    assert "shared_commit_intent_verification_binding" in source_roles
    assert "shared_effect_reconciler" in source_roles
    assert "shared_runtime_assignment" in source_roles
    assert "shared_document_admission_return_contract_registry" in source_roles
    assert "shared_projection_offset_repository" in source_roles
    assert "p1_fragment_locators" in source_roles
    for frozen_role in (
        "frozen_locator_frontdoor_orchestrator",
        "frozen_locator_entities",
        "frozen_locator_graph_persistence",
        "frozen_locator_dry_run",
        "frozen_locator_cleanup",
        "frozen_locator_db_retry",
        "frozen_locator_rollout",
    ):
        assert frozen_role in source_roles
    roles = {entry["role"] for entry in fragment["implementation_bindings"]}
    assert "c7_common_contracts" in roles
    assert "c7_contracts" in roles
    assert "c7_program" in roles
    assert "c7_recovery" in roles
    assert "c7_document_repository" in roles
    assert "c7_projection_common" in roles
    test_roles = {entry["role"] for entry in fragment["test_bindings"]}
    assert "c7_0_return_registry_invariants" in test_roles
    assert "c7_6_disposable_postgres" in test_roles


def test_generator_is_deterministic_and_digest_self_tests() -> None:
    module = _load_generator()
    first = module.build_fragment()
    second = module.build_fragment()
    assert module._canonical_json(first) == module._canonical_json(second)
    digest = module.content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    module._self_test(first)
    persisted = json.loads(module.FRAGMENT_PATH.read_text())
    assert persisted["schema"] == module.FRAGMENT_SCHEMA
    assert persisted["content_digest"] != digest


def test_live_generator_drifts_from_frozen_canonical_without_write() -> None:
    module = _load_generator()
    canonical = module.FRAGMENT_PATH
    before = _file_snapshot(canonical)
    canonical_payload = json.loads(before[0])
    assert hashlib.sha256(before[0]).hexdigest() == _FROZEN_CANONICAL_SHA256
    assert canonical_payload["family"] == "C7"

    legacy_bytes = _legacy_generator_bytes(module)
    shared_bytes = _shared_generator_bytes()
    comparison = "MATCH" if legacy_bytes == before[0] else "DRIFT"
    assert comparison == "DRIFT"
    assert shared_bytes != before[0]

    result = subprocess.run(
        [
            sys.executable,
            str(_SHARED_GENERATOR),
            "--family",
            "C7",
            "--check",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DRIFT" in result.stdout + result.stderr
    assert _file_snapshot(canonical) == before


def test_main_writes_to_tmp_path_without_touching_canonical(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_generator()
    canonical = module.FRAGMENT_PATH
    canonical_before = _file_snapshot(canonical)
    target = tmp_path / "C7.json"
    module.FRAGMENT_PATH = target

    assert module.main([]) == 0

    output = capsys.readouterr().out
    assert target.is_file()
    assert json.loads(target.read_text())["family"] == "C7"
    assert f"WROTE: {target}" in output
    assert _file_snapshot(canonical) == canonical_before


def test_shared_generator_unknown_argument_returns_2_without_write() -> None:
    module = _load_generator()
    canonical = module.FRAGMENT_PATH
    before = _file_snapshot(canonical)

    result = subprocess.run(
        [
            sys.executable,
            str(_SHARED_GENERATOR),
            "--family",
            "C7",
            "--unknown-option",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert _file_snapshot(canonical) == before
