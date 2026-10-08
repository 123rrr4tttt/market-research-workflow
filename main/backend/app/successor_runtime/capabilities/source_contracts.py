"""Self-contained shared DTO/port vocabulary for the C2 source-library family.

C2 implementation modules must not import each other.  This single allowed
public module owns the cross-cell DTOs/contracts: authenticated project scope,
channel catalog, execution request, provider effect request/receipt/readback
outcomes, the C2.2 planning/collection outcome family and the C2.3 effect
ports.  C2.1 remains frozen and untouched; its DTOs are mirrored here with
identical semantics so digests and codecs stay compatible.
The tail of this module also owns the mechanical single-operation assembly
shared by C2.1 and C2.3: profile references, operation-contract digest
construction, payload-codec construction, and catalog/registry packaging.

The module imports nothing from C2 capability modules and performs no effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import (
    Any,
    Literal,
    NoReturn,
    Protocol,
    TypeAlias,
    TypeGuard,
    cast,
    get_args,
    runtime_checkable,
)

from functorial_kit import Failure

from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray as CanonicalJsonArray,  # required by get_type_hints on recursive aliases
    CanonicalJsonValue,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonAtom as FrozenJsonAtom,  # required by get_type_hints on recursive aliases
    FrozenJsonObject,
    FrozenJsonValue as FrozenJsonValue,  # required by get_type_hints on mirrored DTOs
    freeze_json_object,
    is_frozen_json_object,
    thaw_json_value,
)
from mrw_functorial_kit.core.source_semantics import source_contract_failures


SOURCE_TOTAL_CORE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


SourcePlainAtom: TypeAlias = None | bool | int | float | str
SourcePlainValue: TypeAlias = (
    SourcePlainAtom
    | list["SourcePlainValue"]
    | tuple["SourcePlainValue", ...]
    | frozenset[str]
    | dict[str, "SourcePlainValue"]
)
SourcePlainObject: TypeAlias = dict[str, SourcePlainValue]
SourceAuthorization: TypeAlias = None | Mapping[str, SourcePlainValue]


def source_plain_value_to_canonical(
    value: SourcePlainValue,
) -> CanonicalJsonValue:
    """Project source plain values onto the shared canonical JSON wire."""

    if is_frozen_json_object(value):
        return {
            key: source_plain_value_to_canonical(item)
            for key, item in value
        }
    if isinstance(value, dict):
        return {
            key: source_plain_value_to_canonical(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [source_plain_value_to_canonical(item) for item in value]
    if isinstance(value, frozenset):
        return [
            source_plain_value_to_canonical(item)
            for item in sorted(value)
        ]
    return value


def source_contract_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    owner: str,
    public_exception: str = "ValueError",
    public_message: str | None = None,
    **details: Any,
) -> Failure:
    """Build the canonical contract Failure used by C2 pure boundaries."""

    if code not in source_contract_failures.codes:
        details.setdefault("requested_code", code)
        code = "schema_contract_invalid"
    context = {
        "operation": operation,
        "site": site,
        "owner": owner,
        "public_exception": public_exception,
        "public_message": public_message or message,
        "witness": SOURCE_TOTAL_CORE_WITNESS,
        **details,
    }
    return source_contract_failures.fail(code, message, context)


def raise_source_contract_failure(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    """Lift a canonical contract Failure at a compatibility boundary."""

    context = failure.context or {}
    required = {"public_exception", "public_message"}
    if (
        not source_contract_failures.matches(failure)
        or not required <= set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=source_library_c2_shared.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("C2 contract lift context is invalid")
    # kit:boundary owner=source_library_c2_shared.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source.contract.failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context["public_message"]))


def _reject_source_contract(
    message: str,
    *,
    exception_type: type[Exception] = ValueError,
    operation: str = "source.resolve_and_acquire.contract",
    site: str = "source_contracts",
) -> NoReturn:
    """Lift a typed contract failure for the retained constructor ABI."""

    raise_source_contract_failure(
        source_contract_failure(
            "schema_contract_invalid",
            message,
            operation=operation,
            site=site,
            owner="source.resolve_and_acquire.shared.v2",
            public_exception=exception_type.__name__,
        ),
        exception_type,
    )


# --- C2.1 mirror: scope/catalog/mode/taxonomy/params/protocol/request ---
_SCOPE_DIGEST_NAMESPACE = b"mrw.project_scope.v2\n"
_RESOLVED_SCHEMA_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_RESOLVED_SCHEMAS = frozenset(
    {
        "public",
        "pg_catalog",
        "information_schema",
        "pg_toast",
        "pg_temp_1",
        "pg_toast_temp_1",
    }
)

SOURCE_ITEM_DEFINITION_SCHEMA_REF = "mrw.source.source-item-definition.v3"
SOURCE_ITEM_DEFINITION_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.source-item-definition.v1"
SOURCE_TAXONOMY_SCHEMA_REF = "mrw.source.source-taxonomy.v2"
SOURCE_TAXONOMY_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.source-taxonomy.v1"
SOURCE_MODE_SCHEMA_REF = "mrw.source.source-mode.v2"
SOURCE_MODE_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.source-mode.v1"
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = "mrw.source.execution-request.v2"
SOURCE_EXECUTION_REQUEST_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.execution-request.v1"
SOURCE_WARNING_SCHEMA_REF = "mrw.source.warning.v2"
SOURCE_WARNING_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.warning.v1"
SOURCE_REJECTION_SCHEMA_REF = "mrw.source.rejection.v2"
SOURCE_REJECTION_HISTORICAL_SCHEMA_REF = "mrw.successor.source-library.c2-1.rejection.v1"


SourceModeLiteral = Literal["protocol_search", "provider_harvest", "site_search", "url_execution"]
SourceWarningCode: TypeAlias = Literal[
    "SOURCE_MODE_INVALID_IGNORED",
    "SOURCE_MODE_OVERRIDDEN_BY_URLS",
    "SOURCE_MODE_COERCED_BY_SITE_SEARCH",
    "SITE_SEARCH_FORCED_HANDLER_CLUSTER",
    "GENERIC_WEB_INTERNAL_ADAPTER_DETECTED",
    "GENERIC_WEB_MODE_COERCED",
]
SOURCE_MODES: tuple[SourceModeLiteral, ...] = (
    "protocol_search",
    "provider_harvest",
    "site_search",
    "url_execution",
)

SourceRejectionCode: TypeAlias = Literal[
    "INVALID_ITEM",
    "DISABLED_ITEM",
    "INVALID_MODE",
    "FORBIDDEN_INTERNAL_ADAPTER",
    "RESOURCE_CEILING_EXCEEDED",
]
SOURCE_WARNING_CODES: frozenset[str] = frozenset(get_args(SourceWarningCode))
SOURCE_REJECTION_CODES: frozenset[str] = frozenset(get_args(SourceRejectionCode))


def _require_closed_code(value: Any, allowed: frozenset[str], field: str) -> None:
    if not _is_string(value) or value not in allowed:
        _reject_source_contract(f"unsupported {field} {value!r}", exception_type=ValueError)


def _is_string(value: object) -> TypeGuard[str]:
    """Retain constructor validation for values supplied by untyped callers."""
    return isinstance(value, str)


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int)


def _is_boolean(value: object) -> TypeGuard[bool]:
    return isinstance(value, bool)


def _is_credential_ref(value: object) -> TypeGuard[CredentialRef]:
    return isinstance(value, CredentialRef)


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


def _validate_resolved_schema(resolved_schema: str) -> str:
    if (
        not _is_string(resolved_schema)
        or len(resolved_schema.encode("utf-8")) > 63
        or _RESOLVED_SCHEMA_PATTERN.fullmatch(resolved_schema) is None
        or resolved_schema in _FORBIDDEN_RESOLVED_SCHEMAS
    ):
        _reject_source_contract(
            f"invalid resolved project schema identifier {resolved_schema!r}", exception_type=ValueError
        )
    return resolved_schema


def project_scope_digest(
    project_key: str,
    resolved_schema: str,
    project_registry_revision: int,
    incarnation: str,
) -> str:
    """Canonical scope digest matching ``compute_scope_digest`` byte-for-byte."""

    if not _is_string(project_key) or not project_key.strip():
        _reject_source_contract("project_key is required", exception_type=ValueError)
    _validate_resolved_schema(resolved_schema)
    if (
        not _is_integer(project_registry_revision)
        or isinstance(project_registry_revision, bool)
        or project_registry_revision < 0
    ):
        _reject_source_contract("project registry revision must be a non-negative integer", exception_type=ValueError)
    if (
        not _is_string(incarnation)
        or not incarnation
        or incarnation != incarnation.strip()
        or len(incarnation) > 128
    ):
        _reject_source_contract(
            "project scope incarnation must be a non-empty canonical identity", exception_type=ValueError
        )
    payload = (
        _SCOPE_DIGEST_NAMESPACE
        + project_key.encode("utf-8")
        + b"\n"
        + resolved_schema.encode("utf-8")
        + b"\n"
        + str(project_registry_revision).encode("ascii")
        + b"\n"
        + incarnation.encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthenticatedProjectScope:
    """Authenticated project scope bound to one active registry incarnation."""

    project_key: str
    registry_revision: int
    resolved_schema: str
    incarnation: str
    scope_digest: str

    def __post_init__(self) -> None:
        if not _is_string(self.project_key) or not self.project_key.strip():
            _reject_source_contract("AuthenticatedProjectScope.project_key is required", exception_type=ValueError)
        if (
            not _is_integer(self.registry_revision)
            or isinstance(self.registry_revision, bool)
            or self.registry_revision < 0
        ):
            _reject_source_contract(
                "AuthenticatedProjectScope.registry_revision must be non-negative int", exception_type=ValueError
            )
        _validate_resolved_schema(self.resolved_schema)
        if not _is_string(self.incarnation) or not self.incarnation.strip():
            _reject_source_contract("AuthenticatedProjectScope.incarnation is required", exception_type=ValueError)
        expected = project_scope_digest(
            self.project_key,
            self.resolved_schema,
            self.registry_revision,
            self.incarnation,
        )
        if self.scope_digest == "":
            object.__setattr__(self, "scope_digest", expected)
        else:
            require_hex64(self.scope_digest, "AuthenticatedProjectScope.scope_digest")
            if self.scope_digest != expected:
                _reject_source_contract(
                    "AuthenticatedProjectScope.scope_digest does not match the canonical project scope binding",
                    exception_type=ValueError,
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "project_key": self.project_key,
            "registry_revision": self.registry_revision,
            "resolved_schema": self.resolved_schema,
            "incarnation": self.incarnation,
            "scope_digest": self.scope_digest,
        }


@dataclass(frozen=True, slots=True)
class SourceItemDefinition:
    """Frozen source item definition; raw dictionaries stay at the codec edge."""

    revision: int
    incarnation: str
    content_digest: str
    schema_version: str = SOURCE_ITEM_DEFINITION_SCHEMA_REF
    item_key: str = ""
    channel_key: str = ""
    enabled: bool = True
    item_type: str | None = None
    managed_by: str | None = None
    params: FrozenJsonObject = field(default_factory=lambda: freeze_json_object({}))
    extra: FrozenJsonObject = field(default_factory=lambda: freeze_json_object({}))

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_ITEM_DEFINITION_SCHEMA_REF,
            SOURCE_ITEM_DEFINITION_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract(
                "SourceItemDefinition.schema_version is not the frozen schema", exception_type=ValueError
            )
        for name in ("item_key", "channel_key"):
            if not isinstance(getattr(self, name), str):
                _reject_source_contract(f"SourceItemDefinition.{name} must be a string", exception_type=TypeError)
        for name in ("item_type", "managed_by"):
            value = getattr(self, name)
            if value is not None and not _is_string(value):
                _reject_source_contract(
                    f"SourceItemDefinition.{name} must be a string or None", exception_type=ValueError
                )
        object.__setattr__(self, "params", _freeze(self.params))
        object.__setattr__(self, "extra", _freeze(self.extra))
        if not _is_integer(self.revision) or isinstance(self.revision, bool) or self.revision < 0:
            _reject_source_contract("SourceItemDefinition.revision must be non-negative int", exception_type=ValueError)
        if not _is_string(self.incarnation) or not self.incarnation.strip():
            _reject_source_contract("SourceItemDefinition.incarnation is required", exception_type=ValueError)
        expected = source_item_definition_content_digest(
            {
                "item_key": self.item_key,
                "channel_key": self.channel_key,
                "enabled": self.enabled,
                "item_type": self.item_type,
                "managed_by": self.managed_by,
                "params": dict(self.params),
                "extra": dict(self.extra),
                "revision": self.revision,
                "incarnation": self.incarnation,
            }
        )
        if self.content_digest == "":
            object.__setattr__(self, "content_digest", expected)
        else:
            require_hex64(self.content_digest, "SourceItemDefinition.content_digest")
            if self.content_digest != expected:
                _reject_source_contract(
                    "SourceItemDefinition.content_digest does not match item content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "item_key": self.item_key,
            "channel_key": self.channel_key,
            "enabled": self.enabled,
            "item_type": self.item_type,
            "managed_by": self.managed_by,
            "params": cast(SourcePlainValue, thaw_json_value(self.params)),
            "extra": cast(SourcePlainValue, thaw_json_value(self.extra)),
            "revision": self.revision,
            "incarnation": self.incarnation,
            "content_digest": self.content_digest,
            "schema_version": self.schema_version,
        }


def source_item_definition_content_digest(item: dict[str, Any]) -> str:
    """Canonical content digest for one typed source item definition."""

    return content_digest(
        {
            "schema": SOURCE_ITEM_DEFINITION_SCHEMA_REF,
            "item_key": item.get("item_key", ""),
            "channel_key": item.get("channel_key", ""),
            "enabled": bool(item.get("enabled", True)),
            "item_type": item.get("item_type"),
            "managed_by": item.get("managed_by"),
            "params": source_plain_value_to_canonical(item.get("params") or {}),
            "extra": source_plain_value_to_canonical(item.get("extra") or {}),
            "revision": item.get("revision"),
            "incarnation": item.get("incarnation", ""),
        }
    )


def source_item_definition_from_dict(item: dict[str, Any]) -> SourceItemDefinition:
    missing = [name for name in ("revision", "incarnation", "content_digest") if name not in item]
    if missing:
        _reject_source_contract(
            "source item definition requires explicit identity: " + ", ".join(missing), exception_type=ValueError
        )
    return SourceItemDefinition(
        schema_version=SOURCE_ITEM_DEFINITION_SCHEMA_REF,
        item_key=item.get("item_key", ""),
        channel_key=item.get("channel_key", ""),
        enabled=bool(item.get("enabled", True)),
        item_type=item.get("item_type"),
        managed_by=item.get("managed_by"),
        params=freeze_json_object(dict(item.get("params") or {})),
        extra=freeze_json_object(dict(item.get("extra") or {})),
        revision=item["revision"],
        incarnation=item["incarnation"],
        content_digest=item["content_digest"],
    )


@dataclass(frozen=True, slots=True)
class SourceMode:
    """One canonical selected mode."""

    mode: SourceModeLiteral
    version: str = "1"
    schema_version: str = SOURCE_MODE_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_MODE_SCHEMA_REF,
            SOURCE_MODE_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract("SourceMode.schema_version is not the frozen schema", exception_type=ValueError)
        if self.mode not in SOURCE_MODES:
            _reject_source_contract(f"unsupported SourceMode {self.mode!r}", exception_type=ValueError)
        if not _is_string(self.version) or not self.version.strip():
            _reject_source_contract("SourceMode.version is required", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class SourceTaxonomy:
    """Frozen taxonomy snapshot produced by the C2.1 resolve atom."""

    channel_family: str
    item_type: Literal["user_defined", "service_aggregated"]
    managed_by: Literal["user", "system"]
    expected_entry_type: str | None
    internal_adapter_only: bool
    site_search_authoritative: bool
    schema_version: str = SOURCE_TAXONOMY_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_TAXONOMY_SCHEMA_REF,
            SOURCE_TAXONOMY_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract("SourceTaxonomy.schema_version is not the frozen schema", exception_type=ValueError)
        if not _is_string(self.channel_family) or not self.channel_family.strip():
            _reject_source_contract("SourceTaxonomy.channel_family is required", exception_type=ValueError)
        if self.item_type not in {"user_defined", "service_aggregated"}:
            _reject_source_contract(f"unsupported item_type {self.item_type!r}", exception_type=ValueError)
        if self.managed_by not in {"user", "system"}:
            _reject_source_contract(f"unsupported managed_by {self.managed_by!r}", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "channel_family": self.channel_family,
            "item_type": self.item_type,
            "managed_by": self.managed_by,
            "expected_entry_type": self.expected_entry_type,
            "internal_adapter_only": self.internal_adapter_only,
            "site_search_authoritative": self.site_search_authoritative,
        }


@dataclass(frozen=True, slots=True)
class VersionedWarning:
    """Fixed-code, versioned warning with an ordered string payload."""

    code: SourceWarningCode
    version: str
    ordered_payload: tuple[str, ...]
    schema_version: str = SOURCE_WARNING_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_WARNING_SCHEMA_REF,
            SOURCE_WARNING_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract(
                "VersionedWarning.schema_version is not the frozen schema", exception_type=ValueError
            )
        if self.code not in SOURCE_WARNING_CODES:
            _reject_source_contract(f"unregistered warning code {self.code!r}", exception_type=ValueError)
        if not _is_string(self.version) or not self.version.strip():
            _reject_source_contract("VersionedWarning.version is required", exception_type=ValueError)
        object.__setattr__(self, "ordered_payload", tuple(self.ordered_payload))
        if not all(_is_string(item) for item in self.ordered_payload):
            _reject_source_contract("VersionedWarning.ordered_payload must contain strings", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "version": self.version,
            "ordered_payload": list(self.ordered_payload),
        }


_LEGACY_WARNING_PATTERNS: tuple[tuple[str, SourceWarningCode, tuple[int, ...]], ...] = (
    ("invalid_source_mode_ignored", "SOURCE_MODE_INVALID_IGNORED", (0,)),
    ("source_mode_overridden_by_urls", "SOURCE_MODE_OVERRIDDEN_BY_URLS", (0, 1)),
    (
        "source_mode_coerced_by_site_search_taxonomy",
        "SOURCE_MODE_COERCED_BY_SITE_SEARCH",
        (0, 1),
    ),
    ("site_search_forced_handler_cluster", "SITE_SEARCH_FORCED_HANDLER_CLUSTER", (0,)),
    (
        "generic_web_internal_adapter_detected",
        "GENERIC_WEB_INTERNAL_ADAPTER_DETECTED",
        (),
    ),
    ("generic_web_mode_coerced", "GENERIC_WEB_MODE_COERCED", (0, 1)),
)


def versioned_warning_from_legacy_string(value: str) -> VersionedWarning:
    """Map one legacy free-string warning to the frozen canonical union.

    Unknown strings fail closed: the successor union never stores fragile
    free-form warning text as a canonical code.
    """

    for prefix, code, payload_indexes in _LEGACY_WARNING_PATTERNS:
        if value == prefix:
            return VersionedWarning(code=code, version="1", ordered_payload=())
        marker = prefix + ":"
        if value.startswith(marker):
            rest = value[len(marker) :]
            parts = rest.split("->")
            payload = tuple(parts[index] for index in payload_indexes)
            return VersionedWarning(code=code, version="1", ordered_payload=payload)
    _reject_source_contract(f"legacy warning is not in the frozen C2.1 union: {value!r}", exception_type=ValueError)


@dataclass(frozen=True, slots=True)
class SourceRejection:
    """Versioned rejection union for fail-closed source-library resolution."""

    code: SourceRejectionCode
    version: str
    message: str
    schema_version: str = SOURCE_REJECTION_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_REJECTION_SCHEMA_REF,
            SOURCE_REJECTION_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract(
                "SourceRejection.schema_version is not the frozen schema", exception_type=ValueError
            )
        if self.code not in SOURCE_REJECTION_CODES:
            _reject_source_contract(f"unregistered rejection code {self.code!r}", exception_type=ValueError)
        if not _is_string(self.version) or not self.version.strip():
            _reject_source_contract("SourceRejection.version is required", exception_type=ValueError)
        if not _is_string(self.message):
            _reject_source_contract("SourceRejection.message must be a string", exception_type=TypeError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "version": self.version,
            "message": self.message,
        }


def _as_optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _as_optional_ymd(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if (
        len(parts) != 3
        or not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit())
        or len(parts[0]) != 4
        or len(parts[1]) != 2
        or len(parts[2]) != 2
    ):
        return None
    return raw


def _normalize_terms(value: object) -> tuple[str, ...]:
    out: list[str] = []
    if _is_object_sequence(value):
        for item in value:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    else:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def _normalize_site_entries(value: object) -> tuple[str, ...]:
    if _is_string(value):
        raw_entries: list[object] | tuple[object, ...] = [value]
    elif _is_object_sequence(value):
        raw_entries = value
    else:
        return ()
    out: list[str] = []
    for entry in raw_entries:
        site_url = str(entry or "").strip()
        if site_url and site_url not in out:
            out.append(site_url)
    return tuple(out)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


_PARAMS_KNOWN_FIELDS: tuple[str, ...] = (
    "query_terms",
    "max_items",
    "limit",
    "per_keyword_limit",
    "max_candidates",
    "ingest_limit",
    "page",
    "page_size",
    "max_pages",
    "days_back",
    "start_offset",
    "start_time",
    "end_time",
    "date_from",
    "date_to",
    "source_mode",
    "expected_entry_type",
    "urls",
    "site_entries",
    "site_entry_urls",
    "official_access_site_entries",
    "legacy_url_list_frozen",
    "_allow_internal_generic_web",
)


@dataclass(frozen=True, slots=True)
class NormalizedParamsSnapshot:
    """Typed, frozen projection of the legacy normalized search parameters."""

    query_terms: tuple[str, ...] = ()
    max_items: int | None = None
    limit: int | None = None
    per_keyword_limit: int | None = None
    max_candidates: int | None = None
    ingest_limit: int | None = None
    page: int | None = None
    page_size: int | None = None
    max_pages: int | None = None
    days_back: int | None = None
    start_offset: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    source_mode: SourceModeLiteral | None = None
    expected_entry_type: str | None = None
    urls: tuple[str, ...] = ()
    site_entries: tuple[str, ...] = ()
    site_entry_urls: tuple[str, ...] = ()
    official_access_site_entries: tuple[str, ...] = ()
    legacy_url_list_frozen: bool = False
    allow_internal_generic_web: bool = False
    extra: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "query_terms",
            "urls",
            "site_entries",
            "site_entry_urls",
            "official_access_site_entries",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                object.__setattr__(self, name, tuple(value))
        object.__setattr__(
            self,
            "extra",
            tuple(sorted((str(key), str(item)) for key, item in self.extra)),
        )
        for name in (
            "max_items",
            "limit",
            "per_keyword_limit",
            "max_candidates",
            "ingest_limit",
            "page",
            "page_size",
            "max_pages",
            "days_back",
            "start_offset",
        ):
            value = getattr(self, name)
            if value is not None and (not _is_integer(value) or isinstance(value, bool)):
                _reject_source_contract(
                    f"NormalizedParamsSnapshot.{name} must be int or None", exception_type=ValueError
                )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> NormalizedParamsSnapshot:
        values = dict(raw)

        def optional_int(name: str) -> int | None:
            parsed = _as_optional_int(values.get(name))
            return parsed if parsed is not None and parsed > 0 else None

        def optional_ymd(name: str) -> str | None:
            return _as_optional_ymd(values.get(name))

        known: dict[str, Any] = {
            "query_terms": _normalize_terms(values.get("query_terms")),
            "max_items": optional_int("max_items"),
            "limit": optional_int("limit"),
            "per_keyword_limit": optional_int("per_keyword_limit"),
            "max_candidates": optional_int("max_candidates"),
            "ingest_limit": optional_int("ingest_limit"),
            "page": optional_int("page"),
            "page_size": optional_int("page_size"),
            "max_pages": optional_int("max_pages"),
            "days_back": optional_int("days_back"),
            "start_offset": optional_int("start_offset"),
            "start_time": optional_ymd("start_time"),
            "end_time": optional_ymd("end_time"),
            "date_from": optional_ymd("date_from"),
            "date_to": optional_ymd("date_to"),
            "source_mode": values.get("source_mode"),
            "expected_entry_type": values.get("expected_entry_type"),
            "urls": _normalize_site_entries(values.get("urls")),
            "site_entries": _normalize_site_entries(values.get("site_entries")),
            "site_entry_urls": _normalize_site_entries(values.get("site_entry_urls")),
            "official_access_site_entries": _normalize_site_entries(values.get("official_access_site_entries")),
            "legacy_url_list_frozen": _as_bool(values.get("legacy_url_list_frozen"), False),
            "allow_internal_generic_web": _as_bool(values.get("_allow_internal_generic_web"), False),
        }
        extra = tuple((key, _json_text(value)) for key, value in values.items() if key not in _PARAMS_KNOWN_FIELDS)
        return cls(**known, extra=extra)

    def to_dict(self) -> SourcePlainObject:
        out: dict[str, Any] = {}
        attribute_for = {name: name for name in _PARAMS_KNOWN_FIELDS}
        attribute_for["_allow_internal_generic_web"] = "allow_internal_generic_web"
        for name in _PARAMS_KNOWN_FIELDS:
            if name not in out:
                out[name] = getattr(self, attribute_for[name])
        for key, text in self.extra:
            out[key] = json.loads(text)
        return out

    def to_plain(self) -> SourcePlainObject:
        return {
            "query_terms": list(self.query_terms),
            "max_items": self.max_items,
            "limit": self.limit,
            "per_keyword_limit": self.per_keyword_limit,
            "max_candidates": self.max_candidates,
            "ingest_limit": self.ingest_limit,
            "page": self.page,
            "page_size": self.page_size,
            "max_pages": self.max_pages,
            "days_back": self.days_back,
            "start_offset": self.start_offset,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "source_mode": self.source_mode,
            "expected_entry_type": self.expected_entry_type,
            "urls": list(self.urls),
            "site_entries": list(self.site_entries),
            "site_entry_urls": list(self.site_entry_urls),
            "official_access_site_entries": list(self.official_access_site_entries),
            "legacy_url_list_frozen": self.legacy_url_list_frozen,
            "_allow_internal_generic_web": self.allow_internal_generic_web,
            "extra": [[key, text] for key, text in self.extra],
        }


@dataclass(frozen=True, slots=True)
class FrontDoorConcurrencyStage:
    stage: str
    tasks_total: int
    requested_parallelism: int
    parallelism: int
    budget: int
    fail_fast: bool
    timeout_seconds: float | None

    def to_plain(self) -> SourcePlainObject:
        return {
            "stage": self.stage,
            "tasks_total": self.tasks_total,
            "requested_parallelism": self.requested_parallelism,
            "parallelism": self.parallelism,
            "budget": self.budget,
            "fail_fast": self.fail_fast,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class FrontDoorConcurrencyPlan:
    batch_size: int
    shared_budget: int
    search: FrontDoorConcurrencyStage
    url: FrontDoorConcurrencyStage

    def to_plain(self) -> SourcePlainObject:
        return {
            "batch_size": self.batch_size,
            "shared_budget": self.shared_budget,
            "search": self.search.to_plain(),
            "url": self.url.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class FrontDoorProtocol:
    """Frozen front-door protocol snapshot replacing the legacy dataclass."""

    item_key: str
    item_channel_key: str
    project_key: str | None
    front_door_owner: str
    execution_mode: str
    write_mode: str
    route_decision: str
    query_terms: tuple[str, ...]
    site_entries: tuple[str, ...]
    candidate_urls: tuple[str, ...]
    expected_entry_type: str | None
    write_to_pool: bool
    auto_ingest: bool
    ingest_limit: int
    force_url_routing_flow: bool
    prefer_crawler_first: bool
    search_parallelism: int
    routing_parallelism: int
    concurrency_plan: FrontDoorConcurrencyPlan
    source_tier: str
    onboarding_priority: str

    def to_plain(self) -> SourcePlainObject:
        return {
            "item_key": self.item_key,
            "item_channel_key": self.item_channel_key,
            "project_key": self.project_key,
            "front_door_owner": self.front_door_owner,
            "execution_mode": self.execution_mode,
            "write_mode": self.write_mode,
            "route_decision": self.route_decision,
            "query_terms": list(self.query_terms),
            "site_entries": list(self.site_entries),
            "candidate_urls": list(self.candidate_urls),
            "expected_entry_type": self.expected_entry_type,
            "write_to_pool": self.write_to_pool,
            "auto_ingest": self.auto_ingest,
            "ingest_limit": self.ingest_limit,
            "force_url_routing_flow": self.force_url_routing_flow,
            "prefer_crawler_first": self.prefer_crawler_first,
            "search_parallelism": self.search_parallelism,
            "routing_parallelism": self.routing_parallelism,
            "concurrency_plan": self.concurrency_plan.to_plain(),
            "source_tier": self.source_tier,
            "onboarding_priority": self.onboarding_priority,
        }


@dataclass(frozen=True, slots=True)
class SourceExecutionRequest:
    """Frozen successor-native execution request replacing the legacy DTO."""

    source_mode: SourceMode
    item_key: str
    item_channel_key: str
    project_key: str | None
    project_scope: AuthenticatedProjectScope
    item_revision: int
    item_incarnation: str
    item_content_digest: str
    catalog_revision: int
    catalog_incarnation: str
    catalog_digest: str
    params: NormalizedParamsSnapshot
    protocol: FrontDoorProtocol
    warnings: tuple[VersionedWarning, ...]
    taxonomy: SourceTaxonomy
    schema_version: str = SOURCE_EXECUTION_REQUEST_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_EXECUTION_REQUEST_SCHEMA_REF,
            SOURCE_EXECUTION_REQUEST_HISTORICAL_SCHEMA_REF,
        }:
            _reject_source_contract(
                "SourceExecutionRequest.schema_version is not the frozen schema", exception_type=ValueError
            )
        if not _is_integer(self.item_revision) or isinstance(self.item_revision, bool) or self.item_revision < 0:
            _reject_source_contract(
                "SourceExecutionRequest.item_revision must be non-negative int", exception_type=ValueError
            )
        for name, value in (
            ("item_incarnation", self.item_incarnation),
            ("catalog_incarnation", self.catalog_incarnation),
        ):
            if not _is_string(value) or not value.strip():
                _reject_source_contract(f"SourceExecutionRequest.{name} is required", exception_type=ValueError)
        require_hex64(
            self.item_content_digest,
            "SourceExecutionRequest.item_content_digest",
        )
        require_hex64(self.catalog_digest, "SourceExecutionRequest.catalog_digest")

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "source_mode": self.source_mode.to_plain(),
            "item_key": self.item_key,
            "item_channel_key": self.item_channel_key,
            "project_key": self.project_key,
            "project_scope": self.project_scope.to_plain(),
            "item_revision": self.item_revision,
            "item_incarnation": self.item_incarnation,
            "item_content_digest": self.item_content_digest,
            "catalog_revision": self.catalog_revision,
            "catalog_incarnation": self.catalog_incarnation,
            "catalog_digest": self.catalog_digest,
            "params": self.params.to_plain(),
            "protocol": self.protocol.to_plain(),
            "warnings": [warning.to_plain() for warning in self.warnings],
            "taxonomy": self.taxonomy.to_plain(),
        }


# --- C2.3 mirror: provider effect DTOs ---
SOURCE_PROVIDER_ACQUISITION_KIND = "source_library.execute_provider_effect.v1"
SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA = "mrw.source.provider-acquisition.payload.v2"
SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA = "mrw.successor.source-library.c2-3.provider-effect-request.v1"

CREDENTIAL_REF_SCHEMA = "mrw.source.provider-acquisition.credential-ref.v2"
CREDENTIAL_REF_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.credential-ref.v1"
CREDENTIAL_DECISION_SCHEMA = "mrw.source.provider-acquisition.credential-decision-receipt.v2"
PROVIDER_RECEIPT_SCHEMA = "mrw.source.provider-acquisition.provider-receipt.v2"
PROVIDER_RECEIPT_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.provider-receipt.v1"
PROVIDER_ATTEMPT_REF_SCHEMA = "mrw.source.provider-acquisition.attempt-ref.v2"
PROVIDER_ATTEMPT_REF_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.attempt-ref.v1"
CAPTURED_SOURCE_RECORD_REF_SCHEMA = "mrw.source.provider-acquisition.captured-source-record-ref.v2"
CAPTURED_SOURCE_RECORD_REF_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.captured-source-record-ref.v1"
STAGED_ARTIFACT_REF_SCHEMA = "mrw.source.provider-acquisition.staged-artifact-ref.v2"
STAGED_ARTIFACT_REF_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.staged-artifact-ref.v1"
AUTHORITATIVE_READBACK_SCHEMA = "mrw.source.provider-acquisition.authoritative-readback.v2"
NON_START_PROOF_SCHEMA = "mrw.source.provider-acquisition.non-start-proof.v2"
RESOURCE_POLICY_SCHEMA = "mrw.source.provider-acquisition.resource-policy.v2"
RESOURCE_POLICY_HISTORICAL_SCHEMA = "mrw.successor.source-library.c2-3.resource-policy.v1"
CANCEL_RECEIPT_SCHEMA = "mrw.source.provider-acquisition.cancel-receipt.v2"


SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET = 2
SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

ProviderRejectionCode: TypeAlias = Literal[
    "MISSING_CREDENTIAL",
    "INVALID_PARAMS",
    "UNAUTHORIZED",
    "UNSUPPORTED_PROVIDER",
    "REQUEST_BINDING_MISMATCH",
]
ProviderExecutionFailureCode: TypeAlias = Literal[
    "TRANSPORT",
    "TIMEOUT",
    "RATE_LIMIT",
    "PROVIDER_REJECTED",
    "ARTIFACT_WRITE",
    "RESOURCE_CEILING_EXCEEDED",
]
CredentialRejectionCode: TypeAlias = Literal["MISSING_CREDENTIAL", "UNAUTHORIZED"]
AggregateProviderFailureCode: TypeAlias = Literal[
    "MISSING_CREDENTIAL",
    "INVALID_PARAMS",
    "UNAUTHORIZED",
    "UNSUPPORTED_PROVIDER",
    "REQUEST_BINDING_MISMATCH",
    "TRANSPORT",
    "TIMEOUT",
    "RATE_LIMIT",
    "PROVIDER_REJECTED",
    "ARTIFACT_WRITE",
    "RESOURCE_CEILING_EXCEEDED",
    "OUTCOME_UNKNOWN",
    "CANCELLED",
]
ProviderEffectOperationKind: TypeAlias = Literal["source_library.execute_provider_effect.v1"]

SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES: frozenset[str] = frozenset(get_args(AggregateProviderFailureCode))
PROVIDER_REJECTION_CODES: frozenset[str] = frozenset(get_args(ProviderRejectionCode))
PROVIDER_EXECUTION_FAILURE_CODES: frozenset[str] = frozenset(get_args(ProviderExecutionFailureCode))
CREDENTIAL_REJECTION_CODES: frozenset[str] = frozenset(get_args(CredentialRejectionCode))


def _digest_payload(value: Any) -> str:
    return content_digest(value)


def provider_receipt_digest(
    *,
    receipt_id: str,
    provider: str,
    provider_job_id: str | None,
    provider_status: str,
    attempt_ref: str,
    observed_at: str,
    provider_job_uri: str | None = None,
    schema_version: str = PROVIDER_RECEIPT_SCHEMA,
) -> str:
    return content_digest(
        {
            "schema": schema_version,
            "receipt_id": receipt_id,
            "provider": provider,
            "provider_job_id": provider_job_id,
            "provider_status": provider_status,
            "attempt_ref": attempt_ref,
            "observed_at": observed_at,
            "provider_job_uri": provider_job_uri,
        }
    )


_CREDENTIAL_LOCATOR_PATTERN = re.compile(r"^credential:/[A-Za-z0-9][A-Za-z0-9._/-]*(/[A-Za-z0-9][A-Za-z0-9._/-]*)*$")


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered for marker in ("secret", "api_key", "apikey", "token", "password")
    ) and not value.startswith("credential:/")


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """Opaque credential locator; never carries secret bytes or raw material."""

    ref: str
    provider: str
    grant_scope: str
    required: bool = True
    schema_version: str = CREDENTIAL_REF_SCHEMA

    def __post_init__(self) -> None:
        if not _is_string(self.ref) or self.ref != self.ref.strip():
            _reject_source_contract(
                "CredentialRef.ref must be a non-whitespace opaque locator", exception_type=ValueError
            )
        if _CREDENTIAL_LOCATOR_PATTERN.fullmatch(self.ref) is None:
            _reject_source_contract(
                "CredentialRef.ref must use the opaque credential:/locator pattern; "
                "raw secret material, bare values and whitespace are rejected",
                exception_type=ValueError,
            )
        if _looks_like_secret(self.ref):
            _reject_source_contract(
                "CredentialRef.ref must not embed secret-like raw material", exception_type=ValueError
            )
        if not self.provider.strip() or self.provider != self.provider.strip():
            _reject_source_contract("CredentialRef.provider is required and must be trimmed", exception_type=ValueError)
        if self.schema_version not in {
            CREDENTIAL_REF_SCHEMA,
            CREDENTIAL_REF_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract("CredentialRef.schema_version is not the frozen schema", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "ref": self.ref,
            "provider": self.provider,
            "grant_scope": self.grant_scope,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class ProviderResourcePolicy:
    resource_class: str
    concurrency_key: str
    timeout_seconds: int
    retry_budget: int
    artifact_byte_ceiling: int
    rate_limit_budget: int
    reservation_lease_seconds: int
    schema_version: str = RESOURCE_POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {
            RESOURCE_POLICY_SCHEMA,
            RESOURCE_POLICY_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract(
                "ProviderResourcePolicy.schema_version is not the frozen schema", exception_type=ValueError
            )
        for name, value in (
            ("timeout_seconds", self.timeout_seconds),
            ("artifact_byte_ceiling", self.artifact_byte_ceiling),
            ("rate_limit_budget", self.rate_limit_budget),
            ("reservation_lease_seconds", self.reservation_lease_seconds),
        ):
            if not _is_integer(value) or isinstance(value, bool) or value <= 0:
                _reject_source_contract(
                    f"ProviderResourcePolicy.{name} must be positive int", exception_type=ValueError
                )
        if not _is_integer(self.retry_budget) or isinstance(self.retry_budget, bool) or self.retry_budget < 0:
            _reject_source_contract(
                "ProviderResourcePolicy.retry_budget must be non-negative int", exception_type=ValueError
            )
        if self.retry_budget > SOURCE_PROVIDER_ACQUISITION_MAX_RETRY_BUDGET:
            _reject_source_contract("retry_budget exceeds the frozen ceiling", exception_type=ValueError)
        if self.artifact_byte_ceiling > SOURCE_PROVIDER_ACQUISITION_MAX_ARTIFACT_BYTES:
            _reject_source_contract("artifact_byte_ceiling exceeds the frozen ceiling", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "resource_class": self.resource_class,
            "concurrency_key": self.concurrency_key,
            "timeout_seconds": self.timeout_seconds,
            "retry_budget": self.retry_budget,
            "artifact_byte_ceiling": self.artifact_byte_ceiling,
            "rate_limit_budget": self.rate_limit_budget,
            "reservation_lease_seconds": self.reservation_lease_seconds,
        }


@dataclass(frozen=True, slots=True)
class ProviderEffectRequest:
    """One exact-bound provider effect request; secrets never appear here."""

    schema_version: Literal[
        "mrw.source.provider-acquisition.payload.v2",
        "mrw.successor.source-library.c2-3.provider-effect-request.v1",
    ]
    operation_kind: ProviderEffectOperationKind
    request_id: str
    idempotency_key: str
    project_scope: AuthenticatedProjectScope
    item_key: str
    item_revision: int
    item_incarnation: str
    item_content_digest: str
    channel_key: str
    provider: str
    provider_config_ref: str
    effect_payload_codec_ref: str
    effect_payload_digest: str
    effect_payload: FrozenJsonObject
    credential_refs: tuple[CredentialRef, ...]
    policy: ProviderResourcePolicy
    catalog_revision: int
    catalog_incarnation: str
    catalog_digest: str
    terminal_output_only: bool = True
    request_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in {
            SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA,
            SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA,
        }:
            _reject_source_contract(
                "ProviderEffectRequest.schema_version is not the frozen schema", exception_type=ValueError
            )
        if self.operation_kind != SOURCE_PROVIDER_ACQUISITION_KIND:
            _reject_source_contract(f"unsupported operation kind {self.operation_kind!r}", exception_type=ValueError)
        if not self.request_id.strip() or not self.idempotency_key.strip():
            _reject_source_contract(
                "ProviderEffectRequest request/idempotency ids are required", exception_type=ValueError
            )
        require_hex64(self.item_content_digest, "ProviderEffectRequest.item_content_digest")
        require_hex64(self.effect_payload_digest, "ProviderEffectRequest.effect_payload_digest")
        require_hex64(self.catalog_digest, "ProviderEffectRequest.catalog_digest")
        object.__setattr__(self, "effect_payload", _freeze(self.effect_payload))
        object.__setattr__(
            self,
            "credential_refs",
            tuple(ref for ref in self.credential_refs if _is_credential_ref(ref)),
        )
        expected = _digest_payload(self._digest_payload())
        if self.request_digest == "":
            object.__setattr__(self, "request_digest", expected)
        else:
            require_hex64(self.request_digest, "ProviderEffectRequest.request_digest")
            if self.request_digest != expected:
                _reject_source_contract(
                    "ProviderEffectRequest.request_digest does not match content", exception_type=ValueError
                )

    def _digest_payload(self) -> dict[str, Any]:
        digest_schema = (
            "mrw.successor.source-library.c2-3.request.v1"
            if self.schema_version == SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA
            else self.schema_version
        )
        return {
            "schema": digest_schema,
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "project_scope": self.project_scope.to_plain(),
            "item_key": self.item_key,
            "item_revision": self.item_revision,
            "item_incarnation": self.item_incarnation,
            "item_content_digest": self.item_content_digest,
            "channel_key": self.channel_key,
            "provider": self.provider,
            "provider_config_ref": self.provider_config_ref,
            "effect_payload_codec_ref": self.effect_payload_codec_ref,
            "effect_payload_digest": self.effect_payload_digest,
            "effect_payload": thaw_json_value(self.effect_payload),
            "credential_refs": [ref.to_plain() for ref in self.credential_refs],
            "policy": self.policy.to_plain(),
            "catalog_revision": self.catalog_revision,
            "catalog_incarnation": self.catalog_incarnation,
            "catalog_digest": self.catalog_digest,
            "terminal_output_only": self.terminal_output_only,
        }

    def to_plain(self) -> SourcePlainObject:
        return {**self._digest_payload(), "request_digest": self.request_digest}


@dataclass(frozen=True, slots=True)
class ProviderAttemptRef:
    attempt_id: str
    request_digest: str
    provider: str
    epoch: int = 1
    schema_version: str = PROVIDER_ATTEMPT_REF_SCHEMA

    def __post_init__(self) -> None:
        if not self.attempt_id.strip():
            _reject_source_contract("ProviderAttemptRef.attempt_id is required", exception_type=ValueError)
        require_hex64(self.request_digest, "ProviderAttemptRef.request_digest")
        if not _is_integer(self.epoch) or isinstance(self.epoch, bool) or self.epoch < 1:
            _reject_source_contract("ProviderAttemptRef.epoch must be a positive integer", exception_type=ValueError)
        if self.schema_version not in {
            PROVIDER_ATTEMPT_REF_SCHEMA,
            PROVIDER_ATTEMPT_REF_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract(
                "ProviderAttemptRef.schema_version is not the frozen schema", exception_type=ValueError
            )

    def as_ref_string(self) -> str:
        return f"provider-attempt:{self.attempt_id}"

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "request_digest": self.request_digest,
            "provider": self.provider,
            "epoch": self.epoch,
        }


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    receipt_id: str
    provider: str
    provider_job_id: str | None
    provider_status: str
    attempt_ref: str
    observed_at: str
    provider_job_uri: str | None = None
    schema_version: str = PROVIDER_RECEIPT_SCHEMA
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in {
            PROVIDER_RECEIPT_SCHEMA,
            PROVIDER_RECEIPT_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract(
                "ProviderReceipt.schema_version is not the frozen schema", exception_type=ValueError
            )
        expected = provider_receipt_digest(
            receipt_id=self.receipt_id,
            provider=self.provider,
            provider_job_id=self.provider_job_id,
            provider_status=self.provider_status,
            attempt_ref=self.attempt_ref,
            observed_at=self.observed_at,
            provider_job_uri=self.provider_job_uri,
            schema_version=self.schema_version,
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "ProviderReceipt.receipt_digest")
            if self.receipt_digest != expected:
                _reject_source_contract(
                    "ProviderReceipt.receipt_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "provider": self.provider,
            "provider_job_id": self.provider_job_id,
            "provider_status": self.provider_status,
            "attempt_ref": self.attempt_ref,
            "observed_at": self.observed_at,
            "provider_job_uri": self.provider_job_uri,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class CapturedSourceRecordRef:
    record_id: str
    content_ref: str
    content_digest: str
    source_ref: str
    schema_version: str = CAPTURED_SOURCE_RECORD_REF_SCHEMA

    def __post_init__(self) -> None:
        if not self.record_id.strip() or not self.content_ref.strip():
            _reject_source_contract("CapturedSourceRecordRef identities are required", exception_type=ValueError)
        require_hex64(self.content_digest, "CapturedSourceRecordRef.content_digest")
        if self.schema_version not in {
            CAPTURED_SOURCE_RECORD_REF_SCHEMA,
            CAPTURED_SOURCE_RECORD_REF_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract(
                "CapturedSourceRecordRef.schema_version is not the frozen schema", exception_type=ValueError
            )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "content_ref": self.content_ref,
            "content_digest": self.content_digest,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class StagedArtifactRef:
    artifact_id: str
    content_ref: str
    content_digest: str
    byte_size: int
    staging_state: Literal["STAGED"] = "STAGED"
    schema_version: str = STAGED_ARTIFACT_REF_SCHEMA

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.content_ref.strip():
            _reject_source_contract("StagedArtifactRef identities are required", exception_type=ValueError)
        require_hex64(self.content_digest, "StagedArtifactRef.content_digest")
        if not _is_integer(self.byte_size) or isinstance(self.byte_size, bool) or self.byte_size < 0:
            _reject_source_contract("StagedArtifactRef.byte_size must be a non-negative int", exception_type=ValueError)
        if self.staging_state != "STAGED":
            _reject_source_contract("StagedArtifactRef.staging_state must be STAGED", exception_type=ValueError)
        if self.schema_version not in {
            STAGED_ARTIFACT_REF_SCHEMA,
            STAGED_ARTIFACT_REF_HISTORICAL_SCHEMA,
        }:
            _reject_source_contract(
                "StagedArtifactRef.schema_version is not the frozen schema", exception_type=ValueError
            )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "content_ref": self.content_ref,
            "content_digest": self.content_digest,
            "byte_size": self.byte_size,
            "staging_state": self.staging_state,
        }


@dataclass(frozen=True, slots=True)
class CredentialDecisionReceipt:
    """Redacted decision only; secret bytes never enter any payload or digest."""

    decision: Literal["RESOLVED", "MISSING", "UNAUTHORIZED"]
    credential_refs: tuple[str, ...]
    redacted_profile: FrozenJsonObject
    schema_version: str = CREDENTIAL_DECISION_SCHEMA
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.decision not in {"RESOLVED", "MISSING", "UNAUTHORIZED"}:
            _reject_source_contract(f"unsupported credential decision {self.decision!r}", exception_type=ValueError)
        object.__setattr__(self, "credential_refs", tuple(self.credential_refs))
        object.__setattr__(self, "redacted_profile", _freeze(self.redacted_profile))
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "decision": self.decision,
                "credential_refs": list(self.credential_refs),
                "redacted_profile": thaw_json_value(self.redacted_profile),
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "CredentialDecisionReceipt.receipt_digest")
            if self.receipt_digest != expected:
                _reject_source_contract(
                    "CredentialDecisionReceipt.receipt_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "credential_refs": list(self.credential_refs),
            "redacted_profile": cast(
                SourcePlainValue, thaw_json_value(self.redacted_profile)
            ),
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class AuthoritativeProviderReadback:
    attempt_ref: str
    provider_job_id: str | None
    terminal_status: Literal["COMPLETED", "FAILED", "CANCELLED"]
    readback_receipt_id: str
    observed_at: str
    schema_version: str = AUTHORITATIVE_READBACK_SCHEMA
    readback_digest: str = ""

    def __post_init__(self) -> None:
        if self.terminal_status not in {"COMPLETED", "FAILED", "CANCELLED"}:
            _reject_source_contract(
                f"unsupported terminal readback status {self.terminal_status!r}", exception_type=ValueError
            )
        if not self.readback_receipt_id.strip():
            _reject_source_contract("AuthoritativeProviderReadback.receipt id is required", exception_type=ValueError)
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "attempt_ref": self.attempt_ref,
                "provider_job_id": self.provider_job_id,
                "terminal_status": self.terminal_status,
                "readback_receipt_id": self.readback_receipt_id,
                "observed_at": self.observed_at,
            }
        )
        if self.readback_digest == "":
            object.__setattr__(self, "readback_digest", expected)
        else:
            require_hex64(self.readback_digest, "AuthoritativeProviderReadback.readback_digest")
            if self.readback_digest != expected:
                _reject_source_contract(
                    "AuthoritativeProviderReadback.readback_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "attempt_ref": self.attempt_ref,
            "provider_job_id": self.provider_job_id,
            "terminal_status": self.terminal_status,
            "readback_receipt_id": self.readback_receipt_id,
            "observed_at": self.observed_at,
            "readback_digest": self.readback_digest,
        }


@dataclass(frozen=True, slots=True)
class NonStartProof:
    attempt_ref: str
    evidence_locator: str
    schema_version: str = NON_START_PROOF_SCHEMA
    proof_digest: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_locator.strip():
            _reject_source_contract("NonStartProof.evidence_locator is required", exception_type=ValueError)
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "attempt_ref": self.attempt_ref,
                "evidence_locator": self.evidence_locator,
            }
        )
        if self.proof_digest == "":
            object.__setattr__(self, "proof_digest", expected)
        else:
            require_hex64(self.proof_digest, "NonStartProof.proof_digest")
            if self.proof_digest != expected:
                _reject_source_contract("NonStartProof.proof_digest does not match content", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "attempt_ref": self.attempt_ref,
            "evidence_locator": self.evidence_locator,
            "proof_digest": self.proof_digest,
        }


@dataclass(frozen=True, slots=True)
class NonStartUnprovable:
    attempt_ref: str
    reason: str

    def to_plain(self) -> SourcePlainObject:
        return {"attempt_ref": self.attempt_ref, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CancelReceipt:
    cancel_receipt_id: str
    attempt_ref: str
    request_digest: str
    cancel_status: Literal["CANCEL_ACCEPTED", "ALREADY_TERMINAL"] = "CANCEL_ACCEPTED"
    schema_version: str = CANCEL_RECEIPT_SCHEMA
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        require_hex64(self.request_digest, "CancelReceipt.request_digest")
        if self.cancel_status not in {"CANCEL_ACCEPTED", "ALREADY_TERMINAL"}:
            _reject_source_contract(f"unsupported cancel status {self.cancel_status!r}", exception_type=ValueError)
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "cancel_receipt_id": self.cancel_receipt_id,
                "attempt_ref": self.attempt_ref,
                "request_digest": self.request_digest,
                "cancel_status": self.cancel_status,
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "CancelReceipt.receipt_digest")
            if self.receipt_digest != expected:
                _reject_source_contract(
                    "CancelReceipt.receipt_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "cancel_receipt_id": self.cancel_receipt_id,
            "attempt_ref": self.attempt_ref,
            "request_digest": self.request_digest,
            "cancel_status": self.cancel_status,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class OrderedProviderFailure:
    order_index: int
    code: AggregateProviderFailureCode
    message: str
    source: str

    def __post_init__(self) -> None:
        if not _is_integer(self.order_index) or isinstance(self.order_index, bool) or self.order_index < 0:
            _reject_source_contract(
                "OrderedProviderFailure.order_index must be a non-negative int", exception_type=ValueError
            )
        _require_closed_code(self.code, SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES, "ordered provider failure code")
        if not _is_string(self.message):
            _reject_source_contract("OrderedProviderFailure.message must be a string", exception_type=ValueError)
        if not _is_string(self.source) or not self.source.strip():
            _reject_source_contract("OrderedProviderFailure.source is required", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "order_index": self.order_index,
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class CompletedProviderEffect:
    kind: Literal["completed"] = "completed"
    receipt: ProviderReceipt = field(default_factory=lambda: _placeholder_receipt())
    record_refs: tuple[CapturedSourceRecordRef, ...] = ()
    staged_artifact_refs: tuple[StagedArtifactRef, ...] = ()
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
                "record_refs": [ref.to_plain() for ref in self.record_refs],
                "staged_artifact_refs": [ref.to_plain() for ref in self.staged_artifact_refs],
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CompletedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CompletedProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "receipt": self.receipt.to_plain(),
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "staged_artifact_refs": [ref.to_plain() for ref in self.staged_artifact_refs],
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class AcceptedProviderEffect:
    kind: Literal["accepted"] = "accepted"
    receipt: ProviderReceipt = field(default_factory=lambda: _placeholder_receipt())
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "AcceptedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "AcceptedProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "receipt": self.receipt.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class PartiallyCompletedProviderEffect:
    kind: Literal["partially_completed"] = "partially_completed"
    receipt: ProviderReceipt = field(default_factory=lambda: _placeholder_receipt())
    record_refs: tuple[CapturedSourceRecordRef, ...] = ()
    ordered_failures: tuple[OrderedProviderFailure, ...] = ()
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
                "record_refs": [ref.to_plain() for ref in self.record_refs],
                "ordered_failures": [failure.to_plain() for failure in self.ordered_failures],
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest,
                "PartiallyCompletedProviderEffect.outcome_digest",
            )
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "PartiallyCompletedProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "receipt": self.receipt.to_plain(),
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "ordered_failures": [failure.to_plain() for failure in self.ordered_failures],
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class RejectedProviderEffect:
    kind: Literal["rejected"] = "rejected"
    code: ProviderRejectionCode = "INVALID_PARAMS"
    message: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        _require_closed_code(self.code, PROVIDER_REJECTION_CODES, "rejected provider code")
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "code": self.code,
                "message": self.message,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "RejectedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "RejectedProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class FailedProviderEffect:
    kind: Literal["failed"] = "failed"
    code: ProviderExecutionFailureCode = "TRANSPORT"
    message: str = ""
    retryable: bool = False
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        _require_closed_code(self.code, PROVIDER_EXECUTION_FAILURE_CODES, "failed provider code")
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "FailedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "FailedProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CancelledProviderEffect:
    kind: Literal["cancelled"] = "cancelled"
    cancel_receipt: CancelReceipt = field(
        default_factory=lambda: CancelReceipt(
            cancel_receipt_id="cancel:placeholder",
            attempt_ref="attempt:placeholder",
            request_digest=sha256_hex(b"placeholder"),
        )
    )
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "cancel_receipt": self.cancel_receipt.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CancelledProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CancelledProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "cancel_receipt": self.cancel_receipt.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class OutcomeUnknownProviderEffect:
    kind: Literal["outcome_unknown"] = "outcome_unknown"
    attempt_ref: str = ""
    reason: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "attempt_ref": self.attempt_ref,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "OutcomeUnknownProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "OutcomeUnknownProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "attempt_ref": self.attempt_ref,
            "reason": self.reason,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class ReconciledProviderEffect:
    kind: Literal["reconciled"] = "reconciled"
    attempt_ref: str = ""
    readback: AuthoritativeProviderReadback = field(
        default_factory=lambda: AuthoritativeProviderReadback(
            attempt_ref="attempt:placeholder",
            provider_job_id=None,
            terminal_status="COMPLETED",
            readback_receipt_id="readback:placeholder",
            observed_at="1970-01-01T00:00:00Z",
        )
    )
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _digest_payload(
            {
                "schema": "mrw.source.provider-acquisition.outcome.v2",
                "kind": self.kind,
                "attempt_ref": self.attempt_ref,
                "readback": self.readback.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "ReconciledProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "ReconciledProviderEffect.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "attempt_ref": self.attempt_ref,
            "readback": self.readback.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class ReadbackTerminal:
    readback: AuthoritativeProviderReadback

    def to_plain(self) -> SourcePlainObject:
        return {"kind": "terminal", "readback": self.readback.to_plain()}


@dataclass(frozen=True, slots=True)
class ReadbackWaiting:
    attempt_ref: str
    observed_at: str

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": "waiting",
            "attempt_ref": self.attempt_ref,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class ReadbackUnavailable:
    attempt_ref: str
    reason: str

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": "unavailable",
            "attempt_ref": self.attempt_ref,
            "reason": self.reason,
        }


ProviderReadbackResult: TypeAlias = ReadbackTerminal | ReadbackWaiting | ReadbackUnavailable


ProviderEffectOutcome: TypeAlias = (
    CompletedProviderEffect
    | AcceptedProviderEffect
    | PartiallyCompletedProviderEffect
    | RejectedProviderEffect
    | FailedProviderEffect
    | CancelledProviderEffect
    | OutcomeUnknownProviderEffect
    | ReconciledProviderEffect
)


def _placeholder_receipt() -> ProviderReceipt:
    return ProviderReceipt(
        receipt_id="receipt:placeholder",
        provider="fixture",
        provider_job_id=None,
        provider_status="PENDING",
        attempt_ref="attempt:placeholder",
        observed_at="1970-01-01T00:00:00Z",
    )


# --- C2.2 mirror: planning and collection outcome DTOs ---
SOURCE_PLANNING_PROTOCOL_SEARCH_KIND = "source_library.protocol_search.v1"
SOURCE_PLANNING_PROVIDER_HARVEST_KIND = "source_library.provider_harvest.v1"
SOURCE_PLANNING_SITE_SEARCH_KIND = "source_library.site_search.v1"
SOURCE_PLANNING_URL_EXECUTION_KIND = "source_library.url_execution.v1"
SourcePlanningOperationKind: TypeAlias = Literal[
    "source_library.protocol_search.v1",
    "source_library.provider_harvest.v1",
    "source_library.site_search.v1",
    "source_library.url_execution.v1",
]
SOURCE_PLANNING_KINDS: tuple[SourcePlanningOperationKind, ...] = (
    SOURCE_PLANNING_PROTOCOL_SEARCH_KIND,
    SOURCE_PLANNING_PROVIDER_HARVEST_KIND,
    SOURCE_PLANNING_SITE_SEARCH_KIND,
    SOURCE_PLANNING_URL_EXECUTION_KIND,
)
COLLECTION_TERMINAL_SCHEMA = "mrw.source.plan-source-mode.terminal.v2"
PROVIDER_HANDOFF_SCHEMA = "source_library.provider_handoff.v1"


PlanningRejectionCode: TypeAlias = Literal[
    "INVALID_REQUEST",
    "CHANNEL_NOT_FOUND",
    "CHANNEL_DISABLED",
    "FORBIDDEN_INTERNAL_ADAPTER",
    "RESOURCE_CEILING_EXCEEDED",
    "CATALOG_STALE",
]
SOURCE_PLANNING_FAILURE_CODES: frozenset[str] = frozenset(get_args(PlanningRejectionCode))


def _plain_digest(value: Any) -> str:
    return content_digest(value)


@dataclass(frozen=True, slots=True)
class OrderedFailure:
    order_index: int
    code: AggregateProviderFailureCode
    message: str
    source: str

    def __post_init__(self) -> None:
        if not _is_integer(self.order_index) or isinstance(self.order_index, bool) or self.order_index < 0:
            _reject_source_contract("OrderedFailure.order_index must be a non-negative int", exception_type=ValueError)
        _require_closed_code(self.code, SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES, "ordered collection failure code")
        if not _is_string(self.message):
            _reject_source_contract("OrderedFailure.message must be a string", exception_type=ValueError)
        if not _is_string(self.source) or not self.source.strip():
            _reject_source_contract("OrderedFailure.source is required", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "order_index": self.order_index,
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ProviderHandoff:
    handoff_id: str
    mode: SourceModeLiteral
    provider: str
    provider_job_id: str | None
    provider_status: str
    receipt_digest: str
    contract_version: str = PROVIDER_HANDOFF_SCHEMA

    def __post_init__(self) -> None:
        if not self.handoff_id.strip():
            _reject_source_contract("ProviderHandoff.handoff_id is required", exception_type=ValueError)
        require_hex64(self.receipt_digest, "ProviderHandoff.receipt_digest")
        if self.contract_version != PROVIDER_HANDOFF_SCHEMA:
            _reject_source_contract(
                "ProviderHandoff.contract_version is not the frozen contract", exception_type=ValueError
            )

    def to_plain(self) -> SourcePlainObject:
        return {
            "handoff_id": self.handoff_id,
            "mode": self.mode,
            "provider": self.provider,
            "provider_job_id": self.provider_job_id,
            "provider_status": self.provider_status,
            "receipt_digest": self.receipt_digest,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class SourceCollectionTerminal:
    terminal_id: str
    mode: SourceModeLiteral
    status: Literal["ok", "partial", "error", "accepted", "unknown"]
    records_count: int
    provider_handoff: ProviderHandoff | None = None
    ordered_failures: tuple[OrderedFailure, ...] = ()
    schema_version: str = COLLECTION_TERMINAL_SCHEMA
    collection_digest: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"ok", "partial", "error", "accepted", "unknown"}:
            _reject_source_contract(
                f"unsupported collection terminal status {self.status!r}", exception_type=ValueError
            )
        if not _is_integer(self.records_count) or isinstance(self.records_count, bool) or self.records_count < 0:
            _reject_source_contract(
                "SourceCollectionTerminal.records_count must be non-negative", exception_type=ValueError
            )
        expected = _plain_digest(
            {
                "schema_version": self.schema_version,
                "terminal_id": self.terminal_id,
                "mode": self.mode,
                "status": self.status,
                "records_count": self.records_count,
                "provider_handoff": (self.provider_handoff.to_plain() if self.provider_handoff is not None else None),
                "ordered_failures": [failure.to_plain() for failure in self.ordered_failures],
            }
        )
        if self.collection_digest == "":
            object.__setattr__(self, "collection_digest", expected)
        else:
            require_hex64(self.collection_digest, "SourceCollectionTerminal.collection_digest")
            if self.collection_digest != expected:
                _reject_source_contract(
                    "SourceCollectionTerminal.collection_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "schema_version": self.schema_version,
            "terminal_id": self.terminal_id,
            "mode": self.mode,
            "status": self.status,
            "records_count": self.records_count,
            "provider_handoff": (self.provider_handoff.to_plain() if self.provider_handoff is not None else None),
            "ordered_failures": [failure.to_plain() for failure in self.ordered_failures],
            "collection_digest": self.collection_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionCompleted:
    kind: Literal["completed"] = "completed"
    terminal: SourceCollectionTerminal = field(default_factory=lambda: _placeholder_terminal("ok"))
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "terminal": self.terminal.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionCompleted.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionCompleted.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionPartiallyCompleted:
    kind: Literal["partially_completed"] = "partially_completed"
    terminal: SourceCollectionTerminal = field(default_factory=lambda: _placeholder_terminal("partial"))
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "terminal": self.terminal.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest,
                "CollectionPartiallyCompleted.outcome_digest",
            )
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionPartiallyCompleted.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionProviderAccepted:
    kind: Literal["provider_accepted"] = "provider_accepted"
    terminal: SourceCollectionTerminal = field(default_factory=lambda: _placeholder_terminal("accepted"))
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "terminal": self.terminal.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionProviderAccepted.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionProviderAccepted.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionRejected:
    kind: Literal["rejected"] = "rejected"
    code: PlanningRejectionCode = "INVALID_REQUEST"
    message: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        _require_closed_code(self.code, SOURCE_PLANNING_FAILURE_CODES, "collection rejection code")
        if not _is_string(self.message):
            _reject_source_contract("CollectionRejected.message must be a string", exception_type=ValueError)
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "code": self.code,
                "message": self.message,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionRejected.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionRejected.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionFailed:
    kind: Literal["failed"] = "failed"
    code: ProviderExecutionFailureCode = "TRANSPORT"
    message: str = ""
    retryable: bool = False
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        _require_closed_code(
            self.code,
            PROVIDER_EXECUTION_FAILURE_CODES,
            "collection failure code",
        )
        if not _is_string(self.message):
            _reject_source_contract("CollectionFailed.message must be a string", exception_type=ValueError)
        if not _is_boolean(self.retryable):
            _reject_source_contract("CollectionFailed.retryable must be a bool", exception_type=ValueError)
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionFailed.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionFailed.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionCancelled:
    kind: Literal["cancelled"] = "cancelled"
    reason: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionCancelled.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionCancelled.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionOutcomeUnknown:
    kind: Literal["outcome_unknown"] = "outcome_unknown"
    reason: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.source.plan-source-mode.collection-outcome.v2",
                "kind": self.kind,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionOutcomeUnknown.outcome_digest")
            if self.outcome_digest != expected:
                _reject_source_contract(
                    "CollectionOutcomeUnknown.outcome_digest does not match content", exception_type=ValueError
                )

    def to_plain(self) -> SourcePlainObject:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "outcome_digest": self.outcome_digest,
        }


SourceCollectionOutcome: TypeAlias = (
    CollectionCompleted
    | CollectionPartiallyCompleted
    | CollectionProviderAccepted
    | CollectionRejected
    | CollectionFailed
    | CollectionCancelled
    | CollectionOutcomeUnknown
)


def _placeholder_terminal(status: str) -> SourceCollectionTerminal:
    return SourceCollectionTerminal(
        terminal_id="terminal:placeholder",
        mode="protocol_search",
        status=status,  # type: ignore[arg-type]
        records_count=0,
    )


# --- mode mapping ---


# --- C2.3 effect ports ---
@dataclass(frozen=True, slots=True)
class EphemeralCredentialLease:
    """Redacted lease over an opaque credential; no secret bytes."""

    lease_id: str
    credential_ref: str
    provider: str
    expires_at: str
    credential_decision_receipt: CredentialDecisionReceipt

    def to_plain(self) -> SourcePlainObject:
        return {
            "lease_id": self.lease_id,
            "credential_ref": self.credential_ref,
            "provider": self.provider,
            "expires_at": self.expires_at,
            "credential_decision_receipt": self.credential_decision_receipt.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class RedactedCredentialRejection:
    code: CredentialRejectionCode
    credential_ref: str
    message: str
    credential_decision_receipt: CredentialDecisionReceipt | None = None

    def __post_init__(self) -> None:
        _require_closed_code(self.code, CREDENTIAL_REJECTION_CODES, "credential rejection code")
        if not _is_string(self.credential_ref) or not self.credential_ref.strip():
            _reject_source_contract("RedactedCredentialRejection.credential_ref is required", exception_type=ValueError)
        if not _is_string(self.message):
            _reject_source_contract("RedactedCredentialRejection.message must be a string", exception_type=ValueError)

    def to_plain(self) -> SourcePlainObject:
        return {
            "code": self.code,
            "credential_ref": self.credential_ref,
            "message": self.message,
            "credential_decision_receipt": (
                self.credential_decision_receipt.to_plain() if self.credential_decision_receipt is not None else None
            ),
        }


@runtime_checkable
class CredentialResolverPort(Protocol):
    def resolve(
        self,
        ref: CredentialRef,
        authorization: SourceAuthorization,
    ) -> EphemeralCredentialLease | RedactedCredentialRejection:
        """Resolve one opaque credential ref or return a redacted rejection."""
        ...


@runtime_checkable
class ProviderEffectPort(Protocol):
    def execute(
        self,
        request: ProviderEffectRequest,
        ephemeral_credentials: tuple[EphemeralCredentialLease, ...],
    ) -> ProviderEffectOutcome:
        """Execute one provider effect through an authorized interpreter."""
        ...

    def cancel(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> CancelReceipt:
        """Request cancellation; never fabricates terminal state."""
        ...


@runtime_checkable
class ProviderReadbackPort(Protocol):
    def readback(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> ProviderReadbackResult:
        """Return authoritative, waiting or unavailable readback state."""
        ...

    def prove_not_started(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> NonStartProof | NonStartUnprovable:
        """Prove the attempt never started, or honestly return unprovable."""
        ...


@runtime_checkable
class ProviderEffectGateway(Protocol):
    credentials: CredentialResolverPort
    effect: ProviderEffectPort
    readback: ProviderReadbackPort

    def execute(
        self,
        request: ProviderEffectRequest,
        authorization: SourceAuthorization,
    ) -> ProviderEffectOutcome:
        """Resolve credentials then execute one provider effect."""
        ...


class ProviderCallTracer(Protocol):
    """Observable call log for deterministic fixture replay/shadow evidence."""

    provider_calls: list[str]


def _is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))
