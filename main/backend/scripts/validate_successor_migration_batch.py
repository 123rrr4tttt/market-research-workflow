#!/usr/bin/env python3
"""Deterministic read-only P3/P4 successor migration batch validator.

This tool validates a successor migration batch manifest that binds P3
(C2-C6) and P4 (C7-C9) evidence fragments, source bindings, source evidence,
the P1/P2 chain, authority ceilings, and mainline-serialized aggregate
evidence.  It never writes fragment or aggregate evidence; the only optional
write is the canonical validation report requested through ``--report``.

Batch schema: ``mrw.functorial_successor.migration_batch_validation.v1``

Required batch fields:

- ``schema``: exact batch schema id above
- ``batch_id``: non-empty string
- ``root``: workspace root used to resolve every relative path
- ``phase_union``: sorted list of phases, each of which must have complete
  fragment family coverage (P3: C2-C6, P4: C7-C9)
- ``fragments``: list of fragment entries (see below)
- ``p1_artifact`` / ``p2_artifact``: chain bindings with path/file_sha256/
  content_digest

Fragment entry fields: ``phase``, ``family``, ``path``, ``file_sha256``,
``bytes``, ``lines``.  Optional: ``schema``, ``status``, ``line_semantics``,
``aggregate_ref``, ``p1_p2_chain``.

Aggregate entry fields: ``phase``, ``path``, ``schema``, ``status``,
``families``, ``cell_ids``.  Optional: ``file_sha256``, ``bytes``, ``lines``,
``line_semantics``, ``content_digest``, ``authority_ceiling``.

Line counts default to the raw newline count of the file bytes.  An object
may opt into splitlines semantics through ``line_semantics: "splitlines"``
(entry level, then file level, then batch default), or when its declared
schema id contains ``splitlines``.  Source evidence line ranges use the same
semantics as the fragment that carries them.

CLI exit codes: 0 = valid, 1 = validation issues, 2 = usage/IO/fatal error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BATCH_SCHEMA = "mrw.functorial_successor.migration_batch_validation.v1"
REPORT_SCHEMA = "mrw.functorial_successor.migration_batch_validation_report.v1"
P3_AGGREGATE_SCHEMA = "mrw.functorial_successor.p3_capability_migration.v1"
P3_FAMILY_ORDER = ("C2", "C3", "C4", "C5", "C6")
P3_CELL_ORDER = (
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

ALLOWED_PHASES = ("P3", "P4")
PHASE_REQUIRED_FAMILIES = {
    "P3": ("C2", "C3", "C4", "C5", "C6"),
    "P4": ("C7", "C8", "C9"),
}
PHASE_ALLOWED_FAMILIES = {
    phase: frozenset(families) for phase, families in PHASE_REQUIRED_FAMILIES.items()
}

DEFAULT_LINE_SEMANTICS = "raw_newline"
ALLOWED_LINE_SEMANTICS = ("raw_newline", "splitlines")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

BATCH_REQUIRED_FIELDS = (
    "schema",
    "batch_id",
    "root",
    "phase_union",
    "fragments",
    "p1_artifact",
    "p2_artifact",
)
BATCH_ALLOWED_FIELDS = BATCH_REQUIRED_FIELDS + (
    "aggregates",
    "line_semantics",
    "generated_at_utc",
)

FRAGMENT_REQUIRED_FIELDS = ("phase", "family", "path", "file_sha256", "bytes", "lines")
FRAGMENT_ALLOWED_FIELDS = FRAGMENT_REQUIRED_FIELDS + (
    "schema",
    "status",
    "line_semantics",
    "aggregate_ref",
    "p1_p2_chain",
)

AGGREGATE_REQUIRED_FIELDS = (
    "phase",
    "path",
    "schema",
    "status",
    "families",
    "cell_ids",
)
AGGREGATE_ALLOWED_FIELDS = AGGREGATE_REQUIRED_FIELDS + (
    "file_sha256",
    "bytes",
    "lines",
    "line_semantics",
    "content_digest",
    "authority_ceiling",
)

CHAIN_REQUIRED_FIELDS = ("path", "file_sha256", "content_digest")
CHAIN_ALLOWED_FIELDS = CHAIN_REQUIRED_FIELDS

BINDING_REQUIRED_FIELDS = ("path", "sha256", "bytes", "lines")
BINDING_ALLOWED_FIELDS = BINDING_REQUIRED_FIELDS + (
    "symbols",
    "observed_symbols",
    "line_semantics",
    "role",
    "read_only",
)

EVIDENCE_REQUIRED_FIELDS = ("path", "symbol_or_lines", "claim")
EVIDENCE_ALLOWED_FIELDS = EVIDENCE_REQUIRED_FIELDS + ("symbols", "line_semantics")

FRAGMENT_FILE_REQUIRED_FIELDS = ("schema", "content_digest", "cells", "status")
AGGREGATE_FILE_REQUIRED_FIELDS = (
    "schema",
    "content_digest",
    "status",
    "families",
    "cell_ids",
)

AUTHORITY_CEILING_REQUIRED_FLAGS = (
    "production_canonical_write",
    "live_provider",
    "external_delivery",
    "cutover",
    "authority_transfer",
    "legacy_retired",
)
AUTHORITY_KEYS = (
    "authority_ceiling",
    "authority_boundary",
    "authority",
)

FIXED_ISSUE_CODES = tuple(
    sorted(
        {
            "AGGREGATE_CELLS_MISMATCH",
            "AGGREGATE_CLAIM_EXCEEDS_FRAGMENTS",
            "AGGREGATE_CONTENT_DIGEST_MISMATCH",
            "AGGREGATE_ENTRY_STATUS_MISMATCH",
            "AGGREGATE_FAMILIES_MISMATCH",
            "AGGREGATE_FILE_BYTES_MISMATCH",
            "AGGREGATE_FILE_HASH_MISMATCH",
            "AGGREGATE_FILE_LINES_MISMATCH",
            "AGGREGATE_INVALID_JSON",
            "AGGREGATE_PATH_MISSING",
            "AGGREGATE_SCHEMA_MISMATCH",
            "AUTHORITY_CEILING_VIOLATION",
            "BATCH_NOT_OBJECT",
            "BATCH_SCHEMA_INVALID",
            "CELL_ID_INVALID",
            "CHAIN_CONTENT_DIGEST_MISMATCH",
            "CHAIN_FILE_HASH_MISMATCH",
            "CHAIN_PATH_MISSING",
            "CONTENT_DIGEST_MISMATCH",
            "DUPLICATE_CELL_ID",
            "FRAGMENT_AGGREGATE_REF_MISSING",
            "FRAGMENT_CONTENT_DIGEST_MISMATCH",
            "FRAGMENT_ENTRY_STATUS_MISMATCH",
            "FRAGMENT_FAMILY_MISMATCH",
            "FRAGMENT_FILE_BYTES_MISMATCH",
            "FRAGMENT_FILE_HASH_MISMATCH",
            "FRAGMENT_FILE_LINES_MISMATCH",
            "FRAGMENT_INVALID_JSON",
            "FRAGMENT_PATH_MISSING",
            "FRAGMENT_PHASE_MISMATCH",
            "FRAGMENT_SCHEMA_MISMATCH",
            "FRAGMENT_UNEXPECTED_FIELD",
            "LINE_SEMANTICS_INVALID",
            "P1_ARTIFACT_CONTENT_DIGEST_MISMATCH",
            "P1_ARTIFACT_FILE_HASH_MISMATCH",
            "P1_ARTIFACT_PATH_MISSING",
            "P1_P2_CHAIN_MISMATCH",
            "P2_ARTIFACT_CONTENT_DIGEST_MISMATCH",
            "P2_ARTIFACT_FILE_HASH_MISMATCH",
            "P2_ARTIFACT_PATH_MISSING",
            "P3_AGGREGATE_AUTHORITY_VIOLATION",
            "P3_AGGREGATE_CANDIDATE_IDENTITY_PRESENT",
            "P3_AGGREGATE_CELL_ORDER_MISMATCH",
            "P3_AGGREGATE_FAMILY_ORDER_MISMATCH",
            "P3_AGGREGATE_LEGACY_OWNER_VIOLATION",
            "P3_AGGREGATE_OPERATION_IDENTITY_CONFLICT",
            "P3_AGGREGATE_PROMOTION_CLAIM_FORBIDDEN",
            "P3_AGGREGATE_PROVIDER_CALLS_NONZERO",
            "P3_AGGREGATE_REVIEW_BINDING_INVALID",
            "P3_AGGREGATE_SCHEMA_INVALID",
            "PHASE_FAMILY_MISSING",
            "PHASE_FAMILY_UNEXPECTED",
            "PHASE_INVALID",
            "PHASE_UNION_MISMATCH",
            "REQUIRED_FIELD_MISSING",
            "ROOT_MISSING",
            "ROOT_NOT_DIRECTORY",
            "SOURCE_BINDING_BYTES_MISMATCH",
            "SOURCE_BINDING_LINES_MISMATCH",
            "SOURCE_BINDING_PATH_MISSING",
            "SOURCE_BINDING_SHA256_MISMATCH",
            "SOURCE_BINDING_UNEXPECTED_FIELD",
            "SOURCE_EVIDENCE_LINE_OUT_OF_RANGE",
            "SOURCE_EVIDENCE_PATH_MISSING",
            "SOURCE_EVIDENCE_SYMBOL_MISSING",
            "SOURCE_EVIDENCE_UNEXPECTED_FIELD",
            "SOURCE_EVIDENCE_UNPARSEABLE",
            "UNEXPECTED_FIELD",
            "VALIDATION_FATAL",
        }
    )
)

_RANGE_RE = re.compile(
    r"lines?\s+(\d+)(?:\s*[-:]\s*(\d+))?",
    re.IGNORECASE,
)
_SYMBOL_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_SPLITLINES_SCHEMA_MARKER = "splitlines"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: str
    exit_code: int
    batch_id: str
    batch_schema: str
    root: str
    phase_union: tuple[str, ...]
    counts: Mapping[str, int]
    families_by_phase: Mapping[str, tuple[str, ...]]
    aggregate_phases: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    def is_valid(self) -> bool:
        return self.status == "VALID" and not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "status": self.status,
            "valid": self.is_valid(),
            "exit_code": self.exit_code,
            "batch_id": self.batch_id,
            "batch_schema": self.batch_schema,
            "root": self.root,
            "phase_union": list(self.phase_union),
            "counts": dict(self.counts),
            "families_by_phase": {
                phase: list(families)
                for phase, families in sorted(self.families_by_phase.items())
            },
            "aggregate_phases": list(self.aggregate_phases),
            "issues": [issue.as_dict() for issue in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_content_digest(value: Mapping[str, Any]) -> str:
    without_digest = {
        key: item for key, item in value.items() if key != "content_digest"
    }
    return hashlib.sha256(canonical_json_bytes(without_digest)).hexdigest()


def validate_p3_aggregate_document(
    aggregate: Mapping[str, Any],
) -> tuple[ValidationIssue, ...]:
    """Validate P3 aggregate invariants without reading mutable external state.

    Exact external file bindings are checked by the generator's double-read
    closure.  This function validates the self-contained semantic envelope and
    is also used when a P3 aggregate appears in a migration batch.
    """

    issues: list[ValidationIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    if aggregate.get("schema") != P3_AGGREGATE_SCHEMA:
        add(
            "P3_AGGREGATE_SCHEMA_INVALID",
            "$",
            f"expected schema {P3_AGGREGATE_SCHEMA!r}",
        )
    ordered = aggregate.get("ordered_composition")
    if not isinstance(ordered, Mapping):
        add(
            "REQUIRED_FIELD_MISSING",
            "$.ordered_composition",
            "missing ordered composition",
        )
    else:
        if ordered.get("family_order") != list(P3_FAMILY_ORDER):
            add(
                "P3_AGGREGATE_FAMILY_ORDER_MISMATCH",
                "$.ordered_composition.family_order",
                "P3 family order must be C2 through C6",
            )
        if ordered.get("cell_order") != list(P3_CELL_ORDER):
            add(
                "P3_AGGREGATE_CELL_ORDER_MISMATCH",
                "$.ordered_composition.cell_order",
                "P3 cell order does not match the frozen 15-cell order",
            )
        if ordered.get("commutativity_claim") is not False:
            add(
                "P3_AGGREGATE_AUTHORITY_VIOLATION",
                "$.ordered_composition.commutativity_claim",
                "ordered composition must not claim commutativity",
            )

    fragments = aggregate.get("fragment_bindings")
    if not isinstance(fragments, list) or [
        item.get("family") for item in fragments if isinstance(item, Mapping)
    ] != list(P3_FAMILY_ORDER):
        add(
            "P3_AGGREGATE_FAMILY_ORDER_MISMATCH",
            "$.fragment_bindings",
            "fragment bindings must preserve fixed family order",
        )
    cells = aggregate.get("cell_bindings")
    if not isinstance(cells, list) or [
        item.get("cell_id") for item in cells if isinstance(item, Mapping)
    ] != list(P3_CELL_ORDER):
        add(
            "P3_AGGREGATE_CELL_ORDER_MISMATCH",
            "$.cell_bindings",
            "cell bindings must preserve fixed cell order",
        )
    else:
        identities: dict[str, set[Any]] = {}
        for cell_index, cell in enumerate(cells):
            if not isinstance(cell, Mapping):
                continue
            if cell.get("provider_calls") != 0:
                add(
                    "P3_AGGREGATE_PROVIDER_CALLS_NONZERO",
                    f"$.cell_bindings[{cell_index}]",
                    "cell provider_calls must be zero",
                )
            operations = cell.get("operation_bindings")
            if not isinstance(operations, list):
                continue
            for operation in operations:
                if not isinstance(operation, Mapping):
                    continue
                kind = operation.get("operation_kind")
                if isinstance(kind, str):
                    identities.setdefault(kind, set()).add(
                        operation.get("contract_digest")
                    )
        for kind, digests in sorted(identities.items()):
            if len(digests) > 1:
                add(
                    "P3_AGGREGATE_OPERATION_IDENTITY_CONFLICT",
                    "$.cell_bindings",
                    f"operation kind {kind!r} has conflicting contract digests",
                )

    ownership = aggregate.get("canonical_ownership")
    if (
        not isinstance(ownership, Mapping)
        or ownership.get("live_claim_owner") != "legacy"
    ):
        add(
            "P3_AGGREGATE_LEGACY_OWNER_VIOLATION",
            "$.canonical_ownership.live_claim_owner",
            "live claim owner must remain legacy",
        )
    elif ownership.get("conflicting_contract_identities") != []:
        add(
            "P3_AGGREGATE_OPERATION_IDENTITY_CONFLICT",
            "$.canonical_ownership.conflicting_contract_identities",
            "aggregate carries conflicting contract identities",
        )

    authority = aggregate.get("authority_ceiling")
    if not isinstance(authority, Mapping):
        add(
            "REQUIRED_FIELD_MISSING", "$.authority_ceiling", "missing authority ceiling"
        )
    else:
        if authority.get("provider_calls") != 0:
            add(
                "P3_AGGREGATE_PROVIDER_CALLS_NONZERO",
                "$.authority_ceiling.provider_calls",
                "aggregate provider_calls must be zero",
            )
        for flag in (
            "network",
            "production_canonical_write",
            "live_provider",
            "external_delivery",
            "cutover",
            "authority_transfer",
            "legacy_retired",
            "candidate_created",
        ):
            if authority.get(flag) is not False:
                add(
                    "P3_AGGREGATE_AUTHORITY_VIOLATION",
                    f"$.authority_ceiling.{flag}",
                    f"authority flag {flag!r} must be false",
                )

    worktree = aggregate.get("worktree_identity")
    if not isinstance(worktree, Mapping):
        add(
            "REQUIRED_FIELD_MISSING", "$.worktree_identity", "missing worktree identity"
        )
    elif (
        worktree.get("candidate_commit") is not None
        or worktree.get("candidate_tree") is not None
    ):
        add(
            "P3_AGGREGATE_CANDIDATE_IDENTITY_PRESENT",
            "$.worktree_identity",
            "working-tree evidence must not claim a candidate commit or tree",
        )

    prerequisites = aggregate.get("promotion_prerequisites")
    if not isinstance(prerequisites, Mapping):
        add(
            "REQUIRED_FIELD_MISSING",
            "$.promotion_prerequisites",
            "missing prerequisites",
        )
    elif prerequisites.get("promotion_claim") is not False:
        add(
            "P3_AGGREGATE_PROMOTION_CLAIM_FORBIDDEN",
            "$.promotion_prerequisites.promotion_claim",
            "generator evidence must never claim promotion",
        )
    reviews = aggregate.get("external_family_reviews")
    if not isinstance(reviews, list):
        add(
            "P3_AGGREGATE_REVIEW_BINDING_INVALID",
            "$.external_family_reviews",
            "external family reviews must be a list",
        )
    else:
        families = [item.get("family") for item in reviews if isinstance(item, Mapping)]
        if len(families) != len(set(families)) or any(
            family not in P3_FAMILY_ORDER for family in families
        ):
            add(
                "P3_AGGREGATE_REVIEW_BINDING_INVALID",
                "$.external_family_reviews",
                "external review families must be unique P3 families",
            )
    return tuple(sorted(issues, key=lambda item: (item.code, item.path, item.message)))


def fragment_cell_ids(fragment: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Return cell ids for legacy mapping or normalized list fragments."""

    cells = fragment.get("cells")
    if isinstance(cells, Mapping):
        return tuple(str(cell_id) for cell_id in cells)
    if isinstance(cells, list):
        result: list[str] = []
        for cell in cells:
            if not isinstance(cell, Mapping):
                return None
            cell_id = cell.get("cell_id")
            if not isinstance(cell_id, str) or not cell_id:
                return None
            result.append(cell_id)
        return tuple(result)
    return None


