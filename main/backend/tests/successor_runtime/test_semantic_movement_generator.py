"""P1-P3 semantic movement generator determinism and CLI exit-code tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_DEFAULT_REPO = _BACKEND.parents[1]
REPO = Path(
    os.environ.get("P1P3_SEMANTIC_MOVEMENT_REPO_ROOT", str(_DEFAULT_REPO))
).resolve()
OUTPUT = Path(os.environ.get("P1P3_SEMANTIC_MOVEMENT_OUTPUT_ROOT", str(REPO))).resolve()
_GENERATOR = _BACKEND / "scripts/generate_successor_p1_p3_semantic_movement.py"
_FROZEN_PREDECESSOR_COMMIT = "3706655f372f6d34fc62683551b8c3d1f4ff8146"

_FROZEN_SHA256 = {
    "fragments/C1.v1.json": "0ffd28226ff542f7f4d011ccf612bad8a84b35fd390be59c7694318e4b5ef138",
    "fragments/C2.v1.json": "92d0824ec35f8d56f3a530ce484139922a08e3c3a7a6a7869dfbc6099a25aa02",
    "fragments/C3.v1.json": "4d073060363d703a2ecd67368ac7f91ef1c15491e81a8ad696bbd34f04393eca",
    "fragments/C4.v1.json": "c9db07f3383fdc34cb3343ab392acdfac408eb89efa48e9f4ce3d81908a227a5",
    "fragments/C5.v1.json": "3ac6b67ebd0ec0b708a0e4d7ff48d8b61686d08db3bce64e1820c86f6164ed2d",
    "fragments/C6.v1.json": "8f201c3d730d1c3e2429abdb4b7d982abd6eafed361941702e590a82536c31a8",
    "fragments/C7.v1.json": "3d55cff419f4d926f627e75f7a2058dbfee538ce2cce9a2e722c03b1cd52d3a6",
    "fragments/C8.v1.json": "82975be377ab3e0da81da5b96623c26624dce36a0edd01cbf2a5afbf94a56e71",
    "fragments/C9.v1.json": "88a63d5293f827b46bb97d4269aada2c539dac494b2e2e117f19521a022f4230",
    "P1P3LegacyDonorSemanticMovementInventory.v1.json": "c032207f0070424b83fc81a8d49167dbb8f5624f08aaa97853e34f7a6f296be9",
    "P1P3SuccessorMovementMatrix.v1.json": "482ae2934fbe8ffd19a2e8d43365d4f910ff8cb82398cfd885086f07bb2740db",
    "P1P3SemanticMovementGate.v1.json": "74ade16f3113d68ff1642e5bf0a87aac7cc91dac868f5f3e9bcbbe06b0ca3ce0",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p1_p3_semantic_movement", _GENERATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _persisted_paths(module) -> list[Path]:
    return [
        OUTPUT / module.FRAGMENT_REL / f"{family}.v1.json" for family in module.FAMILIES
    ] + [
        OUTPUT / module.INVENTORY_REL,
        OUTPUT / module.MATRIX_REL,
        OUTPUT / module.GATE_REL,
    ]


def _historical_bytes(relative: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{_FROZEN_PREDECESSOR_COMMIT}:{relative}"],
        cwd=_DEFAULT_REPO,
    )


def test_generator_is_deterministic_and_digests_self_test() -> None:
    module = _load_generator()
    first = module.build_documents(REPO)
    second = module.build_documents(REPO)
    assert first == second
    for data in first.values():
        artifact = json.loads(data)
        assert artifact["content_digest"] == module._content_digest(artifact)


def test_persisted_artifacts_are_frozen_predecessors() -> None:
    module = _load_generator()
    persisted = _persisted_paths(module)
    assert len(persisted) == len(_FROZEN_SHA256)
    for path in persisted:
        relative = path.relative_to(OUTPUT / module.FRAGMENT_REL.parent).as_posix()
        historical_path = path.relative_to(OUTPUT).as_posix()
        historical = _historical_bytes(historical_path)
        assert hashlib.sha256(historical).hexdigest() == _FROZEN_SHA256[relative]


def test_cli_check_accepts_canonical_reserialization_and_is_read_only(tmp_path: Path) -> None:
    module = _load_generator()
    from .historical_fixture import write_documents

    write_documents(tmp_path, module.build_documents(REPO))
    paths = [tmp_path / path.relative_to(OUTPUT) for path in _persisted_paths(module)]
    snapshot = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    result = subprocess.run(
        [
            sys.executable,
            str(_GENERATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(tmp_path),
            "--check",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "CHECK_OK"
    assert payload["inline_movements"] == 40
    assert payload["external_c7_movements"] == 20
    assert payload["total_movements"] == 60
    assert payload["exact_blockers"] == 0
    assert "paths" not in payload
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    assert after == snapshot


def test_cli_check_drift_exits_one_without_writing(tmp_path: Path) -> None:
    module = _load_generator()
    drifted_root = tmp_path / "drifted-output"
    for relative in module.build_documents(REPO):
        target = drifted_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUTPUT / relative, target)
    drifted = drifted_root / module.FRAGMENT_REL / "C1.v1.json"
    content = drifted.read_text(encoding="utf-8")
    drifted.write_text(
        content.replace('"status"', '"status_drifted"'), encoding="utf-8"
    )
    before = drifted.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(_GENERATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(drifted_root),
            "--check",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert '"status": "DRIFT"' in result.stdout
    assert drifted.read_bytes() == before


def test_cli_check_invalid_input_root_exits_two() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_GENERATOR),
            "--repo-root",
            str(Path("/nonexistent-p1p3-input-root")),
            "--output-root",
            str(OUTPUT),
            "--check",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout.startswith("INVALID:")
