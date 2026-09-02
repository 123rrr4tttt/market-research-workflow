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
from typing import Any, Protocol, runtime_checkable

INGEST_REGISTRY_PORT_REF = "mrw.successor.ingest-c7.registry.v1"
INGEST_REGISTRY_AUTHORITY_SCHEMA = "mrw.successor.ingest-c7.registry.authority.v1"
INGEST_REGISTRY_READBACK_SCHEMA = "mrw.successor.ingest-c7.registry.readback.v1"
SUCCESSOR_INGEST_SUBMISSION_REGISTRY_TABLE = "successor_ingest_submission_registry"
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00+00:00"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_CREDENTIAL_KEY_MARKERS = (
    "secret",
    "password",
    "credential",
    "api_key",
    "token_secret",
)


class IngestRegistryError(RuntimeError):
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


class IngestRegistryConflictError(IngestRegistryError):
    """A submission already occupies the key with different request content."""


class IngestRegistryNotFoundError(IngestRegistryError):
    """No successor submission row exists for the requested key."""


class IngestRegistryIntegrityError(IngestRegistryError):
    """A successor identity/content invariant was violated."""


class IngestRegistryCredentialError(IngestRegistryError):
    """A payload tried to carry a credential-like field into the registry."""


class IngestRegistryBackendUnavailableError(IngestRegistryError):
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
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must not be blank")
    return text


def _require_hex64(value: Any, name: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a 64-char lowercase hex digest")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a plain JSON object")
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
    raise TypeError(f"{path} must be JSON-compatible")


def _assert_no_credential_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            lowered = str(key).lower()
            if any(marker in lowered for marker in _CREDENTIAL_KEY_MARKERS):
                raise IngestRegistryCredentialError(
                    f"{child_path} is a credential-like field name and is "
                    "not allowed in the ingest submission registry"
                )
            _assert_no_credential_keys(item, child_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_credential_keys(item, f"{path}[{index}]")


class IngestRegistryState(StrEnum):
    SUBMITTED = "submitted"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


def _coerce_state(value: Any, name: str) -> IngestRegistryState:
    if isinstance(value, IngestRegistryState):
        return value
    if isinstance(value, str):
        try:
            return IngestRegistryState(value.strip().lower())
        except ValueError as exc:
            raise ValueError(f"{name} is not a supported lifecycle state") from exc
    raise TypeError(f"{name} must be an IngestRegistryState or its string value")


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
        IngestRegistryState.COMPLETED,
        IngestRegistryState.FAILED,
        IngestRegistryState.OUTCOME_UNKNOWN,
    }
)
_STATE_RANK = {
    IngestRegistryState.SUBMITTED: 0,
    IngestRegistryState.QUEUED: 1,
    IngestRegistryState.COMPLETED: 2,
    IngestRegistryState.FAILED: 2,
    IngestRegistryState.OUTCOME_UNKNOWN: 2,
}


@dataclass(frozen=True, slots=True)
class IngestRegistryAuthority:
    """Readback-only authority snapshot; every grant must stay False."""

    schema_ref: str = INGEST_REGISTRY_AUTHORITY_SCHEMA
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
            raise ValueError("IngestRegistryAuthority.schema_ref is required")
        object.__setattr__(self, "schema_ref", self.schema_ref.strip())
        for name in _AUTHORITY_BOOL_FIELDS:
            value = getattr(self, name)
            if value is not False:
                raise ValueError(
                    f"IngestRegistryAuthority.{name} must be False; "
                    "the successor registry grants no authority"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            **{name: getattr(self, name) for name in _AUTHORITY_BOOL_FIELDS},
        }


@dataclass(frozen=True, slots=True)
class IngestRegistryIdentity:
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
            raise ValueError(
                "registry_key must be trigger_type:project_key:idempotency_key"
            )
        expected_submission_id = _submission_id_for_key(registry_key)
        if submission_id != expected_submission_id:
            raise ValueError("submission_id does not match the registry key")
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
) -> IngestRegistryIdentity:
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
    return IngestRegistryIdentity(
        project_key=project_key,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        request_hash=_canonical_digest(payload),
        registry_key=registry_key,
        submission_id=_submission_id_for_key(registry_key),
    )