def raw_newline_count(data: bytes) -> int:
    return data.count(b"\n")


def splitlines_count(data: bytes) -> int:
    return len(data.decode("utf-8").splitlines())


def resolve_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _semantics_for(
    obj: Mapping[str, Any],
    batch_default: str,
    *,
    schema: str | None = None,
) -> str:
    declared = obj.get("line_semantics", batch_default)
    if isinstance(declared, str) and declared in ALLOWED_LINE_SEMANTICS:
        return declared
    if isinstance(schema, str) and _SPLITLINES_SCHEMA_MARKER in schema:
        return "splitlines"
    return DEFAULT_LINE_SEMANTICS


def _check_required_fields(
    issues: list[ValidationIssue],
    path: str,
    obj: Mapping[str, Any],
    required: Sequence[str],
) -> None:
    for field in required:
        if field not in obj:
            issues.append(
                ValidationIssue(
                    code="REQUIRED_FIELD_MISSING",
                    path=path,
                    message=f"missing required field {field!r}",
                )
            )


def _check_unexpected_fields(
    issues: list[ValidationIssue],
    path: str,
    obj: Mapping[str, Any],
    allowed: Sequence[str],
    code: str = "UNEXPECTED_FIELD",
) -> None:
    allowed_set = set(allowed)
    for field in sorted(set(obj) - allowed_set):
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"unexpected field {field!r}",
            )
        )


