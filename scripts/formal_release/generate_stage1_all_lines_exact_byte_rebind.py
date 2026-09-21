#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Build and validate the additive current-byte AllLines aggregate.

The historical AllLines v1 documents are immutable inputs.  This producer
retains their 237-entry semantic inventory and only rebinds exact working-tree
byte facts.  Dry-run is the default; ``--write`` atomically publishes one
create-only document and never modifies a historical AllLines artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from stage_family_fragment_rebind import (  # noqa: E402
    ValidationError as CandidateValidationError,
    check_candidate,
)


SCHEMA = "mrw.all_lines_exact_byte_aggregate.v1"
STATUS = "LOCAL_DEVELOPMENT_ONLY_NOT_AUTHORITY"
FAMILIES = ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "I1")
CANDIDATE_LIVE_STATUS = "CANDIDATE_VALID_NOT_AUTHORITY"
EXPECTED_ENTRY_COUNT = 237
EVIDENCE_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
ALL_LINES_REL = EVIDENCE_REL / "all-lines-investigation"
DEFAULT_STAGE_ROOT_REL = EVIDENCE_REL / "exact-byte-rebind/stage-b23-2026-09-08"
DEFAULT_OUTPUT_REL = Path(
    "stage1-successor-evidence/stage-convergence-batch-v1/all-lines/"
    "all-lines-exact-byte-aggregate.v1.json"
)

PREDECESSOR_REL = ALL_LINES_REL / "AllLinesDonorByteClosure.v1.json"
PREDECESSOR_SHA256 = "fc1009c172d3880795dbdaebb90d8de41a6359161d5b86a89315ed4abc4077ed"
FREEZE_RECEIPT_REL = ALL_LINES_REL / "AllLinesMigrationScope.freeze-receipt.v1.json"
FREEZE_RECEIPT_SHA256 = "99b9a1c1999925d8b54ce8880468e893bf59237c174ae6c705e00e8e4aa58ef3"
SCOPE_INPUT_HASHES = {
    ALL_LINES_REL / "AllLinesMigrationScope.freeze.v1.json": (
        "d983a922e5c9724922506141c1d25d08a8aec278359bdc4f85ceb6dbf717e756"
    ),
    ALL_LINES_REL / "BackendDonorSurfaceInventory.v1.json": (
        "1328969a9d05a2d583f0ff0862c30de166b932c3ed3df3446ddc9ee5520492bd"
    ),
    ALL_LINES_REL / "LegacyVsMovementGap.v1.json": (
        "401699e5237f776a72dc736c127e5d9d6ad4911d30fb381b583805ddc02c7af7"
    ),
}
MOVEMENT_REL = ALL_LINES_REL / "AllLinesSuccessorMovementInventory.v1.json"
MOVEMENT_SHA256 = "08fad9f59a5c588ca86085410efc792d33114903d4723038f50f46c0f858510d"
KNOWN_SCOPE_EXCLUSIONS = {
    "main/backend/app/services/crawlers/durable_effect_bridge.py": (
        "successor-only implementation created after the frozen donor scope"
    ),
    "main/backend/app/services/graph/ports.py": (
        "successor-only implementation created after the frozen donor scope"
    ),
}
AUTHORITY = {
    "authority_transfer": False,
    "canonical_write": False,
    "cutover": False,
    "external_delivery": False,
    "live_provider": False,
    "production_release": False,
    "promotion": False,
}
LIMITATIONS = (
    "LOCAL_DEVELOPMENT_ONLY",
    "NOT_AUTHORITY",
    "PRODUCTION_RELEASE_NOT_AUTHORIZED",
)


