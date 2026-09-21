"""P4 C9 evidence generator determinism and normalized-root schema tests."""

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

from app.successor_runtime.specification import c9_p4
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    fragment_bytes,
)

_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c9_fragment.py"
_SHARED_GENERATOR = _BACKEND_ROOT / "scripts/generate_family_fragment_shared.py"
_FROZEN_CANONICAL_SHA256 = (
    "fdc4b2ab2616431b2d20ec41e207b41e978df833c94a1c92561360708bc89be1"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c9_fragment",
        _GENERATOR,
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
    return fragment_bytes(c9_p4.CONFIG, build_fragment(c9_p4.CONFIG, _REPOSITORY_ROOT))


def _file_snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): _file_snapshot(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_fragment_root_schema_and_cells_are_normalized() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["phase"] == "P4"
    assert fragment["family"] == "C9"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fragment["p4_status"] == "P4_NOT_STARTED"
    assert fragment["fragment_id"]
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C9.1",
        "C9.2",
        "C9.3",
    ]
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "p4_status",
        "cells",
        "owner_mapping",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    assert set(fragment["owner_mapping"]) == {"C9.1", "C9.2", "C9.3"}


def test_cells_are_reordered_scaffolds_with_bound_p1_and_contract_digests() -> None:
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
    rollback_digests = set()
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert cell["p1_cell_digest"] == module._p1_cell_digest(cell["cell_id"])
        assert len(cell["p1_cell_digest"]) == 64
        assert cell["program_digest"]["value"] is None
        assert cell["plan_digest"]["value"] is None
        assert cell["provider_calls"] == 0
        assert cell["postgres_requirement"] == "not_required"
        assert cell["operation_bindings"]
        for binding in cell["operation_bindings"]:
            assert set(binding) == {"operation_kind", "contract_digest", "role"}
            assert len(binding["contract_digest"]) == 64
        rollback = cell["rollback_observation"]
        assert len(rollback["rollback_digest"]) == 64
        rollback_digests.add(rollback["rollback_digest"])
    assert len(rollback_digests) == 3

    c9_1 = fragment["cells"][0]
    assert c9_1["successor_observation"]["api_status_union"] == [
        "ok",
        "error",
        "unavailable",
        "blocked",
        "waiting",
    ]
    assert c9_1["successor_observation"]["route_defined"] is False
    c9_2 = fragment["cells"][1]
    assert c9_2["successor_observation"]["design_only_typed_contract"] is True
    assert c9_2["successor_observation"]["frontend_bytes_written"] == 0
    assert c9_2["successor_observation"]["ui_observation_states"] == [
        "ready",
        "waiting",
        "blocked",
        "unavailable",
        "conflict",
        "failed",
    ]
    c9_3 = fragment["cells"][2]
    assert c9_3["successor_observation"]["rebuild_execute"] is False
    assert c9_3["successor_observation"]["postgres_executed"] is False
    assert c9_3["successor_observation"]["registry_revision_advance"] is True
    assert c9_3["successor_observation"]["full_rebuild_binding"] == (
        "exact_source_revision_digest_or_closure_receipt"
    )
    assert "receipt_fields" in c9_3["successor_observation"]
    assert "OFFSET_ID_MISMATCH" in c9_3["successor_observation"]["cas_codes"]
    assert (
        "SOURCE_REVISION_DIGEST_CONFLICT" in c9_3["successor_observation"]["cas_codes"]
    )
    assert c9_1["successor_observation"]["external_request_fields"] == [
        "project_locator",
        "command_kind",
        "typed_payload",
    ]
    assert "server_injected_fields" in c9_1["successor_observation"]
    assert "OFFSET_ABA_DETECTED" in c9_3["successor_observation"]["cas_codes"]
    assert "SOURCE_STALE" in c9_3["successor_observation"]["cas_codes"]


def test_bindings_are_exact_authority_false_and_no_false_p0() -> None:
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
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C9_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED" in finding_ids
    assert "P0_TARGET_RUNTIME_ARCHITECTURE_UNFROZEN" not in finding_ids
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert {
        "frozen_contract_document",
        "frozen_contract_manifest",
        "frozen_architecture",
        "frozen_inventory",
        "frozen_locator_inventory",
        "p1_eligibility",
        "p1_fragment",
    } <= source_roles
    assert "capability_ledger" not in source_roles
    assert "frozen_progress_record" not in source_roles
    roles = {entry["role"] for entry in fragment["implementation_bindings"]}
    assert "facade_contracts" in roles
    assert "projector_registry" in roles
    assert "transport_dto" in roles
    test_roles = {entry["role"] for entry in fragment["test_bindings"]}
    assert "c9_5_public_payload_and_caller_schema" in test_roles


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
    assert canonical_payload["family"] == "C9"

    legacy_bytes = _legacy_generator_bytes(module)
    shared_bytes = _shared_generator_bytes()
    assert legacy_bytes == shared_bytes
    assert shared_bytes != before[0]

    result = subprocess.run(
        [
            sys.executable,
            str(_SHARED_GENERATOR),
            "--family",
            "C9",
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
    target = tmp_path / "C9.json"
    fragment = module.build_fragment()

    module.FRAGMENT_PATH = target
    module.build_fragment = lambda: fragment

    module.main()

    output = capsys.readouterr().out
    assert target.is_file()
    assert json.loads(target.read_text())["family"] == "C9"
    assert f"wrote {target}" in output
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
            "C9",
            "--unknown-option",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert _file_snapshot(canonical) == before