def _check_chain(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    chain: Mapping[str, Any],
    *,
    label: str,
) -> None:
    _check_required_fields(issues, path, chain, CHAIN_REQUIRED_FIELDS)
    _check_unexpected_fields(
        issues, path, chain, CHAIN_ALLOWED_FIELDS, "CHAIN_UNEXPECTED_FIELD"
    )
    digest_code = {
        "P1": "P1_ARTIFACT_CONTENT_DIGEST_MISMATCH",
        "P2": "P2_ARTIFACT_CONTENT_DIGEST_MISMATCH",
    }.get(label, "CHAIN_CONTENT_DIGEST_MISMATCH")
    raw_path = chain.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return
    file_path = resolve_path(root, raw_path)
    if not file_path.is_file():
        code = {
            "P1": "P1_ARTIFACT_PATH_MISSING",
            "P2": "P2_ARTIFACT_PATH_MISSING",
        }.get(label, "CHAIN_PATH_MISSING")
        issues.append(
            ValidationIssue(
                code=code, path=path, message=f"missing {label} artifact {raw_path}"
            )
        )
        return
    data = file_path.read_bytes()
    file_sha256 = chain.get("file_sha256")
    if _is_sha256(file_sha256) and hashlib.sha256(data).hexdigest() != file_sha256:
        code = {
            "P1": "P1_ARTIFACT_FILE_HASH_MISMATCH",
            "P2": "P2_ARTIFACT_FILE_HASH_MISMATCH",
        }.get(label, "CHAIN_FILE_HASH_MISMATCH")
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"{label} artifact sha256 mismatch for {raw_path}",
            )
        )
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.append(
            ValidationIssue(
                code=digest_code,
                path=path,
                message=f"{label} artifact is not valid JSON: {exc}",
            )
        )
        return
    if not isinstance(parsed, Mapping):
        return
    content_digest = chain.get("content_digest")
    recomputed = canonical_content_digest(parsed)
    if _is_sha256(content_digest) and content_digest != recomputed:
        issues.append(
            ValidationIssue(
                code=digest_code,
                path=path,
                message=f"{label} artifact content digest mismatch for {raw_path}",
            )
        )