@dataclass(frozen=True, slots=True)
class IngestRegistryReserveCommand:
    identity: IngestRegistryIdentity
    subject_payload: Mapping[str, Any]
    request_payload: Mapping[str, Any]
    authority: IngestRegistryAuthority | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, IngestRegistryIdentity):
            raise TypeError("reserve command identity must be typed")
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
            IngestRegistryAuthority,
        ):
            raise TypeError("reserve command authority must be typed or None")


@dataclass(frozen=True, slots=True)
class IngestRegistryCompleteCommand:
    registry_key: str
    lifecycle_state: IngestRegistryState | str
    observed_status: str
    response_payload: Mapping[str, Any]
    task_id: str | None = None
    authority: IngestRegistryAuthority | None = None

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
                raise TypeError("task_id must be a string or None")
            task_id = self.task_id.strip()
            object.__setattr__(self, "task_id", task_id or None)
        if self.authority is not None and not isinstance(
            self.authority,
            IngestRegistryAuthority,
        ):
            raise TypeError("complete command authority must be typed or None")


@dataclass(frozen=True, slots=True)
class IngestRegistryForgetCommand:
    registry_key: str
    authority: IngestRegistryAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_key",
            _require_text(self.registry_key, "registry_key"),
        )
        if self.authority is not None and not isinstance(
            self.authority,
            IngestRegistryAuthority,
        ):
            raise TypeError("forget command authority must be typed or None")


def _readback_plain(readback: IngestRegistryReadback) -> dict[str, Any]:
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


def _readback_plain_digest(readback: IngestRegistryReadback) -> str:
    body = {"schema": INGEST_REGISTRY_READBACK_SCHEMA, **_readback_plain(readback)}
    return _canonical_digest(body)


@dataclass(frozen=True, slots=True)
class IngestRegistryReadback:
    """Immutable successor registry readback; the digest is derived."""

    identity: IngestRegistryIdentity
    lifecycle_state: IngestRegistryState
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
    authority: IngestRegistryAuthority = field(default_factory=IngestRegistryAuthority)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, IngestRegistryIdentity):
            raise TypeError("readback identity must be typed")
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
                raise TypeError("task_id must be a string or None")
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
            raise TypeError("revision must be an int")
        if self.revision < 1:
            raise ValueError("revision must be >= 1")
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            created_at = DEFAULT_TIMESTAMP
        else:
            created_at = self.created_at.strip()
        if not isinstance(self.updated_at, str) or not self.updated_at.strip():
            updated_at = DEFAULT_TIMESTAMP
        else:
            updated_at = self.updated_at.strip()
        authority = self.authority or IngestRegistryAuthority()
        if not isinstance(authority, IngestRegistryAuthority):
            raise TypeError("readback authority must be typed")
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
    authority: IngestRegistryAuthority,
) -> str:
    body = {
        "schema": INGEST_REGISTRY_READBACK_SCHEMA,
        "registry_key": registry_key,
        "deleted": deleted,
        "authority": authority.to_plain(),
    }
    return _canonical_digest(body)


@dataclass(frozen=True, slots=True)
class IngestRegistryForgetResult:
    registry_key: str
    deleted: bool
    readback_digest: str = field(default="", init=False, repr=False, compare=False)
    authority: IngestRegistryAuthority = field(default_factory=IngestRegistryAuthority)

    def __post_init__(self) -> None:
        registry_key = _require_text(self.registry_key, "registry_key")
        deleted = _require_bool(self.deleted, "deleted")
        authority = self.authority or IngestRegistryAuthority()
        if not isinstance(authority, IngestRegistryAuthority):
            raise TypeError("forget result authority must be typed")
        object.__setattr__(self, "registry_key", registry_key)
        object.__setattr__(self, "deleted", deleted)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(
            self,
            "readback_digest",
            _forget_plain_digest(registry_key, deleted, authority),
        )


@runtime_checkable
class IngestRegistryStore(Protocol):
    """Successor-only registry row interface; never names a donor table."""

    def find(self, registry_key: str) -> IngestRegistryReadback | None: ...

    def insert(self, readback: IngestRegistryReadback) -> None: ...

    def update(self, readback: IngestRegistryReadback) -> None: ...

    def delete(self, registry_key: str) -> bool: ...


