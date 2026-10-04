"""Self-contained shared DTO/port vocabulary for the C2 source-library family.

C2 implementation modules must not import each other.  This single allowed
public module owns the cross-cell DTOs/contracts: authenticated project scope,
channel catalog, execution request, provider effect request/receipt/readback
outcomes, the C2.2 planning/collection outcome family and the C2.3 effect
ports.  C2.1 remains frozen and untouched; its DTOs are mirrored here with
identical semantics so digests and codecs stay compatible.

The module imports nothing from C2 capability modules and performs no effect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    FrozenJsonValue,  # noqa: F401 - required by get_type_hints on mirrored DTOs
    freeze_json_object,
)
from app.successor_runtime.research.object_types import ObjectType

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

SOURCE_ITEM_DEFINITION_SCHEMA_REF = (
    "mrw.successor.source-library.c2-1.source-item-definition.v1"
)
SOURCE_TAXONOMY_SCHEMA_REF = "mrw.successor.source-library.c2-1.source-taxonomy.v1"
SOURCE_MODE_SCHEMA_REF = "mrw.successor.source-library.c2-1.source-mode.v1"
SOURCE_EXECUTION_REQUEST_SCHEMA_REF = (
    "mrw.successor.source-library.c2-1.execution-request.v1"
)
SOURCE_WARNING_SCHEMA_REF = "mrw.successor.source-library.c2-1.warning.v1"
SOURCE_REJECTION_SCHEMA_REF = "mrw.successor.source-library.c2-1.rejection.v1"
SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF = (
    "mrw.successor.source-library.c2-1.observation.v1"
)
RESOURCE_CEILING_SCHEMA_REF = "mrw.successor.source-library.c2-1.resource-ceiling.v1"
DEPLOYMENT_CATALOG_SCHEMA_REF = (
    "mrw.successor.source-library.c2-1.deployment-catalog.v1"
)

SOURCE_MODE_TYPE = ObjectType("SourceMode.v1")
AUTHENTICATED_PROJECT_SCOPE_TYPE = ObjectType("AuthenticatedProjectScope.v1")
CHANNEL_CATALOG_SNAPSHOT_TYPE = ObjectType("ChannelCatalogSnapshot.v1")
SOURCE_ITEM_DEFINITION_TYPE = ObjectType("SourceItemDefinition.v1")
SOURCE_TAXONOMY_TYPE = ObjectType("SourceTaxonomy.v1")
SOURCE_EXECUTION_REQUEST_TYPE = ObjectType("SourceExecutionRequest.v1")
SOURCE_WARNING_TYPE = ObjectType("SourceWarning.v1")
SOURCE_REJECTION_TYPE = ObjectType("SourceRejection.v1")
SOURCE_RESOLUTION_PAYLOAD_TYPE = ObjectType("SourceResolutionPayload.v1")
SOURCE_RESOLUTION_RESULT_TYPE = ObjectType("SourceResolutionResult.v1")
SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE = SOURCE_RESOLUTION_PAYLOAD_TYPE
SOURCE_LIBRARY_C2_1_RESULT_TYPE = SOURCE_RESOLUTION_RESULT_TYPE

SourceModeLiteral = Literal[
    "protocol_search", "provider_harvest", "site_search", "url_execution"
]
SOURCE_MODES: tuple[SourceModeLiteral, ...] = (
    "protocol_search",
    "provider_harvest",
    "site_search",
    "url_execution",
)

SOURCE_WARNING_CODES: frozenset[str] = frozenset(
    {
        "SOURCE_MODE_INVALID_IGNORED",
        "SOURCE_MODE_OVERRIDDEN_BY_URLS",
        "SOURCE_MODE_COERCED_BY_SITE_SEARCH",
        "SITE_SEARCH_FORCED_HANDLER_CLUSTER",
        "GENERIC_WEB_INTERNAL_ADAPTER_DETECTED",
        "GENERIC_WEB_MODE_COERCED",
    }
)
SOURCE_REJECTION_CODES: frozenset[str] = frozenset(
    {
        "INVALID_ITEM",
        "DISABLED_ITEM",
        "INVALID_MODE",
        "FORBIDDEN_INTERNAL_ADAPTER",
        "RESOURCE_CEILING_EXCEEDED",
    }
)


def _derive_digest(value: Any) -> str:
    return content_digest(value)


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


def _validate_resolved_schema(resolved_schema: str) -> str:
    if (
        not isinstance(resolved_schema, str)
        or len(resolved_schema.encode("utf-8")) > 63
        or _RESOLVED_SCHEMA_PATTERN.fullmatch(resolved_schema) is None
        or resolved_schema in _FORBIDDEN_RESOLVED_SCHEMAS
    ):
        raise ValueError(
            f"invalid resolved project schema identifier {resolved_schema!r}"
        )
    return resolved_schema


def project_scope_digest(
    project_key: str,
    resolved_schema: str,
    project_registry_revision: int,
    incarnation: str,
) -> str:
    """Canonical scope digest matching ``compute_scope_digest`` byte-for-byte."""

    if not isinstance(project_key, str) or not project_key.strip():
        raise ValueError("project_key is required")
    _validate_resolved_schema(resolved_schema)
    if (
        not isinstance(project_registry_revision, int)
        or isinstance(project_registry_revision, bool)
        or project_registry_revision < 0
    ):
        raise ValueError("project registry revision must be a non-negative integer")
    if (
        not isinstance(incarnation, str)
        or not incarnation
        or incarnation != incarnation.strip()
        or len(incarnation) > 128
    ):
        raise ValueError(
            "project scope incarnation must be a non-empty canonical identity"
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
class VersionedSchema:
    """Explicit schema ref, per-field requiredness map and pinned digest."""

    schema_ref: str
    field_requiredness: tuple[tuple[str, bool], ...]
    schema_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.schema_ref, str) or not self.schema_ref:
            raise ValueError("VersionedSchema.schema_ref is required")
        object.__setattr__(
            self,
            "field_requiredness",
            tuple(
                (str(name), bool(required))
                for name, required in self.field_requiredness
            ),
        )
        expected = content_digest(
            {
                "schema": "mrw.successor.source-library.c2-1.schema.v1",
                "schema_ref": self.schema_ref,
                "field_requiredness": self.field_requiredness,
            }
        )
        if self.schema_digest == "":
            object.__setattr__(self, "schema_digest", expected)
        else:
            require_hex64(self.schema_digest, "VersionedSchema.schema_digest")
            if self.schema_digest != expected:
                raise ValueError("VersionedSchema.schema_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "field_requiredness": [
                [name, required] for name, required in self.field_requiredness
            ],
            "schema_digest": self.schema_digest,
        }


SOURCE_ITEM_DEFINITION_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_ITEM_DEFINITION_SCHEMA_REF,
    field_requiredness=(
        ("item_key", True),
        ("channel_key", True),
        ("enabled", True),
        ("item_type", False),
        ("managed_by", False),
        ("params", True),
        ("extra", True),
        ("revision", True),
        ("incarnation", True),
        ("content_digest", True),
        ("schema_version", True),
    ),
)
SOURCE_TAXONOMY_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_TAXONOMY_SCHEMA_REF,
    field_requiredness=(
        ("channel_family", True),
        ("item_type", True),
        ("managed_by", True),
        ("expected_entry_type", False),
        ("internal_adapter_only", True),
        ("site_search_authoritative", True),
        ("schema_version", True),
    ),
)
SOURCE_MODE_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_MODE_SCHEMA_REF,
    field_requiredness=(
        ("mode", True),
        ("version", True),
        ("schema_version", True),
    ),
)
SOURCE_EXECUTION_REQUEST_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_EXECUTION_REQUEST_SCHEMA_REF,
    field_requiredness=(
        ("source_mode", True),
        ("item_key", True),
        ("item_channel_key", True),
        ("project_key", False),
        ("project_scope", True),
        ("item_revision", True),
        ("item_incarnation", True),
        ("item_content_digest", True),
        ("catalog_revision", True),
        ("catalog_incarnation", True),
        ("catalog_digest", True),
        ("params", True),
        ("protocol", True),
        ("warnings", True),
        ("taxonomy", True),
        ("schema_version", True),
    ),
)
SOURCE_WARNING_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_WARNING_SCHEMA_REF,
    field_requiredness=(
        ("code", True),
        ("version", True),
        ("ordered_payload", True),
        ("schema_version", True),
    ),
)
SOURCE_REJECTION_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_REJECTION_SCHEMA_REF,
    field_requiredness=(
        ("code", True),
        ("version", True),
        ("message", True),
        ("schema_version", True),
    ),
)
SOURCE_RESOLUTION_OBSERVATION_SCHEMA = VersionedSchema(
    schema_ref=SOURCE_RESOLUTION_OBSERVATION_SCHEMA_REF,
    field_requiredness=(
        ("observation_profile", True),
        ("project_scope", True),
        ("item_revision", True),
        ("item_incarnation", True),
        ("item_content_digest", True),
        ("catalog_revision", True),
        ("catalog_incarnation", True),
        ("catalog_digest", True),
        ("normalized_params", True),
        ("source_mode", True),
        ("taxonomy", True),
        ("warnings", True),
        ("protocol", True),
        ("observation_digest", True),
        ("schema_version", True),
    ),
)


@dataclass(frozen=True, slots=True)
class AuthenticatedProjectScope:
    """Authenticated project scope bound to one active registry incarnation."""

    project_key: str
    registry_revision: int
    resolved_schema: str
    incarnation: str
    scope_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.project_key, str) or not self.project_key.strip():
            raise ValueError("AuthenticatedProjectScope.project_key is required")
        if (
            not isinstance(self.registry_revision, int)
            or isinstance(self.registry_revision, bool)
            or self.registry_revision < 0
        ):
            raise ValueError(
                "AuthenticatedProjectScope.registry_revision must be non-negative int"
            )
        _validate_resolved_schema(self.resolved_schema)
        if not isinstance(self.incarnation, str) or not self.incarnation.strip():
            raise ValueError("AuthenticatedProjectScope.incarnation is required")
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
                raise ValueError(
                    "AuthenticatedProjectScope.scope_digest does not match "
                    "the canonical project scope binding"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "project_key": self.project_key,
            "registry_revision": self.registry_revision,
            "resolved_schema": self.resolved_schema,
            "incarnation": self.incarnation,
            "scope_digest": self.scope_digest,
        }


@dataclass(frozen=True, slots=True)
class ChannelCatalogEntry:
    """One immutable channel identity inside the frozen catalog snapshot."""

    channel_key: str
    provider: str = ""
    provider_type: str = ""
    enabled: bool = True
    extra: FrozenJsonObject = field(default_factory=lambda: freeze_json_object({}))

    def __post_init__(self) -> None:
        if not isinstance(self.channel_key, str) or not self.channel_key.strip():
            raise ValueError("ChannelCatalogEntry.channel_key is required")
        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(self, "provider_type", self.provider_type.strip().lower())
        object.__setattr__(self, "extra", _freeze(self.extra))

    def to_plain_dict(self) -> dict[str, Any]:
        return {
            "channel_key": self.channel_key,
            "provider": self.provider,
            "provider_type": self.provider_type,
            "enabled": self.enabled,
            "extra": dict(self.extra),
        }


def channel_catalog_digest(
    *,
    schema_version: str,
    revision: int,
    incarnation: str,
    entries: tuple[ChannelCatalogEntry, ...],
) -> str:
    return _derive_digest(
        {
            "schema": schema_version,
            "revision": revision,
            "incarnation": incarnation,
            "entries": tuple(
                (
                    entry.channel_key,
                    entry.provider,
                    entry.provider_type,
                    entry.enabled,
                    dict(entry.extra),
                )
                for entry in entries
            ),
        }
    )


@dataclass(frozen=True, slots=True)
class ChannelCatalogSnapshot:
    """Immutable channel catalog snapshot with exact revision/incarnation/digest."""

    schema_version: Literal["mrw.successor.source-library.channel-catalog.v1"]
    revision: int
    incarnation: str
    digest: str
    entries: tuple[ChannelCatalogEntry, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("ChannelCatalogSnapshot.revision must be non-negative int")
        if not isinstance(self.incarnation, str) or not self.incarnation.strip():
            raise ValueError("ChannelCatalogSnapshot.incarnation is required")
        keys = tuple(entry.channel_key for entry in self.entries)
        if len(keys) != len(set(keys)):
            raise ValueError("ChannelCatalogSnapshot channel keys must be unique")
        expected = channel_catalog_digest(
            schema_version=self.schema_version,
            revision=self.revision,
            incarnation=self.incarnation,
            entries=self.entries,
        )
        if self.digest == "":
            object.__setattr__(self, "digest", expected)
        else:
            require_hex64(self.digest, "ChannelCatalogSnapshot.digest")
            if self.digest != expected:
                raise ValueError("ChannelCatalogSnapshot.digest does not match content")

    def entry_by_key(self, channel_key: str) -> ChannelCatalogEntry | None:
        for entry in self.entries:
            if entry.channel_key == channel_key:
                return entry
        return None

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "digest": self.digest,
            "entries": [entry.to_plain_dict() for entry in self.entries],
        }


def build_channel_catalog_snapshot(
    *,
    revision: int = 1,
    incarnation: str = "channel-catalog-incarnation-1",
    entries: tuple[ChannelCatalogEntry, ...] | list[ChannelCatalogEntry] = (),
) -> ChannelCatalogSnapshot:
    return ChannelCatalogSnapshot(
        schema_version="mrw.successor.source-library.channel-catalog.v1",
        revision=revision,
        incarnation=incarnation,
        digest="",
        entries=tuple(entries),
    )


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
        if self.schema_version != SOURCE_ITEM_DEFINITION_SCHEMA_REF:
            raise ValueError(
                "SourceItemDefinition.schema_version is not the frozen schema"
            )
        for name in ("item_key", "channel_key"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"SourceItemDefinition.{name} must be a string")
        for name in ("item_type", "managed_by"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"SourceItemDefinition.{name} must be a string or None"
                )
        object.__setattr__(self, "params", _freeze(self.params))
        object.__setattr__(self, "extra", _freeze(self.extra))
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("SourceItemDefinition.revision must be non-negative int")
        if not isinstance(self.incarnation, str) or not self.incarnation.strip():
            raise ValueError("SourceItemDefinition.incarnation is required")
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
                raise ValueError(
                    "SourceItemDefinition.content_digest does not match item content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "channel_key": self.channel_key,
            "enabled": self.enabled,
            "item_type": self.item_type,
            "managed_by": self.managed_by,
            "params": dict(self.params),
            "extra": dict(self.extra),
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
            "params": dict(item.get("params") or {}),
            "extra": dict(item.get("extra") or {}),
            "revision": item.get("revision"),
            "incarnation": item.get("incarnation", ""),
        }
    )


def source_item_definition_from_dict(item: dict[str, Any]) -> SourceItemDefinition:
    missing = [
        name
        for name in ("revision", "incarnation", "content_digest")
        if name not in item
    ]
    if missing:
        raise ValueError(
            "source item definition requires explicit identity: " + ", ".join(missing)
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
        if self.schema_version != SOURCE_MODE_SCHEMA_REF:
            raise ValueError("SourceMode.schema_version is not the frozen schema")
        if self.mode not in SOURCE_MODES:
            raise ValueError(f"unsupported SourceMode {self.mode!r}")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("SourceMode.version is required")

    def to_plain(self) -> dict[str, Any]:
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
        if self.schema_version != SOURCE_TAXONOMY_SCHEMA_REF:
            raise ValueError("SourceTaxonomy.schema_version is not the frozen schema")
        if not isinstance(self.channel_family, str) or not self.channel_family.strip():
            raise ValueError("SourceTaxonomy.channel_family is required")
        if self.item_type not in {"user_defined", "service_aggregated"}:
            raise ValueError(f"unsupported item_type {self.item_type!r}")
        if self.managed_by not in {"user", "system"}:
            raise ValueError(f"unsupported managed_by {self.managed_by!r}")

    def to_plain(self) -> dict[str, Any]:
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

    code: str
    version: str
    ordered_payload: tuple[str, ...]
    schema_version: str = SOURCE_WARNING_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_WARNING_SCHEMA_REF:
            raise ValueError("VersionedWarning.schema_version is not the frozen schema")
        if self.code not in SOURCE_WARNING_CODES:
            raise ValueError(f"unregistered warning code {self.code!r}")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("VersionedWarning.version is required")
        object.__setattr__(self, "ordered_payload", tuple(self.ordered_payload))
        if not all(isinstance(item, str) for item in self.ordered_payload):
            raise ValueError("VersionedWarning.ordered_payload must contain strings")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "version": self.version,
            "ordered_payload": list(self.ordered_payload),
        }


_LEGACY_WARNING_PATTERNS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
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
    raise ValueError(f"legacy warning is not in the frozen C2.1 union: {value!r}")


@dataclass(frozen=True, slots=True)
class SourceRejection:
    """Versioned rejection union for fail-closed source-library resolution."""

    code: str
    version: str
    message: str
    schema_version: str = SOURCE_REJECTION_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_REJECTION_SCHEMA_REF:
            raise ValueError("SourceRejection.schema_version is not the frozen schema")
        if self.code not in SOURCE_REJECTION_CODES:
            raise ValueError(f"unregistered rejection code {self.code!r}")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("SourceRejection.version is required")
        if not isinstance(self.message, str):
            raise TypeError("SourceRejection.message must be a string")

    def to_plain(self) -> dict[str, Any]:
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


def _normalize_terms(value: Any) -> tuple[str, ...]:
    out: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    else:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def _normalize_site_entries(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_entries: Any = [value]
    elif isinstance(value, (list, tuple)):
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
    source_mode: str | None = None
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
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                raise ValueError(f"NormalizedParamsSnapshot.{name} must be int or None")

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
            "official_access_site_entries": _normalize_site_entries(
                values.get("official_access_site_entries")
            ),
            "legacy_url_list_frozen": _as_bool(
                values.get("legacy_url_list_frozen"), False
            ),
            "allow_internal_generic_web": _as_bool(
                values.get("_allow_internal_generic_web"), False
            ),
        }
        extra = tuple(
            (key, _json_text(value))
            for key, value in values.items()
            if key not in _PARAMS_KNOWN_FIELDS
        )
        return cls(**known, extra=extra)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        attribute_for = {name: name for name in _PARAMS_KNOWN_FIELDS}
        attribute_for["_allow_internal_generic_web"] = "allow_internal_generic_web"
        for name in _PARAMS_KNOWN_FIELDS:
            if name not in out:
                out[name] = getattr(self, attribute_for[name])
        for key, text in self.extra:
            out[key] = json.loads(text)
        return out

    def to_plain(self) -> dict[str, Any]:
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

    def to_plain(self) -> dict[str, Any]:
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

    def to_plain(self) -> dict[str, Any]:
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

    def to_plain(self) -> dict[str, Any]:
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
        if self.schema_version != SOURCE_EXECUTION_REQUEST_SCHEMA_REF:
            raise ValueError(
                "SourceExecutionRequest.schema_version is not the frozen schema"
            )
        if (
            not isinstance(self.item_revision, int)
            or isinstance(self.item_revision, bool)
            or self.item_revision < 0
        ):
            raise ValueError(
                "SourceExecutionRequest.item_revision must be non-negative int"
            )
        for name, value in (
            ("item_incarnation", self.item_incarnation),
            ("catalog_incarnation", self.catalog_incarnation),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SourceExecutionRequest.{name} is required")
        require_hex64(
            self.item_content_digest,
            "SourceExecutionRequest.item_content_digest",
        )
        require_hex64(self.catalog_digest, "SourceExecutionRequest.catalog_digest")

    def to_plain(self) -> dict[str, Any]:
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


@dataclass(frozen=True, slots=True)
class ResourceCeiling:
    """Bounded pure-CPU resource envelope with a frozen numeric ceiling digest."""

    schema_ref: str
    max_catalog_entries: int
    max_payload_bytes: int
    max_query_terms: int
    max_urls: int
    max_site_entries: int
    max_scalar_length: int
    ceiling_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "max_catalog_entries",
            "max_payload_bytes",
            "max_query_terms",
            "max_urls",
            "max_site_entries",
            "max_scalar_length",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"ResourceCeiling.{name} must be a positive int")
        expected = content_digest(
            {
                "schema": RESOURCE_CEILING_SCHEMA_REF,
                "max_catalog_entries": self.max_catalog_entries,
                "max_payload_bytes": self.max_payload_bytes,
                "max_query_terms": self.max_query_terms,
                "max_urls": self.max_urls,
                "max_site_entries": self.max_site_entries,
                "max_scalar_length": self.max_scalar_length,
            }
        )
        if self.ceiling_digest == "":
            object.__setattr__(self, "ceiling_digest", expected)
        else:
            require_hex64(self.ceiling_digest, "ResourceCeiling.ceiling_digest")
            if self.ceiling_digest != expected:
                raise ValueError(
                    "ResourceCeiling.ceiling_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "max_catalog_entries": self.max_catalog_entries,
            "max_payload_bytes": self.max_payload_bytes,
            "max_query_terms": self.max_query_terms,
            "max_urls": self.max_urls,
            "max_site_entries": self.max_site_entries,
            "max_scalar_length": self.max_scalar_length,
            "ceiling_digest": self.ceiling_digest,
        }


RESOURCE_CEILING = ResourceCeiling(
    schema_ref=RESOURCE_CEILING_SCHEMA_REF,
    max_catalog_entries=256,
    max_payload_bytes=64 * 1024,
    max_query_terms=32,
    max_urls=256,
    max_site_entries=256,
    max_scalar_length=4096,
)


def resource_ceiling_digest() -> str:
    return RESOURCE_CEILING.ceiling_digest


# --- C2.3 mirror: provider effect DTOs ---
SOURCE_LIBRARY_C2_3_KIND = "source_library.execute_provider_effect.v1"
SOURCE_LIBRARY_C2_3_OWNER = "source_library.c2_3.v1"
SOURCE_LIBRARY_C2_3_OPERATION_ID = "source_library.execute_provider_effect"
SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA = (
    "mrw.successor.source-library.c2-3.provider-effect-request.v1"
)
SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID = (
    "mrw.successor.source-library.c2-3.payload.codec.v1"
)
SOURCE_LIBRARY_C2_3_CATALOG_ID = (
    "mrw.functorial-successor.source-library.c2-3.operations"
)
SOURCE_LIBRARY_C2_3_CATALOG_VERSION = "1.0.0"
SOURCE_LIBRARY_C2_3_SEMANTIC_IDENTITY = "source-library.execute-provider-effect"
SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE = (
    "mrw.successor.source-library.c2-3.observation.v1"
)

CREDENTIAL_REF_SCHEMA = "mrw.successor.source-library.c2-3.credential-ref.v1"
CREDENTIAL_DECISION_SCHEMA = (
    "mrw.successor.source-library.c2-3.credential-decision-receipt.v1"
)
PROVIDER_EFFECT_REQUEST_SCHEMA = SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA
PROVIDER_RECEIPT_SCHEMA = "mrw.successor.source-library.c2-3.provider-receipt.v1"
PROVIDER_ATTEMPT_REF_SCHEMA = "mrw.successor.source-library.c2-3.attempt-ref.v1"
CAPTURED_SOURCE_RECORD_REF_SCHEMA = (
    "mrw.successor.source-library.c2-3.captured-source-record-ref.v1"
)
STAGED_ARTIFACT_REF_SCHEMA = "mrw.successor.source-library.c2-3.staged-artifact-ref.v1"
AUTHORITATIVE_READBACK_SCHEMA = (
    "mrw.successor.source-library.c2-3.authoritative-readback.v1"
)
NON_START_PROOF_SCHEMA = "mrw.successor.source-library.c2-3.non-start-proof.v1"
RESOURCE_POLICY_SCHEMA = "mrw.successor.source-library.c2-3.resource-policy.v1"
CANCEL_RECEIPT_SCHEMA = "mrw.successor.source-library.c2-3.cancel-receipt.v1"

SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE = ObjectType("ProviderEffectRequest.v1")
SOURCE_LIBRARY_C2_3_OUTCOME_TYPE = ObjectType("ProviderEffectOutcome.v1")
CREDENTIAL_REF_TYPE = ObjectType("CredentialRef.v1")
CREDENTIAL_DECISION_TYPE = ObjectType("CredentialDecisionReceipt.v1")
PROVIDER_RECEIPT_TYPE = ObjectType("ProviderReceipt.v1")
PROVIDER_ATTEMPT_REF_TYPE = ObjectType("ProviderAttemptRef.v1")
READBACK_TYPE = ObjectType("AuthoritativeProviderReadback.v1")
NON_START_PROOF_TYPE = ObjectType("NonStartProof.v1")
CAPTURED_SOURCE_RECORD_REF_TYPE = ObjectType("CapturedSourceRecordRef.v1")
STAGED_ARTIFACT_REF_TYPE = ObjectType("StagedArtifactRef.v1")

C2_3_TIMEOUT_SECONDS = 120
C2_3_MAX_RETRY_BUDGET = 2
C2_3_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
C2_3_RESOURCE_POLICY_REF = "mrw.successor.source-library.c2-3.resource-policy.v1"

CANCELLED_PROVIDER_EFFECT_CODE = "CANCELLED"
C2_3_FAILURE_CODES: frozenset[str] = frozenset(
    {
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
        "OUTCOME_UNKNOWN",
        CANCELLED_PROVIDER_EFFECT_CODE,
        "RESOURCE_CEILING_EXCEEDED",
    }
)


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


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
) -> str:
    return content_digest(
        {
            "schema": PROVIDER_RECEIPT_SCHEMA,
            "receipt_id": receipt_id,
            "provider": provider,
            "provider_job_id": provider_job_id,
            "provider_status": provider_status,
            "attempt_ref": attempt_ref,
            "observed_at": observed_at,
            "provider_job_uri": provider_job_uri,
        }
    )


_CREDENTIAL_LOCATOR_PATTERN = re.compile(
    r"^credential:/[A-Za-z0-9][A-Za-z0-9._/-]*(/[A-Za-z0-9][A-Za-z0-9._/-]*)*$"
)


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in ("secret", "api_key", "apikey", "token", "password")
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
        if not isinstance(self.ref, str) or self.ref != self.ref.strip():
            raise ValueError(
                "CredentialRef.ref must be a non-whitespace opaque locator"
            )
        if _CREDENTIAL_LOCATOR_PATTERN.fullmatch(self.ref) is None:
            raise ValueError(
                "CredentialRef.ref must use the opaque credential:/locator pattern; "
                "raw secret material, bare values and whitespace are rejected"
            )
        if _looks_like_secret(self.ref):
            raise ValueError(
                "CredentialRef.ref must not embed secret-like raw material"
            )
        if not self.provider.strip() or self.provider != self.provider.strip():
            raise ValueError("CredentialRef.provider is required and must be trimmed")
        if self.schema_version != CREDENTIAL_REF_SCHEMA:
            raise ValueError("CredentialRef.schema_version is not the frozen schema")

    def to_plain(self) -> dict[str, Any]:
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
        if self.schema_version != RESOURCE_POLICY_SCHEMA:
            raise ValueError(
                "ProviderResourcePolicy.schema_version is not the frozen schema"
            )
        for name, value in (
            ("timeout_seconds", self.timeout_seconds),
            ("artifact_byte_ceiling", self.artifact_byte_ceiling),
            ("rate_limit_budget", self.rate_limit_budget),
            ("reservation_lease_seconds", self.reservation_lease_seconds),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"ProviderResourcePolicy.{name} must be positive int")
        if (
            not isinstance(self.retry_budget, int)
            or isinstance(self.retry_budget, bool)
            or self.retry_budget < 0
        ):
            raise ValueError(
                "ProviderResourcePolicy.retry_budget must be non-negative int"
            )
        if self.retry_budget > C2_3_MAX_RETRY_BUDGET:
            raise ValueError("retry_budget exceeds the frozen ceiling")
        if self.artifact_byte_ceiling > C2_3_MAX_ARTIFACT_BYTES:
            raise ValueError("artifact_byte_ceiling exceeds the frozen ceiling")

    def to_plain(self) -> dict[str, Any]:
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


C2_3_DEFAULT_RESOURCE_POLICY = ProviderResourcePolicy(
    resource_class="fixture",
    concurrency_key="source-library:c2-3",
    timeout_seconds=C2_3_TIMEOUT_SECONDS,
    retry_budget=0,
    artifact_byte_ceiling=C2_3_MAX_ARTIFACT_BYTES,
    rate_limit_budget=1,
    reservation_lease_seconds=300,
)


@dataclass(frozen=True, slots=True)
class ProviderEffectRequest:
    """One exact-bound provider effect request; secrets never appear here."""

    schema_version: Literal[
        "mrw.successor.source-library.c2-3.provider-effect-request.v1"
    ]
    operation_kind: Literal["source_library.execute_provider_effect.v1"]
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
        if self.schema_version != SOURCE_LIBRARY_C2_3_PAYLOAD_SCHEMA:
            raise ValueError(
                "ProviderEffectRequest.schema_version is not the frozen schema"
            )
        if self.operation_kind != SOURCE_LIBRARY_C2_3_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        if not self.request_id.strip() or not self.idempotency_key.strip():
            raise ValueError(
                "ProviderEffectRequest request/idempotency ids are required"
            )
        require_hex64(
            self.item_content_digest, "ProviderEffectRequest.item_content_digest"
        )
        require_hex64(
            self.effect_payload_digest, "ProviderEffectRequest.effect_payload_digest"
        )
        require_hex64(self.catalog_digest, "ProviderEffectRequest.catalog_digest")
        object.__setattr__(self, "effect_payload", _freeze(self.effect_payload))
        object.__setattr__(
            self,
            "credential_refs",
            tuple(
                ref for ref in self.credential_refs if isinstance(ref, CredentialRef)
            ),
        )
        expected = _digest_payload(self._digest_payload())
        if self.request_digest == "":
            object.__setattr__(self, "request_digest", expected)
        else:
            require_hex64(self.request_digest, "ProviderEffectRequest.request_digest")
            if self.request_digest != expected:
                raise ValueError(
                    "ProviderEffectRequest.request_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": "mrw.successor.source-library.c2-3.request.v1",
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
            "effect_payload": dict(self.effect_payload),
            "credential_refs": [ref.to_plain() for ref in self.credential_refs],
            "policy": self.policy.to_plain(),
            "catalog_revision": self.catalog_revision,
            "catalog_incarnation": self.catalog_incarnation,
            "catalog_digest": self.catalog_digest,
            "terminal_output_only": self.terminal_output_only,
        }

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError("ProviderAttemptRef.attempt_id is required")
        require_hex64(self.request_digest, "ProviderAttemptRef.request_digest")
        if (
            not isinstance(self.epoch, int)
            or isinstance(self.epoch, bool)
            or self.epoch < 1
        ):
            raise ValueError("ProviderAttemptRef.epoch must be a positive integer")
        if self.schema_version != PROVIDER_ATTEMPT_REF_SCHEMA:
            raise ValueError(
                "ProviderAttemptRef.schema_version is not the frozen schema"
            )

    def as_ref_string(self) -> str:
        return f"provider-attempt:{self.attempt_id}"

    def to_plain(self) -> dict[str, Any]:
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
        if self.schema_version != PROVIDER_RECEIPT_SCHEMA:
            raise ValueError("ProviderReceipt.schema_version is not the frozen schema")
        expected = provider_receipt_digest(
            receipt_id=self.receipt_id,
            provider=self.provider,
            provider_job_id=self.provider_job_id,
            provider_status=self.provider_status,
            attempt_ref=self.attempt_ref,
            observed_at=self.observed_at,
            provider_job_uri=self.provider_job_uri,
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "ProviderReceipt.receipt_digest")
            if self.receipt_digest != expected:
                raise ValueError(
                    "ProviderReceipt.receipt_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError("CapturedSourceRecordRef identities are required")
        require_hex64(self.content_digest, "CapturedSourceRecordRef.content_digest")
        if self.schema_version != CAPTURED_SOURCE_RECORD_REF_SCHEMA:
            raise ValueError(
                "CapturedSourceRecordRef.schema_version is not the frozen schema"
            )

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError("StagedArtifactRef identities are required")
        require_hex64(self.content_digest, "StagedArtifactRef.content_digest")
        if (
            not isinstance(self.byte_size, int)
            or isinstance(self.byte_size, bool)
            or self.byte_size < 0
        ):
            raise ValueError("StagedArtifactRef.byte_size must be a non-negative int")
        if self.staging_state != "STAGED":
            raise ValueError("StagedArtifactRef.staging_state must be STAGED")
        if self.schema_version != STAGED_ARTIFACT_REF_SCHEMA:
            raise ValueError(
                "StagedArtifactRef.schema_version is not the frozen schema"
            )

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError(f"unsupported credential decision {self.decision!r}")
        object.__setattr__(self, "credential_refs", tuple(self.credential_refs))
        object.__setattr__(self, "redacted_profile", _freeze(self.redacted_profile))
        expected = content_digest(
            {
                "schema_version": self.schema_version,
                "decision": self.decision,
                "credential_refs": list(self.credential_refs),
                "redacted_profile": dict(self.redacted_profile),
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(
                self.receipt_digest, "CredentialDecisionReceipt.receipt_digest"
            )
            if self.receipt_digest != expected:
                raise ValueError(
                    "CredentialDecisionReceipt.receipt_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "credential_refs": list(self.credential_refs),
            "redacted_profile": dict(self.redacted_profile),
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
            raise ValueError(
                f"unsupported terminal readback status {self.terminal_status!r}"
            )
        if not self.readback_receipt_id.strip():
            raise ValueError("AuthoritativeProviderReadback.receipt id is required")
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
            require_hex64(
                self.readback_digest, "AuthoritativeProviderReadback.readback_digest"
            )
            if self.readback_digest != expected:
                raise ValueError(
                    "AuthoritativeProviderReadback.readback_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError("NonStartProof.evidence_locator is required")
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
                raise ValueError("NonStartProof.proof_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
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

    def to_plain(self) -> dict[str, Any]:
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
            raise ValueError(f"unsupported cancel status {self.cancel_status!r}")
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
                raise ValueError("CancelReceipt.receipt_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
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
    code: str
    message: str
    source: str

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
                "record_refs": [ref.to_plain() for ref in self.record_refs],
                "staged_artifact_refs": [
                    ref.to_plain() for ref in self.staged_artifact_refs
                ],
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CompletedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CompletedProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "receipt": self.receipt.to_plain(),
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "staged_artifact_refs": [
                ref.to_plain() for ref in self.staged_artifact_refs
            ],
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "AcceptedProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "AcceptedProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "receipt": self.receipt.to_plain(),
                "record_refs": [ref.to_plain() for ref in self.record_refs],
                "ordered_failures": [
                    failure.to_plain() for failure in self.ordered_failures
                ],
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
                raise ValueError(
                    "PartiallyCompletedProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "receipt": self.receipt.to_plain(),
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "ordered_failures": [
                failure.to_plain() for failure in self.ordered_failures
            ],
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class RejectedProviderEffect:
    kind: Literal["rejected"] = "rejected"
    code: str = "INVALID_PARAMS"
    message: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        if self.code not in {
            "MISSING_CREDENTIAL",
            "INVALID_PARAMS",
            "UNAUTHORIZED",
            "UNSUPPORTED_PROVIDER",
            "REQUEST_BINDING_MISMATCH",
        }:
            raise ValueError(f"unsupported rejected provider code {self.code!r}")
        expected = _digest_payload(
            {
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
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
                raise ValueError(
                    "RejectedProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class FailedProviderEffect:
    kind: Literal["failed"] = "failed"
    code: str = "TRANSPORT"
    message: str = ""
    retryable: bool = False
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        if self.code not in {
            "TRANSPORT",
            "TIMEOUT",
            "RATE_LIMIT",
            "PROVIDER_REJECTED",
            "ARTIFACT_WRITE",
            "RESOURCE_CEILING_EXCEEDED",
        }:
            raise ValueError(f"unsupported failed provider code {self.code!r}")
        expected = _digest_payload(
            {
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
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
                raise ValueError(
                    "FailedProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "cancel_receipt": self.cancel_receipt.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CancelledProviderEffect.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CancelledProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "attempt_ref": self.attempt_ref,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest, "OutcomeUnknownProviderEffect.outcome_digest"
            )
            if self.outcome_digest != expected:
                raise ValueError(
                    "OutcomeUnknownProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-3.outcome.v1",
                "kind": self.kind,
                "attempt_ref": self.attempt_ref,
                "readback": self.readback.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest, "ReconciledProviderEffect.outcome_digest"
            )
            if self.outcome_digest != expected:
                raise ValueError(
                    "ReconciledProviderEffect.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "attempt_ref": self.attempt_ref,
            "readback": self.readback.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class ReadbackTerminal:
    readback: AuthoritativeProviderReadback

    def to_plain(self) -> dict[str, Any]:
        return {"kind": "terminal", "readback": self.readback.to_plain()}


@dataclass(frozen=True, slots=True)
class ReadbackWaiting:
    attempt_ref: str
    observed_at: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": "waiting",
            "attempt_ref": self.attempt_ref,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class ReadbackUnavailable:
    attempt_ref: str
    reason: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": "unavailable",
            "attempt_ref": self.attempt_ref,
            "reason": self.reason,
        }


ProviderReadbackResult: TypeAlias = (
    ReadbackTerminal | ReadbackWaiting | ReadbackUnavailable
)


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


def provider_effect_outcomes_equal(
    left: ProviderEffectOutcome, right: ProviderEffectOutcome
) -> bool:
    return dataclasses.asdict(left) == dataclasses.asdict(right)


# --- C2.2 mirror: planning and collection outcome DTOs ---
SOURCE_LIBRARY_C2_2_OWNER = "source_library.c2_2.v1"
SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND = "source_library.protocol_search.v1"
SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND = "source_library.provider_harvest.v1"
SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND = "source_library.site_search.v1"
SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND = "source_library.url_execution.v1"
SOURCE_LIBRARY_C2_2_KINDS: tuple[str, ...] = (
    SOURCE_LIBRARY_C2_2_PROTOCOL_SEARCH_KIND,
    SOURCE_LIBRARY_C2_2_PROVIDER_HARVEST_KIND,
    SOURCE_LIBRARY_C2_2_SITE_SEARCH_KIND,
    SOURCE_LIBRARY_C2_2_URL_EXECUTION_KIND,
)
SOURCE_LIBRARY_C2_2_CATALOG_ID = (
    "mrw.functorial-successor.source-library.c2-2.operations"
)
SOURCE_LIBRARY_C2_2_CATALOG_VERSION = "1.0.0"
SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA = (
    "mrw.successor.source-library.c2-2.planning-payload.v1"
)
SOURCE_MODE_PLANNING_OBSERVATION_PROFILE = (
    "mrw.successor.source-library.c2-2.observation.v1"
)
SOURCE_MODE_PLAN_SCHEMA = "mrw.successor.source-library.c2-2.source-mode-plan.v1"
SOURCE_MODE_TASK_SCHEMA = "mrw.successor.source-library.c2-2.source-mode-task.v1"
COLLECTION_TERMINAL_SCHEMA = "mrw.successor.source-library.c2-2.terminal.v1"
PROVIDER_HANDOFF_SCHEMA = "source_library.provider_handoff.v1"
C2_2_RESOURCE_CEILING_REF = "mrw.successor.source-library.c2-2.resource-ceiling.v1"

C2_2_MAX_QUERY_TERMS = 32
C2_2_MAX_URLS = 256
C2_2_MAX_TASKS = 256
C2_2_BATCH_SIZE = 32

C2_2_PLANNING_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "INVALID_REQUEST",
        "CHANNEL_NOT_FOUND",
        "CHANNEL_DISABLED",
        "FORBIDDEN_INTERNAL_ADAPTER",
        "RESOURCE_CEILING_EXCEEDED",
        "CATALOG_STALE",
    }
)

SOURCE_MODE_PLANNING_PAYLOAD_TYPE = ObjectType("SourceModePlanningPayload.v1")
SOURCE_MODE_PLAN_TYPE = ObjectType("SourceModePlan.v1")
SOURCE_MODE_PLANNING_RESULT_TYPE = ObjectType("SourceModePlanningResult.v1")
SOURCE_COLLECTION_TERMINAL_TYPE = ObjectType("SourceCollectionTerminal.v1")
SOURCE_COLLECTION_OUTCOME_TYPE = ObjectType("SourceCollectionOutcome.v1")


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


def _plain_digest(value: Any) -> str:
    return content_digest(value)


@dataclass(frozen=True, slots=True)
class SourceModePlanningPayload:
    """Exact-bound input consumed by one of the four C2.2 planner atoms."""

    schema_version: Literal["mrw.successor.source-library.c2-2.planning-payload.v1"]
    operation_kind: str
    project_scope: AuthenticatedProjectScope
    execution_request: SourceExecutionRequest
    execution_request_digest: str
    catalog: ChannelCatalogSnapshot
    item_revision: int
    item_incarnation: str
    item_content_digest: str
    orchestration_policy_ref: str
    resource_ceiling_digest: str
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA:
            raise ValueError(
                "SourceModePlanningPayload.schema_version is not the frozen schema"
            )
        if self.operation_kind not in SOURCE_LIBRARY_C2_2_KINDS:
            raise ValueError(
                f"unsupported C2.2 planning operation kind {self.operation_kind!r}"
            )
        scope = self.execution_request.project_scope
        if (
            self.project_scope.project_key != scope.project_key
            or self.project_scope.registry_revision != scope.registry_revision
            or self.project_scope.resolved_schema != scope.resolved_schema
            or self.project_scope.incarnation != scope.incarnation
            or self.project_scope.scope_digest != scope.scope_digest
        ):
            raise ValueError(
                "SourceModePlanningPayload project scope does not bind the request"
            )
        if (
            self.execution_request.item_revision != self.item_revision
            or self.execution_request.item_incarnation != self.item_incarnation
            or self.execution_request.item_content_digest != self.item_content_digest
        ):
            raise ValueError(
                "SourceModePlanningPayload item binding does not match the request"
            )
        if (
            self.catalog.revision != self.execution_request.catalog_revision
            or self.catalog.incarnation != self.execution_request.catalog_incarnation
            or self.catalog.digest != self.execution_request.catalog_digest
        ):
            raise ValueError(
                "SourceModePlanningPayload catalog binding does not match the request"
            )
        require_hex64(
            self.execution_request_digest,
            "SourceModePlanningPayload.execution_request_digest",
        )
        require_hex64(
            self.item_content_digest,
            "SourceModePlanningPayload.item_content_digest",
        )
        require_hex64(
            self.resource_ceiling_digest,
            "SourceModePlanningPayload.resource_ceiling_digest",
        )
        expected = _plain_digest(self._digest_payload())
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(
                self.payload_digest, "SourceModePlanningPayload.payload_digest"
            )
            if self.payload_digest != expected:
                raise ValueError(
                    "SourceModePlanningPayload.payload_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": "mrw.successor.source-library.c2-2.planning-payload.v1",
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "project_scope": self.project_scope.to_plain(),
            "execution_request": self.execution_request.to_plain(),
            "execution_request_digest": self.execution_request_digest,
            "catalog": self.catalog.to_plain(),
            "item_revision": self.item_revision,
            "item_incarnation": self.item_incarnation,
            "item_content_digest": self.item_content_digest,
            "orchestration_policy_ref": self.orchestration_policy_ref,
            "resource_ceiling_digest": self.resource_ceiling_digest,
        }

    def to_plain(self) -> dict[str, Any]:
        return {**self._digest_payload(), "payload_digest": self.payload_digest}


@dataclass(frozen=True, slots=True)
class FallbackRule:
    when: str
    reason: str
    target: str
    authority_bound: bool = True

    def to_plain(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "reason": self.reason,
            "target": self.target,
            "authority_bound": self.authority_bound,
        }


@dataclass(frozen=True, slots=True)
class TerminalConstructionProfile:
    terminal_kind: str = "source_collection_terminal.v1"
    collect_only: bool = True
    provider_handoff_contract_version: str = PROVIDER_HANDOFF_SCHEMA
    document_adoption: bool = False

    def to_plain(self) -> dict[str, Any]:
        return {
            "terminal_kind": self.terminal_kind,
            "collect_only": self.collect_only,
            "provider_handoff_contract_version": self.provider_handoff_contract_version,
            "document_adoption": self.document_adoption,
        }


@dataclass(frozen=True, slots=True)
class OrderedFoldPolicy:
    fold_kind: str = "ordered_source_collection_fold.v1"
    failure_mode: Literal["CONTINUE_ON_ORDERED_FAILURE", "FAIL_FAST"] = (
        "CONTINUE_ON_ORDERED_FAILURE"
    )
    keep_ordered_failures: bool = True
    max_partial_failures: int = C2_2_MAX_TASKS

    def __post_init__(self) -> None:
        if self.failure_mode not in {
            "CONTINUE_ON_ORDERED_FAILURE",
            "FAIL_FAST",
        }:
            raise ValueError(f"unsupported fold failure mode {self.failure_mode!r}")
        if (
            not isinstance(self.max_partial_failures, int)
            or isinstance(self.max_partial_failures, bool)
            or self.max_partial_failures < 1
            or self.max_partial_failures > C2_2_MAX_TASKS
        ):
            raise ValueError("max_partial_failures must be a bounded positive int")

    def to_plain(self) -> dict[str, Any]:
        return {
            "fold_kind": self.fold_kind,
            "failure_mode": self.failure_mode,
            "keep_ordered_failures": self.keep_ordered_failures,
            "max_partial_failures": self.max_partial_failures,
        }


@dataclass(frozen=True, slots=True)
class SourceModeTask:
    task_id: str
    occurrence_id: str
    mode: str
    order_index: int
    effect_request: ProviderEffectRequest
    fallback_rule: FallbackRule | None = None
    terminal_output_only: bool = True
    schema_version: str = SOURCE_MODE_TASK_SCHEMA
    task_digest: str = ""

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.occurrence_id.strip():
            raise ValueError("SourceModeTask identities are required")
        if self.mode not in {
            "protocol_search",
            "provider_harvest",
            "site_search",
            "url_execution",
        }:
            raise ValueError(f"unsupported source mode task {self.mode!r}")
        if (
            not isinstance(self.order_index, int)
            or isinstance(self.order_index, bool)
            or self.order_index < 0
        ):
            raise ValueError("SourceModeTask.order_index must be a non-negative int")
        expected = _plain_digest(
            {
                "schema_version": self.schema_version,
                "task_id": self.task_id,
                "occurrence_id": self.occurrence_id,
                "mode": self.mode,
                "order_index": self.order_index,
                "effect_request_digest": self.effect_request.request_digest,
                "fallback_rule": (
                    self.fallback_rule.to_plain()
                    if self.fallback_rule is not None
                    else None
                ),
                "terminal_output_only": self.terminal_output_only,
            }
        )
        if self.task_digest == "":
            object.__setattr__(self, "task_digest", expected)
        else:
            require_hex64(self.task_digest, "SourceModeTask.task_digest")
            if self.task_digest != expected:
                raise ValueError("SourceModeTask.task_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "occurrence_id": self.occurrence_id,
            "mode": self.mode,
            "order_index": self.order_index,
            "effect_request": self.effect_request.to_plain(),
            "fallback_rule": (
                self.fallback_rule.to_plain()
                if self.fallback_rule is not None
                else None
            ),
            "terminal_output_only": self.terminal_output_only,
            "task_digest": self.task_digest,
        }


def source_mode_plan_digest(
    *,
    plan_id: str,
    mode: str,
    execution_request_digest: str,
    catalog_revision: int,
    catalog_incarnation: str,
    catalog_digest: str,
    task_digests: tuple[str, ...],
    fold_policy: OrderedFoldPolicy,
    fallback_rules: tuple[FallbackRule, ...],
    terminal_profile: TerminalConstructionProfile,
) -> str:
    return content_digest(
        {
            "schema": SOURCE_MODE_PLAN_SCHEMA,
            "plan_id": plan_id,
            "mode": mode,
            "execution_request_digest": execution_request_digest,
            "catalog_revision": catalog_revision,
            "catalog_incarnation": catalog_incarnation,
            "catalog_digest": catalog_digest,
            "task_digests": list(task_digests),
            "fold_policy": fold_policy.to_plain(),
            "fallback_rules": [rule.to_plain() for rule in fallback_rules],
            "terminal_profile": terminal_profile.to_plain(),
        }
    )


@dataclass(frozen=True, slots=True)
class SourceModePlan:
    plan_id: str
    mode: str
    execution_request_digest: str
    catalog_revision: int
    catalog_incarnation: str
    catalog_digest: str
    ordered_tasks: tuple[SourceModeTask, ...]
    ordered_fold_policy: OrderedFoldPolicy
    fallback_rules: tuple[FallbackRule, ...]
    terminal_profile: TerminalConstructionProfile
    schema_version: str = SOURCE_MODE_PLAN_SCHEMA
    plan_digest: str = ""

    def __post_init__(self) -> None:
        if self.mode not in {
            "protocol_search",
            "provider_harvest",
            "site_search",
            "url_execution",
        }:
            raise ValueError(f"unsupported source mode plan {self.mode!r}")
        require_hex64(
            self.execution_request_digest,
            "SourceModePlan.execution_request_digest",
        )
        require_hex64(self.catalog_digest, "SourceModePlan.catalog_digest")
        if len(self.ordered_tasks) > C2_2_MAX_TASKS:
            raise ValueError("SourceModePlan exceeds the max task ceiling")
        expected = source_mode_plan_digest(
            plan_id=self.plan_id,
            mode=self.mode,
            execution_request_digest=self.execution_request_digest,
            catalog_revision=self.catalog_revision,
            catalog_incarnation=self.catalog_incarnation,
            catalog_digest=self.catalog_digest,
            task_digests=tuple(task.task_digest for task in self.ordered_tasks),
            fold_policy=self.ordered_fold_policy,
            fallback_rules=self.fallback_rules,
            terminal_profile=self.terminal_profile,
        )
        if self.plan_digest == "":
            object.__setattr__(self, "plan_digest", expected)
        else:
            require_hex64(self.plan_digest, "SourceModePlan.plan_digest")
            if self.plan_digest != expected:
                raise ValueError("SourceModePlan.plan_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "mode": self.mode,
            "execution_request_digest": self.execution_request_digest,
            "catalog_revision": self.catalog_revision,
            "catalog_incarnation": self.catalog_incarnation,
            "catalog_digest": self.catalog_digest,
            "ordered_tasks": [task.to_plain() for task in self.ordered_tasks],
            "ordered_fold_policy": self.ordered_fold_policy.to_plain(),
            "fallback_rules": [rule.to_plain() for rule in self.fallback_rules],
            "terminal_profile": self.terminal_profile.to_plain(),
            "plan_digest": self.plan_digest,
        }


@dataclass(frozen=True, slots=True)
class PlannedPlanning:
    kind: Literal["planned"] = "planned"
    plan: SourceModePlan = field(default_factory=lambda: _placeholder_plan())
    result_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.planning-result.v1",
                "kind": self.kind,
                "plan_digest": self.plan.plan_digest,
            }
        )
        if self.result_digest == "":
            object.__setattr__(self, "result_digest", expected)
        else:
            require_hex64(self.result_digest, "PlannedPlanning.result_digest")
            if self.result_digest != expected:
                raise ValueError("PlannedPlanning.result_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "plan": self.plan.to_plain(),
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class RejectedPlanning:
    kind: Literal["rejected"] = "rejected"
    code: str = "INVALID_REQUEST"
    message: str = ""
    result_digest: str = ""

    def __post_init__(self) -> None:
        if self.code not in C2_2_PLANNING_FAILURE_CODES:
            raise ValueError(f"unsupported planning rejection code {self.code!r}")
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.planning-result.v1",
                "kind": self.kind,
                "code": self.code,
                "message": self.message,
            }
        )
        if self.result_digest == "":
            object.__setattr__(self, "result_digest", expected)
        else:
            require_hex64(self.result_digest, "RejectedPlanning.result_digest")
            if self.result_digest != expected:
                raise ValueError(
                    "RejectedPlanning.result_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "result_digest": self.result_digest,
        }


SourceModePlanningResult: TypeAlias = PlannedPlanning | RejectedPlanning


@dataclass(frozen=True, slots=True)
class OrderedFailure:
    order_index: int
    code: str
    message: str
    source: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "order_index": self.order_index,
            "code": self.code,
            "message": self.message,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ProviderHandoff:
    handoff_id: str
    mode: str
    provider: str
    provider_job_id: str | None
    provider_status: str
    receipt_digest: str
    contract_version: str = PROVIDER_HANDOFF_SCHEMA

    def __post_init__(self) -> None:
        if not self.handoff_id.strip():
            raise ValueError("ProviderHandoff.handoff_id is required")
        require_hex64(self.receipt_digest, "ProviderHandoff.receipt_digest")
        if self.contract_version != PROVIDER_HANDOFF_SCHEMA:
            raise ValueError(
                "ProviderHandoff.contract_version is not the frozen contract"
            )

    def to_plain(self) -> dict[str, Any]:
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
class SourceTaskOutcome:
    task_id: str
    mode: str
    status: Literal[
        "completed",
        "accepted",
        "partially_completed",
        "failed",
        "cancelled",
        "outcome_unknown",
    ]
    ordered_failures: tuple[OrderedFailure, ...] = ()
    provider_handoff: ProviderHandoff | None = None

    def to_plain(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mode": self.mode,
            "status": self.status,
            "ordered_failures": [
                failure.to_plain() for failure in self.ordered_failures
            ],
            "provider_handoff": (
                self.provider_handoff.to_plain()
                if self.provider_handoff is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class SourceCollectionTerminal:
    terminal_id: str
    mode: str
    status: Literal["ok", "partial", "error", "accepted", "unknown"]
    records_count: int
    provider_handoff: ProviderHandoff | None = None
    ordered_failures: tuple[OrderedFailure, ...] = ()
    schema_version: str = COLLECTION_TERMINAL_SCHEMA
    collection_digest: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"ok", "partial", "error", "accepted", "unknown"}:
            raise ValueError(f"unsupported collection terminal status {self.status!r}")
        if (
            not isinstance(self.records_count, int)
            or isinstance(self.records_count, bool)
            or self.records_count < 0
        ):
            raise ValueError(
                "SourceCollectionTerminal.records_count must be non-negative"
            )
        expected = _plain_digest(
            {
                "schema_version": self.schema_version,
                "terminal_id": self.terminal_id,
                "mode": self.mode,
                "status": self.status,
                "records_count": self.records_count,
                "provider_handoff": (
                    self.provider_handoff.to_plain()
                    if self.provider_handoff is not None
                    else None
                ),
                "ordered_failures": [
                    failure.to_plain() for failure in self.ordered_failures
                ],
            }
        )
        if self.collection_digest == "":
            object.__setattr__(self, "collection_digest", expected)
        else:
            require_hex64(
                self.collection_digest, "SourceCollectionTerminal.collection_digest"
            )
            if self.collection_digest != expected:
                raise ValueError(
                    "SourceCollectionTerminal.collection_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "terminal_id": self.terminal_id,
            "mode": self.mode,
            "status": self.status,
            "records_count": self.records_count,
            "provider_handoff": (
                self.provider_handoff.to_plain()
                if self.provider_handoff is not None
                else None
            ),
            "ordered_failures": [
                failure.to_plain() for failure in self.ordered_failures
            ],
            "collection_digest": self.collection_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionCompleted:
    kind: Literal["completed"] = "completed"
    terminal: SourceCollectionTerminal = field(
        default_factory=lambda: _placeholder_terminal("ok")
    )
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
                "kind": self.kind,
                "terminal": self.terminal.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionCompleted.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectionCompleted.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionPartiallyCompleted:
    kind: Literal["partially_completed"] = "partially_completed"
    terminal: SourceCollectionTerminal = field(
        default_factory=lambda: _placeholder_terminal("partial")
    )
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
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
                raise ValueError(
                    "CollectionPartiallyCompleted.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionProviderAccepted:
    kind: Literal["provider_accepted"] = "provider_accepted"
    terminal: SourceCollectionTerminal = field(
        default_factory=lambda: _placeholder_terminal("accepted")
    )
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
                "kind": self.kind,
                "terminal": self.terminal.to_plain(),
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest, "CollectionProviderAccepted.outcome_digest"
            )
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectionProviderAccepted.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "terminal": self.terminal.to_plain(),
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionRejected:
    kind: Literal["rejected"] = "rejected"
    code: str = "INVALID_REQUEST"
    message: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
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
                raise ValueError(
                    "CollectionRejected.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectionFailed:
    kind: Literal["failed"] = "failed"
    code: str = "TRANSPORT"
    message: str = ""
    retryable: bool = False
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        expected = _plain_digest(
            {
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
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
                raise ValueError(
                    "CollectionFailed.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
                "kind": self.kind,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectionCancelled.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectionCancelled.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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
                "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
                "kind": self.kind,
                "reason": self.reason,
            }
        )
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(
                self.outcome_digest, "CollectionOutcomeUnknown.outcome_digest"
            )
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectionOutcomeUnknown.outcome_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
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


def _placeholder_plan() -> SourceModePlan:
    request_digest = content_digest({"request": "placeholder"})
    task = SourceModeTask(
        task_id="task:placeholder",
        occurrence_id="occurrence:placeholder",
        mode="protocol_search",
        order_index=0,
        effect_request=_placeholder_effect_request(),
    )
    return SourceModePlan(
        plan_id="plan:placeholder",
        mode="protocol_search",
        execution_request_digest=request_digest,
        catalog_revision=0,
        catalog_incarnation="placeholder",
        catalog_digest=content_digest({"catalog": "placeholder"}),
        ordered_tasks=(task,),
        ordered_fold_policy=OrderedFoldPolicy(),
        fallback_rules=(),
        terminal_profile=TerminalConstructionProfile(),
    )


def _placeholder_effect_request() -> ProviderEffectRequest:
    scope = AuthenticatedProjectScope(
        project_key="placeholder",
        resolved_schema="mrw_placeholder",
        registry_revision=0,
        incarnation="scope-inc:placeholder",
        scope_digest=project_scope_digest(
            "placeholder", "mrw_placeholder", 0, "scope-inc:placeholder"
        ),
    )
    return ProviderEffectRequest(
        schema_version="mrw.successor.source-library.c2-3.provider-effect-request.v1",
        operation_kind="source_library.execute_provider_effect.v1",
        request_id="request:placeholder",
        idempotency_key="idem:placeholder",
        project_scope=scope,
        item_key="item:placeholder",
        item_revision=0,
        item_incarnation="item-inc:placeholder",
        item_content_digest=content_digest({"item": "placeholder"}),
        channel_key="channel:placeholder",
        provider="fixture",
        provider_config_ref="catalog:placeholder",
        effect_payload_codec_ref="codec:placeholder",
        effect_payload_digest=content_digest({"payload": "placeholder"}),
        effect_payload={"placeholder": True},
        credential_refs=(),
        policy=C2_3_DEFAULT_RESOURCE_POLICY,
        catalog_revision=0,
        catalog_incarnation="catalog-inc:placeholder",
        catalog_digest=content_digest({"catalog": "placeholder"}),
    )


def _placeholder_terminal(status: str) -> SourceCollectionTerminal:
    return SourceCollectionTerminal(
        terminal_id="terminal:placeholder",
        mode="protocol_search",
        status=status,  # type: ignore[arg-type]
        records_count=0,
    )


def source_collection_outcomes_equal(
    left: SourceCollectionOutcome, right: SourceCollectionOutcome
) -> bool:
    return dataclasses.asdict(left) == dataclasses.asdict(right)


# --- mode mapping ---
MODE_BY_KIND: dict[str, str] = {
    "source_library.protocol_search.v1": "protocol_search",
    "source_library.provider_harvest.v1": "provider_harvest",
    "source_library.site_search.v1": "site_search",
    "source_library.url_execution.v1": "url_execution",
}
KIND_BY_MODE: dict[str, str] = {mode: kind for kind, mode in MODE_BY_KIND.items()}


def mode_for_kind(kind: str) -> str:
    try:
        return MODE_BY_KIND[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported C2.2 operation kind {kind!r}") from exc


def kind_for_mode(mode: str) -> str:
    try:
        return KIND_BY_MODE[mode]
    except KeyError as exc:
        raise ValueError(f"unsupported C2.2 source mode {mode!r}") from exc


# --- C2.3 effect ports ---
@dataclass(frozen=True, slots=True)
class EphemeralCredentialLease:
    """Redacted lease over an opaque credential; no secret bytes."""

    lease_id: str
    credential_ref: str
    provider: str
    expires_at: str
    credential_decision_receipt: CredentialDecisionReceipt

    def to_plain(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "credential_ref": self.credential_ref,
            "provider": self.provider,
            "expires_at": self.expires_at,
            "credential_decision_receipt": self.credential_decision_receipt.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class RedactedCredentialRejection:
    code: str
    credential_ref: str
    message: str
    credential_decision_receipt: CredentialDecisionReceipt | None = None

    def to_plain(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "credential_ref": self.credential_ref,
            "message": self.message,
            "credential_decision_receipt": (
                self.credential_decision_receipt.to_plain()
                if self.credential_decision_receipt is not None
                else None
            ),
        }


@runtime_checkable
class CredentialResolverPort(Protocol):
    def resolve(
        self,
        ref: CredentialRef,
        authorization: Any,
    ) -> EphemeralCredentialLease | RedactedCredentialRejection:
        """Resolve one opaque credential ref or return a redacted rejection."""


@runtime_checkable
class ProviderEffectPort(Protocol):
    def execute(
        self,
        request: ProviderEffectRequest,
        ephemeral_credentials: tuple[EphemeralCredentialLease, ...],
    ) -> ProviderEffectOutcome:
        """Execute one provider effect through an authorized interpreter."""

    def cancel(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> CancelReceipt:
        """Request cancellation; never fabricates terminal state."""


@runtime_checkable
class ProviderReadbackPort(Protocol):
    def readback(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> ProviderReadbackResult:
        """Return authoritative, waiting or unavailable readback state."""

    def prove_not_started(
        self,
        attempt_ref: ProviderAttemptRef,
        request: ProviderEffectRequest,
    ) -> NonStartProof | NonStartUnprovable:
        """Prove the attempt never started, or honestly return unprovable."""


@runtime_checkable
class ProviderEffectGateway(Protocol):
    credentials: CredentialResolverPort
    effect: ProviderEffectPort
    readback: ProviderReadbackPort

    def execute(
        self,
        request: ProviderEffectRequest,
        authorization: Any,
    ) -> ProviderEffectOutcome:
        """Resolve credentials then execute one provider effect."""


class ProviderCallTracer(Protocol):
    """Observable call log for deterministic fixture replay/shadow evidence."""

    provider_calls: list[str]


def source_mode_planning_payload_from_plain(
    value: dict[str, Any],
) -> SourceModePlanningPayload:
    """Rebuild the exact C2.2 planning payload from its canonical plain form."""

    scope_plain = dict(value["project_scope"])
    scope = AuthenticatedProjectScope(
        project_key=scope_plain["project_key"],
        registry_revision=int(scope_plain["registry_revision"]),
        resolved_schema=scope_plain["resolved_schema"],
        incarnation=scope_plain["incarnation"],
        scope_digest=scope_plain["scope_digest"],
    )
    request_plain = dict(value["execution_request"])
    params_plain = dict(request_plain["params"])
    params = NormalizedParamsSnapshot(
        query_terms=tuple(params_plain.get("query_terms") or ()),
        max_items=params_plain.get("max_items"),
        limit=params_plain.get("limit"),
        per_keyword_limit=params_plain.get("per_keyword_limit"),
        max_candidates=params_plain.get("max_candidates"),
        ingest_limit=params_plain.get("ingest_limit"),
        page=params_plain.get("page"),
        page_size=params_plain.get("page_size"),
        max_pages=params_plain.get("max_pages"),
        days_back=params_plain.get("days_back"),
        start_offset=params_plain.get("start_offset"),
        start_time=params_plain.get("start_time"),
        end_time=params_plain.get("end_time"),
        date_from=params_plain.get("date_from"),
        date_to=params_plain.get("date_to"),
        source_mode=params_plain.get("source_mode"),
        expected_entry_type=params_plain.get("expected_entry_type"),
        urls=tuple(params_plain.get("urls") or ()),
        site_entries=tuple(params_plain.get("site_entries") or ()),
        site_entry_urls=tuple(params_plain.get("site_entry_urls") or ()),
        official_access_site_entries=tuple(
            params_plain.get("official_access_site_entries") or ()
        ),
        legacy_url_list_frozen=bool(params_plain.get("legacy_url_list_frozen", False)),
        allow_internal_generic_web=bool(
            params_plain.get(
                "_allow_internal_generic_web",
                params_plain.get("allow_internal_generic_web", False),
            )
        ),
        extra=tuple(
            (str(key), str(item)) for key, item in params_plain.get("extra") or []
        ),
    )
    mode_plain = dict(request_plain["source_mode"])
    mode = SourceMode(
        mode=mode_plain["mode"],
        version=mode_plain["version"],
        schema_version=mode_plain.get("schema_version", SOURCE_MODE_SCHEMA_REF),
    )
    taxonomy_plain = dict(request_plain["taxonomy"])
    taxonomy = SourceTaxonomy(
        channel_family=taxonomy_plain["channel_family"],
        item_type=taxonomy_plain["item_type"],
        managed_by=taxonomy_plain["managed_by"],
        expected_entry_type=taxonomy_plain.get("expected_entry_type"),
        internal_adapter_only=bool(taxonomy_plain["internal_adapter_only"]),
        site_search_authoritative=bool(taxonomy_plain["site_search_authoritative"]),
        schema_version=taxonomy_plain.get("schema_version", SOURCE_TAXONOMY_SCHEMA_REF),
    )
    warnings = tuple(
        VersionedWarning(
            code=item["code"],
            version=item["version"],
            ordered_payload=tuple(item["ordered_payload"]),
            schema_version=item.get("schema_version", SOURCE_WARNING_SCHEMA_REF),
        )
        for item in request_plain.get("warnings") or []
    )
    protocol_plain = dict(request_plain["protocol"])
    concurrency_plain = dict(protocol_plain["concurrency_plan"])
    search = FrontDoorConcurrencyStage(**dict(concurrency_plain["search"]))
    url = FrontDoorConcurrencyStage(**dict(concurrency_plain["url"]))
    concurrency = FrontDoorConcurrencyPlan(
        batch_size=int(concurrency_plain["batch_size"]),
        shared_budget=int(concurrency_plain["shared_budget"]),
        search=search,
        url=url,
    )
    protocol = FrontDoorProtocol(
        item_key=protocol_plain["item_key"],
        item_channel_key=protocol_plain["item_channel_key"],
        project_key=protocol_plain.get("project_key"),
        front_door_owner=protocol_plain["front_door_owner"],
        execution_mode=protocol_plain["execution_mode"],
        write_mode=protocol_plain["write_mode"],
        route_decision=protocol_plain["route_decision"],
        query_terms=tuple(protocol_plain.get("query_terms") or ()),
        site_entries=tuple(protocol_plain.get("site_entries") or ()),
        candidate_urls=tuple(protocol_plain.get("candidate_urls") or ()),
        expected_entry_type=protocol_plain.get("expected_entry_type"),
        write_to_pool=bool(protocol_plain.get("write_to_pool", False)),
        auto_ingest=bool(protocol_plain.get("auto_ingest", False)),
        ingest_limit=int(protocol_plain.get("ingest_limit") or 0),
        force_url_routing_flow=bool(
            protocol_plain.get("force_url_routing_flow", False)
        ),
        prefer_crawler_first=bool(protocol_plain.get("prefer_crawler_first", False)),
        search_parallelism=int(protocol_plain.get("search_parallelism") or 1),
        routing_parallelism=int(protocol_plain.get("routing_parallelism") or 1),
        concurrency_plan=concurrency,
        source_tier=protocol_plain.get("source_tier") or "",
        onboarding_priority=protocol_plain.get("onboarding_priority") or "",
    )
    request = SourceExecutionRequest(
        source_mode=mode,
        item_key=request_plain["item_key"],
        item_channel_key=request_plain["item_channel_key"],
        project_key=request_plain.get("project_key"),
        project_scope=scope,
        item_revision=int(request_plain["item_revision"]),
        item_incarnation=request_plain["item_incarnation"],
        item_content_digest=request_plain["item_content_digest"],
        catalog_revision=int(request_plain["catalog_revision"]),
        catalog_incarnation=request_plain["catalog_incarnation"],
        catalog_digest=request_plain["catalog_digest"],
        params=params,
        protocol=protocol,
        warnings=warnings,
        taxonomy=taxonomy,
        schema_version=request_plain.get(
            "schema_version", SOURCE_EXECUTION_REQUEST_SCHEMA_REF
        ),
    )
    catalog_plain = dict(value["catalog"])
    catalog = ChannelCatalogSnapshot(
        schema_version="mrw.successor.source-library.channel-catalog.v1",
        revision=int(catalog_plain["revision"]),
        incarnation=catalog_plain["incarnation"],
        digest=catalog_plain["digest"],
        entries=tuple(
            ChannelCatalogEntry(
                channel_key=entry["channel_key"],
                provider=entry.get("provider") or "",
                provider_type=entry.get("provider_type") or "",
                enabled=bool(entry.get("enabled", True)),
                extra=freeze_json_object(
                    dict(entry["extra"])
                    if isinstance(entry.get("extra"), (tuple, list))
                    else entry.get("extra") or {}
                ),
            )
            for entry in catalog_plain.get("entries") or []
        ),
    )
    return SourceModePlanningPayload(
        schema_version=value.get("schema_version", SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA),
        operation_kind=value["operation_kind"],
        project_scope=scope,
        execution_request=request,
        execution_request_digest=value["execution_request_digest"],
        catalog=catalog,
        item_revision=int(value["item_revision"]),
        item_incarnation=value["item_incarnation"],
        item_content_digest=value["item_content_digest"],
        orchestration_policy_ref=value["orchestration_policy_ref"],
        resource_ceiling_digest=value["resource_ceiling_digest"],
        payload_digest=value.get("payload_digest", ""),
    )
