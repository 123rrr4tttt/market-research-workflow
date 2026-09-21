"""Current and historical family fragment rebind candidate meta-tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.checksum import content_digest
from .current_candidate_support import (
    TEMPORARY_B19_STAGE,
    stage_candidate_in_temporary_repository,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_EVIDENCE_ROOT = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
_REBIND_CHECKER = _REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"
_EXACT_BYTE_REBIND = "exact-byte-rebind"
_STAGE_B8 = "stage-b8-2026-09-05"
_STAGE_B11 = "stage-b11-2026-09-05"
_STAGE_B12 = "stage-b12-2026-09-05"
_STAGE_B18 = "stage-b18-2026-09-05"


@dataclass(frozen=True)
class FamilySpec:
    module: str
    canonical_rel: str
    candidate_rel: str
    canonical_sha256: str
    amendment: str
    live_current: bool


_FAMILIES = {
    "C4": FamilySpec(
        "c4_p3",
        "p3-fragments/C4.json",
        f"{_EXACT_BYTE_REBIND}/stage-b23-2026-09-07/fragments/C4.json",
        "058b02345b9d67c1e7ff51006afb4c28e2c8ce4dadf7a505fac6bbac781bd188",
        "STAGE_B23_C4_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
        True,
    ),
    "C6": FamilySpec(
        "c6_p3",
        "p3-fragments/C6.json",
        f"{_EXACT_BYTE_REBIND}/stage-b23-2026-09-07/fragments/C6.json",
        "de997e287f8c51d8c984ae37c81c102834a2a64061967d089fd7d3180468796f",
        "STAGE_B23_C6_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
        True,
    ),
    "C7": FamilySpec(
        "c7_p4",
        "p4-fragments/C7.json",
        f"{_EXACT_BYTE_REBIND}/stage-b23-2026-09-07/fragments/C7.json",
        "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83",
        "STAGE_B23_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
        True,
    ),
    "C9": FamilySpec(
        "c9_p4",
        "p4-fragments/C9.json",
        f"{_EXACT_BYTE_REBIND}/stage-b23-2026-09-07/fragments/C9.json",
        "fdc4b2ab2616431b2d20ec41e207b41e978df833c94a1c92561360708bc89be1",
        "STAGE_B23_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
        True,
    ),
}

_LIVE_STATUS = "CANDIDATE_VALID_NOT_AUTHORITY"
_HISTORY_STATUS = "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"
_CANDIDATE_SCHEMA = "mrw.family_fragment_rebind.candidate.v2"


_C7_REBIND_TOOL = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "generate_c7_exact_byte_rebind_test_module",
        _REPOSITORY_ROOT / "scripts/generate_c7_exact_byte_rebind.py",
    )
)
assert _C7_REBIND_TOOL.__spec__ and _C7_REBIND_TOOL.__spec__.loader
_C7_REBIND_TOOL.__spec__.loader.exec_module(_C7_REBIND_TOOL)


def _load_config(family: str):
    module_name = _FAMILIES[family].module
    module = __import__(
        f"app.successor_runtime.specification.{module_name}", fromlist=["CONFIG"]
    )
    return module.CONFIG


def _file_snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): _file_snapshot(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _canonical_path(family: str) -> Path:
    return _EVIDENCE_ROOT / _FAMILIES[family].canonical_rel


def _candidate_fragment_path(family: str) -> Path:
    return _EVIDENCE_ROOT / _FAMILIES[family].candidate_rel


def _candidate_path(family: str) -> Path:
    return _candidate_fragment_path(family).parent.parent / "candidates" / family / (
        "candidate.v2.json"
    )


@pytest.mark.parametrize("stage", [_STAGE_B8, _STAGE_B11, _STAGE_B18])
def test_c7_predecessors_are_history_only(stage: str) -> None:
    candidate_path = (
        _EVIDENCE_ROOT
        / _EXACT_BYTE_REBIND
        / stage
        / "candidates/C7/candidate.v2.json"
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    result = subprocess.run(
        [
            sys.executable,
            str(_REBIND_CHECKER),
            "check-candidate",
            "--repo-root",
            str(_REPOSITORY_ROOT),
            "--candidate",
            candidate_path.relative_to(_REPOSITORY_ROOT).as_posix(),
            "--history-only",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "candidate_id": candidate["candidate_id"],
        "family": "C7",
        "status": _HISTORY_STATUS,
    }


def test_b19_c7_current_candidate_stages_live_in_temporary_repository() -> None:
    documents = _C7_REBIND_TOOL._build_documents(
        _REPOSITORY_ROOT,
        stage=TEMPORARY_B19_STAGE,
    )
    fragment_path = next(
        path for path in documents if path.parent.name == "fragments"
    )
    fragment = json.loads(documents[fragment_path])
    assert fragment["family"] == "C7"
    assert all(not value for value in fragment["authority"].values())
    result = stage_candidate_in_temporary_repository(documents, "C7")
    assert len(result["candidate_id"]) == 64
    assert result == {
        "candidate_id": result["candidate_id"],
        "family": "C7",
        "status": _LIVE_STATUS,
    }


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_family_candidate_meta_contract_and_read_only_checks(family: str) -> None:
    spec = _FAMILIES[family]
    config = _load_config(family)
    self_path = Path(__file__).resolve().relative_to(_REPOSITORY_ROOT).as_posix()
    assert self_path not in {binding.path for binding in config.test_bindings}

    canonical_path = _canonical_path(family)
    canonical_before = _file_snapshot(canonical_path)
    canonical_bytes = canonical_before[0]
    assert hashlib.sha256(canonical_bytes).hexdigest() == spec.canonical_sha256
    canonical_payload = json.loads(canonical_bytes)
    assert canonical_payload["family"] == family
    assert canonical_payload["content_digest"] == content_digest(
        {
            key: value
            for key, value in canonical_payload.items()
            if key != "content_digest"
        }
    )

    candidate_fragment_path = _candidate_fragment_path(family)
    candidate_stage_root = candidate_fragment_path.parent.parent
    candidate_path = _candidate_path(family)
    candidate_tree_before = _tree_snapshot(candidate_stage_root)

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_id = candidate["candidate_id"]
    assert candidate["schema"] == _CANDIDATE_SCHEMA
    assert candidate["status"] == _LIVE_STATUS
    assert candidate["family"] == family
    assert candidate["amendment"] == spec.amendment
    assert candidate["content_digest"] == content_digest(
        {key: value for key, value in candidate.items() if key != "content_digest"}
    )
    candidate_reference_paths = {
        reference["path"]
        for group in ("sources", "tests", "fragments")
        for reference in candidate[group]
    }
    assert self_path not in candidate_reference_paths

    candidate_fragment_ref = candidate["fragments"][0]
    candidate_fragment_bytes = candidate_fragment_path.read_bytes()
    candidate_fragment = json.loads(candidate_fragment_bytes)
    assert candidate_fragment_ref["path"] == candidate_fragment_path.relative_to(
        _REPOSITORY_ROOT
    ).as_posix()
    assert candidate_fragment_ref["bytes"] == len(candidate_fragment_bytes)
    assert candidate_fragment_ref["file_sha256"] == hashlib.sha256(
        candidate_fragment_bytes
    ).hexdigest()
    assert candidate_fragment_ref["content_digest"] == candidate_fragment["content_digest"]
    assert candidate_fragment["family"] == family
    assert all(value is False for value in candidate_fragment["authority"].values())
    assert candidate_fragment["content_digest"] == content_digest(
        {
            key: value
            for key, value in candidate_fragment.items()
            if key != "content_digest"
        }
    )

    checks = [(("--history-only",), _HISTORY_STATUS)]
    if spec.live_current:
        checks.insert(0, ((), _LIVE_STATUS))
    for extra_args, expected_status in checks:
        result = subprocess.run(
            [
                sys.executable,
                str(_REBIND_CHECKER),
                "check-candidate",
                "--repo-root",
                str(_REPOSITORY_ROOT),
                "--candidate",
                candidate_path.relative_to(_REPOSITORY_ROOT).as_posix(),
                *extra_args,
            ],
            cwd=_BACKEND_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {
            "candidate_id": candidate_id,
            "family": family,
            "status": expected_status,
        }
        assert _tree_snapshot(candidate_stage_root) == candidate_tree_before
        assert _file_snapshot(canonical_path) == canonical_before
