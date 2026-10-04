"""Pure C9.1 business-line evidence matrix capability (ALL-SM-001).

This module re-expresses the donor business-line evidence matrix as a typed,
read-only seven-line projection.  It never imports legacy business-line
services, never reads credentials, never starts a scheduler/executor, never
touches a provider and never writes a database or canonical record.

Semantic invariants
-------------------
* The seven canonical line keys are fixed and projected in canonical order.
* A worker-required line may only pass with decidable terminal readback
  evidence; success status or HTTP 2xx alone never fabricates that fact.
* A non-worker line may pass only from deterministic endpoint readback
  evidence represented by the caller-supplied typed source refs.
* Any failed/missing/duplicate/unexpected row fails the matrix closed.  A
  matrix with only blocked rows is ``blocked_by_environment``.  Empty source
  evidence never produces ``passed``.
* Every authority flag and ``completion_claim`` stays ``False`` by
  construction.  Row and matrix digests are deterministic content addresses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NoReturn

from functorial_kit import Failure

from app.successor_runtime.capabilities.checksum import content_digest
from mrw_functorial_kit.business_line_vocabulary import (
    BUSINESS_LINE_KEYS as CANONICAL_BUSINESS_LINE_KEYS,
)
from mrw_functorial_kit.business_line_vocabulary import (
    WORKER_REQUIRED_BUSINESS_LINE_KEYS as CANONICAL_WORKER_REQUIRED_BUSINESS_LINE_KEYS,
)
from mrw_functorial_kit.core.w06_semantics import (
    projection_evidence_surface_failures,
)

__all__ = [
    "BUSINESS_LINE_KEYS",
    "EVIDENCE_MATRIX_AUTHORITY_SCHEMA",
    "EVIDENCE_MATRIX_READBACK_SCHEMA",
    "EVIDENCE_MATRIX_SCHEMA",
    "NON_WORKER_TERMINAL_STATUS",
    "PROJECTION_EVIDENCE_MATRIX_FAILURES",
    "WORKER_REQUIRED_BUSINESS_LINE_KEYS",
    "BusinessLineEvidenceMatrix",
    "BusinessLineEvidenceRecord",
    "EvidenceMatrixAuthority",
    "EvidenceMatrixError",
    "EvidenceMatrixIntegrityError",
    "EvidenceMatrixLineSetError",
    "EvidenceMatrixSourceError",
    "EvidenceMatrixSummary",
    "EvidenceRowStatus",
    "EvidenceSourceRef",
    "normalize_evidence_line_key",
    "project_business_line_evidence_matrix",
]

EVIDENCE_MATRIX_SCHEMA = "mrw.projection.evidence-matrix.v2"
EVIDENCE_MATRIX_AUTHORITY_SCHEMA = "mrw.projection.evidence-matrix-authority.v2"
EVIDENCE_MATRIX_READBACK_SCHEMA = "mrw.projection.evidence-matrix-readback.v2"
PROJECTION_EVIDENCE_MATRIX_FAILURES = projection_evidence_surface_failures

BUSINESS_LINE_KEYS = CANONICAL_BUSINESS_LINE_KEYS
WORKER_REQUIRED_BUSINESS_LINE_KEYS = CANONICAL_WORKER_REQUIRED_BUSINESS_LINE_KEYS

NON_WORKER_TERMINAL_STATUS: dict[str, str] = {
    "projects_config_workflow": "applied",
    "dashboard_admin_governance": "available",
    "runtime_ops": "healthy",
}

_AUTHORITY_FLAG_FIELDS = (
    "live_provider",
    "canonical_write",
    "cutover",
    "external_delivery",
    "authority_transfer",
    "scheduler",
    "executor",
    "legacy_db_write",
    "candidate_created",
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


def _failure(
    code: str, message: str, *, public_exception: str = "ValueError", site: str = "c9_evidence_matrix"
) -> Failure:
    return PROJECTION_EVIDENCE_MATRIX_FAILURES.fail(
        code,
        message,
        {
            "owner": "projection.evidence-matrix.v2",
            "site": site,
            "public_exception": public_exception,
            "public_message": message,
            "witness": _FAILURE_WITNESS,
        },
    )


def _raise_contract_failure(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != PROJECTION_EVIDENCE_MATRIX_FAILURES.name
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=c9_evidence_matrix.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("projection evidence matrix contract lift context is incomplete")  # noqa: TRY003
    # kit:boundary owner=c9_evidence_matrix.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=projection.evidence-surface.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context.get("public_message", failure.message)))


def _reject(
    message: str, exception_type: type[Exception] = ValueError, *, code: str = "surface_contract_invalid"
) -> NoReturn:
    _raise_contract_failure(_failure(code, message, public_exception=exception_type.__name__), exception_type)


class EvidenceMatrixError(ValueError):
    """Base fail-closed error for business-line evidence matrices."""


class EvidenceMatrixLineSetError(EvidenceMatrixError):
    """Line set/order/worker-requirement invariants are violated."""


class EvidenceMatrixSourceError(EvidenceMatrixError):
    """Typed source evidence cannot form a valid matrix row."""


class EvidenceMatrixIntegrityError(EvidenceMatrixError):
    """A row/matrix digest no longer matches its canonical plain content."""


class EvidenceRowStatus(StrEnum):
    """Canonical evidence row status vocabulary."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED_BY_ENVIRONMENT = "blocked_by_environment"


