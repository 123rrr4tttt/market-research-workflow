from __future__ import annotations

import importlib.util
import json
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


CHECKER = load_module("check_current_byte_binding_successors", HERE / "check_current_byte_binding_successors.py")


def test_current_byte_successor_bundle_is_exact_and_non_authoritative() -> None:
    assert CHECKER.validate(ROOT) == {
        "status": "PASS",
        "source_count": 4,
        "successor_count": 10,
        "authority_ceiling": CHECKER.BUILDER.AUTHORITY_CEILING,
    }


def test_celery_app_successor_preserves_ordered_b23_chain_and_identity() -> None:
    registry = json.loads((HERE / "current-byte-binding-successors.v1.json").read_text())
    celery = next(
        item
        for item in registry["successors"]
        if item["successor_id"] == "i1-c5-4-celery-app-current-bytes-v1"
    )
    assert celery["family"] == "I1"
    assert celery["cell_id"] == "C5.4"
    assert celery["binding_group"] == "source_bindings"
    assert celery["role"] == "legacy_donor_c5_4_normative"
    assert celery["prior_spec_predecessor_sha256"] == CHECKER.BUILDER.CELERY_SPEC_OLD
    assert celery["predecessor_sha256"] == CHECKER.BUILDER.CELERY_B23
    assert celery["successor_sha256"] == CHECKER.BUILDER.CURRENT_SOURCES[
        "main/backend/app/celery_app.py"
    ]["sha256"]
    assert celery["ordered_sha256_chain"] == [
        {"stage": "SPEC_PREDECESSOR", "sha256": CHECKER.BUILDER.CELERY_SPEC_OLD},
        {"stage": "B23_SUCCESSOR", "sha256": CHECKER.BUILDER.CELERY_B23},
        {
            "stage": "CURRENT_WORKING_TREE_SUCCESSOR",
            "sha256": CHECKER.BUILDER.CURRENT_SOURCES["main/backend/app/celery_app.py"]["sha256"],
        },
    ]


def test_current_byte_successor_checker_is_read_only_and_cli_green() -> None:
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in HERE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    completed = subprocess.run(
        [sys.executable, str(HERE / "check_current_byte_binding_successors.py"), "--repo-root", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["status"] == "PASS"
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in HERE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert after == before


def test_predecessor_artifacts_are_referenced_but_never_targeted() -> None:
    registry = json.loads((HERE / "current-byte-binding-successors.v1.json").read_text())
    targets = {item["snapshot_path"] for item in registry["successors"]}
    predecessors = {
        ref["artifact"]
        for item in registry["successors"]
        for ref in item["predecessor_declarations"]
    }
    assert predecessors
    assert all(path.startswith("snapshots/") for path in targets)
    assert not any(path.startswith("stage1-successor-evidence/") for path in predecessors)
    assert not any("/contracts/" in path for path in targets)
