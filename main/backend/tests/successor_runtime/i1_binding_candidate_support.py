"""Read-only support for the frozen I1 exact-binding successor evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
STAGE_ROOT = REPOSITORY_ROOT / TOPIC / "evidence/exact-byte-rebind/stage-b23-2026-09-05"
CANDIDATE_PATH = STAGE_ROOT / "candidates/I1/candidate.v2.json"
FRAGMENT_PATH = STAGE_ROOT / "fragments/I1.json"
CHECKER_PATH = REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"

B22_HISTORY_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b22-2026-09-05/candidates/I1/candidate.v2.json"
)
B21_HISTORY_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b21-2026-09-05/candidates/I1/candidate.v2.json"
)
B20_HISTORY_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b20-2026-09-05/candidates/I1/candidate.v2.json"
)
B19_HISTORY_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b19-2026-09-05/candidates/I1/candidate.v2.json"
)
B16_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b16-2026-09-05/candidates/I1/candidate.v2.json"
)
B10_CANDIDATE_PATH = (
    REPOSITORY_ROOT / TOPIC
    / "evidence/exact-byte-rebind/stage-b10-2026-09-05/candidates/I1/candidate.v2.json"
)

CURRENT_CANDIDATE_ID = "76f1ff619f769191e6ad2e087ded884f1d9672478565e91b6bfa0f185b2074cb"
CURRENT_CANDIDATE_SHA256 = "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e"
CURRENT_FRAGMENT_SHA256 = "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110"
CURRENT_MANIFEST_SHA256 = "00b0f89e5278f6aee3f5298e5b466d55326292a3fb3421c84daab5740e990521"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_digest(value: dict[str, Any]) -> str:
    return _sha256(
        _canonical_json(
            {key: item for key, item in value.items() if key != "content_digest"}
        )
    )


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


@lru_cache(maxsize=1)
def candidate_context() -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = _load_object(CANDIDATE_PATH)
    fragment = _load_object(FRAGMENT_PATH)
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["family"] == "I1"
    assert candidate["candidate_id"] == CURRENT_CANDIDATE_ID
    assert _sha256(CANDIDATE_PATH.read_bytes()) == CURRENT_CANDIDATE_SHA256
    assert candidate["amendment"] == (
        "STAGE_B23_I1_EXACT_BINDING_REBIND_CANDIDATE_NOT_AUTHORITY"
    )
    assert candidate["content_digest"] == _content_digest(candidate)
    assert fragment["schema"] == "mrw.i1.exact_binding_rebind.fragment.v1"
    assert fragment["status"] == "CANDIDATE_NOT_AUTHORITY"
    assert _sha256(FRAGMENT_PATH.read_bytes()) == CURRENT_FRAGMENT_SHA256
    assert candidate["manifest"]["file_sha256"] == CURRENT_MANIFEST_SHA256
    assert fragment["content_digest"] == _content_digest(fragment)
    assert fragment["frozen_spec_count"] == 30
    assert fragment["frozen_build_manifest_count"] == 30
    assert fragment["authority"] and not any(fragment["authority"].values())
    fragment_ref = candidate["fragments"]
    assert len(fragment_ref) == 1
    assert fragment_ref[0]["file_sha256"] == _sha256(FRAGMENT_PATH.read_bytes())
    return candidate, fragment


def _binding_text(binding: Mapping[str, object] | object, key: str) -> str:
    value = binding[key] if isinstance(binding, Mapping) else getattr(binding, key)
    if not isinstance(value, str):
        raise TypeError(f"binding {key} must be text")
    return value


def _match_historical_direct_successor(
    registry: dict[str, Any],
    cell_id: str,
    group: str,
    binding: Mapping[str, object] | object,
    actual: str,
) -> dict[str, Any] | None:
    """Read frozen direct-successor evidence without granting current status."""
    path = _binding_text(binding, "path")
    predecessor = _binding_text(binding, "file_sha256")
    role = _binding_text(binding, "role")
    matches: list[dict[str, Any]] = []
    for row in registry["successors"]:
        if (
            row.get("relation") != "C5_C6_I1_SHARED_EXACT_BINDING_SUCCESSOR"
            or row.get("source_path") != path
            or row.get("binding_group") != group
            or row.get("predecessor_sha256") != predecessor
            or row.get("successor_sha256") != actual
        ):
            continue
        owning_cells = [
            item for item in row["frozen_cell_sources"]
            if item["cell_id"] == cell_id and item["role"] == role
        ]
        i1_declarations = [
            item for item in row["direct_candidate_declarations"]
            if item["family"] == "I1"
            and item["candidate_path"] == str(CANDIDATE_PATH.relative_to(REPOSITORY_ROOT))
            and item["candidate_sha256"] == CURRENT_CANDIDATE_SHA256
            and item["predecessor_sha256"] == predecessor
        ]
        if len(owning_cells) == 1 and len(i1_declarations) == 1:
            matches.append(row)
    assert len(matches) <= 1, "ambiguous direct I1 successor"
    return matches[0] if matches else None


def _match_direct_successor(
    registry: dict[str, Any],
    cell_id: str,
    group: str,
    binding: Mapping[str, object] | object,
    actual: str,
) -> dict[str, Any] | None:
    """Resolve only the surviving C5.2 identity from historical declarations."""
    if cell_id != "C5.2":
        return None
    return _match_historical_direct_successor(
        registry, cell_id, group, binding, actual
    )