def normalize_evidence_line_key(value: object) -> str:
    """Normalize one raw business-line key to canonical snake_case form."""

    if value is None:
        return ""
    text = str(value).strip().lower()
    return text.replace("-", "_").replace(" ", "_")


def _coerce_row_status(value: object) -> EvidenceRowStatus:
    if isinstance(value, EvidenceRowStatus):
        return value
    text = str(value).strip().lower()
    try:
        return EvidenceRowStatus(text)
    except ValueError:
        _raise_contract_failure(
            _failure(
                "evidence_source_invalid",
                f"unsupported evidence row status {value!r}",
                public_exception="EvidenceMatrixSourceError",
            ),
            EvidenceMatrixSourceError,
        )


def _as_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        _raise_contract_failure(
            _failure("evidence_source_invalid", f"{name} must be bool", public_exception="TypeError"), TypeError
        )
    return value


def _as_text(value: object, name: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        _raise_contract_failure(
            _failure(
                "evidence_source_invalid", f"{name} must be non-empty", public_exception="EvidenceMatrixSourceError"
            ),
            EvidenceMatrixSourceError,
        )
    return text


def _require_digest_hex(value: str, name: str) -> str:
    if _HEX64_RE.fullmatch(value) is None:
        _raise_contract_failure(
            _failure(
                "evidence_integrity_invalid",
                f"{name} must be a 64-char lowercase hex digest",
                public_exception="EvidenceMatrixIntegrityError",
            ),
            EvidenceMatrixIntegrityError,
        )
    return value


def _record_content(record: BusinessLineEvidenceRecord) -> dict[str, Any]:
    plain = record.to_plain()
    plain.pop("row_digest", None)
    return plain


def _record_digest(record: BusinessLineEvidenceRecord) -> str:
    return content_digest(_record_content(record))


def _matrix_content(matrix: BusinessLineEvidenceMatrix) -> dict[str, Any]:
    plain = matrix.to_plain()
    plain.pop("matrix_digest", None)
    return plain


def _matrix_digest(matrix: BusinessLineEvidenceMatrix) -> str:
    return content_digest(_matrix_content(matrix))


@dataclass(frozen=True, slots=True)
class EvidenceMatrixAuthority:
    """Read-only authority ceiling; every flag is always ``False``."""

    schema_ref: str = EVIDENCE_MATRIX_AUTHORITY_SCHEMA
    live_provider: bool = False
    canonical_write: bool = False
    cutover: bool = False
    external_delivery: bool = False
    authority_transfer: bool = False
    scheduler: bool = False
    executor: bool = False
    legacy_db_write: bool = False
    candidate_created: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.schema_ref, str) or not self.schema_ref.strip():
            _reject("EvidenceMatrixAuthority.schema_ref is required", code="authority_contract_invalid")
        for name in _AUTHORITY_FLAG_FIELDS:
            value = _as_bool(getattr(self, name), f"EvidenceMatrixAuthority.{name}")
            if value:
                _reject(
                    f"projection evidence matrix grants no runtime authority; {name} must be False",
                    code="authority_contract_invalid",
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            **{name: getattr(self, name) for name in _AUTHORITY_FLAG_FIELDS},
        }