class ValidationError(ValueError):
    """Raised when a fixed input, scope, candidate, or aggregate is invalid."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _content_digest(document: dict[str, Any]) -> str:
    return _sha256(_canonical({key: value for key, value in document.items() if key != "content_digest"}))


def _git_blob_oid(payload: bytes) -> str:
    header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
    return hashlib.sha1(header + payload).hexdigest()  # noqa: S324 - Git object identity is SHA-1.


def _normalized_relative(root: Path, value: Path | str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError as exc:
            raise ValidationError(f"{label} escapes repository root: {value}") from exc
    if ".." in path.parts:
        raise ValidationError(f"{label} escapes repository root: {value}")
    if not path.parts or any(part in {"", "."} for part in path.parts):
        raise ValidationError(f"{label} must be a normalized repository-relative path: {value}")
    candidate = (root / path).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"{label} escapes repository root: {value}") from exc
    return path


def _reject_symlink_components(root: Path, relative: Path, *, label: str) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return
        if stat.S_ISLNK(mode):
            raise ValidationError(f"{label} must not traverse a symlink: {relative.as_posix()}")


def _read_regular(root: Path, relative: Path | str, *, label: str) -> bytes:
    normalized = _normalized_relative(root, relative, label=label)
    _reject_symlink_components(root, normalized, label=label)
    path = root / normalized
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing: {normalized.as_posix()}") from exc
    if not stat.S_ISREG(mode):
        raise ValidationError(f"{label} must be a regular file: {normalized.as_posix()}")
    return path.read_bytes()


def _read_json(root: Path, relative: Path | str, *, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular(root, relative, label=label)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must contain a JSON object")
    return value, payload


def _read_fixed_json(
    root: Path,
    relative: Path,
    expected_sha256: str,
    *,
    label: str,
) -> dict[str, Any]:
    value, payload = _read_json(root, relative, label=label)
    actual = _sha256(payload)
    if actual != expected_sha256:
        raise ValidationError(
            f"{label} immutable SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )
    return value


def _walk_values(value: Any, *, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for item_key, item in value.items():
            if item_key == key:
                found.append(item)
            found.extend(_walk_values(item, key=key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_values(item, key=key))
    return found


def _directory_references(legacy_gap: dict[str, Any], frozen_paths: set[str]) -> tuple[str, ...]:
    donor_paths: set[str] = set()
    for value in _walk_values(legacy_gap, key="donor_paths"):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValidationError("LegacyVsMovementGap donor_paths must be arrays of paths")
        donor_paths.update(value)
    directories = {
        path
        for path in donor_paths
        if path not in frozen_paths and any(item.startswith(f"{path}/") for item in frozen_paths)
    }
    return tuple(sorted(directories))


def _expand_directory(root: Path, relative: str) -> set[str]:
    normalized = _normalized_relative(root, relative, label="scope directory")
    _reject_symlink_components(root, normalized, label="scope directory")
    directory = root / normalized
    if not directory.is_dir():
        raise ValidationError(f"scope directory is missing or not a directory: {relative}")
    discovered: set[str] = set()
    for current, dirs, files in os.walk(directory, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in sorted(dirs):
            child = current_path / name
            if name in {"__pycache__", ".git", "node_modules"}:
                continue
            if child.is_symlink():
                raise ValidationError(
                    f"scope directory must not contain symlink directories: "
                    f"{child.relative_to(root).as_posix()}"
                )
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            child = current_path / name
            child_rel = child.relative_to(root)
            _read_regular(root, child_rel, label="scope-expanded file")
            discovered.add(child_rel.as_posix())
    return discovered


def _fixed_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    predecessor = _read_fixed_json(
        root, PREDECESSOR_REL, PREDECESSOR_SHA256, label="AllLines donor-byte predecessor"
    )
    _read_fixed_json(
        root, FREEZE_RECEIPT_REL, FREEZE_RECEIPT_SHA256, label="AllLines freeze receipt"
    )
    scope_inputs: dict[Path, dict[str, Any]] = {}
    for relative, expected in SCOPE_INPUT_HASHES.items():
        scope_inputs[relative] = _read_fixed_json(
            root, relative, expected, label=f"AllLines scope input {relative.name}"
        )
    _read_fixed_json(root, MOVEMENT_REL, MOVEMENT_SHA256, label="AllLines movement inventory")

    if predecessor.get("schema") != "mrw.functorial_successor.all_lines_donor_byte_closure.v1":
        raise ValidationError("AllLines donor-byte predecessor schema mismatch")
    entries = predecessor.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_ENTRY_COUNT:
        raise ValidationError(
            f"AllLines donor-byte predecessor must contain exactly {EXPECTED_ENTRY_COUNT} entries"
        )
    legacy_gap = scope_inputs[ALL_LINES_REL / "LegacyVsMovementGap.v1.json"]
    return predecessor, legacy_gap


def _stage_relative(root: Path, stage_root: Path | str | None) -> Path:
    value = DEFAULT_STAGE_ROOT_REL if stage_root is None else Path(stage_root)
    relative = _normalized_relative(root, value, label="stage_root")
    if relative != DEFAULT_STAGE_ROOT_REL:
        raise ValidationError(
            f"stage_root must be the fresh canonical root {DEFAULT_STAGE_ROOT_REL.as_posix()}"
        )
    return relative


def _check_stage_candidates(root: Path, stage_relative: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for family in FAMILIES:
        relative = stage_relative / "candidates" / family / "candidate.v2.json"
        try:
            result = check_candidate(relative, repo_root=root, history_only=False)
        except CandidateValidationError as exc:
            raise ValidationError(f"fresh {family} candidate failed live validation: {exc}") from exc
        if result != {
            "candidate_id": result.get("candidate_id"),
            "family": family,
            "status": CANDIDATE_LIVE_STATUS,
        }:
            raise ValidationError(f"fresh candidate family/status mismatch: {family}")
        value, payload = _read_json(root, relative, label=f"fresh {family} candidate")
        refs.append(
            {
                "path": relative.as_posix(),
                "sha256": _sha256(payload),
                "candidate_id": result["candidate_id"],
                "content_digest": value.get("content_digest"),
                "family": family,
            }
        )
    return refs


def _source_entries(
    root: Path,
    predecessor: dict[str, Any],
    legacy_gap: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frozen = predecessor["entries"]
    paths: list[str] = []
    for index, entry in enumerate(frozen):
        if not isinstance(entry, dict):
            raise ValidationError(f"predecessor.entries[{index}] must be an object")
        path = entry.get("path")
        if not isinstance(path, str):
            raise ValidationError(f"predecessor.entries[{index}].path must be a string")
        paths.append(path)
    if len(set(paths)) != EXPECTED_ENTRY_COUNT:
        raise ValidationError("AllLines donor-byte predecessor paths must be unique")
    if paths != sorted(paths):
        raise ValidationError("AllLines donor-byte predecessor paths must use stable path order")

    frozen_paths = set(paths)
    expanded: set[str] = set()
    for directory in _directory_references(legacy_gap, frozen_paths):
        expanded.update(_expand_directory(root, directory))
    extras = expanded - frozen_paths
    if extras != set(KNOWN_SCOPE_EXCLUSIONS):
        unknown = sorted(extras - set(KNOWN_SCOPE_EXCLUSIONS))
        missing = sorted(set(KNOWN_SCOPE_EXCLUSIONS) - extras)
        raise ValidationError(
            f"scope extras mismatch; unknown={unknown!r}; missing_known_exclusions={missing!r}"
        )

    rebound: list[dict[str, Any]] = []
    for index, entry in enumerate(frozen):
        path = paths[index]
        payload = _read_regular(root, path, label=f"frozen donor entry {index}")
        kind = entry.get("kind")
        origins = entry.get("reference_origins")
        tracked = entry.get("tracked_at_donor_head")
        predecessor_sha = entry.get("byte_hash_sha256")
        if not isinstance(kind, str) or not isinstance(origins, list):
            raise ValidationError(f"predecessor.entries[{index}] semantic fields are invalid")
        if not isinstance(tracked, bool) or not isinstance(predecessor_sha, str):
            raise ValidationError(f"predecessor.entries[{index}] byte metadata is invalid")
        rebound.append(
            {
                "path": path,
                "kind": kind,
                "reference_origins": origins,
                "tracked_at_donor_head": tracked,
                "predecessor_sha256": predecessor_sha,
                "current_sha256": _sha256(payload),
                "bytes": len(payload),
                "lines": payload.count(b"\n"),
                "git_blob_oid": _git_blob_oid(payload),
            }
        )

    exclusions: list[dict[str, Any]] = []
    for path, reason in sorted(KNOWN_SCOPE_EXCLUSIONS.items()):
        payload = _read_regular(root, path, label="known scope exclusion")
        exclusions.append({"path": path, "current_sha256": _sha256(payload), "reason": reason})
    return rebound, exclusions


def build_document(
    root: Path,
    *,
    stage_root: Path | str | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=frozen_all_lines_predecessor+current_repo_bytes+stage0_candidate_bindings "
    "witness=test:test_build_document_authority_metadata",
]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValidationError("repository root must be a directory")
    predecessor, legacy_gap = _fixed_inputs(root)
    stage_relative = _stage_relative(root, stage_root)
    candidates = _check_stage_candidates(root, stage_relative)
    entries, exclusions = _source_entries(root, predecessor, legacy_gap)
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "authoritative": False,
        "authority": dict(AUTHORITY),
        "limitations": list(LIMITATIONS),
        "predecessor": {
            "path": PREDECESSOR_REL.as_posix(),
            "sha256": PREDECESSOR_SHA256,
            "mutation": False,
        },
        "freeze_receipt": {
            "path": FREEZE_RECEIPT_REL.as_posix(),
            "sha256": FREEZE_RECEIPT_SHA256,
        },
        "scope_inputs": [
            {"path": path.as_posix(), "sha256": digest}
            for path, digest in SCOPE_INPUT_HASHES.items()
        ],
        "movement_inventory": {
            "path": MOVEMENT_REL.as_posix(),
            "sha256": MOVEMENT_SHA256,
            "semantic_fields_changed": False,
        },
        "stage_root": stage_relative.as_posix(),
        "stage0_candidates": candidates,
        "scope_exclusions": exclusions,
        "entry_count": len(entries),
        "entries": entries,
        "exact_byte_method": {
            "byte_source": "current repository working-tree bytes",
            "hash_algorithm": "sha256",
            "git_blob_oid_algorithm": "git blob object ID of working-tree bytes",
            "git_object_format": "sha1",
            "lines_algorithm": "count of LF bytes",
            "semantic_fields_changed": False,
        },
    }
    document["content_digest"] = _content_digest(document)
    return document


_DOCUMENT_KEYS = {
    "schema",
    "status",
    "authoritative",
    "authority",
    "limitations",
    "predecessor",
    "freeze_receipt",
    "scope_inputs",
    "movement_inventory",
    "stage_root",
    "stage0_candidates",
    "scope_exclusions",
    "entry_count",
    "entries",
    "exact_byte_method",
    "content_digest",
}


def check_document(
    root: Path,
    document_or_path: dict[str, Any] | Path | str,
    *,
    stage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Validate an aggregate against fixed inputs and current working-tree bytes."""

    root = root.expanduser().resolve(strict=True)
    if isinstance(document_or_path, dict):
        actual = document_or_path
    else:
        actual, _ = _read_json(root, document_or_path, label="AllLines aggregate")
    if set(actual) != _DOCUMENT_KEYS:
        raise ValidationError("AllLines aggregate has unexpected or missing top-level fields")
    if actual.get("schema") != SCHEMA or actual.get("status") != STATUS:
        raise ValidationError("AllLines aggregate schema/status mismatch")
    if actual.get("content_digest") != _content_digest(actual):
        raise ValidationError("AllLines aggregate content_digest mismatch")

    expected = build_document(root, stage_root=stage_root)
    if actual != expected:
        raise ValidationError("AllLines aggregate does not match fixed inputs and live working-tree bytes")
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "entry_count": EXPECTED_ENTRY_COUNT,
        "candidate_count": 9,
        "content_digest": actual["content_digest"],
    }