def _check_authority_ceiling(
    issues: list[ValidationIssue],
    path: str,
    obj: Mapping[str, Any],
) -> None:
    authority: Mapping[str, Any] | None = None
    for key in AUTHORITY_KEYS:
        candidate = obj.get(key)
        if isinstance(candidate, Mapping):
            authority = candidate
            break
    if authority is None:
        issues.append(
            ValidationIssue(
                code="REQUIRED_FIELD_MISSING",
                path=path,
                message="missing authority ceiling (authority_ceiling or authority_boundary)",
            )
        )
        return
    for flag in AUTHORITY_CEILING_REQUIRED_FLAGS:
        if flag not in authority:
            issues.append(
                ValidationIssue(
                    code="REQUIRED_FIELD_MISSING",
                    path=path,
                    message=f"missing authority ceiling flag {flag!r}",
                )
            )
    for flag, value in sorted(authority.items()):
        if value is True:
            issues.append(
                ValidationIssue(
                    code="AUTHORITY_CEILING_VIOLATION",
                    path=path,
                    message=f"authority ceiling flag {flag!r} must be false",
                )
            )


def _line_count(data: bytes, semantics: str) -> int:
    if semantics == "splitlines":
        return splitlines_count(data)
    return raw_newline_count(data)


def _symbol_present(text: str, symbol: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def _check_binding(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    binding: Mapping[str, Any],
    batch_default_semantics: str,
) -> int:
    _check_required_fields(issues, path, binding, BINDING_REQUIRED_FIELDS)
    _check_unexpected_fields(
        issues,
        path,
        binding,
        BINDING_ALLOWED_FIELDS,
        "SOURCE_BINDING_UNEXPECTED_FIELD",
    )
    raw_path = binding.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return 0
    file_path = resolve_path(root, raw_path)
    if not file_path.is_file():
        issues.append(
            ValidationIssue(
                code="SOURCE_BINDING_PATH_MISSING",
                path=path,
                message=f"missing bound source file {raw_path}",
            )
        )
        return 0
    data = file_path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    semantics = _semantics_for(binding, batch_default_semantics)
    declared_sha = binding.get("sha256")
    if _is_sha256(declared_sha) and hashlib.sha256(data).hexdigest() != declared_sha:
        issues.append(
            ValidationIssue(
                code="SOURCE_BINDING_SHA256_MISMATCH",
                path=path,
                message=f"sha256 mismatch for {raw_path}",
            )
        )
    declared_bytes = binding.get("bytes")
    if isinstance(declared_bytes, int) and declared_bytes != len(data):
        issues.append(
            ValidationIssue(
                code="SOURCE_BINDING_BYTES_MISMATCH",
                path=path,
                message=f"bytes mismatch for {raw_path}",
            )
        )
    declared_lines = binding.get("lines")
    if isinstance(declared_lines, int) and declared_lines != _line_count(
        data, semantics
    ):
        issues.append(
            ValidationIssue(
                code="SOURCE_BINDING_LINES_MISMATCH",
                path=path,
                message=(
                    f"lines mismatch for {raw_path} "
                    f"(declared {declared_lines}, {semantics} {_line_count(data, semantics)})"
                ),
            )
        )
    symbols = binding.get("symbols", binding.get("observed_symbols"))
    if isinstance(symbols, list):
        for symbol in symbols:
            if not isinstance(symbol, str) or not _symbol_present(text, symbol):
                issues.append(
                    ValidationIssue(
                        code="SOURCE_EVIDENCE_SYMBOL_MISSING",
                        path=path,
                        message=f"symbol {symbol!r} not found in {raw_path}",
                    )
                )
    return 1


def _check_evidence(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    evidence: Mapping[str, Any],
    batch_default_semantics: str,
) -> int:
    _check_required_fields(issues, path, evidence, EVIDENCE_REQUIRED_FIELDS)
    _check_unexpected_fields(
        issues,
        path,
        evidence,
        EVIDENCE_ALLOWED_FIELDS,
        "SOURCE_EVIDENCE_UNEXPECTED_FIELD",
    )
    raw_path = evidence.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return 0
    file_path = resolve_path(root, raw_path)
    if not file_path.is_file():
        issues.append(
            ValidationIssue(
                code="SOURCE_EVIDENCE_PATH_MISSING",
                path=path,
                message=f"missing source evidence file {raw_path}",
            )
        )
        return 0
    data = file_path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    semantics = _semantics_for(evidence, batch_default_semantics)
    total_lines = _line_count(data, semantics)
    descriptor = evidence.get("symbol_or_lines")
    ranges: list[tuple[int, int]] = []
    symbols: list[str] = []
    if isinstance(descriptor, str):
        ranges = [
            (int(start), int(end) if end else int(start))
            for start, end in _RANGE_RE.findall(descriptor)
        ]
        symbols = [
            match.group(0)
            for match in _SYMBOL_RE.finditer(descriptor)
            if match.group(0).lower() not in {"lines", "line"}
        ]
    extra_symbols = evidence.get("symbols")
    if isinstance(extra_symbols, list):
        symbols.extend(item for item in extra_symbols if isinstance(item, str))
    if not ranges and not symbols:
        issues.append(
            ValidationIssue(
                code="SOURCE_EVIDENCE_UNPARSEABLE",
                path=path,
                message=f"no parseable line range or symbol in {raw_path}",
            )
        )
    for start, end in ranges:
        if start < 1 or start > total_lines or end < start or end > total_lines:
            issues.append(
                ValidationIssue(
                    code="SOURCE_EVIDENCE_LINE_OUT_OF_RANGE",
                    path=path,
                    message=(
                        f"line range {start}-{end} out of range for {raw_path} "
                        f"({total_lines} {semantics} lines)"
                    ),
                )
            )
    for symbol in symbols:
        if not _symbol_present(text, symbol):
            issues.append(
                ValidationIssue(
                    code="SOURCE_EVIDENCE_SYMBOL_MISSING",
                    path=path,
                    message=f"symbol {symbol!r} not found in {raw_path}",
                )
            )
    return 1


def _read_json(
    issues: list[ValidationIssue],
    path: str,
    file_path: Path,
    code: str,
) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(file_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"invalid JSON: {exc}",
            )
        )
        return None
    if not isinstance(parsed, Mapping):
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message="expected a JSON object",
            )
        )
        return None
    return parsed


