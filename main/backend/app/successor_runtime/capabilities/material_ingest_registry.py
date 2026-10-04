"""Typed successor ingest submission registry port (ALL-SM-002 C7.2).

The donor ``api/ingest.py`` registry keeps an untyped status string and
silently degrades to an in-memory dictionary when the database is
unavailable.  This successor port separates the donor-visible
``observed_status`` from the controlled ``lifecycle_state``, supports only
the bounded submission lifecycle vocabulary, and never accepts a true
authority field.  Reserving the same ``registry_key`` with a different
request digest is a typed conflict instead of a silent overwrite.

This module is a self-contained provider-independent port: it imports no
database library, no donor service code and no runtime substrate.  The
included local store is deterministic and writes only to the successor-only
table ``successor_ingest_submission_registry``; no legacy/donor table
parameter is accepted and no database-unavailable fallback is performed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, NoReturn, Protocol, runtime_checkable

from functorial_kit import Failure
from mrw_functorial_kit.core.w06_semantics import material_ingest_registry_failures

MATERIAL_INGEST_REGISTRY_PORT_REF = "mrw.material.ingest.submission-registry.v2"
MATERIAL_INGEST_REGISTRY_AUTHORITY_SCHEMA = "mrw.material.ingest.submission-registry.authority.v2"
MATERIAL_INGEST_REGISTRY_READBACK_SCHEMA = "mrw.material.ingest.submission-registry.readback.v2"
SUCCESSOR_MATERIAL_INGEST_SUBMISSION_REGISTRY_TABLE = "successor_ingest_submission_registry"
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00+00:00"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_CREDENTIAL_KEY_MARKERS = (
    "secret",
    "password",
    "credential",
    "api_key",
    "token_secret",
)

_MATERIAL_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"
_MATERIAL_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _failure(
    code: str,
    message: object,
    exception_type: type[Exception] = ValueError,
    *,
    operation: str = "ingest.registry",
    site: str = "app.successor_runtime.capabilities.ingest_c7_registry",
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> Failure:
    """Create a closed C7 registry failure before the public ABI lift."""

    public_message = str(exception_type(message))
    context: dict[str, Any] = {
        "boundary_class": boundary_class,
        "failure_family": material_ingest_registry_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": exception_type.__name__,
        "public_message": public_message,
        "site": site,
        "witness": _MATERIAL_FAILURE_WITNESS,
    }
    context.update(details)
    return material_ingest_registry_failures.fail(code, public_message, context)


def _raise_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift one complete C7 registry failure while retaining the legacy ABI."""

    context = failure.context or {}
    if (
        not material_ingest_registry_failures.matches(failure)
        or _MATERIAL_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("failure_family") != failure.family
        or context.get("boundary_class")
        not in {"PURE_CONTRACT_FAILURE", "EFFECT_OR_PROVIDER_FAILURE"}
        or context.get("public_exception") != exception_type.__name__
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=successor.ingest_c7_registry.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("ingest registry failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if issubclass(exception_type, MaterialIngestRegistryError):
        error = exception_type(
            message,
            registry_key=context.get("registry_key"),
            request_hash=context.get("request_hash"),
        )
    else:
        error = exception_type(message)
    if cause is None:
        # kit:boundary owner=successor.ingest_c7_registry.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=material.ingest.registry_failure witness=test:test_w06_c2_total_core_failure_lifts
        raise error
    # kit:boundary owner=successor.ingest_c7_registry.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=material.ingest.registry_failure witness=test:test_w06_c2_total_core_failure_lifts
    raise error from cause


def _fail_and_raise(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    operation: str,
    site: str,
    cause: BaseException | None = None,
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> NoReturn:
    _raise_failure(
        _failure(
            code,
            message,
            exception_type,
            operation=operation,
            site=site,
            boundary_class=boundary_class,
            **details,
        ),
        exception_type,
        cause=cause,
    )


def _propagate_registry_error(error: MaterialIngestRegistryError, *, operation: str, site: str) -> NoReturn:
    """Re-encode a typed store error through the closed family before lifting."""

    code_by_type: tuple[tuple[type[MaterialIngestRegistryError], str], ...] = (
        (MaterialIngestRegistryConflictError, "conflict"),
        (MaterialIngestRegistryNotFoundError, "not_found"),
        (MaterialIngestRegistryCredentialError, "credential_rejected"),
        (MaterialIngestRegistryBackendUnavailableError, "backend_unavailable"),
        (MaterialIngestRegistryIntegrityError, "integrity_violation"),
    )
    code = next(
        (candidate for error_type, candidate in code_by_type if isinstance(error, error_type)),
        "integrity_violation",
    )
    boundary_class = (
        "EFFECT_OR_PROVIDER_FAILURE"
        if code == "backend_unavailable"
        else "PURE_CONTRACT_FAILURE"
    )
    _fail_and_raise(
        code,
        str(error),
        type(error),
        operation=operation,
        site=site,
        boundary_class=boundary_class,
        registry_key=error.registry_key,
        request_hash=error.request_hash,
    )


class MaterialIngestRegistryError(RuntimeError):
    """Base typed failure for ingest submission registry operations."""

    def __init__(
        self,
        message: str,
        *,
        registry_key: str | None = None,
        request_hash: str | None = None,
    ) -> None:
        super().__init__(message)
        self.registry_key = registry_key
        self.request_hash = request_hash


class MaterialIngestRegistryConflictError(MaterialIngestRegistryError):
    """A submission already occupies the key with different request content."""


class MaterialIngestRegistryNotFoundError(MaterialIngestRegistryError):
    """No successor submission row exists for the requested key."""


class MaterialIngestRegistryIntegrityError(MaterialIngestRegistryError):
    """A successor identity/content invariant was violated."""


class MaterialIngestRegistryCredentialError(MaterialIngestRegistryError):
    """A payload tried to carry a credential-like field into the registry."""


class MaterialIngestRegistryBackendUnavailableError(MaterialIngestRegistryError):
    """The successor store backend could not answer; no degradation occurs."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _submission_id_for_key(registry_key: str) -> str:
    return "sub_" + hashlib.sha256(registry_key.encode("utf-8")).hexdigest()[:20]


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        _fail_and_raise(
            "input_contract_invalid",
            f"{name} must be a string",
            TypeError,
            operation="ingest.registry.require_text",
            site="app.successor_runtime.capabilities.ingest_c7_registry._require_text",
        )
    text = value.strip()
    if not text:
        _fail_and_raise(
            "input_contract_invalid",
            f"{name} must not be blank",
            ValueError,
            operation="ingest.registry.require_text",
            site="app.successor_runtime.capabilities.ingest_c7_registry._require_text",
        )
    return text


def _require_hex64(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        _fail_and_raise(
            "integrity_violation",
            f"{name} must be a 64-char lowercase hex digest",
            ValueError,
            operation="ingest.registry.require_hex64",
            site="app.successor_runtime.capabilities.ingest_c7_registry._require_hex64",
        )
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _fail_and_raise(
            "input_contract_invalid",
            f"{name} must be a bool",
            TypeError,
            operation="ingest.registry.require_bool",
            site="app.successor_runtime.capabilities.ingest_c7_registry._require_bool",
        )
    return value


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _fail_and_raise(
            "input_contract_invalid",
            f"{name} must be a plain JSON object",
            TypeError,
            operation="ingest.registry.require_mapping",
            site="app.successor_runtime.capabilities.ingest_c7_registry._require_mapping",
        )
    return _plain_copy(value, name)


def _plain_copy(value: Any, path: str) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_copy(item, f"{path}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [
            _plain_copy(item, f"{path}[{index}]") for index, item in enumerate(value)
        ]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    _fail_and_raise(
        "input_contract_invalid",
        f"{path} must be JSON-compatible",
        TypeError,
        operation="ingest.registry.plain_copy",
        site="app.successor_runtime.capabilities.ingest_c7_registry._plain_copy",
    )


def _assert_no_credential_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            lowered = str(key).lower()
            if any(marker in lowered for marker in _CREDENTIAL_KEY_MARKERS):
                _fail_and_raise(
                    "credential_rejected",
                    f"{child_path} is a credential-like field name and is "
                    "not allowed in the ingest submission registry",
                    MaterialIngestRegistryCredentialError,
                    operation="ingest.registry.credential_guard",
                    site="app.successor_runtime.capabilities.ingest_c7_registry._assert_no_credential_keys",
                    registry_key=None,
                )
            _assert_no_credential_keys(item, child_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_credential_keys(item, f"{path}[{index}]")


class MaterialIngestRegistryState(StrEnum):
    SUBMITTED = "submitted"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


def _coerce_state(value: Any, name: str) -> MaterialIngestRegistryState:
    if isinstance(value, MaterialIngestRegistryState):
        return value
    if isinstance(value, str):
        try:
            return MaterialIngestRegistryState(value.strip().lower())
        except ValueError as exc:
            _fail_and_raise(
                "integrity_violation",
                f"{name} is not a supported lifecycle state",
                ValueError,
                operation="ingest.registry.lifecycle_state",
                site="app.successor_runtime.capabilities.ingest_c7_registry._coerce_state",
                cause=exc,
            )
    _fail_and_raise(
        "input_contract_invalid",
        f"{name} must be an IngestRegistryState or its string value",
        TypeError,
        operation="ingest.registry.lifecycle_state",
        site="app.successor_runtime.capabilities.ingest_c7_registry._coerce_state",
    )


_AUTHORITY_BOOL_FIELDS = (
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

_TERMINAL_STATES = frozenset(
    {
        MaterialIngestRegistryState.COMPLETED,
        MaterialIngestRegistryState.FAILED,
        MaterialIngestRegistryState.OUTCOME_UNKNOWN,
    }
)
_STATE_RANK = {
    MaterialIngestRegistryState.SUBMITTED: 0,
    MaterialIngestRegistryState.QUEUED: 1,
    MaterialIngestRegistryState.COMPLETED: 2,
    MaterialIngestRegistryState.FAILED: 2,
    MaterialIngestRegistryState.OUTCOME_UNKNOWN: 2,
}


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryAuthority:
    """Readback-only authority snapshot; every grant must stay False."""

    schema_ref: str = MATERIAL_INGEST_REGISTRY_AUTHORITY_SCHEMA
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
            _fail_and_raise(
                "input_contract_invalid",
                "IngestRegistryAuthority.schema_ref is required",
                ValueError,
                operation="ingest.registry.authority",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryAuthority",
            )
        object.__setattr__(self, "schema_ref", self.schema_ref.strip())
        for name in _AUTHORITY_BOOL_FIELDS:
            value = getattr(self, name)
            if value is not False:
                _fail_and_raise(
                    "integrity_violation",
                    f"IngestRegistryAuthority.{name} must be False; "
                    "the successor registry grants no authority",
                    ValueError,
                    operation="ingest.registry.authority",
                    site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryAuthority",
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            **{name: getattr(self, name) for name in _AUTHORITY_BOOL_FIELDS},
        }


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryIdentity:
    """Canonical three-part submission identity and request fingerprint."""

    project_key: str
    trigger_type: str
    idempotency_key: str
    request_hash: str
    registry_key: str
    submission_id: str

    def __post_init__(self) -> None:
        project_key = _require_text(self.project_key, "project_key")
        trigger_type = _require_text(self.trigger_type, "trigger_type")
        idempotency_key = _require_text(
            self.idempotency_key,
            "idempotency_key",
        )
        request_hash = _require_hex64(self.request_hash, "request_hash")
        registry_key = _require_text(self.registry_key, "registry_key")
        submission_id = _require_text(self.submission_id, "submission_id")
        expected_key = f"{trigger_type}:{project_key}:{idempotency_key}"
        if registry_key != expected_key:
            _fail_and_raise(
                "integrity_violation",
                "registry_key must be trigger_type:project_key:idempotency_key",
                ValueError,
                operation="ingest.registry.identity",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryIdentity",
            )
        expected_submission_id = _submission_id_for_key(registry_key)
        if submission_id != expected_submission_id:
            _fail_and_raise(
                "integrity_violation",
                "submission_id does not match the registry key",
                ValueError,
                operation="ingest.registry.identity",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryIdentity",
                registry_key=registry_key,
                request_hash=request_hash,
            )
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "trigger_type", trigger_type)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "request_hash", request_hash)
        object.__setattr__(self, "registry_key", registry_key)
        object.__setattr__(self, "submission_id", submission_id)

    def to_plain(self) -> dict[str, Any]:
        return {
            "project_key": self.project_key,
            "trigger_type": self.trigger_type,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "registry_key": self.registry_key,
            "submission_id": self.submission_id,
        }


def derive_registry_identity(
    project_key: str,
    trigger_type: str,
    idempotency_key: str,
    request_payload: Mapping[str, Any],
) -> MaterialIngestRegistryIdentity:
    """Derive the direct three-part registry identity and request hash.

    The donor-derived 24-hex ``public_key`` prefix is intentionally omitted:
    the caller-supplied idempotency key is used verbatim as the third segment
    of ``trigger_type:project_key:idempotency_key``.
    """

    project_key = _require_text(project_key, "project_key")
    trigger_type = _require_text(trigger_type, "trigger_type")
    idempotency_key = _require_text(idempotency_key, "idempotency_key")
    payload = _require_mapping(request_payload, "request_payload")
    registry_key = f"{trigger_type}:{project_key}:{idempotency_key}"
    return MaterialIngestRegistryIdentity(
        project_key=project_key,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        request_hash=_canonical_digest(payload),
        registry_key=registry_key,
        submission_id=_submission_id_for_key(registry_key),
    )


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryReserveCommand:
    identity: MaterialIngestRegistryIdentity
    subject_payload: Mapping[str, Any]
    request_payload: Mapping[str, Any]
    authority: MaterialIngestRegistryAuthority | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MaterialIngestRegistryIdentity):
            _fail_and_raise(
                "input_contract_invalid",
                "reserve command identity must be typed",
                TypeError,
                operation="ingest.registry.reserve.command",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReserveCommand",
            )
        object.__setattr__(
            self,
            "subject_payload",
            _require_mapping(self.subject_payload, "subject_payload"),
        )
        object.__setattr__(
            self,
            "request_payload",
            _require_mapping(self.request_payload, "request_payload"),
        )
        self._validate_authority()

    def _validate_authority(self) -> None:
        if self.authority is not None and not isinstance(
            self.authority,
            MaterialIngestRegistryAuthority,
        ):
            _fail_and_raise(
                "input_contract_invalid",
                "reserve command authority must be typed or None",
                TypeError,
                operation="ingest.registry.reserve.command",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReserveCommand",
            )


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryCompleteCommand:
    registry_key: str
    lifecycle_state: MaterialIngestRegistryState | str
    observed_status: str
    response_payload: Mapping[str, Any]
    task_id: str | None = None
    authority: MaterialIngestRegistryAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_key",
            _require_text(self.registry_key, "registry_key"),
        )
        object.__setattr__(
            self,
            "lifecycle_state",
            _coerce_state(self.lifecycle_state, "lifecycle_state"),
        )
        observed_status = _require_text(
            self.observed_status,
            "observed_status",
        )
        object.__setattr__(self, "observed_status", observed_status)
        object.__setattr__(
            self,
            "response_payload",
            _require_mapping(self.response_payload, "response_payload"),
        )
        if self.task_id is not None:
            if not isinstance(self.task_id, str):
                _fail_and_raise(
                    "input_contract_invalid",
                    "task_id must be a string or None",
                    TypeError,
                    operation="ingest.registry.complete.command",
                    site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryCompleteCommand",
                )
            task_id = self.task_id.strip()
            object.__setattr__(self, "task_id", task_id or None)
        if self.authority is not None and not isinstance(
            self.authority,
            MaterialIngestRegistryAuthority,
        ):
            _fail_and_raise(
                "input_contract_invalid",
                "complete command authority must be typed or None",
                TypeError,
                operation="ingest.registry.complete.command",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryCompleteCommand",
            )


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryForgetCommand:
    registry_key: str
    authority: MaterialIngestRegistryAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_key",
            _require_text(self.registry_key, "registry_key"),
        )
        if self.authority is not None and not isinstance(
            self.authority,
            MaterialIngestRegistryAuthority,
        ):
            _fail_and_raise(
                "input_contract_invalid",
                "forget command authority must be typed or None",
                TypeError,
                operation="ingest.registry.forget.command",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryForgetCommand",
            )


def _readback_plain(readback: MaterialIngestRegistryReadback) -> dict[str, Any]:
    return {
        "identity": readback.identity.to_plain(),
        "lifecycle_state": readback.lifecycle_state.value,
        "observed_status": readback.observed_status,
        "duplicate": readback.duplicate,
        "task_id": readback.task_id,
        "subject_payload": readback.subject_payload,
        "response_payload": readback.response_payload,
        "value_ref": readback.value_ref,
        "revision": readback.revision,
        "created_at": readback.created_at,
        "updated_at": readback.updated_at,
        "authority": readback.authority.to_plain(),
    }


def _readback_plain_digest(readback: MaterialIngestRegistryReadback) -> str:
    body = {"schema": MATERIAL_INGEST_REGISTRY_READBACK_SCHEMA, **_readback_plain(readback)}
    return _canonical_digest(body)


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryReadback:
    """Immutable successor registry readback; the digest is derived."""

    identity: MaterialIngestRegistryIdentity
    lifecycle_state: MaterialIngestRegistryState
    observed_status: str
    duplicate: bool
    task_id: str | None
    subject_payload: Mapping[str, Any]
    response_payload: Mapping[str, Any] | None
    value_ref: str
    revision: int
    readback_digest: str = field(default="", init=False, repr=False, compare=False)
    created_at: str = DEFAULT_TIMESTAMP
    updated_at: str = DEFAULT_TIMESTAMP
    authority: MaterialIngestRegistryAuthority = field(default_factory=MaterialIngestRegistryAuthority)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MaterialIngestRegistryIdentity):
            _fail_and_raise(
                "input_contract_invalid",
                "readback identity must be typed",
                TypeError,
                operation="ingest.registry.readback",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReadback",
            )
        lifecycle_state = _coerce_state(
            self.lifecycle_state,
            "readback lifecycle_state",
        )
        observed_status = _require_text(
            self.observed_status,
            "observed_status",
        )
        duplicate = _require_bool(self.duplicate, "duplicate")
        if self.task_id is not None:
            if not isinstance(self.task_id, str):
                _fail_and_raise(
                    "input_contract_invalid",
                    "task_id must be a string or None",
                    TypeError,
                    operation="ingest.registry.readback",
                    site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReadback",
                )
            task_id = self.task_id.strip() or None
        else:
            task_id = None
        subject_payload = _require_mapping(
            self.subject_payload,
            "subject_payload",
        )
        response_payload = (
            _require_mapping(self.response_payload, "response_payload")
            if self.response_payload is not None
            else None
        )
        value_ref = _require_text(self.value_ref, "value_ref")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            _fail_and_raise(
                "input_contract_invalid",
                "revision must be an int",
                TypeError,
                operation="ingest.registry.readback",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReadback",
            )
        if self.revision < 1:
            _fail_and_raise(
                "integrity_violation",
                "revision must be >= 1",
                ValueError,
                operation="ingest.registry.readback",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReadback",
            )
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            created_at = DEFAULT_TIMESTAMP
        else:
            created_at = self.created_at.strip()
        if not isinstance(self.updated_at, str) or not self.updated_at.strip():
            updated_at = DEFAULT_TIMESTAMP
        else:
            updated_at = self.updated_at.strip()
        authority = self.authority or MaterialIngestRegistryAuthority()
        if not isinstance(authority, MaterialIngestRegistryAuthority):
            _fail_and_raise(
                "input_contract_invalid",
                "readback authority must be typed",
                TypeError,
                operation="ingest.registry.readback",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryReadback",
            )
        object.__setattr__(self, "lifecycle_state", lifecycle_state)
        object.__setattr__(self, "observed_status", observed_status)
        object.__setattr__(self, "duplicate", duplicate)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "subject_payload", subject_payload)
        object.__setattr__(self, "response_payload", response_payload)
        object.__setattr__(self, "value_ref", value_ref)
        object.__setattr__(self, "revision", self.revision)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "readback_digest", _readback_plain_digest(self))


def _forget_plain_digest(
    registry_key: str,
    deleted: bool,
    authority: MaterialIngestRegistryAuthority,
) -> str:
    body = {
        "schema": MATERIAL_INGEST_REGISTRY_READBACK_SCHEMA,
        "registry_key": registry_key,
        "deleted": deleted,
        "authority": authority.to_plain(),
    }
    return _canonical_digest(body)


@dataclass(frozen=True, slots=True)
class MaterialIngestRegistryForgetResult:
    registry_key: str
    deleted: bool
    readback_digest: str = field(default="", init=False, repr=False, compare=False)
    authority: MaterialIngestRegistryAuthority = field(default_factory=MaterialIngestRegistryAuthority)

    def __post_init__(self) -> None:
        registry_key = _require_text(self.registry_key, "registry_key")
        deleted = _require_bool(self.deleted, "deleted")
        authority = self.authority or MaterialIngestRegistryAuthority()
        if not isinstance(authority, MaterialIngestRegistryAuthority):
            _fail_and_raise(
                "input_contract_invalid",
                "forget result authority must be typed",
                TypeError,
                operation="ingest.registry.forget.result",
                site="app.successor_runtime.capabilities.ingest_c7_registry.IngestRegistryForgetResult",
            )
        object.__setattr__(self, "registry_key", registry_key)
        object.__setattr__(self, "deleted", deleted)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(
            self,
            "readback_digest",
            _forget_plain_digest(registry_key, deleted, authority),
        )


@runtime_checkable
class MaterialIngestRegistryStore(Protocol):
    """Successor-only registry row interface; never names a donor table."""

    def find(self, registry_key: str) -> MaterialIngestRegistryReadback | None: ...

    def insert(self, readback: MaterialIngestRegistryReadback) -> None: ...

    def update(self, readback: MaterialIngestRegistryReadback) -> None: ...

    def delete(self, registry_key: str) -> bool: ...


def _reserve_readback(command: MaterialIngestRegistryReserveCommand) -> MaterialIngestRegistryReadback:
    identity = command.identity
    return MaterialIngestRegistryReadback(
        identity=identity,
        lifecycle_state=MaterialIngestRegistryState.SUBMITTED,
        observed_status=MaterialIngestRegistryState.SUBMITTED.value,
        duplicate=False,
        task_id=None,
        subject_payload=command.subject_payload,
        response_payload=None,
        value_ref=(
            f"{SUCCESSOR_MATERIAL_INGEST_SUBMISSION_REGISTRY_TABLE}:{identity.submission_id}"
        ),
        revision=1,
        authority=command.authority or MaterialIngestRegistryAuthority(),
    )


def reserve_material_submission(
    store: MaterialIngestRegistryStore,
    command: MaterialIngestRegistryReserveCommand,
) -> MaterialIngestRegistryReadback:
    """Reserve once, replay an exact duplicate, or conflict on hash drift."""

    if not isinstance(command, MaterialIngestRegistryReserveCommand):
        _fail_and_raise(
            "input_contract_invalid",
            "reserve_submission requires an IngestRegistryReserveCommand",
            TypeError,
            operation="ingest.registry.reserve",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
        )
    _assert_no_credential_keys(command.subject_payload, "subject_payload")
    _assert_no_credential_keys(command.request_payload, "request_payload")
    identity = command.identity
    actual_hash = _canonical_digest(command.request_payload)
    if actual_hash != identity.request_hash:
        _fail_and_raise(
            "integrity_violation",
            "reserve command request_payload does not match identity.request_hash",
            MaterialIngestRegistryIntegrityError,
            operation="ingest.registry.reserve",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
            registry_key=identity.registry_key,
            request_hash=identity.request_hash,
        )
    try:
        existing = store.find(identity.registry_key)
    except MaterialIngestRegistryError as exc:
        _propagate_registry_error(
            exc,
            operation="ingest.registry.reserve.find",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
        )
    except Exception as exc:
        _fail_and_raise(
            "backend_unavailable",
            str(exc),
            MaterialIngestRegistryBackendUnavailableError,
            operation="ingest.registry.reserve.find",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
            boundary_class="EFFECT_OR_PROVIDER_FAILURE",
            registry_key=identity.registry_key,
            cause=exc,
        )
    if existing is not None:
        if not isinstance(existing, MaterialIngestRegistryReadback):
            _fail_and_raise(
                "integrity_violation",
                "successor store returned a non-readback row",
                MaterialIngestRegistryIntegrityError,
                operation="ingest.registry.reserve",
                site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
                registry_key=identity.registry_key,
            )
        if existing.identity.request_hash != identity.request_hash:
            _fail_and_raise(
                "conflict",
                "registry_key already exists with a different request_hash",
                MaterialIngestRegistryConflictError,
                operation="ingest.registry.reserve",
                site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
                registry_key=identity.registry_key,
                request_hash=identity.request_hash,
            )
        if existing.identity != identity:
            _fail_and_raise(
                "integrity_violation",
                "registry_key identity fields drifted from the stored row",
                MaterialIngestRegistryIntegrityError,
                operation="ingest.registry.reserve",
                site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
                registry_key=identity.registry_key,
            )
        if existing.duplicate:
            return existing
        return replace(existing, duplicate=True)
    readback = _reserve_readback(command)
    try:
        store.insert(readback)
    except MaterialIngestRegistryError as exc:
        _propagate_registry_error(
            exc,
            operation="ingest.registry.reserve.insert",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
        )
    except Exception as exc:
        _fail_and_raise(
            "backend_unavailable",
            str(exc),
            MaterialIngestRegistryBackendUnavailableError,
            operation="ingest.registry.reserve.insert",
            site="app.successor_runtime.capabilities.ingest_c7_registry.reserve_submission",
            boundary_class="EFFECT_OR_PROVIDER_FAILURE",
            registry_key=identity.registry_key,
            cause=exc,
        )
    return readback


def _response_digest(payload: Mapping[str, Any] | None) -> str:
    return _canonical_digest(_require_mapping(payload, "response_payload"))


def _completion_matches(
    existing: MaterialIngestRegistryReadback,
    command: MaterialIngestRegistryCompleteCommand,
) -> bool:
    return (
        existing.lifecycle_state == command.lifecycle_state
        and existing.observed_status == command.observed_status
        and existing.task_id == command.task_id
        and _response_digest(existing.response_payload)
        == _response_digest(command.response_payload)
    )


def complete_material_submission(
    store: MaterialIngestRegistryStore,
    command: MaterialIngestRegistryCompleteCommand,
) -> MaterialIngestRegistryReadback:
    """Write a typed completion readback or replay an exact terminal result."""

    if not isinstance(command, MaterialIngestRegistryCompleteCommand):
        _fail_and_raise(
            "input_contract_invalid",
            "complete_submission requires an IngestRegistryCompleteCommand",
            TypeError,
            operation="ingest.registry.complete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
        )
    _assert_no_credential_keys(command.response_payload, "response_payload")
    try:
        existing = store.find(command.registry_key)
    except MaterialIngestRegistryError as exc:
        _propagate_registry_error(
            exc,
            operation="ingest.registry.complete.find",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
        )
    except Exception as exc:
        _fail_and_raise(
            "backend_unavailable",
            str(exc),
            MaterialIngestRegistryBackendUnavailableError,
            operation="ingest.registry.complete.find",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            boundary_class="EFFECT_OR_PROVIDER_FAILURE",
            registry_key=command.registry_key,
            cause=exc,
        )
    if existing is None:
        _fail_and_raise(
            "not_found",
            "cannot complete an absent ingest submission",
            MaterialIngestRegistryNotFoundError,
            operation="ingest.registry.complete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            registry_key=command.registry_key,
        )
    if not isinstance(existing, MaterialIngestRegistryReadback):
        _fail_and_raise(
            "integrity_violation",
            "successor store returned a non-readback row",
            MaterialIngestRegistryIntegrityError,
            operation="ingest.registry.complete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            registry_key=command.registry_key,
        )
    if existing.lifecycle_state in _TERMINAL_STATES:
        if _completion_matches(existing, command):
            return existing
        _fail_and_raise(
            "conflict",
            "terminal ingest submission cannot be overwritten by a different "
            "completion",
            MaterialIngestRegistryConflictError,
            operation="ingest.registry.complete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            registry_key=command.registry_key,
        )
    if _completion_matches(existing, command):
        return existing
    if _STATE_RANK[command.lifecycle_state] < _STATE_RANK[existing.lifecycle_state]:
        _fail_and_raise(
            "conflict",
            "ingest submission lifecycle cannot move backwards",
            MaterialIngestRegistryConflictError,
            operation="ingest.registry.complete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            registry_key=command.registry_key,
        )
    updated = replace(
        existing,
        lifecycle_state=command.lifecycle_state,
        observed_status=command.observed_status,
        duplicate=False,
        task_id=command.task_id,
        response_payload=command.response_payload,
        revision=existing.revision + 1,
        updated_at=DEFAULT_TIMESTAMP,
        authority=(
            command.authority if command.authority is not None else existing.authority
        ),
    )
    try:
        store.update(updated)
    except MaterialIngestRegistryError as exc:
        _propagate_registry_error(
            exc,
            operation="ingest.registry.complete.update",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
        )
    except Exception as exc:
        _fail_and_raise(
            "backend_unavailable",
            str(exc),
            MaterialIngestRegistryBackendUnavailableError,
            operation="ingest.registry.complete.update",
            site="app.successor_runtime.capabilities.ingest_c7_registry.complete_submission",
            boundary_class="EFFECT_OR_PROVIDER_FAILURE",
            registry_key=command.registry_key,
            cause=exc,
        )
    return updated


def forget_material_submission(
    store: MaterialIngestRegistryStore,
    command: MaterialIngestRegistryForgetCommand,
) -> MaterialIngestRegistryForgetResult:
    """Delete one successor row; a missing row is an explicit no-op."""

    if not isinstance(command, MaterialIngestRegistryForgetCommand):
        _fail_and_raise(
            "input_contract_invalid",
            "forget_submission requires an IngestRegistryForgetCommand",
            TypeError,
            operation="ingest.registry.forget",
            site="app.successor_runtime.capabilities.ingest_c7_registry.forget_submission",
        )
    try:
        deleted = store.delete(command.registry_key)
    except MaterialIngestRegistryError as exc:
        _propagate_registry_error(
            exc,
            operation="ingest.registry.forget.delete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.forget_submission",
        )
    except Exception as exc:
        _fail_and_raise(
            "backend_unavailable",
            str(exc),
            MaterialIngestRegistryBackendUnavailableError,
            operation="ingest.registry.forget.delete",
            site="app.successor_runtime.capabilities.ingest_c7_registry.forget_submission",
            boundary_class="EFFECT_OR_PROVIDER_FAILURE",
            registry_key=command.registry_key,
            cause=exc,
        )
    return MaterialIngestRegistryForgetResult(
        registry_key=command.registry_key,
        deleted=deleted,
        authority=command.authority or MaterialIngestRegistryAuthority(),
    )


class LocalSuccessorMaterialIngestRegistryStore:
    """Deterministic successor-only in-memory registry.

    The class deliberately accepts no table-name parameter: every write goes
    to ``successor_ingest_submission_registry`` and legacy/donor table writes
    are structurally impossible.
    """

    table_name: str = SUCCESSOR_MATERIAL_INGEST_SUBMISSION_REGISTRY_TABLE
    legacy_table_writes = 0

    def __init__(self) -> None:
        self._rows: dict[str, MaterialIngestRegistryReadback] = {}
        self.legacy_table_writes = 0
        self.inserts = 0
        self.updates = 0
        self.deletes = 0

    def _guard_table(self, table_name: str) -> None:
        if table_name != self.table_name:
            self.legacy_table_writes += 1
            _fail_and_raise(
                "integrity_violation",
                f"refusing table write outside {self.table_name}: {table_name}",
                MaterialIngestRegistryIntegrityError,
                operation="ingest.registry.store.table_guard",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )

    def find(self, registry_key: str) -> MaterialIngestRegistryReadback | None:
        if not isinstance(registry_key, str):
            _fail_and_raise(
                "input_contract_invalid",
                "registry_key must be a string",
                TypeError,
                operation="ingest.registry.store.find",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )
        return self._rows.get(registry_key)

    def insert(self, readback: MaterialIngestRegistryReadback) -> None:
        if not isinstance(readback, MaterialIngestRegistryReadback):
            _fail_and_raise(
                "input_contract_invalid",
                "store insert requires an IngestRegistryReadback",
                TypeError,
                operation="ingest.registry.store.insert",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )
        self._guard_table(self.table_name)
        key = readback.identity.registry_key
        if key in self._rows:
            _fail_and_raise(
                "conflict",
                "successor registry row already exists",
                MaterialIngestRegistryConflictError,
                operation="ingest.registry.store.insert",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
                registry_key=key,
            )
        self._rows[key] = readback
        self.inserts += 1

    def update(self, readback: MaterialIngestRegistryReadback) -> None:
        if not isinstance(readback, MaterialIngestRegistryReadback):
            _fail_and_raise(
                "input_contract_invalid",
                "store update requires an IngestRegistryReadback",
                TypeError,
                operation="ingest.registry.store.update",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )
        self._guard_table(self.table_name)
        key = readback.identity.registry_key
        if key not in self._rows:
            _fail_and_raise(
                "not_found",
                "cannot update an absent successor registry row",
                MaterialIngestRegistryNotFoundError,
                operation="ingest.registry.store.update",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
                registry_key=key,
            )
        if self._rows[key].identity.request_hash != readback.identity.request_hash:
            _fail_and_raise(
                "conflict",
                "successor registry row request_hash cannot change in place",
                MaterialIngestRegistryConflictError,
                operation="ingest.registry.store.update",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
                registry_key=key,
            )
        self._rows[key] = readback
        self.updates += 1

    def delete(self, registry_key: str) -> bool:
        if not isinstance(registry_key, str):
            _fail_and_raise(
                "input_contract_invalid",
                "registry_key must be a string",
                TypeError,
                operation="ingest.registry.store.delete",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )
        self._guard_table(self.table_name)
        if registry_key not in self._rows:
            return False
        del self._rows[registry_key]
        self.deletes += 1
        return True

    def reserve(
        self,
        readback: MaterialIngestRegistryReadback,
    ) -> tuple[MaterialIngestRegistryReadback, bool]:
        """Lower-level exact reserve: returns ``(row, duplicate)``."""

        if not isinstance(readback, MaterialIngestRegistryReadback):
            _fail_and_raise(
                "input_contract_invalid",
                "store reserve requires an IngestRegistryReadback",
                TypeError,
                operation="ingest.registry.store.reserve",
                site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
            )
        key = readback.identity.registry_key
        existing = self._rows.get(key)
        if existing is not None:
            if existing.identity.request_hash != readback.identity.request_hash:
                _fail_and_raise(
                    "conflict",
                    "registry_key already exists with a different request_hash",
                    MaterialIngestRegistryConflictError,
                    operation="ingest.registry.store.reserve",
                    site="app.successor_runtime.capabilities.ingest_c7_registry.LocalSuccessorIngestRegistryStore",
                    registry_key=key,
                )
            return existing, True
        self._rows[key] = readback
        self.inserts += 1
        return readback, False


__all__ = [
    "DEFAULT_TIMESTAMP",
    "MATERIAL_INGEST_REGISTRY_AUTHORITY_SCHEMA",
    "MATERIAL_INGEST_REGISTRY_PORT_REF",
    "MATERIAL_INGEST_REGISTRY_READBACK_SCHEMA",
    "SUCCESSOR_MATERIAL_INGEST_SUBMISSION_REGISTRY_TABLE",
    "MaterialIngestRegistryAuthority",
    "MaterialIngestRegistryBackendUnavailableError",
    "MaterialIngestRegistryCompleteCommand",
    "MaterialIngestRegistryConflictError",
    "MaterialIngestRegistryCredentialError",
    "MaterialIngestRegistryError",
    "MaterialIngestRegistryForgetCommand",
    "MaterialIngestRegistryForgetResult",
    "MaterialIngestRegistryIdentity",
    "MaterialIngestRegistryIntegrityError",
    "MaterialIngestRegistryNotFoundError",
    "MaterialIngestRegistryReadback",
    "MaterialIngestRegistryReserveCommand",
    "MaterialIngestRegistryState",
    "MaterialIngestRegistryStore",
    "LocalSuccessorMaterialIngestRegistryStore",
    "complete_material_submission",
    "derive_registry_identity",
    "forget_material_submission",
    "reserve_material_submission",
]
