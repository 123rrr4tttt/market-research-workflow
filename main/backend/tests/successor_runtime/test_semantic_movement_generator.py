"""P1-P3 semantic movement generator determinism and CLI exit-code tests."""

from __future__ import annotations

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


def test_generator_is_deterministic_and_digests_self_test() -> None:
    module = _load_generator()
    first = module.build_documents(REPO)
    second = module.build_documents(REPO)
    assert first == second
    for data in first.values():
        artifact = json.loads(data)
        assert artifact["content_digest"] == module._content_digest(artifact)


def test_persisted_artifacts_match_regenerated_bytes() -> None:
    module = _load_generator()
    documents = module.build_documents(REPO)
    for relative, expected in documents.items():
        assert (OUTPUT / relative).read_bytes() == expected


def test_cli_check_ok_is_read_only(tmp_path: Path) -> None:
    module = _load_generator()
    paths = _persisted_paths(module)
    snapshot = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    result = subprocess.run(
        [
            sys.executable,
            str(_GENERATOR),
            "--repo-root",
            str(REPO),
            "--output-root",
            str(OUTPUT),
            "--check",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "CHECK_OK"' in result.stdout
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