@dataclass(frozen=True, slots=True)
class EvidenceMatrixSummary:
    """Deterministic row-status counts for one canonical matrix."""

    total: int
    passed: int
    blocked: int
    failed: int

    def __post_init__(self) -> None:
        for name in ("total", "passed", "blocked", "failed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _reject(f"EvidenceMatrixSummary.{name} must be a non-negative integer", code="projection_input_invalid")
        if self.total != self.passed + self.blocked + self.failed:
            _reject("EvidenceMatrixSummary counts must cover every row status", code="projection_input_invalid")

    def to_plain(self) -> dict[str, int]:
        return {
            "total": self.total,
            "passed": self.passed,
            "blocked": self.blocked,
            "failed": self.failed,
        }

    def to_dict(self) -> dict[str, int]:
        return self.to_plain()


@dataclass(frozen=True, slots=True)
class EvidenceSourceRef:
    """One typed source/readback observation behind a matrix row."""

    source_kind: str
    observed_at: str
    status: str
    reason_code: str
    digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", _as_text(self.source_kind, "source_kind"))
        object.__setattr__(self, "observed_at", _as_text(self.observed_at, "observed_at"))
        object.__setattr__(self, "status", _as_text(self.status, "status"))
        object.__setattr__(self, "reason_code", _as_text(self.reason_code, "reason_code"))
        digest = str(self.digest or "").strip()
        if digest and _HEX64_RE.fullmatch(digest) is None:
            _reject(
                "EvidenceSourceRef.digest must be a 64-char lowercase hex digest",
                EvidenceMatrixSourceError,
                code="evidence_source_invalid",
            )
        object.__setattr__(self, "digest", digest)

    def to_plain(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "observed_at": self.observed_at,
            "status": self.status,
            "reason_code": self.reason_code,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class BusinessLineEvidenceRecord:
    """One immutable, content-addressed business-line evidence row."""

    line_key: str
    status: EvidenceRowStatus
    reason_code: str
    requires_worker_readback: bool
    persistence_decidable: bool
    source_refs: tuple[EvidenceSourceRef, ...] = ()
    observed_at: str = ""
    row_digest: str = ""

    def __post_init__(self) -> None:
        normalized_key = normalize_evidence_line_key(self.line_key)
        if normalized_key not in BUSINESS_LINE_KEYS:
            _reject(
                f"unknown business-line key {self.line_key!r}",
                EvidenceMatrixLineSetError,
                code="evidence_line_set_invalid",
            )
        object.__setattr__(self, "line_key", normalized_key)
        object.__setattr__(self, "status", _coerce_row_status(self.status))
        object.__setattr__(
            self,
            "reason_code",
            _as_text(self.reason_code, "reason_code"),
        )
        object.__setattr__(
            self,
            "requires_worker_readback",
            _as_bool(
                self.requires_worker_readback,
                "requires_worker_readback",
            ),
        )
        object.__setattr__(
            self,
            "persistence_decidable",
            _as_bool(self.persistence_decidable, "persistence_decidable"),
        )
        source_refs = tuple(self.source_refs)
        if any(not isinstance(item, EvidenceSourceRef) for item in source_refs):
            _reject(
                "BusinessLineEvidenceRecord.source_refs must be typed source refs",
                EvidenceMatrixSourceError,
                code="evidence_source_invalid",
            )
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "observed_at", _as_text(self.observed_at, "observed_at"))
        expected_worker = normalized_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
        if self.requires_worker_readback != expected_worker:
            _reject(
                f"worker requirement mismatch for line {normalized_key!r}",
                EvidenceMatrixLineSetError,
                code="evidence_line_set_invalid",
            )
        provided = str(self.row_digest or "").strip()
        expected = _record_digest(self)
        if not provided:
            object.__setattr__(self, "row_digest", expected)
        else:
            _require_digest_hex(provided, "BusinessLineEvidenceRecord.row_digest")
            if provided != expected:
                _reject(
                    "BusinessLineEvidenceRecord.row_digest does not match content",
                    EvidenceMatrixIntegrityError,
                    code="evidence_integrity_invalid",
                )

    def verify_digest(self) -> None:
        """Fail closed when a caller changed the row without its digest."""

        expected = _record_digest(self)
        if self.row_digest != expected:
            _reject(
                "BusinessLineEvidenceRecord.row_digest does not match content",
                EvidenceMatrixIntegrityError,
                code="evidence_integrity_invalid",
            )

    def to_plain(self) -> dict[str, Any]:
        return {
            "line_key": self.line_key,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "requires_worker_readback": self.requires_worker_readback,
            "persistence_decidable": self.persistence_decidable,
            "source_refs": [source.to_plain() for source in self.source_refs],
            "observed_at": self.observed_at,
            "row_digest": self.row_digest,
        }


@dataclass(frozen=True, slots=True)
class BusinessLineEvidenceMatrix:
    """Immutable canonical seven-line evidence matrix projection."""

    expected_line_keys: tuple[str, ...]
    rows: tuple[BusinessLineEvidenceRecord, ...]
    summary: EvidenceMatrixSummary
    source_status: EvidenceRowStatus
    observed_at: str
    matrix_digest: str = ""
    authority: EvidenceMatrixAuthority = field(default_factory=EvidenceMatrixAuthority)
    completion_claim: bool = False

    def __post_init__(self) -> None:
        expected_line_keys = tuple(self.expected_line_keys)
        rows = tuple(self.rows)
        object.__setattr__(self, "expected_line_keys", expected_line_keys)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "observed_at", _as_text(self.observed_at, "observed_at"))
        if expected_line_keys != BUSINESS_LINE_KEYS:
            _reject(
                "projection evidence matrix requires the canonical seven line keys",
                EvidenceMatrixLineSetError,
                code="evidence_line_set_invalid",
            )
        if any(not isinstance(row, BusinessLineEvidenceRecord) for row in rows):
            _reject(
                "BusinessLineEvidenceMatrix.rows must be typed evidence records",
                EvidenceMatrixSourceError,
                code="evidence_source_invalid",
            )
        row_keys = tuple(row.line_key for row in rows)
        if row_keys != expected_line_keys:
            _reject(
                "projection evidence matrix rows are not unique canonical ordered lines",
                EvidenceMatrixLineSetError,
                code="evidence_line_set_invalid",
            )
        for row in rows:
            expected_worker = row.line_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
            if row.requires_worker_readback != expected_worker:
                _reject(
                    f"worker requirement mismatch for line {row.line_key!r}",
                    EvidenceMatrixLineSetError,
                    code="evidence_line_set_invalid",
                )
            row.verify_digest()
        if not isinstance(self.summary, EvidenceMatrixSummary):
            _reject("BusinessLineEvidenceMatrix.summary must be typed", TypeError, code="projection_input_invalid")
        if not isinstance(self.authority, EvidenceMatrixAuthority):
            _reject("BusinessLineEvidenceMatrix.authority must be typed", TypeError, code="authority_contract_invalid")
        if not isinstance(self.completion_claim, bool):
            _reject(
                "BusinessLineEvidenceMatrix.completion_claim must be bool", TypeError, code="projection_input_invalid"
            )
        if self.completion_claim:
            _reject("projection evidence matrix never claims real completion", code="authority_contract_invalid")
        source_status = _coerce_row_status(self.source_status)
        object.__setattr__(self, "source_status", source_status)
        passed = sum(row.status is EvidenceRowStatus.PASSED for row in rows)
        blocked = sum(row.status is EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT for row in rows)
        failed = sum(row.status is EvidenceRowStatus.FAILED for row in rows)
        if (
            self.summary.total != len(rows)
            or self.summary.passed != passed
            or self.summary.blocked != blocked
            or self.summary.failed != failed
        ):
            _reject(
                "projection evidence matrix summary does not match its rows",
                EvidenceMatrixIntegrityError,
                code="evidence_integrity_invalid",
            )
        if passed == len(rows):
            aggregate = EvidenceRowStatus.PASSED
        elif failed:
            aggregate = EvidenceRowStatus.FAILED
        elif blocked:
            aggregate = EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
        else:
            aggregate = EvidenceRowStatus.FAILED
        if source_status is not aggregate:
            _reject(
                "projection evidence matrix source_status does not match row statuses",
                EvidenceMatrixIntegrityError,
                code="evidence_integrity_invalid",
            )
        provided = str(self.matrix_digest or "").strip()
        expected = _matrix_digest(self)
        if not provided:
            object.__setattr__(self, "matrix_digest", expected)
        else:
            _require_digest_hex(provided, "BusinessLineEvidenceMatrix.matrix_digest")
            if provided != expected:
                _reject(
                    "BusinessLineEvidenceMatrix.matrix_digest does not match content",
                    EvidenceMatrixIntegrityError,
                    code="evidence_integrity_invalid",
                )

    def verify_digest(self) -> None:
        """Fail closed when rows or matrix content were mutated in place."""

        for row in self.rows:
            row.verify_digest()
        expected = _matrix_digest(self)
        if self.matrix_digest != expected:
            _reject(
                "BusinessLineEvidenceMatrix.matrix_digest does not match content",
                EvidenceMatrixIntegrityError,
                code="evidence_integrity_invalid",
            )

    def to_plain(self) -> dict[str, Any]:
        return {
            "expected_line_keys": list(self.expected_line_keys),
            "rows": [row.to_plain() for row in self.rows],
            "summary": self.summary.to_plain(),
            "source_status": self.source_status.value,
            "observed_at": self.observed_at,
            "matrix_digest": self.matrix_digest,
            "authority": self.authority.to_plain(),
            "completion_claim": self.completion_claim,
        }


