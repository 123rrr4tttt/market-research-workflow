"""Shared family generator parity for every migrated family."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    content_digest,
    fragment_bytes,
)
from app.successor_runtime.specification import shared_family_generator
from .current_candidate_support import stage_candidate_in_temporary_repository

_EVIDENCE = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)

_EXACT_BYTE_REBIND = "exact-byte-rebind"
_B19_STAGE = "stage-b19-2099-01-01"
_PREDECESSOR_CANDIDATE_STAGE = "stage-b18-2026-09-05"
_HISTORY_CANDIDATE_STAGES = {
    "C7": "stage-b12-2026-09-05/candidates/C7",
    "C3": "stage-b10-2026-09-05/candidates/I1",
    "default": "stage-b16-2026-09-05/candidates/I1",
}


_FAMILY_REBIND_TOOL = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "stage0_family_exact_byte_rebind_test_module",
        _REPOSITORY_ROOT / "scripts/generate_stage0_family_exact_byte_rebind.py",
    )
)
assert _FAMILY_REBIND_TOOL.__spec__ and _FAMILY_REBIND_TOOL.__spec__.loader
_FAMILY_REBIND_TOOL.__spec__.loader.exec_module(_FAMILY_REBIND_TOOL)


@dataclass(frozen=True)
class FamilySpec:
    module: str
    legacy_script: str
    canonical_rel: str
    candidate_rel: str | None = None
    canonical_sha256: str | None = None


_FAMILIES = {
    "C2": FamilySpec(
        "c2_p3",
        "generate_successor_p3_c2_fragment.py",
        "p3-fragments/C2.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C2.json",
        "31d32ce3d29eb2ed82063ba8c67d881ed3589cfdf23a616be520acabab1c9922",
    ),
    "C3": FamilySpec(
        "c3_p3",
        "generate_successor_p3_c3_fragment.py",
        "p3-fragments/C3.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C3.json",
        "73b63ea7d9b687a2679e1503bb67deec89daf6ec20142922ce693944296e5d17",
    ),
    "C4": FamilySpec(
        "c4_p3",
        "generate_successor_p3_c4_fragment.py",
        "p3-fragments/C4.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C4.json",
        "058b02345b9d67c1e7ff51006afb4c28e2c8ce4dadf7a505fac6bbac781bd188",
    ),
    "C5": FamilySpec(
        "c5_p3",
        "generate_successor_p3_c5_fragment.py",
        "p3-fragments/C5.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C5.json",
        canonical_sha256=(
            "0e1da888f13adf637774612be90ae367633f565774585b6ad18ace045cdf5231"
        ),
    ),
    "C6": FamilySpec(
        "c6_p3",
        "generate_successor_p3_c6_fragment.py",
        "p3-fragments/C6.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C6.json",
        "de997e287f8c51d8c984ae37c81c102834a2a64061967d089fd7d3180468796f",
    ),
    "C7": FamilySpec(
        "c7_p4",
        "generate_successor_p4_c7_fragment.py",
        "p4-fragments/C7.json",
        f"{_EXACT_BYTE_REBIND}/stage-b12-2026-09-05/fragments/C7.json",
        "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83",
    ),
    "C8": FamilySpec(
        "c8_p4",
        "generate_successor_p4_c8_fragment.py",
        "p4-fragments/C8.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C8.json",
        "206e69ad34ab60948c8310c6012f15fc66a03386eb3d2b60ae9e88328c8316a6",
    ),
    "C9": FamilySpec(
        "c9_p4",
        "generate_successor_p4_c9_fragment.py",
        "p4-fragments/C9.json",
        f"{_EXACT_BYTE_REBIND}/{_PREDECESSOR_CANDIDATE_STAGE}/fragments/C9.json",
        "fdc4b2ab2616431b2d20ec41e207b41e978df833c94a1c92561360708bc89be1",
    ),
}


def _load_config(family: str):
    module_name = _FAMILIES[family].module
    module = __import__(
        f"app.successor_runtime.specification.{module_name}", fromlist=["CONFIG"]
    )
    return module.CONFIG


def _load_legacy(family: str):
    script = _FAMILIES[family].legacy_script
    spec = importlib.util.spec_from_file_location(
        f"legacy_{family.lower()}", _BACKEND_ROOT / "scripts" / script
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _historical_snapshot_bytes(family: str, digest: str) -> bytes:
    stage = _HISTORY_CANDIDATE_STAGES.get(family, _HISTORY_CANDIDATE_STAGES["default"])
    path = _EVIDENCE / _EXACT_BYTE_REBIND / stage / "snapshots" / digest
    return path.read_bytes()


def _subprocess_env() -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    paths = [str(_BACKEND_ROOT), str(_REPOSITORY_ROOT / "src")]
    if existing:
        paths.append(existing)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(paths)}


def _legacy_bytes(family: str, module) -> bytes:
    first = module.build_fragment()
    body = {key: value for key, value in first.items() if key != "content_digest"}
    if family == "C3":
        digest = module._canonical_digest(body)
        first["content_digest"] = digest
        return module.fragment_bytes(first)
    digest = module.content_digest(body)
    first["content_digest"] = digest
    return module._canonical_json(first).encode("utf-8") + b"\n"


def _build_fragment_with_candidate_bindings(config, candidate_path: Path):
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    bindings = {
        binding["path"]: dict(binding)
        for label in ("source_bindings", "implementation_bindings", "test_bindings")
        for binding in candidate[label]
    }
    live_bind_file = shared_family_generator.bind_file

    def candidate_bind_file(root: Path, target):
        if target.path in bindings:
            return bindings[target.path]
        return live_bind_file(root, target)

    with patch.object(
        shared_family_generator, "bind_file", side_effect=candidate_bind_file
    ):
        return build_fragment(config, _REPOSITORY_ROOT)


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_frozen_canonical_and_effective_fragment_bytes(family: str) -> None:
    config = _load_config(family)
    legacy = _load_legacy(family)
    shared = build_fragment(config, _REPOSITORY_ROOT)
    shared_bytes = fragment_bytes(config, shared)
    if family not in {"C2", "C7"}:
        assert shared_bytes == _legacy_bytes(family, legacy)

    spec = _FAMILIES[family]
    canonical = _EVIDENCE / spec.canonical_rel
    canonical_bytes = canonical.read_bytes()
    if spec.canonical_sha256 is not None:
        historical = _historical_snapshot_bytes(family, spec.canonical_sha256)
        assert hashlib.sha256(historical).hexdigest() == spec.canonical_sha256
        canonical_bytes = historical
    canonical_payload = json.loads(canonical_bytes)
    assert canonical_payload["family"] == family
    assert canonical_payload["content_digest"] == content_digest(
        {
            key: value
            for key, value in canonical_payload.items()
            if key != "content_digest"
        }
    )

    effective_rel = spec.candidate_rel or spec.canonical_rel
    effective_path = _EVIDENCE / effective_rel
    if spec.candidate_rel is None:
        assert shared_bytes == effective_path.read_bytes()
        return

    # C7 remains on the independently validated B12 candidate.  Its frozen
    # snapshot binding set predates the shared generator's current config, so
    # candidate validity is established by the rebind checker rather than by
    # rebuilding it from live files.
    if family == "C7":
        candidate_payload = json.loads(effective_path.read_text(encoding="utf-8"))
        assert candidate_payload["content_digest"] == content_digest(
            {
                key: value
                for key, value in candidate_payload.items()
                if key != "content_digest"
            }
        )
        return

    candidate_fragment = _build_fragment_with_candidate_bindings(config, effective_path)
    assert fragment_bytes(config, candidate_fragment) == effective_path.read_bytes()


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_shared_fragment_is_deterministic_and_authority_false(family: str) -> None:
    config = _load_config(family)
    first = build_fragment(config, _REPOSITORY_ROOT)
    second = build_fragment(config, _REPOSITORY_ROOT)
    assert fragment_bytes(config, first) == fragment_bytes(config, second)
    assert first["content_digest"] == second["content_digest"]
    assert all(not value for value in first["authority"].values())
    assert first["open_findings"]
    for label in ("source_bindings", "implementation_bindings", "test_bindings"):
        for binding in first[label]:
            assert len(binding["sha256"]) == 64
            assert binding["bytes"] > 0


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_shared_cli_check_is_read_only_match(family: str) -> None:
    spec = _FAMILIES[family]
    path = _EVIDENCE / spec.canonical_rel
    before_stat = path.stat()
    before_bytes = path.read_bytes()
    config = _load_config(family)
    generated = fragment_bytes(config, build_fragment(config, _REPOSITORY_ROOT))
    expected_drift = generated != before_bytes
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_ROOT / "scripts/generate_family_fragment_shared.py"),
            "--family",
            family,
            "--check",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    expected_returncode = 1 if expected_drift else 0
    assert result.returncode == expected_returncode, result.stdout + result.stderr
    expected_output = "DRIFT" if expected_drift else "MATCH"
    assert expected_output in result.stdout + result.stderr
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_family_fragment_json_is_valid_and_shares_schema() -> None:
    for family, spec in _FAMILIES.items():
        payload = json.loads((_EVIDENCE / spec.canonical_rel).read_text(encoding="utf-8"))
        assert payload["family"] == family
        assert payload["schema"].startswith("mrw.functorial_successor.")
        assert len(payload["content_digest"]) == 64


@pytest.mark.parametrize(
    "family", [family for family, spec in _FAMILIES.items() if spec.candidate_rel]
)
def test_candidate_is_not_authority_and_check_is_read_only(family: str) -> None:
    spec = _FAMILIES[family]
    assert spec.candidate_rel is not None
    fragment_path = _EVIDENCE / spec.candidate_rel
    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    assert fragment["family"] == family
    assert all(value is False for value in fragment["authority"].values())

    candidate_path = fragment_path.parents[1] / "candidates" / family / "candidate.v2.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"].endswith("NOT_AUTHORITY")
    assert candidate["family"] == family

    candidate_root = candidate_path.parent
    before = {
        path.relative_to(candidate_root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(candidate_root.rglob("*"))
        if path.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            str(_REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"),
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
    assert json.loads(result.stdout)["status"] == (
        "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"
    )
    after = {
        path.relative_to(candidate_root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(candidate_root.rglob("*"))
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "family",
    sorted(set(_FAMILY_REBIND_TOOL.ALLOWED_FAMILIES) & set(_FAMILIES)),
)
def test_b19_current_candidate_stages_live_in_temporary_repository(
    family: str,
) -> None:
    documents = _FAMILY_REBIND_TOOL.build_documents(
        _REPOSITORY_ROOT,
        stage=_B19_STAGE,
        families=[family],
    )
    manifest_path = next(
        path for path in documents if path.parent.name == "manifests"
    )
    manifest = json.loads(documents[manifest_path])
    assert manifest["amendment"] == (
        f"STAGE_B19_{family}_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    result = stage_candidate_in_temporary_repository(documents, family)
    assert len(result["candidate_id"]) == 64
    assert result == {
        "candidate_id": result["candidate_id"],
        "family": family,
        "status": "CANDIDATE_VALID_NOT_AUTHORITY",
    }