def _ensure_output_parent(root: Path, relative: Path) -> Path:
    current = root
    for part in relative.parent.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise ValidationError(f"output parent must be a real directory: {current}")
        else:
            current.mkdir()
    return current


def write_create_only(root: Path, output: Path | str, document: dict[str, Any]) -> Path:
    root = root.expanduser().resolve(strict=True)
    relative = _normalized_relative(root, output, label="output")
    _reject_symlink_components(root, relative, label="output")
    target = root / relative
    if target.exists() or target.is_symlink():
        raise ValidationError(f"create-only output already exists: {relative.as_posix()}")
    check_document(root, document, stage_root=document["stage_root"])
    parent = _ensure_output_parent(root, relative)
    payload = _canonical(document) + b"\n"
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValidationError(f"create-only output already exists: {relative.as_posix()}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def _parse_root(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"repository root is not a directory: {value}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=_parse_root, default=REPOSITORY_ROOT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT_REL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_REL)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            summary = check_document(args.root, args.output, stage_root=args.stage_root)
            print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
            return 0
        document = build_document(args.root, stage_root=args.stage_root)
        check_document(args.root, document, stage_root=args.stage_root)
        if args.write:
            target = write_create_only(args.root, args.output, document)
            result = {"mode": "write", "output": target.relative_to(args.root).as_posix()}
        else:
            result = {
                "mode": "dry-run",
                "output": _normalized_relative(args.root, args.output, label="output").as_posix(),
                "document": document,
            }
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0  # noqa: TRY300
    except (OSError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