def _check_entry_file_binding(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    entry: Mapping[str, Any],
    batch_default_semantics: str,
    *,
    kind: str,
) -> bytes | None:
    raw_path = entry.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    file_path = resolve_path(root, raw_path)
    if not file_path.is_file():
        code = (
            "FRAGMENT_PATH_MISSING" if kind == "fragment" else "AGGREGATE_PATH_MISSING"
        )
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"missing {kind} file {raw_path}",
            )
        )
        return None
    data = file_path.read_bytes()
    declared_sha = entry.get("file_sha256")
    if _is_sha256(declared_sha) and hashlib.sha256(data).hexdigest() != declared_sha:
        code = (
            "FRAGMENT_FILE_HASH_MISMATCH"
            if kind == "fragment"
            else "AGGREGATE_FILE_HASH_MISMATCH"
        )
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"{kind} file sha256 mismatch for {raw_path}",
            )
        )
    declared_bytes = entry.get("bytes")
    if isinstance(declared_bytes, int) and declared_bytes != len(data):
        code = (
            "FRAGMENT_FILE_BYTES_MISMATCH"
            if kind == "fragment"
            else "AGGREGATE_FILE_BYTES_MISMATCH"
        )
        issues.append(
            ValidationIssue(
                code=code,
                path=path,
                message=f"{kind} file bytes mismatch for {raw_path}",
            )
        )
    declared_lines = entry.get("lines")
    if isinstance(declared_lines, int):
        semantics = _semantics_for(entry, batch_default_semantics)
        actual = _line_count(data, semantics)
        if declared_lines != actual:
            code = (
                "FRAGMENT_FILE_LINES_MISMATCH"
                if kind == "fragment"
                else "AGGREGATE_FILE_LINES_MISMATCH"
            )
            issues.append(
                ValidationIssue(
                    code=code,
                    path=path,
                    message=(
                        f"{kind} file lines mismatch for {raw_path} "
                        f"(declared {declared_lines}, {semantics} {actual})"
                    ),
                )
            )
    return data


def _validate_fragment_file(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    entry: Mapping[str, Any],
    batch_default_semantics: str,
) -> Mapping[str, Any] | None:
    data = _check_entry_file_binding(
        issues,
        root,
        path,
        entry,
        batch_default_semantics,
        kind="fragment",
    )
    if data is None:
        return None
    raw_path = entry["path"]
    file_path = resolve_path(root, raw_path)
    fragment = _read_json(issues, path, file_path, "FRAGMENT_INVALID_JSON")
    if fragment is None:
        return None
    _check_required_fields(issues, path, fragment, FRAGMENT_FILE_REQUIRED_FIELDS)
    semantics = _semantics_for(
        entry,
        batch_default_semantics,
        schema=fragment.get("schema"),
    )
    if semantics not in ALLOWED_LINE_SEMANTICS:
        issues.append(
            ValidationIssue(
                code="LINE_SEMANTICS_INVALID",
                path=path,
                message=f"invalid line_semantics {semantics!r}",
            )
        )
    declared_digest = fragment.get("content_digest")
    if _is_sha256(declared_digest) and declared_digest != canonical_content_digest(
        fragment
    ):
        issues.append(
            ValidationIssue(
                code="FRAGMENT_CONTENT_DIGEST_MISMATCH",
                path=path,
                message=f"fragment content digest mismatch for {raw_path}",
            )
        )
    entry_schema = entry.get("schema")
    if isinstance(entry_schema, str) and fragment.get("schema") != entry_schema:
        issues.append(
            ValidationIssue(
                code="FRAGMENT_SCHEMA_MISMATCH",
                path=path,
                message=f"fragment schema mismatch for {raw_path}",
            )
        )
    for key, label in (
        ("phase", "FRAGMENT_PHASE_MISMATCH"),
        ("family", "FRAGMENT_FAMILY_MISMATCH"),
    ):
        file_value = fragment.get(key)
        entry_value = entry.get(key)
        if isinstance(file_value, str) and file_value != entry_value:
            issues.append(
                ValidationIssue(
                    code=label,
                    path=path,
                    message=f"fragment {key} mismatch for {raw_path}",
                )
            )
    entry_status = entry.get("status")
    if isinstance(entry_status, str) and fragment.get("status") != entry_status:
        issues.append(
            ValidationIssue(
                code="FRAGMENT_ENTRY_STATUS_MISMATCH",
                path=path,
                message=f"fragment status mismatch for {raw_path}",
            )
        )
    _check_authority_ceiling(issues, path, fragment)
    cells = fragment_cell_ids(fragment)
    if cells is None:
        issues.append(
            ValidationIssue(
                code="REQUIRED_FIELD_MISSING",
                path=path,
                message=(
                    "fragment cells must be a JSON object or normalized list "
                    "of objects with cell_id"
                ),
            )
        )
    binding_groups = []
    legacy_bindings = fragment.get("files")
    if isinstance(legacy_bindings, list):
        binding_groups.append(legacy_bindings)
    for key in ("source_bindings", "implementation_bindings", "test_bindings"):
        group = fragment.get(key)
        if isinstance(group, list):
            binding_groups.append(group)
    bindings = [item for group in binding_groups for item in group]
    if not binding_groups:
        issues.append(
            ValidationIssue(
                code="REQUIRED_FIELD_MISSING",
                path=path,
                message=(
                    "fragment requires files or source/implementation/test bindings"
                ),
            )
        )
    for index, binding in enumerate(bindings):
        if isinstance(binding, Mapping):
            _check_binding(
                issues,
                root,
                f"{path}.bindings[{index}]",
                binding,
                semantics,
            )
    evidence_entries = fragment.get("source_evidence")
    if isinstance(evidence_entries, list):
        for index, evidence in enumerate(evidence_entries):
            if isinstance(evidence, Mapping):
                _check_evidence(
                    issues,
                    root,
                    f"{path}.source_evidence[{index}]",
                    evidence,
                    semantics,
                )
    observed_symbols = fragment.get("observed_symbols")
    if isinstance(observed_symbols, list):
        bound_text = "\n".join(
            resolve_path(root, item.get("path", "")).read_text(
                encoding="utf-8", errors="replace"
            )
            for item in bindings
            if isinstance(item, Mapping)
            and isinstance(item.get("path"), str)
            and resolve_path(root, item["path"]).is_file()
        )
        for symbol in observed_symbols:
            if not isinstance(symbol, str) or not _symbol_present(bound_text, symbol):
                issues.append(
                    ValidationIssue(
                        code="SOURCE_EVIDENCE_SYMBOL_MISSING",
                        path=path,
                        message=f"observed symbol {symbol!r} not present in bound sources",
                    )
                )
    return fragment


