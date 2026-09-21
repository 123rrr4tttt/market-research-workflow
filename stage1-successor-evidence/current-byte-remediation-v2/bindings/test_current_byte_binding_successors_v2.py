from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_module(
    "check_current_byte_binding_successors_v2",
    HERE / "check_current_byte_binding_successors_v2.py",
)


def test_v2_bundle_is_exact_extended_and_non_authoritative() -> None:
    assert CHECKER.validate(ROOT) == {
        "status": "PASS",
        "source_count": 5,
        "successor_count": 11,
        "expanded_i1_binding_count": 4,
        "authority_ceiling": CHECKER.BUILDER.AUTHORITY_CEILING,
    }


def test_shared_c6_row_is_single_candidate_resolution_and_two_cell_bindings() -> None:
    registry = json.loads(
        (HERE / "current-byte-binding-successors.v2.json").read_text(encoding="utf-8")
    )
    rows = [
        row
        for row in registry["successors"]
        if row["source_path"] == CHECKER.BUILDER.NATIVE_PATH
        and row["predecessor_sha256"] == CHECKER.BUILDER.B23_SUCCESSOR
        and row["successor_sha256"] == CHECKER.BUILDER.CURRENT_SUCCESSOR
    ]
    assert len(rows) == 1
    assert rows[0]["cell_ids"] == ["C6.1", "C6.2"]
    assert len(set(rows[0]["cell_ids"])) == 2


def test_v2_checker_is_read_only_and_v1_bundle_is_unchanged() -> None:
    v1_root = ROOT / CHECKER.BUILDER.V1_REL
    before_v1 = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in v1_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    before_v2 = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in HERE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(HERE / "check_current_byte_binding_successors_v2.py"),
            "--repo-root",
            str(ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["status"] == "PASS"
    after_v1 = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in v1_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    after_v2 = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in HERE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert after_v1 == before_v1
    assert after_v2 == before_v2
