#!/usr/bin/env python3
"""Build deterministic, working-tree-bound P3 aggregate evidence.

The default mode is read-only.  Incomplete external reviews are represented as
unsatisfied prerequisites, never inferred from fragment-local review text.  An
incomplete aggregate may only be staged below the operating-system temporary
directory.  Writing the canonical evidence path additionally requires every
prerequisite and an explicit ``--allow-canonical-write`` switch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Direct execution (``python scripts/generate_...py``) puts only the scripts
# directory on sys.path, whereas module execution already exposes backend.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_successor_migration_batch import (
    BATCH_SCHEMA,
    canonical_content_digest,
    canonical_json_bytes,
    validate_batch,
    validate_p3_aggregate_document,
)

AGGREGATE_SCHEMA = "mrw.functorial_successor.p3_capability_migration.v1"
FAMILY_ORDER = ("C2", "C3", "C4", "C5", "C6")
CELL_ORDER = (
    "C2.2",
    "C2.3",
    "C2.4",
    "C3.1",
    "C3.2",
    "C4.1",
    "C4.2",
    "C4.3",
    "C5.1",
    "C5.2",
    "C5.3",
    "C5.4",
    "C6.1",
    "C6.2",
    "C6.3",
)

TOPIC_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
DEFAULT_LEDGER_REL = TOPIC_REL / "04_functorial-successor-capability-ledger.json"
DEFAULT_PROGRESS_REL = (
    TOPIC_REL / "03_functorial-successor-migration-development-progress.md"
)
P1_REL = TOPIC_REL / "evidence/P1FunctorizationEligibility.v1.json"
P2_SELECTION_REL = TOPIC_REL / "evidence/P2C21Selection.v1.json"
CANONICAL_OUTPUT_REL = TOPIC_REL / "evidence/P3CapabilityMigration.v1.json"
FRAGMENT_RELS = {
    family: TOPIC_REL / f"evidence/p3-fragments/{family}.json"
    for family in FAMILY_ORDER
}

AUTHORITY_FALSE_FLAGS = (
    "production_canonical_write",
    "live_provider",
    "external_delivery",
    "cutover",
    "authority_transfer",
    "legacy_retired",
)


class AggregateBuildError(RuntimeError):
    """Fail-closed aggregate construction error."""


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: str
    data: bytes
    sha256: str
    bytes: int
    lines: int

    def file_binding(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "file_sha256": self.sha256,
            "bytes": self.bytes,
            "lines": self.lines,
        }


@dataclass(frozen=True, slots=True)
class AggregateBuild:
    artifact: Mapping[str, Any]
    batch: Mapping[str, Any]
    prerequisites_satisfied: bool
    unsatisfied: tuple[str, ...]
    snapshots: Mapping[str, FileSnapshot]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_slice_digest(value: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(value))


def _promotion_anchor(
    progress_text: str, *, required_tokens: Sequence[str], label: str
) -> dict[str, Any] | None:
    matches = [
        line
        for line in progress_text.splitlines()
        if line.startswith("- ") and all(token in line for token in required_tokens)
    ]
    if len(matches) != 1:
        return None
    text = matches[0]
    return {
        "label": label,
        "required_tokens": list(required_tokens),
        "text": text,
        "text_sha256": _sha256(text.encode("utf-8")),
    }


def _relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise AggregateBuildError(f"path escapes repository root: {path}") from exc


def _snapshot(root: Path, path: Path) -> FileSnapshot:
    resolved = path if path.is_absolute() else root / path
    if not resolved.is_file():
        raise AggregateBuildError(f"required input missing: {resolved}")
    data = resolved.read_bytes()
    return FileSnapshot(
        path=_relpath(root, resolved),
        data=data,
        sha256=_sha256(data),
        bytes=len(data),
        lines=data.count(b"\n"),
    )


def _json(
    snapshot: FileSnapshot, *, require_content_digest: bool = True
) -> Mapping[str, Any]:
    try:
        value = json.loads(snapshot.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AggregateBuildError(f"invalid JSON input {snapshot.path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise AggregateBuildError(f"JSON input must be an object: {snapshot.path}")
    expected = value.get("content_digest")
    actual = canonical_content_digest(value)
    if require_content_digest and expected != actual:
        raise AggregateBuildError(
            f"content digest mismatch for {snapshot.path}: {expected!r} != {actual}"
        )
    return value


def _content_binding(
    snapshot: FileSnapshot, value: Mapping[str, Any]
) -> dict[str, Any]:
    binding = snapshot.file_binding()
    binding["content_digest"] = value["content_digest"]
    return binding


def _resolve_ledger_path(root: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AggregateBuildError(f"ledger does not name {label}")
    path = Path(value)
    return path if path.is_absolute() else root / path


def _select_p2_packet(root: Path, p2_state: Mapping[str, Any]) -> Path:
    # An additive packet is the current predecessor once it exists, even while
    # its external review remains pending.  Historical v4 must not be silently
    # selected merely because the mutable ledger has not yet promoted v5.
    for key in ("pending_additive_packet", "current_capability_packet"):
        raw = p2_state.get(key)
        if (
            isinstance(raw, str)
            and raw
            and _resolve_ledger_path(root, raw, label=key).is_file()
        ):
            return _resolve_ledger_path(root, raw, label=key)
    raise AggregateBuildError("no readable current or pending P2 capability packet")


def _binding_entries(fragment: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for key in ("source_bindings", "implementation_bindings", "test_bindings", "files"):
        entries = fragment.get(key)
        if isinstance(entries, list):
            result.extend(item for item in entries if isinstance(item, Mapping))
    return result


def _fragment_cells(fragment: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cells = fragment.get("cells")
    if not isinstance(cells, list) or any(
        not isinstance(item, Mapping) for item in cells
    ):
        raise AggregateBuildError(
            f"{fragment.get('family')} cells must be normalized objects"
        )
    return list(cells)


def _assert_authority_and_effect_ceiling(fragment: Mapping[str, Any]) -> None:
    family = fragment.get("family")
    authority = fragment.get("authority")
    if not isinstance(authority, Mapping):
        raise AggregateBuildError(f"{family} fragment has no authority object")
    true_flags = sorted(key for key, value in authority.items() if value is True)
    if true_flags:
        raise AggregateBuildError(f"{family} authority ceiling violation: {true_flags}")
    for cell in _fragment_cells(fragment):
        cell_id = cell.get("cell_id")
        if cell.get("provider_calls") != 0:
            raise AggregateBuildError(f"{cell_id} provider_calls must be zero")
        successor = cell.get("successor_observation")
        if isinstance(successor, Mapping) and successor.get("provider_calls", 0) != 0:
            raise AggregateBuildError(
                f"{cell_id} successor provider_calls must be zero"
            )
        rollback = cell.get("rollback_observation")
        if not isinstance(rollback, Mapping) or rollback.get("claim_owner") != "legacy":
            raise AggregateBuildError(
                f"{cell_id} rollback claim owner must remain legacy"
            )


def _operation_identities(
    cells: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    digests: dict[str, set[Any]] = defaultdict(set)
    for cell in cells:
        cell_id = str(cell["cell_id"])
        operations = cell.get("operation_bindings")
        if not isinstance(operations, list):
            raise AggregateBuildError(f"{cell_id} operation_bindings must be a list")
        for position, operation in enumerate(operations):
            if not isinstance(operation, Mapping):
                raise AggregateBuildError(
                    f"{cell_id} operation binding {position} is not an object"
                )
            kind = operation.get("operation_kind")
            if not isinstance(kind, str) or not kind:
                raise AggregateBuildError(
                    f"{cell_id} operation binding {position} has no kind"
                )
            digest = operation.get("contract_digest")
            digests[kind].add(digest)
            refs[kind].append(
                {
                    "cell_id": cell_id,
                    "position": position,
                    "role": operation.get("role"),
                    "contract_digest": digest,
                }
            )
    conflicts = [
        {
            "operation_kind": kind,
            "contract_digests": sorted(
                values, key=lambda value: "" if value is None else str(value)
            ),
            "references": refs[kind],
        }
        for kind, values in sorted(digests.items())
        if len(values) != 1
    ]
    shared = [
        {
            "operation_kind": kind,
            "contract_digest": next(iter(digests[kind])),
            "references": refs[kind],
        }
        for kind in sorted(refs)
        if len(refs[kind]) > 1 and len(digests[kind]) == 1
    ]
    return shared, conflicts


def _family_manifest_digest(fragment: Mapping[str, Any]) -> str:
    payload = [
        {
            "path": item.get("path"),
            "sha256": item.get("sha256"),
            "bytes": item.get("bytes"),
            "lines": item.get("lines"),
        }
        for item in _binding_entries(fragment)
    ]
    return _sha256(canonical_json_bytes(payload))


def _finding_scopes(finding_id: str) -> list[str]:
    upper = finding_id.upper()
    scopes: list[str] = []
    if "LIVE" in upper or "PROVIDER" in upper or "CREDENTIAL" in upper:
        scopes.append("LIVE_PROVIDER")
    if "PRODUCTION" in upper or "CONTROL_NOT_MIGRATED" in upper:
        scopes.append("PRODUCTION_CANONICAL_WRITE")
    if "REVIEW_SURFACE" in upper or "GIT_IDENTIFIED" in upper:
        scopes.append("P5_EXACT_CANDIDATE")
    if "NAMESPACE_COLLISION" in upper:
        scopes.append("MAINTENANCE")
    if not scopes:
        scopes.append("P5_EXACT_CANDIDATE")
    return scopes


def _external_family_review(
    family: str,
    fragment_snapshot: FileSnapshot,
    fragment: Mapping[str, Any],
    disposition: Any,
    ledger_snapshot: FileSnapshot,
    progress_snapshot: FileSnapshot,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(disposition, Mapping):
        return None, f"MISSING_EXACT_FAMILY_REVIEW:{family}"
    state = disposition.get("state")
    decision = disposition.get("review_disposition")
    task_ref = disposition.get("independent_review")
    digest_exact = disposition.get("fragment_content_digest") == fragment.get(
        "content_digest"
    )
    file_exact = disposition.get("fragment_file_sha256") in (
        None,
        fragment_snapshot.sha256,
    )
    blockers_p0 = disposition.get("open_blocking_p0")
    blockers_p1 = disposition.get("open_blocking_p1")
    anchor = _promotion_anchor(
        progress_snapshot.data.decode("utf-8", errors="replace"),
        required_tokens=(
            f"P3 {family}",
            str(task_ref),
            str(fragment.get("content_digest")),
        ),
        label=f"P3_{family}_EXACT_PROMOTION",
    )
    allowed = (
        isinstance(state, str)
        and "PROMOTED_LOCAL_ONLY" in state
        and isinstance(decision, str)
        and "ALLOW" in decision
        and digest_exact
        and file_exact
        and blockers_p0 == []
        and blockers_p1 == []
        and anchor is not None
    )
    if not allowed:
        return None, f"MISSING_OR_STALE_EXACT_FAMILY_REVIEW:{family}"
    return (
        {
            "family": family,
            "fragment_file_sha256": fragment_snapshot.sha256,
            "fragment_content_digest": fragment["content_digest"],
            "record_source": {
                "kind": "mutable_external_disposition",
                "path": ledger_snapshot.path,
                "json_pointer": f"/phases/P3/family_dispositions/{family}",
                "canonical_slice_digest": _canonical_slice_digest(disposition),
            },
            "progress_exact_binding": {
                "path": progress_snapshot.path,
                "anchor": anchor,
            },
            "task_ref": task_ref,
            "disposition": decision,
            "open_blocking_p0": [],
            "open_blocking_p1": [],
            "authority_ceiling": disposition.get(
                "authority_ceiling", "LOCAL_ONLY_NOT_LIVE"
            ),
            "family_manifest_digest": _family_manifest_digest(fragment),
            "validation_evidence": disposition.get("observed_validation", {}),
        },
        None,
    )


def _p2_external_disposition(
    packet_snapshot: FileSnapshot,
    packet: Mapping[str, Any],
    p2_state: Mapping[str, Any],
    ledger_snapshot: FileSnapshot,
    progress_snapshot: FileSnapshot,
) -> tuple[dict[str, Any], bool]:
    packet_path = packet_snapshot.path
    is_pending = p2_state.get("pending_additive_packet") == packet_path
    if is_pending:
        digest = p2_state.get("pending_packet_content_digest")
        file_sha = p2_state.get("pending_packet_file_sha256")
        review = p2_state.get("pending_packet_review")
        state = p2_state.get("pending_packet_binding_state")
    else:
        digest = p2_state.get("current_packet_content_digest")
        file_sha = p2_state.get("current_packet_file_sha256")
        review = p2_state.get("current_packet_review")
        state = p2_state.get("current_packet_binding_state")
    anchor = _promotion_anchor(
        progress_snapshot.data.decode("utf-8", errors="replace"),
        required_tokens=(
            "P2 v5 exact closure",
            str(p2_state.get("independent_review")),
            str(packet.get("content_digest")),
        ),
        label="P2_CURRENT_PACKET_EXACT_PROMOTION",
    )
    exact = (
        digest == packet.get("content_digest")
        and file_sha == packet_snapshot.sha256
        and isinstance(review, str)
        and "ALLOW" in review
        and isinstance(state, str)
        and state.startswith("BOUND")
        and anchor is not None
    )
    return (
        {
            "record_kind": "mutable_external_disposition",
            "ledger_path": ledger_snapshot.path,
            "json_pointer": "/phases/P2",
            "canonical_slice_digest": _canonical_slice_digest(p2_state),
            "task_ref": p2_state.get("independent_review"),
            "disposition": review,
            "binding_state": state,
            "open_blocking_p0": p2_state.get("open_p0", []),
            "exact_for_selected_packet": exact,
            "progress_exact_binding": {
                "path": progress_snapshot.path,
                "anchor": anchor,
            },
        },
        exact,
    )


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=not binary,
    )
    return result.stdout


def _filter_git_status(data: bytes, excluded_paths: set[str]) -> bytes:
    """Remove explicitly self-referential evidence paths from -z status."""

    records = data.split(b"\0")
    filtered: list[bytes] = []
    for record in records:
        if not record:
            continue
        try:
            path = record[3:].decode("utf-8", errors="surrogateescape")
        except IndexError:
            filtered.append(record)
            continue
        if path in excluded_paths:
            continue
        filtered.append(record)
    return b"\0".join(filtered) + (b"\0" if filtered else b"")


def _path_manifest(
    snapshots: Mapping[str, FileSnapshot],
    *,
    excluded_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    excluded = excluded_paths or set()
    rows = [
        {
            "path": item.path,
            "sha256": item.sha256,
            "bytes": item.bytes,
            "lines": item.lines,
        }
        for item in sorted(snapshots.values(), key=lambda item: item.path)
        if item.path not in excluded
    ]
    return rows, _sha256(canonical_json_bytes(rows))


def _identity_digest(artifact: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in artifact.items()
        if key not in {"aggregate_id", "content_digest"}
    }
    return _sha256(canonical_json_bytes(body))


def build_p3_aggregate(
    repo_root: str | Path,
    *,
    ledger: str | Path = DEFAULT_LEDGER_REL,
    progress: str | Path = DEFAULT_PROGRESS_REL,
) -> AggregateBuild:
    root = Path(repo_root).resolve()
    if not (root / ".git").exists() and not (root / ".git").is_file():
        raise AggregateBuildError(f"repository root has no .git: {root}")

    snapshots: dict[str, FileSnapshot] = {}

    def take(path: str | Path) -> FileSnapshot:
        item = _snapshot(root, Path(path))
        snapshots[item.path] = item
        return item

    ledger_snapshot = take(ledger)
    progress_snapshot = take(progress)
    ledger_doc = _json(ledger_snapshot, require_content_digest=False)
    p2_state = ledger_doc.get("phases", {}).get("P2", {})
    p3_state = ledger_doc.get("phases", {}).get("P3", {})
    if not isinstance(p2_state, Mapping) or not isinstance(p3_state, Mapping):
        raise AggregateBuildError("ledger is missing phases/P2 or phases/P3")

    p1_snapshot = take(P1_REL)
    p1 = _json(p1_snapshot)
    selection_snapshot = take(P2_SELECTION_REL)
    selection = _json(selection_snapshot)
    packet_snapshot = take(_select_p2_packet(root, p2_state))
    packet = _json(packet_snapshot)

    fragment_snapshots: dict[str, FileSnapshot] = {}
    fragments: dict[str, Mapping[str, Any]] = {}
    batch_entries: list[dict[str, Any]] = []
    ordered_cells: list[Mapping[str, Any]] = []
    fragment_bindings: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        snapshot = take(FRAGMENT_RELS[family])
        fragment = _json(snapshot)
        if fragment.get("family") != family or fragment.get("phase") != "P3":
            raise AggregateBuildError(f"fragment identity mismatch: {snapshot.path}")
        _assert_authority_and_effect_ceiling(fragment)
        fragment_snapshots[family] = snapshot
        fragments[family] = fragment
        cells = _fragment_cells(fragment)
        ordered_cells.extend(cells)
        batch_entries.append(
            {
                "phase": "P3",
                "family": family,
                **snapshot.file_binding(),
            }
        )
        fragment_bindings.append(
            {
                "family": family,
                **snapshot.file_binding(),
                "content_digest": fragment["content_digest"],
                "status": fragment.get("status"),
                "family_manifest_digest": _family_manifest_digest(fragment),
            }
        )
        for binding in _binding_entries(fragment):
            raw_path = binding.get("path")
            if isinstance(raw_path, str) and raw_path:
                bound_snapshot = take(raw_path)
                if (
                    binding.get("sha256") != bound_snapshot.sha256
                    or binding.get("bytes") != bound_snapshot.bytes
                    or binding.get("lines") != bound_snapshot.lines
                ):
                    raise AggregateBuildError(
                        f"fragment source binding drift: {raw_path}"
                    )

    actual_cells = tuple(str(cell.get("cell_id")) for cell in ordered_cells)
    if actual_cells != CELL_ORDER:
        raise AggregateBuildError(f"P3 cell order mismatch: {actual_cells!r}")

    generator_rel = Path(__file__).resolve().relative_to(root)
    validator_rel = (
        Path(__file__)
        .with_name("validate_successor_migration_batch.py")
        .resolve()
        .relative_to(root)
    )
    aggregate_test_rel = Path(
        "main/backend/tests/successor_runtime/test_p3_aggregate_evidence.py"
    )
    validator_test_rel = Path(
        "main/backend/tests/successor_runtime/test_successor_migration_batch_validation.py"
    )
    for path in (generator_rel, validator_rel, aggregate_test_rel, validator_test_rel):
        if (root / path).is_file():
            take(path)

    batch = {
        "schema": BATCH_SCHEMA,
        "batch_id": "p3-capability-migration-pre-aggregate-v1",
        "root": ".",
        "phase_union": ["P3"],
        "fragments": batch_entries,
        "aggregates": [],
        "p1_artifact": {
            "path": p1_snapshot.path,
            "file_sha256": p1_snapshot.sha256,
            "content_digest": p1["content_digest"],
        },
        "p2_artifact": {
            "path": packet_snapshot.path,
            "file_sha256": packet_snapshot.sha256,
            "content_digest": packet["content_digest"],
        },
    }
    batch_report = validate_batch(batch, root)
    if not batch_report.is_valid():
        raise AggregateBuildError(
            "migration batch invalid: "
            + json.dumps(
                [issue.as_dict() for issue in batch_report.issues], sort_keys=True
            )
        )

    shared_contracts, conflicts = _operation_identities(ordered_cells)
    if conflicts:
        raise AggregateBuildError(
            "CONFLICTING_CONTRACT_IDENTITY: " + json.dumps(conflicts, sort_keys=True)
        )

    p2_external, p2_exact = _p2_external_disposition(
        packet_snapshot,
        packet,
        p2_state,
        ledger_snapshot,
        progress_snapshot,
    )
    unsatisfied: list[str] = []
    satisfied = [
        "P3_FRAGMENT_BATCH_VALID",
        "AUTHORITY_CEILING_FALSE",
        "LEGACY_CLAIM_OWNER_RETAINED",
        "OPERATION_IDENTITIES_UNIQUE",
    ]
    if p2_exact:
        satisfied.append("P2_CURRENT_PACKET_EXTERNAL_REVIEW_EXACT")
    else:
        unsatisfied.append("P2_CURRENT_PACKET_EXTERNAL_REVIEW_MISSING_OR_STALE")

    dispositions = p3_state.get("family_dispositions", {})
    if not isinstance(dispositions, Mapping):
        dispositions = {}
    external_reviews: list[dict[str, Any]] = []
    reviewed_families: set[str] = set()
    for family in FAMILY_ORDER:
        review, missing = _external_family_review(
            family,
            fragment_snapshots[family],
            fragments[family],
            dispositions.get(family),
            ledger_snapshot,
            progress_snapshot,
        )
        if review is not None:
            external_reviews.append(review)
            reviewed_families.add(family)
            satisfied.append(f"EXACT_FAMILY_REVIEW:{family}")
        elif missing:
            unsatisfied.append(missing)

    finding_rows: dict[str, dict[str, Any]] = {}
    finding_conflicts: set[str] = set()
    blocking: list[dict[str, Any]] = []
    nonblocking: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        fragment = fragments[family]
        for finding in fragment.get("open_findings", []):
            if not isinstance(finding, Mapping) or not isinstance(
                finding.get("id"), str
            ):
                raise AggregateBuildError(f"{family} has malformed open finding")
            finding_id = finding["id"]
            row = finding_rows.get(finding_id)
            severity = finding.get("severity")
            description = finding.get("description")
            if row is not None and row["severity"] != severity:
                finding_conflicts.add(finding_id)
            if row is None:
                disposition = (
                    "OPEN_NONBLOCKING" if family in reviewed_families else "UNREVIEWED"
                )
                row = {
                    "finding_id": finding_id,
                    "severity": severity,
                    "description": description,
                    "description_variants": [],
                    "review_state": disposition,
                    "blocking_scopes": _finding_scopes(finding_id),
                    "reported_by": [],
                }
                finding_rows[finding_id] = row
            if description not in row["description_variants"]:
                row["description_variants"].append(description)
            # Exact external review owns disposition.  Equivalent prose
            # variants are retained for audit but do not conflict when their
            # severity and reviewed disposition agree.
            row["reported_by"].append(family)
        for finding in fragment.get("resolved_findings", []):
            if not isinstance(finding, Mapping) or not isinstance(
                finding.get("evidence_ref"), Mapping
            ):
                raise AggregateBuildError(
                    f"{family} resolved finding lacks evidence binding"
                )
            evidence_ref = finding["evidence_ref"]
            evidence_snapshot = take(str(evidence_ref.get("path", "")))
            if evidence_ref.get("file_sha256") != evidence_snapshot.sha256:
                raise AggregateBuildError(
                    f"resolved finding evidence drift: {finding.get('id')}"
                )
            resolved.append({**finding, "reported_by": [family]})

    for row in sorted(finding_rows.values(), key=lambda item: item["finding_id"]):
        if (
            row["review_state"] == "OPEN_BLOCKING"
            and "P3_LOCAL_ONLY_PROMOTION" in row["blocking_scopes"]
        ):
            blocking.append(row)
        else:
            nonblocking.append(row)

    if blocking:
        unsatisfied.append("OPEN_BLOCKING_FINDINGS_FOR_P3_LOCAL_ONLY")
    unsatisfied.extend(
        f"FINDING_DISPOSITION_CONFLICT:{finding_id}"
        for finding_id in sorted(finding_conflicts)
    )
    all_ready = not unsatisfied
    status = (
        "REVIEW_COMPLETE_DECISION_PENDING_NOT_PROMOTED"
        if all_ready
        else "PREREQUISITES_UNSATISFIED_NOT_PROMOTED"
    )

    mutable_current_state_paths = {ledger_snapshot.path, progress_snapshot.path}
    bound_paths, manifest_digest = _path_manifest(
        snapshots, excluded_paths=mutable_current_state_paths
    )
    git_status_raw = _git(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True
    )
    assert isinstance(git_status_raw, bytes)
    git_status_exclusions = {
        CANONICAL_OUTPUT_REL.as_posix(),
        *mutable_current_state_paths,
    }
    git_status = _filter_git_status(git_status_raw, git_status_exclusions)
    branch = str(_git(root, "branch", "--show-current")).strip()
    head = str(_git(root, "rev-parse", "HEAD")).strip()
    head_tree = str(_git(root, "rev-parse", "HEAD^{tree}")).strip()

    cell_bindings = []
    semantic_owners = []
    for cell in ordered_cells:
        cell_id = str(cell["cell_id"])
        cell_bindings.append(
            {
                "cell_id": cell_id,
                "family": cell_id.split(".", 1)[0],
                "owner_capability_id": cell.get("owner_capability_id"),
                "p1_cell_digest": cell.get("p1_cell_digest"),
                "program_digest": cell.get("program_digest"),
                "plan_digest": cell.get("plan_digest"),
                # Preserve the fragment's declared order.  These operations are
                # not sorted and no commutativity claim is made.
                "operation_bindings": cell.get("operation_bindings"),
                "legacy_observation_digest": _sha256(
                    canonical_json_bytes(cell.get("legacy_observation"))
                ),
                "successor_observation_digest": _sha256(
                    canonical_json_bytes(cell.get("successor_observation"))
                ),
                "rollback_observation_digest": _sha256(
                    canonical_json_bytes(cell.get("rollback_observation"))
                ),
                "provider_calls": cell.get("provider_calls"),
            }
        )
        semantic_owners.append(
            {"cell_id": cell_id, "owner_capability_id": cell.get("owner_capability_id")}
        )

    artifact: dict[str, Any] = {
        "schema": AGGREGATE_SCHEMA,
        "status": status,
        "phase": "P3",
        "families": list(FAMILY_ORDER),
        "cell_ids": list(CELL_ORDER),
        "predecessor_bindings": {
            "p1_artifact": _content_binding(p1_snapshot, p1),
            "p2_selection": _content_binding(selection_snapshot, selection),
            "p2_current_packet": {
                **_content_binding(packet_snapshot, packet),
                "packet_self_review": packet.get("independent_review"),
            },
            "p2_external_disposition": p2_external,
        },
        "ordered_composition": {
            "family_order": list(FAMILY_ORDER),
            "cell_order": list(CELL_ORDER),
            "order_meaning": "canonical serialization and serial adoption order",
            "cross_family_execution_order_claim": False,
            "commutativity_claim": False,
        },
        "fragment_bindings": fragment_bindings,
        "cell_bindings": cell_bindings,
        "external_family_reviews": external_reviews,
        "canonical_ownership": {
            "live_claim_owner": "legacy",
            "business_authority_migrated": False,
            "cell_semantic_owners": semantic_owners,
            "shared_contract_identities": shared_contracts,
            "conflicting_contract_identities": [],
        },
        "validation": {
            "batch_validator_binding": snapshots[str(validator_rel)].file_binding(),
            "aggregate_generator_binding": snapshots[str(generator_rel)].file_binding(),
            "batch_report": batch_report.as_dict(),
        },
        "findings": {
            "open_blocking_for_p3_local_only": blocking,
            "open_nonblocking_for_p3_local_only": nonblocking,
            "resolved": sorted(resolved, key=lambda item: str(item.get("id"))),
            "superseded_or_historical": historical,
        },
        "worktree_identity": {
            "branch": branch,
            "head": head,
            "head_tree": head_tree,
            "candidate_commit": None,
            "candidate_tree": None,
            "review_surface_kind": "WORKING_TREE_EXACT_BOUND_PATHS",
            "git_status_porcelain_v1_z_sha256": _sha256(git_status),
            "git_status_exclusions": sorted(git_status_exclusions),
            "bound_path_manifest_digest": manifest_digest,
            "bound_paths": bound_paths,
        },
        "authority_ceiling": {
            "scope": "LOCAL_ONLY",
            "provider_calls": 0,
            "network": False,
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "promotion_prerequisites": {
            "decision_owner": "root_supervisor",
            "promotion_claim": False,
            "satisfied": sorted(satisfied),
            "unsatisfied": sorted(set(unsatisfied)),
        },
    }
    artifact["aggregate_id"] = f"p3:sha256:{_identity_digest(artifact)}"
    artifact["content_digest"] = canonical_content_digest(artifact)
    aggregate_issues = validate_p3_aggregate_document(artifact)
    if aggregate_issues:
        raise AggregateBuildError(
            "aggregate document invalid: "
            + json.dumps(
                [issue.as_dict() for issue in aggregate_issues], sort_keys=True
            )
        )
    return AggregateBuild(
        artifact=artifact,
        batch=batch,
        prerequisites_satisfied=all_ready,
        unsatisfied=tuple(sorted(set(unsatisfied))),
        snapshots=snapshots,
    )


def _assert_inputs_unchanged(root: Path, snapshots: Mapping[str, FileSnapshot]) -> None:
    changed = []
    for relpath, before in sorted(snapshots.items()):
        path = root / relpath
        try:
            after = path.read_bytes()
        except OSError:
            changed.append(relpath)
            continue
        if (
            _sha256(after) != before.sha256
            or len(after) != before.bytes
            or after.count(b"\n") != before.lines
        ):
            changed.append(relpath)
    if changed:
        raise AggregateBuildError(f"INPUT_CHANGED_DURING_GENERATION:{changed}")


def _serialized_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialized_json(value)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _resolve_cli_output(root: Path, raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER_REL))
    parser.add_argument("--progress", default=str(DEFAULT_PROGRESS_REL))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--emit-batch")
    parser.add_argument("--allow-canonical-write", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        build = build_p3_aggregate(root, ledger=args.ledger, progress=args.progress)
        _assert_inputs_unchanged(root, build.snapshots)
        output = _resolve_cli_output(root, args.output)
        batch_output = _resolve_cli_output(root, args.emit_batch)
        canonical = (root / CANONICAL_OUTPUT_REL).resolve()
        staging_roots = {
            Path(tempfile.gettempdir()).resolve(),
            Path("/tmp").resolve(),
            Path("/private/tmp").resolve(),
        }
        for target in (output, batch_output):
            if (
                target is not None
                and not build.prerequisites_satisfied
                and not any(_is_under(target, parent) for parent in staging_roots)
            ):
                raise AggregateBuildError(
                    f"incomplete aggregate may only be staged below {tempfile.gettempdir()}: {target}"
                )
        if output == canonical and not args.allow_canonical_write:
            raise AggregateBuildError(
                "canonical write requires --allow-canonical-write"
            )
        if output == canonical and not build.prerequisites_satisfied:
            raise AggregateBuildError(
                "canonical write refused: promotion prerequisites unsatisfied"
            )
        if output is not None:
            _write_json_atomic(output, build.artifact)
        batch_value = dict(build.batch)
        if output is not None:
            output_data = _serialized_json(build.artifact)
            try:
                output_path = output.relative_to(root).as_posix()
            except ValueError:
                output_path = str(output)
            batch_value["aggregates"] = [
                {
                    "phase": "P3",
                    "path": output_path,
                    "schema": build.artifact["schema"],
                    "status": build.artifact["status"],
                    "families": build.artifact["families"],
                    "cell_ids": build.artifact["cell_ids"],
                    "file_sha256": _sha256(output_data),
                    "bytes": len(output_data),
                    "lines": output_data.count(b"\n"),
                    "content_digest": build.artifact["content_digest"],
                    "authority_ceiling": build.artifact["authority_ceiling"],
                }
            ]
        if batch_output is not None:
            _write_json_atomic(batch_output, batch_value)
        summary = {
            "schema": "mrw.functorial_successor.p3_aggregate_generation_report.v1",
            "status": "VALID_READY"
            if build.prerequisites_satisfied
            else "VALID_NOT_READY",
            "check_only": output is None and batch_output is None,
            "artifact_content_digest": build.artifact["content_digest"],
            "unsatisfied": list(build.unsatisfied),
            "output": str(output) if output is not None else None,
            "batch_output": str(batch_output) if batch_output is not None else None,
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (AggregateBuildError, OSError, subprocess.CalledProcessError) as exc:
        print(
            json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