def _validate_aggregate_file(
    issues: list[ValidationIssue],
    root: Path,
    path: str,
    entry: Mapping[str, Any],
    batch_default_semantics: str,
) -> Mapping[str, Any] | None:
    data = _check_entry_file_binding(
        issues,
        root,
        path,
        entry,
        batch_default_semantics,
        kind="aggregate",
    )
    if data is None:
        return None
    raw_path = entry["path"]
    file_path = resolve_path(root, raw_path)
    aggregate = _read_json(issues, path, file_path, "AGGREGATE_INVALID_JSON")
    if aggregate is None:
        return None
    _check_required_fields(issues, path, aggregate, AGGREGATE_FILE_REQUIRED_FIELDS)
    semantics = _semantics_for(
        entry,
        batch_default_semantics,
        schema=aggregate.get("schema"),
    )
    if semantics not in ALLOWED_LINE_SEMANTICS:
        issues.append(
            ValidationIssue(
                code="LINE_SEMANTICS_INVALID",
                path=path,
                message=f"invalid line_semantics {semantics!r}",
            )
        )
    declared_digest = aggregate.get("content_digest")
    if _is_sha256(declared_digest) and declared_digest != canonical_content_digest(
        aggregate
    ):
        issues.append(
            ValidationIssue(
                code="AGGREGATE_CONTENT_DIGEST_MISMATCH",
                path=path,
                message=f"aggregate content digest mismatch for {raw_path}",
            )
        )
    entry_digest = entry.get("content_digest")
    if _is_sha256(entry_digest) and entry_digest != aggregate.get("content_digest"):
        issues.append(
            ValidationIssue(
                code="AGGREGATE_CONTENT_DIGEST_MISMATCH",
                path=path,
                message=f"aggregate entry content digest mismatch for {raw_path}",
            )
        )
    if entry.get("schema") != aggregate.get("schema"):
        issues.append(
            ValidationIssue(
                code="AGGREGATE_SCHEMA_MISMATCH",
                path=path,
                message=f"aggregate schema mismatch for {raw_path}",
            )
        )
    if entry.get("status") != aggregate.get("status"):
        issues.append(
            ValidationIssue(
                code="AGGREGATE_ENTRY_STATUS_MISMATCH",
                path=path,
                message=f"aggregate status mismatch for {raw_path}",
            )
        )
    for field in ("families", "cell_ids"):
        entry_value = entry.get(field)
        file_value = aggregate.get(field)
        if isinstance(entry_value, list) and entry_value != file_value:
            code = (
                "AGGREGATE_FAMILIES_MISMATCH"
                if field == "families"
                else "AGGREGATE_CELLS_MISMATCH"
            )
            issues.append(
                ValidationIssue(
                    code=code,
                    path=path,
                    message=f"aggregate {field} mismatch for {raw_path}",
                )
            )
    _check_authority_ceiling(issues, path, aggregate)
    entry_authority = entry.get("authority_ceiling")
    if isinstance(entry_authority, Mapping):
        for flag, value in sorted(entry_authority.items()):
            if value is True:
                issues.append(
                    ValidationIssue(
                        code="AUTHORITY_CEILING_VIOLATION",
                        path=path,
                        message=f"aggregate authority ceiling flag {flag!r} must be false",
                    )
                )
    if aggregate.get("schema") == P3_AGGREGATE_SCHEMA:
        for issue in validate_p3_aggregate_document(aggregate):
            issues.append(
                ValidationIssue(
                    code=issue.code,
                    path=f"{path}{issue.path[1:]}",
                    message=issue.message,
                )
            )
    return aggregate