def _reserve_readback(command: IngestRegistryReserveCommand) -> IngestRegistryReadback:
    identity = command.identity
    return IngestRegistryReadback(
        identity=identity,
        lifecycle_state=IngestRegistryState.SUBMITTED,
        observed_status=IngestRegistryState.SUBMITTED.value,
        duplicate=False,
        task_id=None,
        subject_payload=command.subject_payload,
        response_payload=None,
        value_ref=(
            f"{SUCCESSOR_INGEST_SUBMISSION_REGISTRY_TABLE}:{identity.submission_id}"
        ),
        revision=1,
        authority=command.authority or IngestRegistryAuthority(),
    )


def reserve_submission(
    store: IngestRegistryStore,
    command: IngestRegistryReserveCommand,
) -> IngestRegistryReadback:
    """Reserve once, replay an exact duplicate, or conflict on hash drift."""

    if not isinstance(command, IngestRegistryReserveCommand):
        raise TypeError("reserve_submission requires an IngestRegistryReserveCommand")
    _assert_no_credential_keys(command.subject_payload, "subject_payload")
    _assert_no_credential_keys(command.request_payload, "request_payload")
    identity = command.identity
    actual_hash = _canonical_digest(command.request_payload)
    if actual_hash != identity.request_hash:
        raise IngestRegistryIntegrityError(
            "reserve command request_payload does not match identity.request_hash",
            registry_key=identity.registry_key,
            request_hash=identity.request_hash,
        )
    existing = store.find(identity.registry_key)
    if existing is not None:
        if not isinstance(existing, IngestRegistryReadback):
            raise IngestRegistryIntegrityError(
                "successor store returned a non-readback row",
                registry_key=identity.registry_key,
            )
        if existing.identity.request_hash != identity.request_hash:
            raise IngestRegistryConflictError(
                "registry_key already exists with a different request_hash",
                registry_key=identity.registry_key,
                request_hash=identity.request_hash,
            )
        if existing.identity != identity:
            raise IngestRegistryIntegrityError(
                "registry_key identity fields drifted from the stored row",
                registry_key=identity.registry_key,
            )
        if existing.duplicate:
            return existing
        return replace(existing, duplicate=True)
    readback = _reserve_readback(command)
    store.insert(readback)
    return readback


def _response_digest(payload: Mapping[str, Any] | None) -> str:
    return _canonical_digest(_require_mapping(payload, "response_payload"))


def _completion_matches(
    existing: IngestRegistryReadback,
    command: IngestRegistryCompleteCommand,
) -> bool:
    return (
        existing.lifecycle_state == command.lifecycle_state
        and existing.observed_status == command.observed_status
        and existing.task_id == command.task_id
        and _response_digest(existing.response_payload)
        == _response_digest(command.response_payload)
    )


