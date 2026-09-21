"""Test support for the additive I1 exact-binding successor chain."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.successor_runtime.specification import CapabilityCellSpec, ExactFileBinding


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
STAGE_ROOT = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b23-2026-09-05"
)
CANDIDATE_PATH = STAGE_ROOT / "candidates/I1/candidate.v2.json"
FRAGMENT_PATH = STAGE_ROOT / "fragments/I1.json"
CHECKER_PATH = REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"

CURRENT_SUCCESSOR_ROOT = (
    REPOSITORY_ROOT
    / "stage1-successor-evidence/current-byte-remediation-v2/bindings"
)
CURRENT_SUCCESSOR_REGISTRY_PATH = (
    CURRENT_SUCCESSOR_ROOT / "current-byte-binding-successors.v2.json"
)
CURRENT_SUCCESSOR_CHECKER_PATH = (
    CURRENT_SUCCESSOR_ROOT / "check_current_byte_binding_successors_v2.py"
)
CURRENT_SUCCESSOR_AUTHORITY_CEILING = (
    "EXACT_BYTE_CORRESPONDENCE_ONLY_NO_CANDIDATE_PROMOTION_NO_STAGE0_REWRITE_"
    "NO_PRODUCTION_AUTHORITY"
)
DIRECT_SUCCESSOR_ROOT = (
    REPOSITORY_ROOT / "stage1-successor-evidence/current-byte-remediation-v3/bindings"
)
SEMANTIC_SUCCESSOR_ROOT = (
    REPOSITORY_ROOT / "stage1-successor-evidence/current-byte-remediation-v3/semantic-bindings"
)

# B23 is a frozen predecessor projection. These immutable identifiers pin the
# audited candidate inputs without making that historical candidate authoritative.
CURRENT_CANDIDATE_ID = (
    "76f1ff619f769191e6ad2e087ded884f1d9672478565e91b6bfa0f185b2074cb"
)
CURRENT_CANDIDATE_SHA256 = (
    "bb4fc787fbc0d1959f04797e45a99b3da1d00a544501ab30abcc5ff017af0e7e"
)
CURRENT_FRAGMENT_SHA256 = (
    "8c99a91c0891589073318c9b872d977ec95e37e8e206e66255c88f72578d9110"
)
CURRENT_MANIFEST_SHA256 = (
    "00b0f89e5278f6aee3f5298e5b466d55326292a3fb3421c84daab5740e990521"
)

B22_HISTORY_ROOT = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b22-2026-09-05"
)
B22_HISTORY_CANDIDATE_PATH = B22_HISTORY_ROOT / "candidates/I1/candidate.v2.json"

B21_HISTORY_ROOT = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b21-2026-09-05"
)
B21_HISTORY_CANDIDATE_PATH = B21_HISTORY_ROOT / "candidates/I1/candidate.v2.json"

B20_HISTORY_ROOT = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b20-2026-09-05"
)
B20_HISTORY_CANDIDATE_PATH = B20_HISTORY_ROOT / "candidates/I1/candidate.v2.json"

B19_HISTORY_ROOT = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b19-2026-09-05"
)
B19_HISTORY_CANDIDATE_PATH = B19_HISTORY_ROOT / "candidates/I1/candidate.v2.json"

# Earlier stages remain history-only witnesses. They are intentionally kept
# separate from the current successor registry so a later stage cannot rewrite history.
B10_CANDIDATE_PATH = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b10-2026-09-05/candidates/I1/candidate.v2.json"
)
# B22 remains the immediate predecessor witness; it is never checked as live.
PREDECESSOR_CANDIDATE_PATH = B22_HISTORY_CANDIDATE_PATH
B16_CANDIDATE_PATH = (
    REPOSITORY_ROOT
    / TOPIC
    / "evidence/exact-byte-rebind/stage-b16-2026-09-05/candidates/I1/candidate.v2.json"
)


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


def _binding_key(
    cell_id: str,
    group: str,
    binding: ExactFileBinding,
) -> tuple[str, str, str, str, str]:
    return (
        cell_id,
        group,
        binding.path,
        binding.role,
        binding.file_sha256,
    )


@lru_cache(maxsize=1)
def _candidate_bindings() -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    _, fragment = candidate_context()
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for item in fragment["bindings"]:
        key = (
            item["cell_id"],
            item["binding_group"],
            item["path"],
            item["role"],
            item["predecessor_sha256"],
        )
        assert key not in result
        result[key] = item
    return result


def check_current_successor_live() -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the current-byte checker as the default live binding check."""
    completed = subprocess.run(
        [
            sys.executable,
            str(CURRENT_SUCCESSOR_CHECKER_PATH),
            "--repo-root",
            str(REPOSITORY_ROOT),
        ],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    registry = _load_object(CURRENT_SUCCESSOR_REGISTRY_PATH)
    outcome = json.loads(completed.stdout)
    assert outcome["status"] == "PASS"
    assert outcome["authority_ceiling"] == CURRENT_SUCCESSOR_AUTHORITY_CEILING
    assert outcome["successor_count"] == len(registry["successors"])
    assert outcome["source_count"] == len(
        {item["source_path"] for item in registry["successors"]}
    )
    assert registry["schema"] == "mrw.current_byte_binding_successors.v2"
    assert registry["status"] == (
        "CURRENT_BYTES_BOUND_BY_ADDITIVE_SUCCESSORS_NOT_AUTHORITY"
    )
    assert registry["authoritative"] is False
    assert registry["authority"] and not any(registry["authority"].values())
    assert registry["authority_ceiling"] == CURRENT_SUCCESSOR_AUTHORITY_CEILING
    extends = registry["extends"]
    assert extends["mutation"] is False
    predecessor_path = REPOSITORY_ROOT / extends["path"]
    assert _sha256(predecessor_path.read_bytes()) == extends["sha256"]
    predecessor_registry = _load_object(predecessor_path)
    assert predecessor_registry["schema"] == extends["schema"]
    assert predecessor_registry["record_id"] == extends["record_id"]
    assert predecessor_registry["content_digest"] == extends["content_digest"]
    assert predecessor_registry["declaration_alignment"]["b19_and_b23_candidates"] == (
        "IMMUTABLE_PREDECESSOR_DECLARATIONS"
    )
    for stage in ("stage0_v3", "stage0_v4"):
        declaration = predecessor_registry["declaration_alignment"][stage]
        assert declaration["preserved"] is True
        assert _sha256((REPOSITORY_ROOT / declaration["path"]).read_bytes()) == (
            declaration["sha256"]
        )
    return outcome, registry


def _expand_current_binding_successors(
    registry: dict[str, Any],
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Expand singleton and shared I1 rows into exact lookup keys."""
    successors = registry.get("successors")
    inherited_count = registry.get("inherited_successor_count")
    extends = registry.get("extends")
    assert isinstance(successors, list)
    assert isinstance(inherited_count, int) and 0 <= inherited_count <= len(successors)
    assert isinstance(extends, dict) and isinstance(extends.get("path"), str)
    inherited_snapshot_root = (REPOSITORY_ROOT / extends["path"]).parent

    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for index, raw_item in enumerate(successors):
        assert isinstance(raw_item, dict)
        relation = raw_item.get("relation")
        if relation == "I1_EXACT_BINDING_SUCCESSOR":
            cell_ids = (raw_item.get("cell_id"),)
        elif relation == "I1_SHARED_EXACT_BINDING_SUCCESSOR":
            shared_cell_ids = raw_item.get("cell_ids")
            assert isinstance(shared_cell_ids, list) and shared_cell_ids
            assert all(isinstance(cell_id, str) and cell_id for cell_id in shared_cell_ids)
            assert len(shared_cell_ids) == len(set(shared_cell_ids))
            cell_ids = tuple(shared_cell_ids)
            spec_bindings = raw_item.get("spec_bindings")
            assert isinstance(spec_bindings, list)
            assert {binding.get("cell_id") for binding in spec_bindings} == set(cell_ids)
        else:
            continue
        for cell_id in cell_ids:
            assert isinstance(cell_id, str) and cell_id
            item = dict(raw_item)
            item["cell_id"] = cell_id
            item["snapshot_root"] = (
                inherited_snapshot_root
                if index < inherited_count
                else CURRENT_SUCCESSOR_ROOT
            )
            key = (
                cell_id,
                item["binding_group"],
                item["source_path"],
                item["role"],
                item["prior_spec_predecessor_sha256"],
            )
            assert key not in result, f"duplicate expanded I1 successor key: {key}"
            result[key] = item
    assert result
    return result


def _current_binding_successors() -> dict[
    tuple[str, str, str, str, str], dict[str, Any]
]:
    _, registry = check_current_successor_live()
    result = _expand_current_binding_successors(registry)
    # v3 preserves v2 and adds a separately checked C5 approval-failure refinement.
    direct_registry = _checked_direct_successor_registry()
    repairs = [row for row in direct_registry["successors"][11:]
               if row.get("relation") == "I1_SHARED_EXACT_BINDING_SUCCESSOR"]
    if repairs:
        expanded = _expand_current_binding_successors({
            "successors": repairs, "inherited_successor_count": 0,
            "extends": direct_registry["extends"],
        })
        assert not (result.keys() & expanded.keys()), "ambiguous current I1 repair"
        for row in expanded.values():
            row["snapshot_root"] = DIRECT_SUCCESSOR_ROOT
        result.update(expanded)
    semantic_registry = _checked_semantic_successor_registry()
    semantic = _expand_current_binding_successors({
        "successors": semantic_registry["successors"],
        "inherited_successor_count": 0,
        "extends": semantic_registry["extends"],
    })
    assert not (result.keys() & semantic.keys()), "ambiguous semantic current I1 repair"
    for row in semantic.values():
        row["snapshot_root"] = SEMANTIC_SUCCESSOR_ROOT
    result.update(semantic)
    return result


@lru_cache(maxsize=1)
def _checked_direct_successor_registry() -> dict[str, Any]:
    """Validate v3 without replacing the inherited v2 cell-binding chain."""
    completed = subprocess.run(
        [sys.executable, str(DIRECT_SUCCESSOR_ROOT / "check_current_byte_binding_successors_v3.py"),
         "--repo-root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["status"] == "PASS"
    assert outcome["authority_ceiling"] == CURRENT_SUCCESSOR_AUTHORITY_CEILING
    registry = _load_object(DIRECT_SUCCESSOR_ROOT / "current-byte-binding-successors.v3.json")
    assert registry["schema"] == "mrw.current_byte_binding_successors.v3"
    assert registry["authoritative"] is False
    return registry


@lru_cache(maxsize=1)
def _checked_semantic_successor_registry() -> dict[str, Any]:
    """Validate the additive semantic-movement current-byte extension."""
    completed = subprocess.run(
        [sys.executable, str(SEMANTIC_SUCCESSOR_ROOT / "check_semantic_binding_successors_v3.py"),
         "--repo-root", str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    outcome = json.loads(completed.stdout)
    assert outcome["status"] == "PASS"
    assert outcome["authority_ceiling"] == CURRENT_SUCCESSOR_AUTHORITY_CEILING
    registry = _load_object(
        SEMANTIC_SUCCESSOR_ROOT / "semantic-binding-successors.v3.json"
    )
    assert registry["schema"] == "mrw.current_byte_semantic_binding_successors.v3"
    assert registry["authoritative"] is False
    return registry


def _match_direct_successor(registry, cell_id, group, binding, actual):
    """A direct declaration admits only its explicitly frozen cell and role."""
    matches = []
    for row in registry["successors"]:
        if (row.get("relation") != "C5_C6_I1_SHARED_EXACT_BINDING_SUCCESSOR"
                or row.get("source_path") != binding.path
                or row.get("binding_group") != group
                or row.get("predecessor_sha256") != binding.file_sha256
                or row.get("successor_sha256") != actual):
            continue
        owning_cells = [item for item in row["frozen_cell_sources"]
                        if item["cell_id"] == cell_id and item["role"] == binding.role]
        i1_declarations = [item for item in row["direct_candidate_declarations"]
                           if item["family"] == "I1"
                           and item["candidate_path"] == str(CANDIDATE_PATH.relative_to(REPOSITORY_ROOT))
                           and item["candidate_sha256"] == CURRENT_CANDIDATE_SHA256
                           and item["predecessor_sha256"] == binding.file_sha256]
        if len(owning_cells) == 1 and len(i1_declarations) == 1:
            matches.append(row)
    assert len(matches) <= 1, "ambiguous direct I1 successor"
    return matches[0] if matches else None


def direct_successor_binding_keys() -> set[tuple[str, str, str, str, str]]:
    registry = _checked_direct_successor_registry()
    return {
        (cell["cell_id"], row["binding_group"], row["source_path"], cell["role"], row["predecessor_sha256"])
        for row in registry["successors"]
        if row.get("relation") == "C5_C6_I1_SHARED_EXACT_BINDING_SUCCESSOR"
        for cell in row["frozen_cell_sources"]
    }


def verify_exact_binding(
    spec: CapabilityCellSpec,
    group: str,
    binding: ExactFileBinding,
) -> str:
    path = Path(binding.path)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    resolved = path.resolve()
    assert resolved.is_relative_to(REPOSITORY_ROOT.resolve()), (
        f"exact binding escapes repository root: {binding.path}"
    )
    assert resolved.is_file(), f"exact binding missing: {binding.path}"
    payload = resolved.read_bytes()
    actual = _sha256(payload)
    if actual == binding.file_sha256:
        return "PREDECESSOR_MATCH"

    candidate, _ = candidate_context()
    key = _binding_key(spec.cell_id, group, binding)
    item = _candidate_bindings().get(key)
    if item is None:
        direct = _match_direct_successor(
            _checked_direct_successor_registry(), spec.cell_id, group, binding, actual)
        assert direct is not None, f"unbound direct I1 drift: {spec.cell_id}: {binding.path}"
        assert direct["bytes"] == len(payload)
        snapshot = DIRECT_SUCCESSOR_ROOT / direct["snapshot_path"]
        assert snapshot.read_bytes() == payload
        return "ADDITIVE_CURRENT_BYTE_SUCCESSOR_NOT_AUTHORITY"
    assert item is not None, (
        f"unbound I1 exact-binding drift: {spec.cell_id}: {binding.path}: "
        f"{actual} != {binding.file_sha256}"
    )
    spec_path = REPOSITORY_ROOT / item["spec_path"]
    assert _sha256(spec_path.read_bytes()) == item["spec_sha256"]
    if item["successor_sha256"] == actual:
        assert item["bytes"] == len(payload)
        source_ref = next(
            ref
            for ref in candidate["sources"]
            if ref["path"] == binding.path and ref["file_sha256"] == actual
        )
        snapshot = CANDIDATE_PATH.parent / source_ref["snapshot_path"]
        assert snapshot.read_bytes() == payload
        return "ADDITIVE_CANDIDATE_NOT_AUTHORITY"

    current = _current_binding_successors().get(key)
    assert current is not None, (
        f"unbound current-byte I1 drift: {spec.cell_id}: {binding.path}: "
        f"{actual} != {item['successor_sha256']}"
    )
    assert current["predecessor_sha256"] == item["successor_sha256"]
    assert current["successor_sha256"] == actual
    assert current["bytes"] == len(payload)
    snapshot = current["snapshot_root"] / current["snapshot_path"]
    assert snapshot.read_bytes() == payload
    return "ADDITIVE_CURRENT_BYTE_SUCCESSOR_NOT_AUTHORITY"


def verify_spec_bindings(spec: CapabilityCellSpec) -> list[str]:
    dispositions: list[str] = []
    for group, bindings in (
        ("source_bindings", spec.source_bindings),
        ("test_bindings", spec.test_bindings),
        ("rollback_bindings", spec.rollback_bindings),
    ):
        dispositions.extend(
            verify_exact_binding(spec, group, binding) for binding in bindings
        )
    return dispositions


def candidate_binding_keys() -> set[tuple[str, str, str, str, str]]:
    return set(_candidate_bindings())


def current_successor_binding_keys() -> set[tuple[str, str, str, str, str]]:
    return set(_current_binding_successors())
