"""P3 C4 evidence generator determinism and normalized-root schema tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.successor_runtime.capabilities.checksum import content_digest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c4_fragment.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c4_fragment", _GENERATOR
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
    assert fragment["family"] == "C4"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert fragment["fragment_id"]
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C4.1",
        "C4.2",
        "C4.3",
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
    assert fragment["cells"][0]["program_digest"]["value"]
    assert fragment["cells"][0]["plan_digest"]["value"]
    assert fragment["cells"][1]["program_digest"]["value"]
    assert fragment["cells"][1]["plan_digest"]["value"]
    assert fragment["cells"][2]["program_digest"]["value"]
    assert fragment["cells"][2]["plan_digest"]["value"]
    assert fragment["cells"][2]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c4_worker_test"
    )
    assert "traversal_program_digest" in fragment["cells"][0]["successor_observation"]
    assert "generic_idempotency_enum" in fragment["cells"][2]["successor_observation"]


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
    assert all(not value for value in fragment["authority"].values())
    assert fragment["open_findings"]
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C4_1_STATIC_SHAPE_TRAVERSAL_BINDING_REQUIRED" not in finding_ids
    assert "C4_3_SHARED_IDEMPOTENCY_ENUM_MISMATCH" not in finding_ids
    roles = {entry["role"] for entry in fragment["implementation_bindings"]}
    assert "shared_compiler_traversal_dependency" in roles
    assert "shared_idempotency_repository_dependency" in roles


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


def test_persisted_fragment_matches_generated_bytes() -> None:
    module = _load_generator()
    persisted = json.loads(module.FRAGMENT_PATH.read_text())
    rebuilt = module.build_fragment()
    rebuilt["content_digest"] = content_digest(
        {key: value for key, value in rebuilt.items() if key != "content_digest"}
    )
    assert module._canonical_json(rebuilt) == module._canonical_json(persisted)


def test_cli_check_ok_is_read_only(tmp_path: Path) -> None:
    import subprocess
    import sys

    module = _load_generator()
    snapshot = module.FRAGMENT_PATH.read_bytes()
    snapshot_mtime = module.FRAGMENT_PATH.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "check ok" in result.stdout
    assert module.FRAGMENT_PATH.read_bytes() == snapshot
    assert module.FRAGMENT_PATH.stat().st_mtime_ns == snapshot_mtime


def test_cli_check_drift_exits_one_without_writing(tmp_path: Path, monkeypatch) -> None:
    module = _load_generator()
    drifted_path = tmp_path / "C4.drifted.json"
    snapshot = module.FRAGMENT_PATH.read_bytes()
    drifted = snapshot.replace(
        b'"status":"IMPLEMENTED_CANDIDATE_NOT_PROMOTED"', b'"status":"DRIFTED"'
    )
    assert drifted != snapshot
    drifted_path.write_bytes(drifted)
    monkeypatch.setattr(module, "FRAGMENT_PATH", drifted_path)
    assert module.main(["--check"]) == 1
    assert drifted_path.read_bytes() == drifted


def test_cli_unknown_argument_exits_two() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--definitely-unknown"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