def complete_submission(
    store: IngestRegistryStore,
    command: IngestRegistryCompleteCommand,
) -> IngestRegistryReadback:
    """Write a typed completion readback or replay an exact terminal result."""

    if not isinstance(command, IngestRegistryCompleteCommand):
        raise TypeError("complete_submission requires an IngestRegistryCompleteCommand")
    _assert_no_credential_keys(command.response_payload, "response_payload")
    existing = store.find(command.registry_key)
    if existing is None:
        raise IngestRegistryNotFoundError(
            "cannot complete an absent ingest submission",
            registry_key=command.registry_key,
        )
    if not isinstance(existing, IngestRegistryReadback):
        raise IngestRegistryIntegrityError(
            "successor store returned a non-readback row",
            registry_key=command.registry_key,
        )
    if existing.lifecycle_state in _TERMINAL_STATES:
        if _completion_matches(existing, command):
            return existing
        raise IngestRegistryConflictError(
            "terminal ingest submission cannot be overwritten by a different "
            "completion",
            registry_key=command.registry_key,
        )
    if _completion_matches(existing, command):
        return existing
    if _STATE_RANK[command.lifecycle_state] < _STATE_RANK[existing.lifecycle_state]:
        raise IngestRegistryConflictError(
            "ingest submission lifecycle cannot move backwards",
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
    store.update(updated)
    return updated


def forget_submission(
    store: IngestRegistryStore,
    command: IngestRegistryForgetCommand,
) -> IngestRegistryForgetResult:
    """Delete one successor row; a missing row is an explicit no-op."""

    if not isinstance(command, IngestRegistryForgetCommand):
        raise TypeError("forget_submission requires an IngestRegistryForgetCommand")
    deleted = store.delete(command.registry_key)
    return IngestRegistryForgetResult(
        registry_key=command.registry_key,
        deleted=deleted,
        authority=command.authority or IngestRegistryAuthority(),
    )


class LocalSuccessorIngestRegistryStore:
    """Deterministic successor-only in-memory registry.

    The class deliberately accepts no table-name parameter: every write goes
    to ``successor_ingest_submission_registry`` and legacy/donor table writes
    are structurally impossible.
    """

    table_name: str = SUCCESSOR_INGEST_SUBMISSION_REGISTRY_TABLE
    legacy_table_writes = 0

    def __init__(self) -> None:
        self._rows: dict[str, IngestRegistryReadback] = {}
        self.legacy_table_writes = 0
        self.inserts = 0
        self.updates = 0
        self.deletes = 0

    def _guard_table(self, table_name: str) -> None:
        if table_name != self.table_name:
            self.legacy_table_writes += 1
            raise IngestRegistryIntegrityError(
                f"refusing table write outside {self.table_name}: {table_name}",
            )

    def find(self, registry_key: str) -> IngestRegistryReadback | None:
        if not isinstance(registry_key, str):
            raise TypeError("registry_key must be a string")
        return self._rows.get(registry_key)

    def insert(self, readback: IngestRegistryReadback) -> None:
        if not isinstance(readback, IngestRegistryReadback):
            raise TypeError("store insert requires an IngestRegistryReadback")
        self._guard_table(self.table_name)
        key = readback.identity.registry_key
        if key in self._rows:
            raise IngestRegistryConflictError(
                "successor registry row already exists",
                registry_key=key,
            )
        self._rows[key] = readback
        self.inserts += 1

    def update(self, readback: IngestRegistryReadback) -> None:
        if not isinstance(readback, IngestRegistryReadback):
            raise TypeError("store update requires an IngestRegistryReadback")
        self._guard_table(self.table_name)
        key = readback.identity.registry_key
        if key not in self._rows:
            raise IngestRegistryNotFoundError(
                "cannot update an absent successor registry row",
                registry_key=key,
            )
        if self._rows[key].identity.request_hash != readback.identity.request_hash:
            raise IngestRegistryConflictError(
                "successor registry row request_hash cannot change in place",
                registry_key=key,
            )
        self._rows[key] = readback
        self.updates += 1

    def delete(self, registry_key: str) -> bool:
        if not isinstance(registry_key, str):
            raise TypeError("registry_key must be a string")
        self._guard_table(self.table_name)
        if registry_key not in self._rows:
            return False
        del self._rows[registry_key]
        self.deletes += 1
        return True

    def reserve(
        self,
        readback: IngestRegistryReadback,
    ) -> tuple[IngestRegistryReadback, bool]:
        """Lower-level exact reserve: returns ``(row, duplicate)``."""

        if not isinstance(readback, IngestRegistryReadback):
            raise TypeError("store reserve requires an IngestRegistryReadback")
        key = readback.identity.registry_key
        existing = self._rows.get(key)
        if existing is not None:
            if existing.identity.request_hash != readback.identity.request_hash:
                raise IngestRegistryConflictError(
                    "registry_key already exists with a different request_hash",
                    registry_key=key,
                )
            return existing, True
        self._rows[key] = readback
        self.inserts += 1
        return readback, False


__all__ = [
    "DEFAULT_TIMESTAMP",
    "INGEST_REGISTRY_AUTHORITY_SCHEMA",
    "INGEST_REGISTRY_PORT_REF",
    "INGEST_REGISTRY_READBACK_SCHEMA",
    "SUCCESSOR_INGEST_SUBMISSION_REGISTRY_TABLE",
    "IngestRegistryAuthority",
    "IngestRegistryBackendUnavailableError",
    "IngestRegistryCompleteCommand",
    "IngestRegistryConflictError",
    "IngestRegistryCredentialError",
    "IngestRegistryError",
    "IngestRegistryForgetCommand",
    "IngestRegistryForgetResult",
    "IngestRegistryIdentity",
    "IngestRegistryIntegrityError",
    "IngestRegistryNotFoundError",
    "IngestRegistryReadback",
    "IngestRegistryReserveCommand",
    "IngestRegistryState",
    "IngestRegistryStore",
    "LocalSuccessorIngestRegistryStore",
    "complete_submission",
    "derive_registry_identity",
    "forget_submission",
    "reserve_submission",
]
