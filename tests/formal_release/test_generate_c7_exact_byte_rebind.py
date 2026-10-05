"""Read-only validation for the retired C7 exact-byte rebind history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
EXACT_REBIND = EVIDENCE / "exact-byte-rebind"
P4_FRAGMENT = EVIDENCE / "p4-fragments/C7.json"

_STAGE_ROOTS = {
    "B8": EXACT_REBIND / "stage-b8-2026-09-05",
    "B11": EXACT_REBIND / "stage-b11-2026-09-05",
    "B12": EXACT_REBIND / "stage-b12-2026-09-05",
    "B18": EXACT_REBIND / "stage-b18-2026-09-05",
    "B19": EXACT_REBIND / "stage-b19-2026-09-05",
    "B23": EXACT_REBIND / "stage-b23-2026-09-07",
}

_EXPECTED_FILE_SHA256 = {
    P4_FRAGMENT: "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83",
    _STAGE_ROOTS["B8"] / "fragments/C7.json": "d1724ee0a77f6808f6266106c5aea9640e0649c3b29a9527518a14b3af3b30e7",
    _STAGE_ROOTS["B8"] / "manifests/C7.json": "10d6200d1c2d36523ef71ac3ca3ec255333d714e953405f22294974557bd4321",
    _STAGE_ROOTS["B8"] / "candidates/C7/candidate.v2.json": "6101a031f6b089ee628af41e993d599dab7170a69d686cb714b8b2d00c01508a",
    _STAGE_ROOTS["B11"] / "fragments/C7.json": "70f35fb895558ab2c98f8f203c8130ea0d5af9098d02b9dbfbb7f2ae65926266",
    _STAGE_ROOTS["B11"] / "manifests/C7.json": "5a08ea38b8e987b2efbfd0c9bd329285391d10d66ba23dafa02c21b2f1f83c1d",
    _STAGE_ROOTS["B11"] / "candidates/C7/candidate.v2.json": "8ff4a4173a9708f6f15eb43ead435d1037dd868083113759e86c7f1e32c65bbf",
    _STAGE_ROOTS["B12"] / "fragments/C7.json": "23b3d2978e19c53ef9cf2689ed687b9e7a670bf922a9861ef622ce0804793489",
    _STAGE_ROOTS["B12"] / "manifests/C7.json": "371ebdf820bf60fc633dc0ae18090942404afc355832d312b7b5207416ae206e",
    _STAGE_ROOTS["B12"] / "candidates/C7/candidate.v2.json": "12cc0ecd4c0bf7e529ac51a18d225685f048c5e5a7b5e19d9c204a7b6910a817",
    _STAGE_ROOTS["B18"] / "fragments/C7.json": "f4f571eab84dca83015cd5d247f221696aedc30ca99f97fe3530ce4b97a25ff2",
    _STAGE_ROOTS["B18"] / "manifests/C7.json": "d12a24c3de1894f08796b5eef736b9a5f17d1ada90c44b4fad0fc179ad4d1c92",
    _STAGE_ROOTS["B18"] / "candidates/C7/candidate.v2.json": "b018ee04a5108beb5e9603e47ecac81d4c69496a4fb97037071cea24ee3aa340",
    _STAGE_ROOTS["B19"] / "fragments/C7.json": "b1bdc5524461cf84638f3ec86dbb68d5e2d5a4cc164bbc4f277f26d7457a7aa1",
    _STAGE_ROOTS["B19"] / "manifests/C7.json": "8c697b0736bbb0b1083707a559d4a1d22bcf5a4d185dc7909b8bb3c21ec4662c",
    _STAGE_ROOTS["B19"] / "candidates/C7/candidate.v2.json": "630e2bb6d77b5f6de24357e331c5dd8fcb31cf9135d400187ce71f01058e1c6b",
    _STAGE_ROOTS["B23"] / "fragments/C7.json": "6824c30fc94da8d8198b52682b40540da665c8648ba34d4417c6325f3f02f2a2",
    _STAGE_ROOTS["B23"] / "manifests/C7.json": "4a08edfc8e13c76999f34270ec72d334feac91e1336c688e03563b716e236ca6",
    _STAGE_ROOTS["B23"] / "candidates/C7/candidate.v2.json": "a7ff7ffa62b1e2541d5f54e6b1d6a7d71e4215b4ef63addb2d88b6b2bd6807c5",
}

_EXPECTED_AMENDMENTS = {
    "B8": "STAGE_B8_BOUND_WITNESS_REBIND_CANDIDATE_NOT_AUTHORITY",
    "B11": "STAGE_B11_C7_TOTAL_FAILURE_REBIND_CANDIDATE_NOT_AUTHORITY",
    "B12": "STAGE_B12_C7_FINAL_FAILURE_REBIND_CANDIDATE_NOT_AUTHORITY",
    "B18": "STAGE_B18_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
    "B19": "STAGE_B19_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
    "B23": "STAGE_B23_C7_CURRENT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _content_digest(value: dict[str, object]) -> str:
    body = {key: item for key, item in value.items() if key != "content_digest"}
    canonical = json.dumps(
        body, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@pytest.mark.parametrize(("path", "expected"), sorted(_EXPECTED_FILE_SHA256.items()))
def test_frozen_c7_rebind_file_bytes_are_fixed(path: Path, expected: str) -> None:
    assert path.is_file(), path
    assert _sha256(path) == expected


def test_frozen_p4_fragment_schema_digest_and_authority_ceiling() -> None:
    fragment = json.loads(P4_FRAGMENT.read_text(encoding="utf-8"))
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert all(value is False for value in fragment["authority"].values())
    assert fragment["content_digest"] == _content_digest(fragment)


@pytest.mark.parametrize("stage", sorted(_STAGE_ROOTS))
def test_frozen_c7_stage_records_are_history_only(stage: str) -> None:
    root = _STAGE_ROOTS[stage]
    fragment_path = root / "fragments/C7.json"
    manifest_path = root / "manifests/C7.json"
    candidate_path = root / "candidates/C7/candidate.v2.json"

    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert all(value is False for value in fragment["authority"].values())
    assert fragment["content_digest"] == _content_digest(fragment)

    assert manifest["schema"] == "mrw.family_fragment_rebind.stage_manifest.v2"
    assert manifest["family"] == "C7"
    assert manifest["amendment"] == _EXPECTED_AMENDMENTS[stage]
    manifest_fragment = manifest["fragments"][0]
    assert manifest_fragment["path"] == fragment_path.relative_to(ROOT).as_posix()
    assert manifest_fragment["file_sha256"] == _sha256(fragment_path)
    assert manifest_fragment["content_digest"] == fragment["content_digest"]

    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["family"] == "C7"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"] == _EXPECTED_AMENDMENTS[stage]
    assert candidate["content_digest"] == _content_digest(candidate)
    candidate_fragment = candidate["fragments"][0]
    assert candidate_fragment["path"] == fragment_path.relative_to(ROOT).as_posix()
    assert candidate_fragment["file_sha256"] == _sha256(fragment_path)
    assert candidate_fragment["content_digest"] == fragment["content_digest"]
    assert candidate["manifest"]["path"] == manifest_path.relative_to(ROOT).as_posix()
    assert candidate["manifest"]["file_sha256"] == _sha256(manifest_path)
