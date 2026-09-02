"""Typed successor port for the strict single-source execution guard.

The legacy donor ``services/source_library/single_source_guard.py`` validates a
merged source-library override before provider/crawler dispatch: the guard must
declare exactly one allowed URL, ``strict_source`` and ``guarantee`` must be
true, no blocked reason may be present, and the declared site-entry set must
equal the allowed URL.  This successor port re-expresses the same decision as a
typed execution-boundary guard:

- admitted: the declaration is well formed and the raw claimed source set
  contains the single allowed URL exactly once and nothing else.  An execution
  fact is emitted for readback;
- rejected: the declaration is absent, malformed, blocked, or conflicts with
  the claimed source set.  Dispatch must stay blocked and no fact is emitted;
- fail-closed: unknown source claims, duplicate claims, empty claims and any
  URL-bearing sibling override are rejected unless they equal the single
  allowed URL.

Authority stays false on every outcome.  This module only gates dispatch; it
grants no provider, network, credential, canonical-write or live authority and
performs no effect.  A caller that maps an admitted decision to dispatch must
pass its own explicit successor authority gate.

The module is intentionally self-contained: no legacy donor code is imported
or copied verbatim, and only the successor checksum helper is used.  No schema,
compiler, runtime-kernel or registry registration is performed here; shared
registration is a main-thread integration contract.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from app.successor_runtime.capabilities.checksum import sha256_hex

SINGLE_SOURCE_GUARD_DECISION_SCHEMA = (
    "mrw.successor.source-library.single-source-guard.decision.v1"
)
SINGLE_SOURCE_GUARD_FACT_SCHEMA = (
    "mrw.successor.source-library.single-source-guard.execution-fact.v1"
)
SOURCE_LIBRARY_EXECUTION_FACT_CONTRACT = "source_library.execution_fact.v1"
SITE_ENTRY_GUARD_CONTRACT = "resource_pool.site_entry.single_source_guard.v1"

GUARD_OUTCOME_ADMITTED: Literal["admitted"] = "admitted"
GUARD_OUTCOME_REJECTED: Literal["rejected"] = "rejected"
GuardOutcome = Literal["admitted", "rejected"]

GUARD_PASSED_REASON = "single_source_guard_passed"
GUARD_MISSING_CODE = "single_source_guard_missing"
GUARD_INVALID_SHAPE_CODE = "single_source_guard_invalid_shape"
GUARD_STRICT_SOURCE_REQUIRED_CODE = "single_source_guard_strict_source_required"
GUARD_BLOCKED_CODE = "single_source_guard_blocked"
GUARD_ALLOWED_URLS_INVALID_CODE = "single_source_guard_allowed_urls_invalid"
GUARD_SITE_ENTRIES_MISMATCH_CODE = "single_source_guard_site_entries_mismatch"
GUARD_AUTHORITY_FALSE_REASON = "single-source guard grants no execution authority"

_MAX_STRING_BYTES = 4096
_MAX_SOURCE_REF_STRING_BYTES = 1024
_CREDENTIAL_MARKERS = ("secret", "api_key", "apikey", "token", "password")


def _require_trimmed(value: Any, name: str, *, max_bytes: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} must not be blank")
    if len(trimmed.encode("utf-8")) > max_bytes:
        raise ValueError(f"{name} exceeds the {max_bytes}-byte ceiling")
    return trimmed


def _plain_json(value: Any) -> Any:
    """Recursively copy a JSON-compatible value into plain containers."""

    if isinstance(value, dict):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    raise TypeError("source metadata must be JSON-compatible")


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith("credential:/"):
        return False
    return any(marker in lowered for marker in _CREDENTIAL_MARKERS)


def _scan_json(value: Any, name: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan_json(item, f"{name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_json(item, f"{name}[{index}]")
    elif isinstance(value, str):
        _require_trimmed(value, name, max_bytes=_MAX_SOURCE_REF_STRING_BYTES)
        if _looks_like_secret(value):
            raise ValueError(f"{name} must not carry credential-like raw material")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def _validate_json_object(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a plain JSON object")
    plain = _plain_json(value)
    _scan_json(plain, name)
    return plain


def _string_claims(value: Any, name: str) -> tuple[str, ...]:
    """Normalize one URL-bearing override field, preserving duplicates/order."""

    if value is None:
        return ()
    if isinstance(value, (str, bytes, dict)) or not isinstance(value, Iterable):
        raise TypeError(f"{name} must be a list of URL strings")
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise TypeError(f"{name} must contain only URL strings")
        url = _require_trimmed(entry, name, max_bytes=_MAX_STRING_BYTES)
        out.append(url)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class SourceDispatchClaims:
    """URL-bearing claims selected for one source-library dispatch.

    ``site_entries`` is the donor-parity field checked against the guard.
    The other fields are declared only when they select dispatch URLs; the
    port treats them as conflicts when they add any URL outside the single
    allowed source.
    """

    site_entries: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    site_entry_urls: tuple[str, ...] = ()
    official_access_site_entries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "site_entries",
            "urls",
            "site_entry_urls",
            "official_access_site_entries",
        ):
            object.__setattr__(
                self,
                name,
                _string_claims(getattr(self, name), f"SourceDispatchClaims.{name}"),
            )

    @classmethod
    def from_plain(cls, value: dict[str, Any]) -> SourceDispatchClaims:
        if not isinstance(value, dict):
            raise TypeError("dispatch claims must be an object")
        return cls(
            site_entries=_string_claims(
                value.get("site_entries"), "SourceDispatchClaims.site_entries"
            ),
            urls=_string_claims(value.get("urls"), "SourceDispatchClaims.urls"),
            site_entry_urls=_string_claims(
                value.get("site_entry_urls"), "SourceDispatchClaims.site_entry_urls"
            ),
            official_access_site_entries=_string_claims(
                value.get("official_access_site_entries"),
                "SourceDispatchClaims.official_access_site_entries",
            ),
        )

    def exact_claims(self) -> tuple[str, ...]:
        return (
            self.site_entries
            + self.urls
            + self.site_entry_urls
            + self.official_access_site_entries
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "site_entries": list(self.site_entries),
            "urls": list(self.urls),
            "site_entry_urls": list(self.site_entry_urls),
            "official_access_site_entries": list(self.official_access_site_entries),
        }


@dataclass(frozen=True, slots=True)
class SingleSourceGuardDeclaration:
    """Strict single-source declaration carried by an override payload."""

    allowed_urls: tuple[str, ...]
    allowed_count: int
    strict_source: bool
    guarantee: bool
    blocked_reason: str | None
    contract_version: str
    reason_code: str | None = None
    status: str | None = None
    source_ref: dict[str, Any] = field(default_factory=dict)
    report_source_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_urls",
            _string_claims(
                self.allowed_urls, "SingleSourceGuardDeclaration.allowed_urls"
            ),
        )
        if self.allowed_count is not None and (
            not isinstance(self.allowed_count, int)
            or isinstance(self.allowed_count, bool)
            or self.allowed_count < 0
        ):
            raise ValueError("allowed_count must be a non-negative integer or None")
        if self.blocked_reason is not None:
            if not isinstance(self.blocked_reason, str):
                raise TypeError("blocked_reason must be a string or None")
            blocked = self.blocked_reason.strip()
            object.__setattr__(self, "blocked_reason", blocked or None)
        if self.reason_code is not None:
            if not isinstance(self.reason_code, str):
                raise TypeError("reason_code must be a string or None")
            reason = self.reason_code.strip()
            object.__setattr__(self, "reason_code", reason or None)
        if self.status is not None:
            if not isinstance(self.status, str):
                raise TypeError("status must be a string or None")
            status = self.status.strip()
            object.__setattr__(self, "status", status or None)
        if (
            not isinstance(self.contract_version, str)
            or not self.contract_version.strip()
        ):
            raise ValueError("contract_version is required")
        if not isinstance(self.report_source_ref, str):
            raise TypeError("report_source_ref must be a string")
        if (
            self.report_source_ref.strip()
            and self.report_source_ref != self.report_source_ref.strip()
        ):
            raise ValueError("report_source_ref must be trimmed")
        object.__setattr__(
            self,
            "source_ref",
            _validate_json_object(self.source_ref, "source_ref"),
        )

    def to_plain(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "contract_version": self.contract_version,
            "strict_source": self.strict_source,
            "guarantee": self.guarantee,
            "allowed_urls": list(self.allowed_urls),
            "allowed_count": self.allowed_count,
            "blocked_reason": self.blocked_reason,
            "reason_code": self.reason_code,
            "source_ref": self.source_ref,
            "report_source_ref": self.report_source_ref,
        }
        if self.status is not None:
            out["status"] = self.status
        return out

    @classmethod
    def from_dict(cls, value: Any) -> SingleSourceGuardDeclaration:
        if value is None:
            raise TypeError("single_source_guard is required")
        if not isinstance(value, dict):
            raise TypeError("single_source_guard must be an object")
        return cls(
            contract_version=str(
                value.get("contract_version") or SITE_ENTRY_GUARD_CONTRACT
            ),
            allowed_urls=_string_claims(
                value.get("allowed_urls"), "single_source_guard.allowed_urls"
            ),
            allowed_count=value.get("allowed_count"),
            strict_source=value.get("strict_source"),
            guarantee=value.get("guarantee"),
            blocked_reason=value.get("blocked_reason"),
            reason_code=value.get("reason_code"),
            status=value.get("status"),
            source_ref=value.get("source_ref"),
            report_source_ref=value.get("report_source_ref"),
        )


@dataclass(frozen=True, slots=True)
class SingleSourceExecutionFact:
    """Readback-shaped execution fact emitted only after guard admission."""

    contract_version: str = SOURCE_LIBRARY_EXECUTION_FACT_CONTRACT
    reason_code: str = GUARD_PASSED_REASON
    item_key: str = ""
    project_key: str = ""
    guard_status: Literal["passed"] = "passed"
    guard_reason_code: str | None = None
    source_refs: tuple[dict[str, Any], ...] = ()
    source_ref: dict[str, Any] = field(default_factory=dict)
    report_source_ref: str = ""
    single_source_guard: SingleSourceGuardDeclaration | None = None
    schema_version: str = SINGLE_SOURCE_GUARD_FACT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SINGLE_SOURCE_GUARD_FACT_SCHEMA:
            raise ValueError("SingleSourceExecutionFact.schema_version is not frozen")
        if self.contract_version != SOURCE_LIBRARY_EXECUTION_FACT_CONTRACT:
            raise ValueError("SingleSourceExecutionFact.contract_version is not frozen")
        if self.reason_code != GUARD_PASSED_REASON:
            raise ValueError("SingleSourceExecutionFact.reason_code must be passed")
        if self.guard_status != "passed":
            raise ValueError("SingleSourceExecutionFact.guard_status must be passed")
        for name in ("item_key", "project_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or value != value.strip():
                raise ValueError(f"SingleSourceExecutionFact.{name} must be trimmed")
        if not isinstance(self.report_source_ref, str):
            raise TypeError("report_source_ref must be a string")
        if not isinstance(self.source_refs, tuple):
            object.__setattr__(self, "source_refs", tuple(self.source_refs))
        if not all(isinstance(ref, dict) for ref in self.source_refs):
            raise TypeError("source_refs must contain JSON objects")
        for index, ref in enumerate(self.source_refs):
            _validate_json_object(ref, f"source_refs[{index}]")
        object.__setattr__(
            self,
            "source_ref",
            _validate_json_object(self.source_ref, "source_ref"),
        )

    def digest(self) -> str:
        return sha256_hex(
            json.dumps(
                self.to_plain(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "reason_code": self.reason_code,
            "item_key": self.item_key,
            "project_key": self.project_key,
            "guard_status": self.guard_status,
            "guard_reason_code": self.guard_reason_code,
            "source_refs": [dict(ref) for ref in self.source_refs],
            "source_ref": dict(self.source_ref),
            "report_source_ref": self.report_source_ref,
            "single_source_guard": (
                self.single_source_guard.to_plain()
                if self.single_source_guard is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class GuardAuthoritySnapshot:
    """Authority boundary carried by every guard outcome.

    Always false by construction.  Admitted means admission completed, not that
    dispatch authority was granted.
    """

    granted: bool = False
    live_provider_allowed: bool = False
    reason: str = GUARD_AUTHORITY_FALSE_REASON

    def __post_init__(self) -> None:
        if self.granted is not False:
            raise ValueError("single-source guard port cannot grant authority")
        if self.live_provider_allowed is not False:
            raise ValueError(
                "single-source guard port cannot allow live provider execution"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("GuardAuthoritySnapshot.reason is required")

    def to_plain(self) -> dict[str, Any]:
        return {
            "granted": self.granted,
            "live_provider_allowed": self.live_provider_allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class GuardRejectionDetails:
    """Structured reason preserving the donor rejection vocabulary."""

    reason_code: str
    field: str
    expected: dict[str, Any]
    actual: dict[str, Any]

    def to_plain(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "field": self.field,
            "expected": dict(self.expected),
            "actual": dict(self.actual),
        }


@dataclass(frozen=True, slots=True)
class GuardRejected:
    """Fail-closed decision: this dispatch must not proceed."""

    outcome: Literal["rejected"] = GUARD_OUTCOME_REJECTED
    reason_code: str = GUARD_MISSING_CODE
    details: GuardRejectionDetails | None = None
    guard: SingleSourceGuardDeclaration | None = None
    dispatch_allowed: bool = False
    authority: GuardAuthoritySnapshot = field(default_factory=GuardAuthoritySnapshot)
    schema_version: str = SINGLE_SOURCE_GUARD_DECISION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SINGLE_SOURCE_GUARD_DECISION_SCHEMA:
            raise ValueError("GuardRejected.schema_version is not the frozen schema")
        if self.dispatch_allowed is not False:
            raise ValueError("GuardRejected.dispatch_allowed must be false")
        if not isinstance(self.reason_code, str) or not self.reason_code:
            raise ValueError("GuardRejected.reason_code is required")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "details": self.details.to_plain() if self.details is not None else None,
            "guard": self.guard.to_plain() if self.guard is not None else None,
            "dispatch_allowed": self.dispatch_allowed,
            "authority": self.authority.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class GuardAdmitted:
    """Admission decision carrying the emitted execution fact."""

    outcome: Literal["admitted"] = GUARD_OUTCOME_ADMITTED
    guard: SingleSourceGuardDeclaration | None = None
    dispatch_allowed: bool = True
    authority: GuardAuthoritySnapshot = field(default_factory=GuardAuthoritySnapshot)
    execution_fact: SingleSourceExecutionFact | None = None
    schema_version: str = SINGLE_SOURCE_GUARD_DECISION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SINGLE_SOURCE_GUARD_DECISION_SCHEMA:
            raise ValueError("GuardAdmitted.schema_version is not the frozen schema")
        if self.dispatch_allowed is not True:
            raise ValueError("GuardAdmitted.dispatch_allowed must be true")
        if not isinstance(self.guard, SingleSourceGuardDeclaration):
            raise TypeError("GuardAdmitted.guard is required")
        if not isinstance(self.execution_fact, SingleSourceExecutionFact):
            raise TypeError("GuardAdmitted.execution_fact is required")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "guard": self.guard.to_plain() if self.guard is not None else None,
            "dispatch_allowed": self.dispatch_allowed,
            "authority": self.authority.to_plain(),
            "execution_fact": (
                self.execution_fact.to_plain()
                if self.execution_fact is not None
                else None
            ),
        }


GuardDecision = GuardAdmitted | GuardRejected


def build_guard_execution_fact(
    guard: SingleSourceGuardDeclaration,
    *,
    item_key: str = "",
    project_key: str = "",
    reason_code: str = GUARD_PASSED_REASON,
) -> SingleSourceExecutionFact:
    """Build the donor-shaped execution fact for an admitted guard."""

    return SingleSourceExecutionFact(
        contract_version=SOURCE_LIBRARY_EXECUTION_FACT_CONTRACT,
        reason_code=reason_code,
        item_key=str(item_key or "").strip(),
        project_key=str(project_key or "").strip(),
        guard_status="passed",
        guard_reason_code=guard.reason_code or guard.blocked_reason,
        source_refs=(
            {
                "kind": "resource_pool.site_entry",
                "report_source_ref": guard.report_source_ref,
                "site_entry_url": guard.allowed_urls[0],
                "source_ref": dict(guard.source_ref),
            },
        ),
        source_ref=dict(guard.source_ref),
        report_source_ref=guard.report_source_ref,
        single_source_guard=guard,
    )


def _rejected(
    *,
    reason_code: str,
    details: GuardRejectionDetails,
    guard: SingleSourceGuardDeclaration | None = None,
) -> GuardRejected:
    return GuardRejected(
        reason_code=reason_code,
        details=details,
        guard=guard,
        dispatch_allowed=False,
        authority=GuardAuthoritySnapshot(),
    )


def evaluate_guard_declaration(
    declaration: SingleSourceGuardDeclaration,
    claims: SourceDispatchClaims,
) -> GuardDecision:
    """Evaluate one typed declaration against the dispatch source claims."""

    if declaration.strict_source is not True:
        return _rejected(
            reason_code=GUARD_STRICT_SOURCE_REQUIRED_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_STRICT_SOURCE_REQUIRED_CODE,
                field="override_params.single_source_guard",
                expected={"strict_source": True},
                actual={"strict_source": declaration.strict_source},
            ),
            guard=declaration,
        )
    if declaration.guarantee is not True or declaration.blocked_reason is not None:
        return _rejected(
            reason_code=GUARD_BLOCKED_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_BLOCKED_CODE,
                field="override_params.single_source_guard",
                expected={"guarantee": True, "blocked_reason": None},
                actual={
                    "guarantee": declaration.guarantee,
                    "blocked_reason": declaration.blocked_reason,
                },
            ),
            guard=declaration,
        )
    if len(declaration.allowed_urls) != 1 or declaration.allowed_count != 1:
        return _rejected(
            reason_code=GUARD_ALLOWED_URLS_INVALID_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_ALLOWED_URLS_INVALID_CODE,
                field="override_params.single_source_guard",
                expected={"allowed_count": 1, "allowed_urls_length": 1},
                actual={
                    "allowed_count": declaration.allowed_count,
                    "allowed_urls": list(declaration.allowed_urls),
                    "allowed_urls_length": len(declaration.allowed_urls),
                },
            ),
            guard=declaration,
        )
    claimed = claims.exact_claims()
    if not claimed or claimed != declaration.allowed_urls:
        return _rejected(
            reason_code=GUARD_SITE_ENTRIES_MISMATCH_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_SITE_ENTRIES_MISMATCH_CODE,
                field="override_params.single_source_guard",
                expected={"site_entries": list(declaration.allowed_urls)},
                actual={
                    "site_entries": list(claims.site_entries),
                    "claims": list(claimed),
                },
            ),
            guard=declaration,
        )
    return GuardAdmitted(
        guard=declaration,
        dispatch_allowed=True,
        authority=GuardAuthoritySnapshot(),
        execution_fact=build_guard_execution_fact(declaration),
    )


def guard_override_decision(
    override_params: dict[str, Any] | None,
    *,
    item_key: str = "",
    project_key: str = "",
    declared_sources: SourceDispatchClaims | None = None,
) -> GuardDecision:
    """Evaluate a raw override payload through the guard boundary.

    Mirrors the donor entrypoint ordering: guard shape/count failures take
    precedence over site-entry mismatch, and only an admitted guard emits an
    execution fact.  Rejected decisions never dispatch.
    """

    if override_params is None:
        return GuardRejected(
            reason_code=GUARD_MISSING_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_MISSING_CODE,
                field="override_params.single_source_guard",
                expected={"single_source_guard": "object"},
                actual={"single_source_guard": "absent"},
            ),
        )
    if not isinstance(override_params, dict):
        return GuardRejected(
            reason_code=GUARD_MISSING_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_MISSING_CODE,
                field="override_params",
                expected={"override_params": "object"},
                actual={"override_params": type(override_params).__name__},
            ),
        )
    if "single_source_guard" not in override_params:
        return GuardRejected(
            reason_code=GUARD_MISSING_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_MISSING_CODE,
                field="override_params.single_source_guard",
                expected={"single_source_guard": "object"},
                actual={"single_source_guard": "absent"},
            ),
        )
    try:
        declaration = SingleSourceGuardDeclaration.from_dict(
            override_params.get("single_source_guard")
        )
    except (TypeError, ValueError) as exc:
        return GuardRejected(
            reason_code=GUARD_INVALID_SHAPE_CODE,
            details=GuardRejectionDetails(
                reason_code=GUARD_INVALID_SHAPE_CODE,
                field="override_params.single_source_guard",
                expected={"single_source_guard": "object"},
                actual={"error": str(exc)},
            ),
        )
    claims = declared_sources or SourceDispatchClaims.from_plain(override_params)
    decision = evaluate_guard_declaration(declaration, claims)
    if isinstance(decision, GuardAdmitted):
        return GuardAdmitted(
            guard=decision.guard,
            dispatch_allowed=True,
            authority=decision.authority,
            execution_fact=build_guard_execution_fact(
                declaration,
                item_key=item_key,
                project_key=project_key,
            ),
        )
    return decision


@runtime_checkable
class SingleSourceGuardPort(Protocol):
    """Execution-boundary port: admit or reject before provider dispatch."""

    def evaluate(
        self,
        request: dict[str, Any],
        *,
        declared_sources: SourceDispatchClaims | None = None,
    ) -> GuardDecision: ...


class DefaultSingleSourceGuardPort:
    """Deterministic pure port implementation for the guard boundary."""

    def evaluate(
        self,
        request: dict[str, Any],
        *,
        declared_sources: SourceDispatchClaims | None = None,
    ) -> GuardDecision:
        if not isinstance(request, dict):
            return GuardRejected(
                reason_code=GUARD_MISSING_CODE,
                details=GuardRejectionDetails(
                    reason_code=GUARD_MISSING_CODE,
                    field="request",
                    expected={"request": "object"},
                    actual={"request": type(request).__name__},
                ),
            )
        return guard_override_decision(
            request.get("override_params"),
            item_key=str(request.get("item_key") or "").strip(),
            project_key=str(request.get("project_key") or "").strip(),
            declared_sources=declared_sources,
        )


class SourceLibrarySingleSourceGuardError(ValueError):
    """Typed rejection for callers that map rejection to an exception."""

    def __init__(
        self,
        message: str,
        *,
        details: GuardRejectionDetails,
    ) -> None:
        super().__init__(message)
        self.details = details


def validate_single_source_guard(
    declaration: SingleSourceGuardDeclaration | None,
    claims: SourceDispatchClaims | None = None,
) -> SingleSourceGuardDeclaration | None:
    """Validate a typed declaration, raising on rejection.

    ``None`` means no guard override was declared and is valid only for call
    sites that do not require a single-source guard.  A rejected declaration
    raises the donor-shaped error so dispatch boundaries stay fail-closed.
    """

    if declaration is None:
        return None
    decision = evaluate_guard_declaration(
        declaration,
        claims or SourceDispatchClaims(),
    )
    if isinstance(decision, GuardRejected):
        details = decision.details or GuardRejectionDetails(
            reason_code=decision.reason_code,
            field="override_params.single_source_guard",
            expected={},
            actual={},
        )
        raise SourceLibrarySingleSourceGuardError(
            f"single_source_guard is blocked: {details.reason_code}",
            details=details,
        )
    return declaration


__all__ = [
    "GUARD_ALLOWED_URLS_INVALID_CODE",
    "GUARD_BLOCKED_CODE",
    "GUARD_INVALID_SHAPE_CODE",
    "GUARD_MISSING_CODE",
    "GUARD_OUTCOME_ADMITTED",
    "GUARD_OUTCOME_REJECTED",
    "GUARD_PASSED_REASON",
    "GUARD_SITE_ENTRIES_MISMATCH_CODE",
    "GUARD_STRICT_SOURCE_REQUIRED_CODE",
    "SINGLE_SOURCE_GUARD_DECISION_SCHEMA",
    "SINGLE_SOURCE_GUARD_FACT_SCHEMA",
    "SITE_ENTRY_GUARD_CONTRACT",
    "SOURCE_LIBRARY_EXECUTION_FACT_CONTRACT",
    "DefaultSingleSourceGuardPort",
    "GuardAdmitted",
    "GuardAuthoritySnapshot",
    "GuardDecision",
    "GuardOutcome",
    "GuardRejected",
    "GuardRejectionDetails",
    "SingleSourceExecutionFact",
    "SingleSourceGuardDeclaration",
    "SingleSourceGuardPort",
    "SourceDispatchClaims",
    "SourceLibrarySingleSourceGuardError",
    "build_guard_execution_fact",
    "evaluate_guard_declaration",
    "guard_override_decision",
    "validate_single_source_guard",
]