def _promotion_claim(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    upper = text.upper()
    if any(
        token in upper
        for token in ("NOT_PROMOTED", "UNPROMOTED", "NO_PROMOTION", "PENDING")
    ):
        return False
    return any(
        token in upper
        for token in (
            "PROMOTED",
            "ADOPTED",
            "MIGRATED",
            "CUTOVER",
            "LIVE_PROVIDER",
            "CANARY_PASS",
        )
    )


def validate_batch(
    batch: Any,
    root: str | Path,
    *,
    line_semantics: str | None = None,
) -> ValidationReport:
    """Validate a parsed migration batch without writing any files."""
    root_path = Path(root)
    issues: list[ValidationIssue] = []
    batch_id = ""
    batch_schema = ""
    declared_phases: list[str] = []
    fragment_phases: set[str] = set()
    families_by_phase: dict[str, list[str]] = {}
    aggregate_phases: list[str] = []
    cell_owners: dict[str, str] = {}
    fragment_count = 0
    aggregate_count = 0
    binding_count = 0
    evidence_count = 0

    if not isinstance(batch, Mapping):
        issues.append(
            ValidationIssue(
                code="BATCH_NOT_OBJECT",
                path="$",
                message="batch root must be a JSON object",
            )
        )
        return _build_report(
            issues=issues,
            batch_id=batch_id,
            batch_schema=batch_schema,
            root=root_path,
            declared_phases=declared_phases,
            families_by_phase=families_by_phase,
            aggregate_phases=aggregate_phases,
            counts={},
        )

    batch_id = batch.get("batch_id") if isinstance(batch.get("batch_id"), str) else ""
    batch_schema = batch.get("schema") if isinstance(batch.get("schema"), str) else ""
    _check_required_fields(issues, "$", batch, BATCH_REQUIRED_FIELDS)
    _check_unexpected_fields(issues, "$", batch, BATCH_ALLOWED_FIELDS)
    if batch_schema != BATCH_SCHEMA:
        issues.append(
            ValidationIssue(
                code="BATCH_SCHEMA_INVALID",
                path="$",
                message=f"expected schema {BATCH_SCHEMA!r}, got {batch_schema!r}",
            )
        )

    default_semantics = (
        line_semantics or batch.get("line_semantics") or DEFAULT_LINE_SEMANTICS
    )
    if default_semantics not in ALLOWED_LINE_SEMANTICS:
        issues.append(
            ValidationIssue(
                code="LINE_SEMANTICS_INVALID",
                path="$",
                message=f"invalid line_semantics {default_semantics!r}",
            )
        )
        default_semantics = DEFAULT_LINE_SEMANTICS

    if not root_path.exists():
        issues.append(
            ValidationIssue(
                code="ROOT_MISSING",
                path="$",
                message=f"root does not exist: {root_path}",
            )
        )
    elif not root_path.is_dir():
        issues.append(
            ValidationIssue(
                code="ROOT_NOT_DIRECTORY",
                path="$",
                message=f"root is not a directory: {root_path}",
            )
        )

    declared_phases_value = batch.get("phase_union")
    if isinstance(declared_phases_value, list):
        declared_phases = [str(item) for item in declared_phases_value]
        if sorted(declared_phases) != declared_phases or len(
            set(declared_phases)
        ) != len(declared_phases):
            issues.append(
                ValidationIssue(
                    code="PHASE_UNION_MISMATCH",
                    path="$.phase_union",
                    message="phase_union must be sorted with unique phases",
                )
            )
    for phase in declared_phases:
        if phase not in ALLOWED_PHASES:
            issues.append(
                ValidationIssue(
                    code="PHASE_INVALID",
                    path="$.phase_union",
                    message=f"unknown phase {phase!r}",
                )
            )

    p1_chain = batch.get("p1_artifact")
    p2_chain = batch.get("p2_artifact")
    if isinstance(p1_chain, Mapping):
        _check_chain(issues, root_path, "$.p1_artifact", p1_chain, label="P1")
    if isinstance(p2_chain, Mapping):
        _check_chain(issues, root_path, "$.p2_artifact", p2_chain, label="P2")

    fragments = batch.get("fragments")
    if isinstance(fragments, list):
        for index, entry in enumerate(fragments):
            if not isinstance(entry, Mapping):
                issues.append(
                    ValidationIssue(
                        code="REQUIRED_FIELD_MISSING",
                        path=f"$.fragments[{index}]",
                        message="fragment entry must be a JSON object",
                    )
                )
                continue
            fragment_count += 1
            entry_path = f"$.fragments[{index}]"
            _check_required_fields(issues, entry_path, entry, FRAGMENT_REQUIRED_FIELDS)
            _check_unexpected_fields(
                issues,
                entry_path,
                entry,
                FRAGMENT_ALLOWED_FIELDS,
                "FRAGMENT_UNEXPECTED_FIELD",
            )
            phase = entry.get("phase")
            family = entry.get("family")
            if isinstance(phase, str):
                fragment_phases.add(phase)
                if phase not in ALLOWED_PHASES:
                    issues.append(
                        ValidationIssue(
                            code="PHASE_INVALID",
                            path=entry_path,
                            message=f"unknown fragment phase {phase!r}",
                        )
                    )
                elif (
                    isinstance(family, str)
                    and family not in PHASE_ALLOWED_FAMILIES[phase]
                ):
                    issues.append(
                        ValidationIssue(
                            code="PHASE_FAMILY_UNEXPECTED",
                            path=entry_path,
                            message=f"family {family!r} is not allowed in phase {phase}",
                        )
                    )
            if isinstance(phase, str) and isinstance(family, str):
                families_by_phase.setdefault(phase, []).append(family)
            fragment = _validate_fragment_file(
                issues,
                root_path,
                entry_path,
                entry,
                default_semantics,
            )
            if fragment is not None:
                cells = fragment_cell_ids(fragment)
                if cells is not None:
                    for cell_id in cells:
                        if not isinstance(cell_id, str) or not cell_id:
                            issues.append(
                                ValidationIssue(
                                    code="CELL_ID_INVALID",
                                    path=entry_path,
                                    message="cell ids must be non-empty strings",
                                )
                            )
                            continue
                        owner = cell_owners.get(cell_id)
                        if owner is not None:
                            issues.append(
                                ValidationIssue(
                                    code="DUPLICATE_CELL_ID",
                                    path=entry_path,
                                    message=f"cell id {cell_id!r} already declared by {owner}",
                                )
                            )
                        else:
                            cell_owners[cell_id] = entry_path
                for key in (
                    "files",
                    "source_bindings",
                    "implementation_bindings",
                    "test_bindings",
                ):
                    bindings = fragment.get(key)
                    if isinstance(bindings, list):
                        binding_count += sum(
                            1 for item in bindings if isinstance(item, Mapping)
                        )
                evidence = fragment.get("source_evidence")
                if isinstance(evidence, list):
                    evidence_count += sum(
                        1 for item in evidence if isinstance(item, Mapping)
                    )
            chain = entry.get("p1_p2_chain")
            if isinstance(chain, Mapping):
                for label, key in (("P1", "p1_artifact"), ("P2", "p2_artifact")):
                    bound_chain = chain.get(key)
                    if not isinstance(bound_chain, Mapping):
                        issues.append(
                            ValidationIssue(
                                code="REQUIRED_FIELD_MISSING",
                                path=f"{entry_path}.p1_p2_chain",
                                message=f"missing {key!r} chain binding",
                            )
                        )
                        continue
                    _check_chain(
                        issues,
                        root_path,
                        f"{entry_path}.p1_p2_chain.{key}",
                        bound_chain,
                        label=label,
                    )
                    batch_chain = p1_chain if label == "P1" else p2_chain
                    if isinstance(batch_chain, Mapping):
                        for field in CHAIN_REQUIRED_FIELDS:
                            if bound_chain.get(field) != batch_chain.get(field):
                                issues.append(
                                    ValidationIssue(
                                        code="P1_P2_CHAIN_MISMATCH",
                                        path=entry_path,
                                        message=(
                                            f"fragment {label} chain {field} does not "
                                            "match batch chain"
                                        ),
                                    )
                                )

    aggregates = batch.get("aggregates")
    if aggregates is None:
        aggregates = []
    aggregate_by_path: dict[str, str] = {}
    if isinstance(aggregates, list):
        aggregate_objects: list[tuple[str, Mapping[str, Any]]] = []
        for index, entry in enumerate(aggregates):
            if not isinstance(entry, Mapping):
                issues.append(
                    ValidationIssue(
                        code="REQUIRED_FIELD_MISSING",
                        path=f"$.aggregates[{index}]",
                        message="aggregate entry must be a JSON object",
                    )
                )
                continue
            aggregate_count += 1
            entry_path = f"$.aggregates[{index}]"
            _check_required_fields(issues, entry_path, entry, AGGREGATE_REQUIRED_FIELDS)
            _check_unexpected_fields(
                issues, entry_path, entry, AGGREGATE_ALLOWED_FIELDS
            )
            phase = entry.get("phase")
            if isinstance(phase, str) and phase in ALLOWED_PHASES:
                aggregate_phases.append(phase)
            aggregate = _validate_aggregate_file(
                issues,
                root_path,
                entry_path,
                entry,
                default_semantics,
            )
            if aggregate is not None:
                aggregate_objects.append((entry_path, aggregate))

        for entry_path, aggregate in aggregate_objects:
            raw_path = aggregate.get("path", "")
            if isinstance(raw_path, str):
                aggregate_by_path[raw_path] = entry_path

        for index, entry in enumerate(aggregates):
            if not isinstance(entry, Mapping):
                continue
            entry_path = f"$.aggregates[{index}]"
            phase = entry.get("phase")
            families = entry.get("families")
            cell_ids = entry.get("cell_ids")
            status = entry.get("status")
            if not isinstance(phase, str) or not isinstance(families, list):
                continue
            expected_families = sorted(families_by_phase.get(phase, []))
            if sorted(families) != expected_families:
                issues.append(
                    ValidationIssue(
                        code="AGGREGATE_FAMILIES_MISMATCH",
                        path=entry_path,
                        message=(
                            f"aggregate families {sorted(families)} do not match "
                            f"fragment families {expected_families}"
                        ),
                    )
                )
            if isinstance(cell_ids, list):
                fragment_cells: list[str] = []
                for frag_entry in fragments:
                    if not isinstance(frag_entry, Mapping):
                        continue
                    if frag_entry.get("phase") != phase:
                        continue
                    frag_path = frag_entry.get("path")
                    if not isinstance(frag_path, str):
                        continue
                    frag_file = _read_json(
                        issues,
                        entry_path,
                        resolve_path(root_path, frag_path),
                        "FRAGMENT_INVALID_JSON",
                    )
                    if frag_file is not None:
                        ids = fragment_cell_ids(frag_file)
                        if ids is not None:
                            fragment_cells.extend(ids)
                if sorted(cell_ids) != sorted(fragment_cells):
                    issues.append(
                        ValidationIssue(
                            code="AGGREGATE_CELLS_MISMATCH",
                            path=entry_path,
                            message=(
                                f"aggregate cell ids {sorted(cell_ids)} do not match "
                                f"fragment cell ids {sorted(fragment_cells)}"
                            ),
                        )
                    )
            if isinstance(status, str) and _promotion_claim(status):
                fragment_statuses = [
                    frag_file.get("status", "")
                    for frag_entry in fragments
                    if isinstance(frag_entry, Mapping)
                    and frag_entry.get("phase") == phase
                    for frag_file in [
                        _read_json(
                            issues,
                            entry_path,
                            resolve_path(
                                root_path,
                                frag_entry.get("path", ""),
                            ),
                            "FRAGMENT_INVALID_JSON",
                        )
                    ]
                    if frag_file is not None
                ]
                if any(not _promotion_claim(item) for item in fragment_statuses):
                    issues.append(
                        ValidationIssue(
                            code="AGGREGATE_CLAIM_EXCEEDS_FRAGMENTS",
                            path=entry_path,
                            message="aggregate promotion claim exceeds fragment statuses",
                        )
                    )

    for index, entry in enumerate(fragments if isinstance(fragments, list) else []):
        if not isinstance(entry, Mapping):
            continue
        aggregate_ref = entry.get("aggregate_ref")
        if isinstance(aggregate_ref, str) and aggregate_ref not in aggregate_by_path:
            issues.append(
                ValidationIssue(
                    code="FRAGMENT_AGGREGATE_REF_MISSING",
                    path=f"$.fragments[{index}]",
                    message=f"aggregate_ref {aggregate_ref!r} is not a batch aggregate path",
                )
            )

    for phase in declared_phases:
        if phase not in ALLOWED_PHASES:
            continue
        present = sorted(set(families_by_phase.get(phase, [])))
        required = sorted(PHASE_REQUIRED_FAMILIES[phase])
        if present != required:
            missing = sorted(set(required) - set(present))
            if missing:
                issues.append(
                    ValidationIssue(
                        code="PHASE_FAMILY_MISSING",
                        path="$.phase_union",
                        message=f"phase {phase} missing fragment families {missing}",
                    )
                )

    if isinstance(declared_phases_value, list):
        declared_set = set(declared_phases)
        if declared_set != fragment_phases:
            issues.append(
                ValidationIssue(
                    code="PHASE_UNION_MISMATCH",
                    path="$.phase_union",
                    message=(
                        f"declared phase_union {sorted(declared_set)} does not match "
                        f"fragment phases {sorted(fragment_phases)}"
                    ),
                )
            )

    counts = {
        "fragments": fragment_count,
        "aggregates": aggregate_count,
        "cells": len(cell_owners),
        "source_bindings": binding_count,
        "source_evidence": evidence_count,
        "issues": len(issues),
    }
    return _build_report(
        issues=issues,
        batch_id=batch_id,
        batch_schema=batch_schema,
        root=root_path,
        declared_phases=declared_phases,
        families_by_phase=families_by_phase,
        aggregate_phases=aggregate_phases,
        counts=counts,
    )


def _build_report(
    *,
    issues: list[ValidationIssue],
    batch_id: str,
    batch_schema: str,
    root: Path,
    declared_phases: list[str],
    families_by_phase: Mapping[str, list[str]],
    aggregate_phases: list[str],
    counts: Mapping[str, int],
) -> ValidationReport:
    sorted_issues = tuple(
        sorted(issues, key=lambda item: (item.code, item.path, item.message))
    )
    valid = not sorted_issues
    return ValidationReport(
        status="VALID" if valid else "INVALID",
        exit_code=0 if valid else 1,
        batch_id=batch_id,
        batch_schema=batch_schema,
        root=str(root),
        phase_union=tuple(declared_phases),
        counts=counts,
        families_by_phase={
            phase: tuple(sorted(set(families)))
            for phase, families in families_by_phase.items()
        },
        aggregate_phases=tuple(aggregate_phases),
        issues=sorted_issues,
    )


def _fatal_report(batch_path: Path, message: str) -> ValidationReport:
    issue = ValidationIssue(
        code="VALIDATION_FATAL",
        path=str(batch_path),
        message=message,
    )
    return ValidationReport(
        status="ERROR",
        exit_code=2,
        batch_id="",
        batch_schema="",
        root="",
        phase_union=(),
        counts={"issues": 1},
        families_by_phase={},
        aggregate_phases=(),
        issues=(issue,),
    )


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a P3/P4 successor migration batch read-only."
    )
    parser.add_argument("--batch", required=True, help="path to batch JSON")
    parser.add_argument("--root", default=None, help="override batch root")
    parser.add_argument(
        "--report", default=None, help="optional canonical report output"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress stdout report")
    args = parser.parse_args(argv)

    batch_path = Path(args.batch)
    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report = _fatal_report(batch_path, f"unable to read batch JSON: {exc}")
        if args.report:
            try:
                _write_text_atomic(Path(args.report), report.to_json() + "\n")
            except OSError:
                return 2
        if not args.quiet:
            print(report.to_json())
        return 2

    declared_root = batch.get("root") if isinstance(batch, Mapping) else None
    if args.root:
        root = Path(args.root)
    elif isinstance(declared_root, str):
        root = Path.cwd() / declared_root
    else:
        root = Path.cwd()
    report = validate_batch(batch, root)
    if args.report:
        try:
            _write_text_atomic(Path(args.report), report.to_json() + "\n")
        except OSError as exc:
            if not args.quiet:
                print(f"unable to write report: {exc}", file=sys.stderr)
            return 2
    if not args.quiet:
        print(report.to_json())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(run_cli())
