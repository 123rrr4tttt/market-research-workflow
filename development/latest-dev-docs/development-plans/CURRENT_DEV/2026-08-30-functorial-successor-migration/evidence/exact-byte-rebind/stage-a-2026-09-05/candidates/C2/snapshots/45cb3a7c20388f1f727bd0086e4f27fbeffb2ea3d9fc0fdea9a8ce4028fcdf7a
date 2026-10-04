"""P3 C2 evidence generator determinism and normalized-root schema tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.successor_runtime.capabilities.checksum import content_digest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c2_fragment.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c2_fragment", _GENERATOR
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
    assert fragment["family"] == "C2"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert fragment["fragment_id"]
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C2.2",
        "C2.3",
        "C2.4",
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
    assert fragment["cells"][2]["postgres_requirement"] == (
        "required_and_verified_mrw_p3_c2_worker_test"
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
    assert all(not value for value in fragment["authority"].values())
    assert fragment["open_findings"]


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


def _run_cli(*args: str):
    return subprocess.run(
        [sys.executable, str(_GENERATOR), *args],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_ROOT),
        check=False,
    )


def test_cli_check_is_read_only_and_exact() -> None:
    module = _load_generator()
    target = module.FRAGMENT_PATH
    before = target.stat()
    proc = _run_cli("--check")
    assert proc.returncode == 0, proc.stderr
    assert "unchanged" in proc.stdout
    after = target.stat()
    assert before.st_mtime_ns == after.st_mtime_ns
    assert before.st_size == after.st_size


def test_cli_check_drift_exits_1_without_writing(tmp_path: Path) -> None:
    module = _load_generator()
    target = tmp_path / "C2.drift.json"
    target.write_bytes(module.FRAGMENT_PATH.read_bytes())
    corrupted = b'{"schema": "drift"}'
    target.write_bytes(corrupted)
    proc = _run_cli("--check", "--fragment-path", str(target))
    assert proc.returncode == 1
    assert "no write performed" in proc.stderr
    assert target.read_bytes() == corrupted


def test_cli_check_missing_fragment_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "C2.missing.json"
    proc = _run_cli("--check", "--fragment-path", str(missing))
    assert proc.returncode == 2
    assert "missing" in proc.stderr
