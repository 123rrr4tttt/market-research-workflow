"""C8.3 successor report-export one-time token-state contract.

Movement binding: ALL-SM-009 | C8.3 report delivery cluster.  This module is
a self-contained successor contract for claim/revoke/readback/prune token
state.  It contains no DB or SQL and never imports donor services or models.
Only digest and metadata fields exist on state records: raw token secrets,
full signed ``artifact_token`` values, credentials or live authority flags are
rejected before they can reach a record, readback or observable output.

The successor deliberately differs from the donor in one recovery way:
when the backend is unavailable no process-memory fallback claim is made.
``degraded`` is only an observational marker; a degraded result can never be
reported as a durable claim.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Final, NoReturn, Protocol, runtime_checkable

from functorial_kit import Failure
from mrw_functorial_kit.core.knowledge_semantics import (
    knowledge_report_export_token_state_failures,
)

__all__ = [
    "REPORT_EXPORT_TOKEN_STATE_AUTHORITY_SCHEMA",
    "REPORT_EXPORT_TOKEN_STATE_RECORD_SCHEMA",
    "REPORT_EXPORT_TOKEN_STATE_SCHEMA",
    "SUCCESSOR_REPORT_EXPORT_TOKEN_STATES_TABLE",
    "ClaimExportTokenCommand",
    "LocalSuccessorReportExportTokenStore",
    "PruneExportTokenStatesCommand",
    "ReadbackExportTokenCommand",
    "ReportExportTokenStateAuthority",
    "ReportExportTokenStateRecord",
    "ReportExportTokenStateStore",
    "ReportExportTokenStateValue",
    "RevokeExportTokenCommand",
    "TokenClaimRecord",
    "TokenPruneRecord",
    "TokenReadbackRecord",
    "TokenRevokeRecord",
    "TokenStateBackendUnavailableError",
    "TokenStateConflictError",
    "TokenStateCredentialError",
    "TokenStateError",
    "TokenStateNotFoundError",
    "claim_report_export_token_once",
    "prune_report_export_token_states",
    "readback_report_export_token",
    "revoke_report_export_token",
]

_TOKEN_STATE_OWNER = "knowledge.report.export-token-state.v2"
_TOKEN_STATE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"
_TOKEN_STATE_CONTEXT_KEYS = frozenset(
    {
        "owner",
        "effect_boundary",
        "boundary_class",
        "failure_family",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _failure(
    code: str,
    message: str,
    *,
    site: str,
    public_exception: str,
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> Failure:
    """Create the closed C8 token-state failure value before ABI lifting."""

    return knowledge_report_export_token_state_failures.fail(
        code,
        message,
        {
            "owner": _TOKEN_STATE_OWNER,
            "effect_boundary": "knowledge.report.export_token_state.contract_core",
            "boundary_class": boundary_class,
            "failure_family": knowledge_report_export_token_state_failures.name,
            "public_exception": public_exception,
            "public_message": message,
            "site": site,
            "witness": _TOKEN_STATE_WITNESS,
            **details,
        },
    )


def _raise_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    """Lift a complete typed failure at the retained public ABI boundary."""

    context = failure.context or {}
    if (
        failure.family != knowledge_report_export_token_state_failures.name
        or _TOKEN_STATE_CONTEXT_KEYS - set(context)
        or context.get("failure_family")
        != knowledge_report_export_token_state_failures.name
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=c8_report_export_token_state.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("token-state failure lift context is incomplete or inconsistent")
    # kit:boundary owner=c8_report_export_token_state.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=knowledge.report.export-token-state.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context["public_message"]))


def _raise_effect_failure(
    failure: Failure,
    exception_type: type[Exception] | None = None,
) -> NoReturn:
    """Lift backend/provider failure while retaining effect-boundary semantics."""

    exception_type = exception_type or TokenStateBackendUnavailableError
    context = failure.context or {}
    if (
        failure.family != knowledge_report_export_token_state_failures.name
        or context.get("boundary_class") != "SHELL_BOUNDARY_EXCEPTION"
        or context.get("failure_family")
        != knowledge_report_export_token_state_failures.name
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=c8_report_export_token_state.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("token-state effect lift context is incomplete or inconsistent")
    # kit:boundary owner=c8_report_export_token_state.py class=SHELL_BOUNDARY_EXCEPTION failure_family=knowledge.report.export-token-state.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context["public_message"]))

REPORT_EXPORT_TOKEN_STATE_SCHEMA: Final[str] = (
    "mrw.knowledge.report-export-token-state.v2"
)
REPORT_EXPORT_TOKEN_STATE_AUTHORITY_SCHEMA: Final[str] = (
    "mrw.knowledge.report-export-token-state.authority.v2"
)
REPORT_EXPORT_TOKEN_STATE_RECORD_SCHEMA: Final[str] = (
    "mrw.knowledge.report-export-token-state.record.v2"
)
SUCCESSOR_REPORT_EXPORT_TOKEN_STATES_TABLE: Final[str] = (
    "successor_report_export_token_states"
)

_SHA256_HEX = frozenset("0123456789abcdef")
_SENSITIVE_VALUE_SENTINELS: Final[tuple[str, ...]] = (
    "llmrpt-v1.",
    "mrw-successor-c8-report-export-local-v1",
)
_AUTHORITY_BOOL_FIELDS: Final[tuple[str, ...]] = (
    "live_provider",
    "canonical_write",
    "cutover",
    "external_delivery",
    "authority_transfer",
    "scheduler",
    "executor",
    "credential_read",
    "legacy_db_write",
)
_RECORD_SCHEMA_FIELD = "record_digest"


def _clean_text(value: Any, *, max_length: int = 128) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _require_text_failure(
    value: Any,
    *,
    name: str,
    max_length: int = 128,
) -> str | Failure:
    text = _clean_text(value, max_length=max_length)
    if text is None:
        return _failure(
            "input_contract_invalid",
            f"{name} is required",
            site=f"input/{name}",
            public_exception="ValueError",
        )
    return text


def _require_text(value: Any, *, name: str, max_length: int = 128) -> str:
    outcome = _require_text_failure(value, name=name, max_length=max_length)
    if isinstance(outcome, Failure):
        _raise_failure(outcome, ValueError)
    return outcome


def _require_sha256_hex(value: Any, *, name: str) -> str:
    digest = _require_text(value, name=name, max_length=64)
    if len(digest) != 64 or any(char not in _SHA256_HEX for char in digest):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                f"{name} must be a 64-char lowercase sha256 hex digest",
                site=f"digest/{name}",
                public_exception="ValueError",
            ),
            ValueError,
        )
    return digest


def _as_bool(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                f"{name} must be bool",
                site=f"input/{name}",
                public_exception="TypeError",
            ),
            TypeError,
        )
    return value


def _as_int_or_none(value: Any, *, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                f"{name} must be int or None",
                site=f"input/{name}",
                public_exception="TypeError",
            ),
            TypeError,
        )
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        _raise_failure(
            _failure(
                "input_contract_invalid",
                str(exc),
                site=f"input/{name}",
                public_exception=type(exc).__name__,
            ),
            type(exc),
        )


def _as_utc(value: datetime | None, *, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                f"{name} must be datetime",
                site=f"input/{name}",
                public_exception="TypeError",
            ),
            TypeError,
        )
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return _as_utc(value, name="datetime").isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _json_ready(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_digest(instance: Any) -> str:
    plain = dataclasses.asdict(instance)
    plain.pop(_RECORD_SCHEMA_FIELD, None)
    return _stable_digest(plain)


def _iter_string_values(value: Any) -> Any:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_string_values(item)


def _is_credential_like(value: str) -> bool:
    if not value:
        return False
    if any(value.startswith(sentinel) for sentinel in _SENSITIVE_VALUE_SENTINELS):
        return True
    parts = value.split(".")
    return len(parts) == 3 and parts[0] == "llmrpt-v1" and bool(parts[1] and parts[2])


def _guard_no_credentials(instance: Any) -> None:
    """Reject raw secret/token material anywhere on a typed value."""

    for candidate in fields(instance):
        value = getattr(instance, candidate.name)
        for text in _iter_string_values(value):
            if _is_credential_like(text):
                _raise_failure(
                    _failure(
                        "credential_rejected",
                        f"{type(instance).__name__} must not carry raw secret or "
                        "token material",
                        site=f"credentials/{type(instance).__name__}",
                        public_exception="TokenStateCredentialError",
                    ),
                    TokenStateCredentialError,
                )


def _all_authority_false(
    authority: ReportExportTokenStateAuthority,
) -> bool:
    return not any(getattr(authority, name) for name in _AUTHORITY_BOOL_FIELDS)


class ReportExportTokenStateValue(StrEnum):
    UNUSED = "unused"
    USED = "used"
    REVOKED = "revoked"
    USED_AND_REVOKED = "used_and_revoked"


class TokenStateError(RuntimeError):
    """Base fail-closed token-state error."""


class TokenStateConflictError(TokenStateError):
    """A token-state transition or result conflicts with durable semantics."""


class TokenStateNotFoundError(TokenStateError):
    """Required token state is absent or has already been pruned."""


class TokenStateCredentialError(TokenStateError):
    """Credential-like material was rejected before it reached state."""


class TokenStateBackendUnavailableError(TokenStateError):
    """The token-state backend is unavailable; no fallback claim is made."""


@dataclass(frozen=True, slots=True)
class ReportExportTokenStateAuthority:
    """All-false authority ceiling for token-state records and results."""

    schema_ref: str = REPORT_EXPORT_TOKEN_STATE_AUTHORITY_SCHEMA
    live_provider: bool = False
    canonical_write: bool = False
    cutover: bool = False
    external_delivery: bool = False
    authority_transfer: bool = False
    scheduler: bool = False
    executor: bool = False
    credential_read: bool = False
    legacy_db_write: bool = False

    def __post_init__(self) -> None:
        if not self.schema_ref or not isinstance(self.schema_ref, str):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "ReportExportTokenStateAuthority requires schema_ref",
                    site="authority/schema_ref",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        for name in _AUTHORITY_BOOL_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, bool):
                _raise_failure(
                    _failure(
                        "input_contract_invalid",
                        f"ReportExportTokenStateAuthority.{name} must be bool",
                        site=f"authority/{name}",
                        public_exception="TypeError",
                    ),
                    TypeError,
                )
            if value:
                _raise_failure(
                    _failure(
                        "conflict",
                        "report-export token state grants no runtime authority; "
                        f"{name} must be False",
                        site=f"authority/{name}",
                        public_exception="ValueError",
                    ),
                    ValueError,
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            **{name: getattr(self, name) for name in _AUTHORITY_BOOL_FIELDS},
        }


def _authority_for(
    authority: ReportExportTokenStateAuthority | None,
) -> ReportExportTokenStateAuthority:
    if authority is None:
        return ReportExportTokenStateAuthority()
    if not isinstance(authority, ReportExportTokenStateAuthority):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "token-state authority must be typed",
                site="authority/type",
                public_exception="TypeError",
            ),
            TypeError,
        )
    if not _all_authority_false(authority):
        _raise_failure(
            _failure(
                "conflict",
                "token-state records require an all-False authority ceiling",
                site="authority/ceiling",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    return authority


@dataclass(frozen=True, slots=True)
class ReportExportTokenStateRecord:
    """Digest-only durable token-state row value.

    The row stores only digests and metadata.  A raw actor, token secret or
    full signed artifact token can never be represented by this type.
    """

    artifact_id: str
    actor_digest: str
    project_key: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    job_id: int | None = None
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    last_seen_at: datetime | None = None
    payload_digest: str | None = None
    state: ReportExportTokenStateValue = ReportExportTokenStateValue.UNUSED
    record_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenStateAuthority = field(
        default_factory=ReportExportTokenStateAuthority
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        for name in ("project_key", "trace_id", "request_id", "revoke_reason"):
            object.__setattr__(
                self,
                name,
                _clean_text(getattr(self, name), max_length=128),
            )
        object.__setattr__(
            self,
            "job_id",
            _as_int_or_none(self.job_id, name="job_id"),
        )
        for name in ("used_at", "revoked_at", "last_seen_at"):
            object.__setattr__(
                self,
                name,
                _as_utc(getattr(self, name), name=name),
            )
        if self.payload_digest is not None:
            object.__setattr__(
                self,
                "payload_digest",
                _require_sha256_hex(self.payload_digest, name="payload_digest"),
            )
        object.__setattr__(
            self,
            "state",
            self._normalize_state(self.state),
        )
        object.__setattr__(
            self,
            "authority",
            _authority_for(self.authority),
        )
        _guard_no_credentials(self)
        object.__setattr__(self, "record_digest", _record_digest(self))

    @staticmethod
    def _normalize_state(value: Any) -> ReportExportTokenStateValue:
        if isinstance(value, ReportExportTokenStateValue):
            return value
        if isinstance(value, str):
            try:
                return ReportExportTokenStateValue(value)
            except ValueError as exc:
                _raise_failure(
                    _failure(
                        "input_contract_invalid",
                        f"unknown token state value: {value}",
                        site="state/value",
                        public_exception="ValueError",
                    ),
                    ValueError,
                )
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "state must be ReportExportTokenStateValue",
                site="state/type",
                public_exception="TypeError",
            ),
            TypeError,
        )


@dataclass(frozen=True, slots=True)
class ClaimExportTokenCommand:
    artifact_id: str
    actor_digest: str
    project_key: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    job_id: int | None = None
    payload_digest: str | None = None
    authority: ReportExportTokenStateAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        for name in ("project_key", "trace_id", "request_id"):
            object.__setattr__(
                self,
                name,
                _clean_text(getattr(self, name), max_length=128),
            )
        object.__setattr__(
            self,
            "job_id",
            _as_int_or_none(self.job_id, name="job_id"),
        )
        if self.payload_digest is not None:
            object.__setattr__(
                self,
                "payload_digest",
                _require_sha256_hex(self.payload_digest, name="payload_digest"),
            )
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)


@dataclass(frozen=True, slots=True)
class RevokeExportTokenCommand:
    artifact_id: str
    actor_digest: str
    reason: str
    authority: ReportExportTokenStateAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        reason = _clean_text(self.reason, max_length=256) or "manual_revoke"
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)


@dataclass(frozen=True, slots=True)
class ReadbackExportTokenCommand:
    artifact_id: str
    authority: ReportExportTokenStateAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)


@dataclass(frozen=True, slots=True)
class PruneExportTokenStatesCommand:
    retention_days: int
    dry_run: bool
    now: datetime
    authority: ReportExportTokenStateAuthority | None = None

    def __post_init__(self) -> None:
        if isinstance(self.retention_days, bool) or not isinstance(
            self.retention_days,
            int,
        ):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "retention_days must be int",
                    site="prune/retention_days",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        if self.retention_days < 1:
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "retention_days must be >= 1",
                    site="prune/retention_days",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        object.__setattr__(self, "dry_run", _as_bool(self.dry_run, name="dry_run"))
        now = _as_utc(self.now, name="now")
        if now is None:
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "prune now is required",
                    site="prune/now",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        object.__setattr__(self, "now", now)
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)


@dataclass(frozen=True, slots=True)
class TokenClaimRecord:
    """Typed result of one claim attempt against the token-state store."""

    artifact_id: str
    actor_digest: str
    claimed: bool
    already_used: bool
    revoked: bool
    degraded: bool
    claimed_at: datetime
    record_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenStateAuthority = field(
        default_factory=ReportExportTokenStateAuthority
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        for name in ("claimed", "already_used", "revoked", "degraded"):
            object.__setattr__(
                self,
                name,
                _as_bool(getattr(self, name), name=name),
            )
        claimed_at = _as_utc(self.claimed_at, name="claimed_at")
        if claimed_at is None:
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "claimed_at is required",
                    site="claim/claimed_at",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        object.__setattr__(self, "claimed_at", claimed_at)
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)
        object.__setattr__(self, "record_digest", _record_digest(self))


@dataclass(frozen=True, slots=True)
class TokenRevokeRecord:
    """Typed result of one revoke operation."""

    artifact_id: str
    actor_digest: str
    revoked: bool
    already_used: bool
    degraded: bool
    used_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None
    record_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenStateAuthority = field(
        default_factory=ReportExportTokenStateAuthority
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        object.__setattr__(
            self,
            "actor_digest",
            _require_text(self.actor_digest, name="actor_digest", max_length=128),
        )
        for name in ("revoked", "already_used", "degraded"):
            object.__setattr__(
                self,
                name,
                _as_bool(getattr(self, name), name=name),
            )
        object.__setattr__(self, "used_at", _as_utc(self.used_at, name="used_at"))
        object.__setattr__(
            self,
            "revoked_at",
            _as_utc(self.revoked_at, name="revoked_at"),
        )
        object.__setattr__(
            self,
            "revoke_reason",
            _clean_text(self.revoke_reason, max_length=256),
        )
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)
        object.__setattr__(self, "record_digest", _record_digest(self))


@dataclass(frozen=True, slots=True)
class TokenReadbackRecord:
    """Readback result including the successor crash-recovery observation.

    When a used/claimed row has no delivery receipt, the successor readback
    reports a ``plan_only`` recovery mode with ``outcome_unknown``.  The
    readback never suggests that a repeat binary export is permitted.
    """

    artifact_id: str
    actor_digest: str | None = None
    project_key: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    job_id: int | None = None
    payload_digest: str | None = None
    state: ReportExportTokenStateValue = ReportExportTokenStateValue.UNUSED
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    last_seen_at: datetime | None = None
    delivery_receipt_present: bool = False
    found: bool = True
    used: bool = field(init=False, default=False)
    claimed: bool = field(init=False, default=False)
    revoked: bool = field(init=False, default=False)
    delivery_receipt_absent: bool = field(init=False, default=False)
    recovery_mode: str = field(init=False, default="none")
    recovery_outcome: str = field(init=False, default="none")
    plan_only_recovery: bool = field(init=False, default=False)
    outcome_unknown_recovery: bool = field(init=False, default=False)
    record_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenStateAuthority = field(
        default_factory=ReportExportTokenStateAuthority
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, name="artifact_id", max_length=128),
        )
        if self.actor_digest is not None:
            object.__setattr__(
                self,
                "actor_digest",
                _require_text(self.actor_digest, name="actor_digest", max_length=128),
            )
        for name in ("project_key", "trace_id", "request_id", "revoke_reason"):
            object.__setattr__(
                self,
                name,
                _clean_text(getattr(self, name), max_length=128),
            )
        object.__setattr__(
            self,
            "job_id",
            _as_int_or_none(self.job_id, name="job_id"),
        )
        if self.payload_digest is not None:
            object.__setattr__(
                self,
                "payload_digest",
                _require_sha256_hex(self.payload_digest, name="payload_digest"),
            )
        state = ReportExportTokenStateRecord._normalize_state(self.state)
        for name in ("used_at", "revoked_at", "last_seen_at"):
            object.__setattr__(
                self,
                name,
                _as_utc(getattr(self, name), name=name),
            )
        object.__setattr__(
            self,
            "delivery_receipt_present",
            _as_bool(
                self.delivery_receipt_present,
                name="delivery_receipt_present",
            ),
        )
        object.__setattr__(self, "found", _as_bool(self.found, name="found"))
        used = self.used_at is not None or state in {
            ReportExportTokenStateValue.USED,
            ReportExportTokenStateValue.USED_AND_REVOKED,
        }
        revoked = self.revoked_at is not None or state in {
            ReportExportTokenStateValue.REVOKED,
            ReportExportTokenStateValue.USED_AND_REVOKED,
        }
        if used:
            state = (
                ReportExportTokenStateValue.USED_AND_REVOKED
                if revoked
                else ReportExportTokenStateValue.USED
            )
        elif revoked:
            state = ReportExportTokenStateValue.REVOKED
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "used", used)
        object.__setattr__(self, "claimed", used)
        object.__setattr__(self, "revoked", revoked)
        absent = not self.delivery_receipt_present
        object.__setattr__(self, "delivery_receipt_absent", absent)
        if used and absent:
            object.__setattr__(self, "recovery_mode", "plan_only")
            object.__setattr__(self, "recovery_outcome", "outcome_unknown")
            object.__setattr__(self, "plan_only_recovery", True)
            object.__setattr__(self, "outcome_unknown_recovery", True)
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)
        object.__setattr__(self, "record_digest", _record_digest(self))


@dataclass(frozen=True, slots=True)
class TokenPruneRecord:
    """Typed result of a dry-run or executed retention prune."""

    retention_days: int
    cutoff: datetime
    dry_run: bool
    candidate_count: int
    deleted_count: int
    degraded: bool = False
    record_digest: str = field(init=False, default="", repr=False)
    authority: ReportExportTokenStateAuthority = field(
        default_factory=ReportExportTokenStateAuthority
    )

    def __post_init__(self) -> None:
        if isinstance(self.retention_days, bool) or not isinstance(
            self.retention_days,
            int,
        ):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "retention_days must be int",
                    site="prune/retention_days",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        if self.retention_days < 1:
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "retention_days must be >= 1",
                    site="prune/retention_days",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        cutoff = _as_utc(self.cutoff, name="cutoff")
        if cutoff is None:
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "cutoff is required",
                    site="prune/cutoff",
                    public_exception="ValueError",
                ),
                ValueError,
            )
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "dry_run", _as_bool(self.dry_run, name="dry_run"))
        for name in ("candidate_count", "deleted_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                _raise_failure(
                    _failure(
                        "input_contract_invalid",
                        f"{name} must be int",
                        site=f"prune/{name}",
                        public_exception="TypeError",
                    ),
                    TypeError,
                )
            if value < 0:
                _raise_failure(
                    _failure(
                        "input_contract_invalid",
                        f"{name} must be >= 0",
                        site=f"prune/{name}",
                        public_exception="ValueError",
                    ),
                    ValueError,
                )
            object.__setattr__(self, name, value)
        object.__setattr__(self, "degraded", _as_bool(self.degraded, name="degraded"))
        object.__setattr__(self, "authority", _authority_for(self.authority))
        _guard_no_credentials(self)
        object.__setattr__(self, "record_digest", _record_digest(self))


@runtime_checkable
class ReportExportTokenStateStore(Protocol):
    """Backend protocol for claim/revoke/readback/prune token state."""

    def claim(self, command: ClaimExportTokenCommand) -> TokenClaimRecord: ...

    def revoke(self, command: RevokeExportTokenCommand) -> TokenRevokeRecord: ...

    def readback(self, command: ReadbackExportTokenCommand) -> TokenReadbackRecord: ...

    def prune(self, command: PruneExportTokenStatesCommand) -> TokenPruneRecord: ...


class LocalSuccessorReportExportTokenStore:
    """Process-local successor token-state store (test/offline only).

    The store models the ``successor_report_export_token_states`` table and
    never touches legacy tables.  ``degraded=True`` makes every operation fail
    closed with :class:`TokenStateBackendUnavailableError`; it never fabricates
    an in-memory durable claim.
    """

    table_name = SUCCESSOR_REPORT_EXPORT_TOKEN_STATES_TABLE

    def __init__(
        self,
        *,
        degraded: bool = False,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.degraded = _as_bool(degraded, name="degraded")
        if now_provider is not None and not callable(now_provider):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "now_provider must be callable",
                    site="store/now_provider",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        self.now_provider = now_provider or _utc_now
        self._rows: dict[str, dict[str, Any]] = {}
        self.reads = 0
        self.writes = 0

    @property
    def read_count(self) -> int:
        return self.reads

    @property
    def write_count(self) -> int:
        return self.writes

    def _now(self) -> datetime:
        now = self.now_provider()
        if not isinstance(now, datetime):
            _raise_failure(
                _failure(
                    "conflict",
                    "now_provider must return datetime",
                    site="store/now_provider",
                    public_exception="TokenStateConflictError",
                ),
                TokenStateConflictError,
            )
        return _as_utc(now, name="now") or _utc_now()

    def _require_available(self) -> None:
        if self.degraded:
            _raise_effect_failure(
                _failure(
                    "backend_unavailable",
                    f"{self.table_name} backend unavailable; no durable claim made",
                    site="store/backend",
                    public_exception="TokenStateBackendUnavailableError",
                    boundary_class="SHELL_BOUNDARY_EXCEPTION",
                ),
            )

    def _existing_or_empty(self, artifact_id: str) -> dict[str, Any]:
        return self._rows.get(artifact_id) or {
            "artifact_id": artifact_id,
            "actor_digest": None,
            "project_key": None,
            "trace_id": None,
            "request_id": None,
            "job_id": None,
            "payload_digest": None,
            "used_at": None,
            "revoked_at": None,
            "revoke_reason": None,
            "last_seen_at": None,
        }

    @staticmethod
    def _state_for(used_at: datetime | None, revoked_at: datetime | None):
        if used_at is not None and revoked_at is not None:
            return ReportExportTokenStateValue.USED_AND_REVOKED
        if used_at is not None:
            return ReportExportTokenStateValue.USED
        if revoked_at is not None:
            return ReportExportTokenStateValue.REVOKED
        return ReportExportTokenStateValue.UNUSED

    def _record_from_row(
        self,
        row: dict[str, Any],
        authority: ReportExportTokenStateAuthority,
    ) -> ReportExportTokenStateRecord:
        used_at = _as_utc(row.get("used_at"), name="used_at")
        revoked_at = _as_utc(row.get("revoked_at"), name="revoked_at")
        return ReportExportTokenStateRecord(
            artifact_id=str(row["artifact_id"]),
            actor_digest=(
                str(row.get("actor_digest")) or "authenticated:0000000000000000"
            ),
            project_key=_clean_text(row.get("project_key"), max_length=64),
            trace_id=_clean_text(row.get("trace_id"), max_length=128),
            request_id=_clean_text(row.get("request_id"), max_length=128),
            job_id=_as_int_or_none(row.get("job_id"), name="job_id"),
            used_at=used_at,
            revoked_at=revoked_at,
            revoke_reason=_clean_text(row.get("revoke_reason"), max_length=256),
            last_seen_at=_as_utc(row.get("last_seen_at"), name="last_seen_at"),
            payload_digest=(
                str(row.get("payload_digest"))
                if row.get("payload_digest") is not None
                else None
            ),
            state=self._state_for(used_at, revoked_at),
            authority=authority,
        )

    def claim(self, command: ClaimExportTokenCommand) -> TokenClaimRecord:
        if not isinstance(command, ClaimExportTokenCommand):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "claim requires a ClaimExportTokenCommand",
                    site="store/claim/command",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        _guard_no_credentials(command)
        self._require_available()
        artifact_id = command.artifact_id
        now = self._now()
        existing = self._existing_or_empty(artifact_id)
        used_at = _as_utc(existing.get("used_at"), name="used_at")
        revoked_at = _as_utc(existing.get("revoked_at"), name="revoked_at")
        authority = _authority_for(command.authority)
        if used_at is None and revoked_at is None:
            row = {
                "artifact_id": artifact_id,
                "actor_digest": command.actor_digest,
                "project_key": command.project_key,
                "trace_id": command.trace_id,
                "request_id": command.request_id,
                "job_id": command.job_id,
                "payload_digest": command.payload_digest,
                "used_at": now,
                "revoked_at": None,
                "revoke_reason": None,
                "last_seen_at": now,
            }
            self._rows[artifact_id] = row
            self.writes += 1
            record = self._record_from_row(row, authority)
            return TokenClaimRecord(
                artifact_id=record.artifact_id,
                actor_digest=record.actor_digest,
                claimed=True,
                already_used=False,
                revoked=False,
                degraded=False,
                claimed_at=now,
                authority=authority,
            )
        row = dict(existing)
        row["last_seen_at"] = now
        self._rows[artifact_id] = row
        self.writes += 1
        record = self._record_from_row(row, authority)
        return TokenClaimRecord(
            artifact_id=record.artifact_id,
            actor_digest=record.actor_digest,
            claimed=False,
            already_used=used_at is not None,
            revoked=revoked_at is not None,
            degraded=False,
            claimed_at=now,
            authority=authority,
        )

    def revoke(self, command: RevokeExportTokenCommand) -> TokenRevokeRecord:
        if not isinstance(command, RevokeExportTokenCommand):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "revoke requires a RevokeExportTokenCommand",
                    site="store/revoke/command",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        _guard_no_credentials(command)
        self._require_available()
        artifact_id = command.artifact_id
        now = self._now()
        existing = self._existing_or_empty(artifact_id)
        authority = _authority_for(command.authority)
        used_at = _as_utc(existing.get("used_at"), name="used_at")
        revoked_at = _as_utc(existing.get("revoked_at"), name="revoked_at")
        row = dict(existing)
        row["artifact_id"] = artifact_id
        if row.get("actor_digest") is None:
            row["actor_digest"] = command.actor_digest
        if revoked_at is None:
            revoked_at = now
            row["revoked_at"] = revoked_at
            row["revoke_reason"] = command.reason
        row["last_seen_at"] = now
        self._rows[artifact_id] = row
        self.writes += 1
        record = self._record_from_row(row, authority)
        return TokenRevokeRecord(
            artifact_id=record.artifact_id,
            actor_digest=record.actor_digest,
            revoked=True,
            already_used=used_at is not None,
            degraded=False,
            used_at=used_at,
            revoked_at=revoked_at,
            revoke_reason=record.revoke_reason,
            authority=authority,
        )

    def readback(self, command: ReadbackExportTokenCommand) -> TokenReadbackRecord:
        if not isinstance(command, ReadbackExportTokenCommand):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "readback requires a ReadbackExportTokenCommand",
                    site="store/readback/command",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        _guard_no_credentials(command)
        self._require_available()
        artifact_id = command.artifact_id
        authority = _authority_for(command.authority)
        self.reads += 1
        row = self._rows.get(artifact_id)
        if row is None:
            return TokenReadbackRecord(
                artifact_id=artifact_id,
                authority=authority,
                found=False,
            )
        record = self._record_from_row(row, authority)
        return TokenReadbackRecord(
            artifact_id=record.artifact_id,
            actor_digest=record.actor_digest,
            project_key=record.project_key,
            trace_id=record.trace_id,
            request_id=record.request_id,
            job_id=record.job_id,
            payload_digest=record.payload_digest,
            state=record.state,
            used_at=record.used_at,
            revoked_at=record.revoked_at,
            revoke_reason=record.revoke_reason,
            last_seen_at=record.last_seen_at,
            delivery_receipt_present=False,
            found=True,
            authority=authority,
        )

    def prune(self, command: PruneExportTokenStatesCommand) -> TokenPruneRecord:
        if not isinstance(command, PruneExportTokenStatesCommand):
            _raise_failure(
                _failure(
                    "input_contract_invalid",
                    "prune requires a PruneExportTokenStatesCommand",
                    site="store/prune/command",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        _guard_no_credentials(command)
        self._require_available()
        authority = _authority_for(command.authority)
        cutoff = _as_utc(command.now, name="now") or _utc_now()
        cutoff -= timedelta(days=command.retention_days)
        self.reads += 1
        terminal = {
            ReportExportTokenStateValue.USED,
            ReportExportTokenStateValue.REVOKED,
            ReportExportTokenStateValue.USED_AND_REVOKED,
        }
        candidates = [
            artifact_id
            for artifact_id, row in self._rows.items()
            if self._record_from_row(row, authority).state in terminal
            and (
                row.get("last_seen_at") is not None
                and _as_utc(row.get("last_seen_at"), name="last_seen_at") < cutoff
            )
        ]
        if command.dry_run:
            return TokenPruneRecord(
                retention_days=command.retention_days,
                cutoff=cutoff,
                dry_run=True,
                candidate_count=len(candidates),
                deleted_count=0,
                degraded=False,
                authority=authority,
            )
        for artifact_id in candidates:
            self._rows.pop(artifact_id, None)
        self.writes += 1
        return TokenPruneRecord(
            retention_days=command.retention_days,
            cutoff=cutoff,
            dry_run=False,
            candidate_count=len(candidates),
            deleted_count=len(candidates),
            degraded=False,
            authority=authority,
        )


def _require_store(store: Any, operation: str) -> ReportExportTokenStateStore:
    if not isinstance(store, ReportExportTokenStateStore):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                f"{operation} requires a ReportExportTokenStateStore",
                site=f"{operation}/store",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    return store


def _require_result_authority(record: Any) -> None:
    authority = getattr(record, "authority", None)
    if not isinstance(authority, ReportExportTokenStateAuthority):
        _raise_failure(
            _failure(
                "conflict",
                "store returned an untyped authority",
                site="result/authority",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    if not _all_authority_false(authority):
        _raise_failure(
            _failure(
                "conflict",
                "store returned an authority that grants runtime power",
                site="result/authority",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )


def claim_report_export_token_once(
    store: ReportExportTokenStateStore,
    command: ClaimExportTokenCommand,
) -> TokenClaimRecord:
    """Claim a one-time export token exactly once, fail closed on degrade."""

    store = _require_store(store, "claim_report_export_token_once")
    if not isinstance(command, ClaimExportTokenCommand):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "claim_report_export_token_once requires typed command",
                site="claim/command",
                public_exception="TypeError",
            ),
            TypeError,
        )
    _guard_no_credentials(command)
    record = store.claim(command)
    if not isinstance(record, TokenClaimRecord):
        _raise_failure(
            _failure(
                "conflict",
                "store claim returned the wrong record type",
                site="claim/result",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    _require_result_authority(record)
    if record.degraded and record.claimed:
        _raise_failure(
            _failure(
                "conflict",
                "degraded token state cannot be reported as a durable claim",
                site="claim/degraded",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    return record


def revoke_report_export_token(
    store: ReportExportTokenStateStore,
    command: RevokeExportTokenCommand,
) -> TokenRevokeRecord:
    """Revoke a token state row without erasing an earlier claim/use."""

    store = _require_store(store, "revoke_report_export_token")
    if not isinstance(command, RevokeExportTokenCommand):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "revoke_report_export_token requires typed command",
                site="revoke/command",
                public_exception="TypeError",
            ),
            TypeError,
        )
    _guard_no_credentials(command)
    record = store.revoke(command)
    if not isinstance(record, TokenRevokeRecord):
        _raise_failure(
            _failure(
                "conflict",
                "store revoke returned the wrong record type",
                site="revoke/result",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    _require_result_authority(record)
    if record.degraded and record.revoked:
        _raise_failure(
            _failure(
                "conflict",
                "degraded token state cannot be reported as durable revocation",
                site="revoke/degraded",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    return record


def readback_report_export_token(
    store: ReportExportTokenStateStore,
    command: ReadbackExportTokenCommand,
) -> TokenReadbackRecord:
    """Read the current token-state row and its recovery observation."""

    store = _require_store(store, "readback_report_export_token")
    if not isinstance(command, ReadbackExportTokenCommand):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "readback_report_export_token requires typed command",
                site="readback/command",
                public_exception="TypeError",
            ),
            TypeError,
        )
    _guard_no_credentials(command)
    record = store.readback(command)
    if not isinstance(record, TokenReadbackRecord):
        _raise_failure(
            _failure(
                "conflict",
                "store readback returned the wrong record type",
                site="readback/result",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    _require_result_authority(record)
    return record


def prune_report_export_token_states(
    store: ReportExportTokenStateStore,
    command: PruneExportTokenStatesCommand,
) -> TokenPruneRecord:
    """Prune only terminal rows older than the retention cutoff."""

    store = _require_store(store, "prune_report_export_token_states")
    if not isinstance(command, PruneExportTokenStatesCommand):
        _raise_failure(
            _failure(
                "input_contract_invalid",
                "prune_report_export_token_states requires typed command",
                site="prune/command",
                public_exception="TypeError",
            ),
            TypeError,
        )
    _guard_no_credentials(command)
    record = store.prune(command)
    if not isinstance(record, TokenPruneRecord):
        _raise_failure(
            _failure(
                "conflict",
                "store prune returned the wrong record type",
                site="prune/result",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    _require_result_authority(record)
    if record.degraded and record.deleted_count:
        _raise_failure(
            _failure(
                "conflict",
                "degraded prune cannot report durable deletions",
                site="prune/degraded",
                public_exception="TokenStateConflictError",
            ),
            TokenStateConflictError,
        )
    return record