def _canonicalize_row(record: BusinessLineEvidenceRecord) -> BusinessLineEvidenceRecord:
    """Reclassify undecidable/source-less pass claims fail closed."""

    if record.status is not EvidenceRowStatus.PASSED:
        return record
    status = record.status
    reason_code = record.reason_code
    if record.requires_worker_readback and not record.persistence_decidable:
        status = EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
        reason_code = f"{reason_code}:worker_terminal_readback_not_decidable"
    elif not record.source_refs:
        status = EvidenceRowStatus.FAILED
        reason_code = f"{reason_code}:missing_source_evidence"
    if status is record.status and reason_code == record.reason_code:
        return record
    return BusinessLineEvidenceRecord(
        line_key=record.line_key,
        status=status,
        reason_code=reason_code,
        requires_worker_readback=record.requires_worker_readback,
        persistence_decidable=record.persistence_decidable,
        source_refs=record.source_refs,
        observed_at=record.observed_at,
    )


def project_business_line_evidence_matrix(
    records: Any,
) -> BusinessLineEvidenceMatrix:
    """Project exactly seven typed records into one canonical evidence matrix.

    The projection is pure and read-only.  Line-set drift returns through the
    :class:`EvidenceMatrixLineSetError` compatibility boundary; non-typed rows
    use :class:`EvidenceMatrixSourceError`; stale row digests use
    :class:`EvidenceMatrixIntegrityError`.
    """

    typed = tuple(records)
    by_key: dict[str, BusinessLineEvidenceRecord] = {}
    duplicate_keys: list[str] = []
    unexpected_keys: list[str] = []
    for record in typed:
        if not isinstance(record, BusinessLineEvidenceRecord):
            _reject(
                "projection evidence matrix requires typed evidence records",
                EvidenceMatrixSourceError,
                code="projection_input_invalid",
            )
        key = normalize_evidence_line_key(record.line_key)
        if key not in BUSINESS_LINE_KEYS:
            unexpected_keys.append(record.line_key)
            continue
        if key in by_key:
            duplicate_keys.append(key)
            continue
        by_key[key] = record

    missing_keys = [key for key in BUSINESS_LINE_KEYS if key not in by_key]
    if missing_keys or duplicate_keys or unexpected_keys:
        _reject(
            "projection evidence matrix line set is not exactly canonical: "
            f"missing={sorted(missing_keys)} "
            f"duplicate={sorted(set(duplicate_keys))} "
            f"unexpected={sorted(str(item) for item in unexpected_keys)}",
            EvidenceMatrixLineSetError,
            code="evidence_line_set_invalid",
        )

    for key in BUSINESS_LINE_KEYS:
        record = by_key[key]
        expected_worker = key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
        if record.requires_worker_readback != expected_worker:
            _reject(
                f"worker requirement mismatch for line {key!r}",
                EvidenceMatrixLineSetError,
                code="evidence_line_set_invalid",
            )
    for key in BUSINESS_LINE_KEYS:
        by_key[key].verify_digest()

    rows = tuple(_canonicalize_row(by_key[key]) for key in BUSINESS_LINE_KEYS)
    passed = sum(row.status is EvidenceRowStatus.PASSED for row in rows)
    blocked = sum(row.status is EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT for row in rows)
    failed = sum(row.status is EvidenceRowStatus.FAILED for row in rows)
    if failed:
        source_status = EvidenceRowStatus.FAILED
    elif blocked:
        source_status = EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
    elif passed == len(rows):
        source_status = EvidenceRowStatus.PASSED
    else:
        source_status = EvidenceRowStatus.FAILED
    observed_at = max(row.observed_at for row in rows)
    return BusinessLineEvidenceMatrix(
        expected_line_keys=BUSINESS_LINE_KEYS,
        rows=rows,
        summary=EvidenceMatrixSummary(
            total=len(rows),
            passed=passed,
            blocked=blocked,
            failed=failed,
        ),
        source_status=source_status,
        observed_at=observed_at,
        authority=EvidenceMatrixAuthority(),
        completion_claim=False,
    )
