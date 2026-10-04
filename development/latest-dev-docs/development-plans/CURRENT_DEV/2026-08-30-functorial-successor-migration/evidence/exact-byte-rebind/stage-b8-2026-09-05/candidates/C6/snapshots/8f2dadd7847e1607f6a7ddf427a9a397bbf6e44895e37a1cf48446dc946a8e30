"""Family-local shared vocabulary for the P3 C6 AgentCore successor line.

This module is the only cross-cell sharing point for the C6.1/C6.2/C6.3
capabilities.  It owns the family deployment-catalog identity, the canonical
project scope binding, the ordered model-step/tool-call/tool-result DTOs and a
strict payload codec helper.  It never imports legacy agent services, never
reads process configuration, and never performs network, provider, database or
credential work.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import sys
import types
import typing
from dataclasses import dataclass, field, fields
from typing import Any, Generic, Literal, TypeAlias, TypeVar, get_args, get_origin

from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, codec_digest
from app.successor_runtime.capabilities.contracts import OperationContractRef
from app.successor_runtime.language import algebra as _algebra
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    _FrozenJsonObjectMarker,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AGENT_CORE_C6_FAMILY_ID",
    "AGENT_CORE_C6_FAMILY_OWNER",
    "AGENT_MODEL_STEP_SCHEMA",
    "AGENT_TOOL_CALL_SCHEMA",
    "AGENT_TOOL_RESULT_SCHEMA",
    "AgentModelStep",
    "AgentModelStepFailure",
    "AgentModelStepOutcome",
    "AgentToolCall",
    "AgentToolResult",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterSuccess",
    "ProjectScope",
    "SchemaSpec",
    "build_p3_c6_fragment",
    "build_payload_codec",
    "c6_deployment_catalog_digest",
    "freeze_c6_json_object",
    "freeze_c6_json_value",
    "project_scope_digest",
    "rollback_authority_ceiling",
    "thaw_json_value",
]


AGENT_CORE_C6_FAMILY_ID = "mrw.successor.agent-core.c6"
AGENT_CORE_C6_FAMILY_OWNER = "agent_core.c6.v1"
_SCOPE_DIGEST_NAMESPACE = b"mrw.project_scope.v2\n"
_C6_SCHEMA_DIGEST_SCHEMA = "mrw.successor.agent-core.c6.schema.v1"
_C6_DEPLOYMENT_CATALOG_SCHEMA = "mrw.successor.agent-core.c6.deployment-catalog.v1"

AGENT_TOOL_CALL_SCHEMA_REF = "mrw.successor.agent-core.c6.tool-call.v1"
AGENT_TOOL_RESULT_SCHEMA_REF = "mrw.successor.agent-core.c6.tool-result.v1"
AGENT_MODEL_STEP_SCHEMA_REF = "mrw.successor.agent-core.c6.model-step.v1"

PROJECT_SCOPE_TYPE = ObjectType("ProjectScope.v1")
AGENT_TOOL_CALL_TYPE = ObjectType("AgentToolCall.v1")
AGENT_TOOL_RESULT_TYPE = ObjectType("AgentToolResult.v1")
AGENT_MODEL_STEP_TYPE = ObjectType("AgentModelStep.v1")


def project_scope_digest(
    project_key: str,
    resolved_schema: str,
    project_registry_revision: int,
    incarnation: str,
) -> str:
    """Canonical scope digest matching ``compute_scope_digest`` byte-for-byte."""

    if not isinstance(project_key, str) or not project_key.strip():
        raise ValueError("project_key is required")
    if (
        not isinstance(resolved_schema, str)
        or len(resolved_schema.encode("utf-8")) > 63
        or not resolved_schema.islower()
        or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for char in resolved_schema
        )
        or not resolved_schema[:1].isalpha()
        or resolved_schema
        in {
            "public",
            "pg_catalog",
            "information_schema",
            "pg_toast",
            "pg_temp_1",
            "pg_toast_temp_1",
        }
    ):
        raise ValueError("invalid resolved project schema identifier")
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
class ProjectScope:
    """Authenticated project scope bound to one active registry incarnation."""

    project_key: str
    registry_revision: int
    resolved_schema: str
    incarnation: str
    scope_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.project_key, str) or not self.project_key.strip():
            raise ValueError("ProjectScope.project_key is required")
        if (
            not isinstance(self.registry_revision, int)
            or isinstance(self.registry_revision, bool)
            or self.registry_revision < 0
        ):
            raise ValueError("ProjectScope.registry_revision must be non-negative int")
        if not isinstance(self.incarnation, str) or not self.incarnation.strip():
            raise ValueError("ProjectScope.incarnation is required")
        expected = project_scope_digest(
            self.project_key,
            self.resolved_schema,
            self.registry_revision,
            self.incarnation,
        )
        if self.scope_digest == "":
            object.__setattr__(self, "scope_digest", expected)
        else:
            require_hex64(self.scope_digest, "ProjectScope.scope_digest")
            if self.scope_digest != expected:
                raise ValueError(
                    "ProjectScope.scope_digest does not match the canonical binding"
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
class SchemaSpec:
    """Explicit schema ref, per-field requiredness map and pinned digest."""

    schema_ref: str
    field_requiredness: tuple[tuple[str, bool], ...]
    schema_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.schema_ref, str) or not self.schema_ref:
            raise ValueError("SchemaSpec.schema_ref is required")
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
                "schema": _C6_SCHEMA_DIGEST_SCHEMA,
                "schema_ref": self.schema_ref,
                "field_requiredness": self.field_requiredness,
            }
        )
        if self.schema_digest == "":
            object.__setattr__(self, "schema_digest", expected)
        else:
            require_hex64(self.schema_digest, "SchemaSpec.schema_digest")
            if self.schema_digest != expected:
                raise ValueError("SchemaSpec.schema_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "field_requiredness": [
                [name, required] for name, required in self.field_requiredness
            ],
            "schema_digest": self.schema_digest,
        }


AGENT_TOOL_CALL_SCHEMA = SchemaSpec(
    schema_ref=AGENT_TOOL_CALL_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("call_id", True),
        ("tool_name", True),
        ("arguments", True),
        ("reason", False),
    ),
)
AGENT_TOOL_RESULT_SCHEMA = SchemaSpec(
    schema_ref=AGENT_TOOL_RESULT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("call_id", True),
        ("tool_name", True),
        ("status", True),
        ("model_summary", True),
        ("ui_summary", False),
        ("structured_content", True),
        ("error", False),
        ("retry_hint", False),
    ),
)
AGENT_MODEL_STEP_SCHEMA = SchemaSpec(
    schema_ref=AGENT_MODEL_STEP_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("step_type", True),
        ("content", False),
        ("tool_calls", True),
        ("metadata", True),
    ),
)


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    """Canonical ordered tool-call shape for the C6 loop/provider boundary."""

    call_id: str
    tool_name: str
    arguments: FrozenJsonObject = field(
        default_factory=lambda: freeze_c6_json_object({})
    )
    reason: str | None = None
    schema_version: str = AGENT_TOOL_CALL_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_TOOL_CALL_SCHEMA_REF:
            raise ValueError("AgentToolCall.schema_version is not frozen")
        for name in ("call_id", "tool_name"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"AgentToolCall.{name} is required")
        object.__setattr__(
            self, "arguments", freeze_c6_json_object(dict(self.arguments))
        )
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("AgentToolCall.reason must be a string or None")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": thaw_json_value(self.arguments),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    """Canonical tool-result envelope; raw content stays interpreter-local."""

    call_id: str
    tool_name: str
    status: Literal["completed", "failed", "canceled", "needs_approval", "deferred"]
    model_summary: str
    ui_summary: str | None = None
    structured_content: FrozenJsonObject = field(
        default_factory=lambda: freeze_c6_json_object({})
    )
    error: FrozenJsonObject | None = None
    retry_hint: str | None = None
    schema_version: str = AGENT_TOOL_RESULT_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_TOOL_RESULT_SCHEMA_REF:
            raise ValueError("AgentToolResult.schema_version is not frozen")
        if self.status not in {
            "completed",
            "failed",
            "canceled",
            "needs_approval",
            "deferred",
        }:
            raise ValueError(f"unsupported AgentToolResult.status {self.status!r}")
        for name in ("call_id", "tool_name"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"AgentToolResult.{name} is required")
        object.__setattr__(
            self,
            "structured_content",
            freeze_c6_json_object(dict(self.structured_content)),
        )
        if self.error is not None:
            object.__setattr__(self, "error", freeze_c6_json_object(dict(self.error)))

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "model_summary": self.model_summary,
            "ui_summary": self.ui_summary or self.model_summary,
            "structured_content": thaw_json_value(self.structured_content),
            "error": (None if self.error is None else thaw_json_value(self.error)),
            "retry_hint": self.retry_hint,
        }


@dataclass(frozen=True, slots=True)
class AgentModelStep:
    """Three-way deterministic model step (delta/final/tool calls)."""

    step_type: Literal["assistant_delta", "final_answer", "tool_calls"]
    content: str = ""
    tool_calls: tuple[AgentToolCall, ...] = ()
    metadata: FrozenJsonObject = field(
        default_factory=lambda: freeze_c6_json_object({})
    )
    schema_version: str = AGENT_MODEL_STEP_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_MODEL_STEP_SCHEMA_REF:
            raise ValueError("AgentModelStep.schema_version is not frozen")
        if self.step_type not in {"assistant_delta", "final_answer", "tool_calls"}:
            raise ValueError(f"unsupported AgentModelStep.step_type {self.step_type!r}")
        if not isinstance(self.content, str):
            raise TypeError("AgentModelStep.content must be a string")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "metadata", freeze_c6_json_object(dict(self.metadata)))
        if self.step_type == "tool_calls" and not self.tool_calls:
            raise ValueError("tool_calls step requires at least one tool call")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "step_type": self.step_type,
            "content": self.content,
            "tool_calls": [call.to_plain() for call in self.tool_calls],
            "metadata": thaw_json_value(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AgentModelStepFailure:
    """Typed provider/model-step failure union shared by C6.1 and C6.2."""

    code: Literal[
        "unsupported_model_step",
        "provider_unavailable",
        "provider_invocation_failed",
        "provider_protocol_invalid",
        "provider_timeout",
        "provider_rate_limited",
        "provider_credential_rejected",
        "provider_fallback_selected",
        "provider_outcome_unknown",
    ]
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


AgentModelStepOutcome: TypeAlias = AgentModelStep | AgentModelStepFailure


T = TypeVar("T")


class _C6FrozenObjectMarker(tuple):
    """Family-local frozen-object marker at every nesting level."""


def freeze_c6_json_value(value: Any) -> Any:
    """Freeze JSON preserving dict/array identity at every nesting level."""

    if isinstance(value, (_FrozenJsonObjectMarker, _C6FrozenObjectMarker)):
        return value
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and math.isnan(value):
            raise ValueError("non-finite float is not a frozen JSON value")
        return value
    if isinstance(value, dict):
        return _C6FrozenObjectMarker(
            (str(key), freeze_c6_json_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_c6_json_value(item) for item in value)
    raise TypeError(f"unsupported JSON value type: {type(value)!r}")


def freeze_c6_json_object(value: dict[str, Any]) -> FrozenJsonObject:
    """Freeze one JSON object with family-local markers at every level."""

    if not isinstance(value, dict):
        raise TypeError("expected a JSON object value")
    frozen = freeze_c6_json_value(value)
    if not isinstance(frozen, _C6FrozenObjectMarker):
        raise TypeError("frozen object did not produce an object marker")
    return frozen


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    value: T
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    code: str
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


InterpreterOutcome: TypeAlias = InterpreterSuccess[T] | InterpreterFailure


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _rebuild_value(value: Any, hint: Any) -> Any:
    if value is None or hint is Any:
        return value
    origin = get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        candidates = [
            candidate for candidate in get_args(hint) if candidate is not type(None)
        ]
        if value is None:
            return None
        for candidate in candidates:
            try:
                return _rebuild_value(value, candidate)
            except (TypeError, ValueError):
                continue
        raise ValueError(f"cannot rebuild union value for {hint}")
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_rebuild_value(item, args[0]) for item in value)
        return tuple(
            _rebuild_value(item, args[index]) for index, item in enumerate(value)
        )
    if origin is list:
        return [_rebuild_value(item, get_args(hint)[0]) for item in value]
    if dataclasses.is_dataclass(hint):
        return _decode_plain(hint, value)
    return value


def _decode_plain(cls: type[Any], value: dict[str, Any]) -> Any:
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(
            f"{cls.__name__} codec rejected payload fields: "
            f"missing={missing} extra={extra}"
        )
    namespace = dict(vars(sys.modules[cls.__module__]))
    namespace.update(vars(_algebra))
    hints = typing.get_type_hints(cls, globalns=namespace)
    kwargs = {
        item.name: _rebuild_value(value[item.name], hints.get(item.name, item.type))
        for item in fields(cls)
    }
    return cls(**kwargs)


def build_payload_codec(
    *,
    codec_id: str,
    codec_version: str,
    contract_ref: OperationContractRef,
    payload_type_id: str,
    dto_cls: type[Any],
) -> PayloadCodec:
    """Build a strict family-local payload codec rejecting field drift."""

    def encode(value: Any) -> dict[str, Any]:
        if not isinstance(value, dto_cls):
            raise TypeError(f"{codec_id} codec expected {dto_cls.__name__}")
        result = _plain(value)
        if not isinstance(result, dict):
            raise TypeError("payload codec produced a non-object encoding")
        return result

    def decode(value: dict[str, Any]) -> Any:
        if not isinstance(value, dict):
            raise TypeError("payload codec requires a JSON object")
        return _decode_plain(dto_cls, value)

    return PayloadCodec(
        codec_id=codec_id,
        codec_version=codec_version,
        contract_ref=contract_ref,
        payload_type_id=payload_type_id,
        encode=encode,
        decode=decode,
        codec_digest=codec_digest(
            codec_id=codec_id,
            codec_version=codec_version,
            contract_ref=contract_ref,
            payload_type_id=payload_type_id,
        ),
    )


def c6_deployment_catalog_digest() -> str:
    """Immutable family deployment identity distinct from each operation catalog."""

    return content_digest(
        {
            "schema": _C6_DEPLOYMENT_CATALOG_SCHEMA,
            "family": "agent-core-c6",
            "cells": ("C6.1", "C6.2", "C6.3"),
            "legacy_interpreters": (
                "legacy.agent_core.c6_1.episode.v1",
                "legacy.agent_core.c6_2.provider.v1",
                "legacy.agent_core.c6_3.redaction.v1",
            ),
            "successor_interpreters": (
                "successor.agent_core.c6_1.episode.v1",
                "successor.agent_core.c6_2.provider.v1",
                "successor.agent_core.c6_3.redaction.v1",
            ),
            "provider_calls": 0,
            "network_required": False,
        }
    )


def rollback_authority_ceiling() -> dict[str, Any]:
    """Deterministic local-only rollback/authority ceiling for the C6 family."""

    return {
        "schema": "mrw.successor.agent-core.c6.rollback-ceiling.v1",
        "status": "LOCAL_FIXTURE_ONLY_PROMOTED_NOT_LIVE",
        "provider_calls": 0,
        "network_required": False,
        "raw_value_persisted": False,
        "successor_journal_retained_on_rollback": True,
        "dual_claim_authority": False,
        "authority": {
            "business_authority_migrated": False,
            "successor_claim_enabled": False,
            "live_provider": False,
            "external_delivery": False,
            "production_canonical_write": False,
            "cutover": False,
            "authority_transfer": False,
        },
    }


def family_digest(value: Any) -> str:
    """Deterministic SHA-256 over canonical family JSON content."""

    return content_digest(
        {"schema": "mrw.successor.agent-core.c6.content.v1", "value": value}
    )


def thaw_json_value(value: Any) -> Any:
    """Canonical recursive thaw from frozen JSON back to dict/list scalars.

    ``freeze_c6_json_object`` marks objects with
    ``_C6FrozenObjectMarker`` at every level and freezes arrays to plain
    tuples.  Thawing uses marker identity, never a tuple-shape heuristic, so
    empty arrays and ambiguous arrays-of-pairs stay arrays.  This is the
    single boundary helper that restores plain ``dict``/``list`` values
    before legacy or capability adapters hand tool arguments to codecs and
    payload builders.  It never reintroduces raw secret bytes; it only
    changes container representation.
    """

    if isinstance(value, (_FrozenJsonObjectMarker, _C6FrozenObjectMarker)):
        return {str(key): thaw_json_value(item) for key, item in value}
    if isinstance(value, dict):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    if isinstance(value, list):
        return [thaw_json_value(item) for item in value]
    return value


def build_p3_c6_fragment(
    *,
    files: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    independent_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic P3 C6 evidence fragment (no raw values)."""

    ordered_files = sorted(files, key=lambda entry: entry["path"])
    ordered_cells = sorted(cells, key=lambda entry: entry["cell"])
    review = independent_review or {
        "task": None,
        "disposition": "PENDING_INDEPENDENT_REVIEW",
        "open_p0": [],
        "open_p1": ["P3C6_INDEPENDENT_REVIEW_NOT_RUN"],
    }
    fragment = {
        "schema": "mrw.successor.p3-fragment.v1",
        "family": "C6",
        "status": "IMPLEMENTED_LOCAL_ONLY_PROMOTED_NOT_LIVE",
        "provider_calls": 0,
        "network_required": False,
        "raw_sensitive_values_absent": True,
        "cells": ordered_cells,
        "files": ordered_files,
        "independent_review": review,
        "authority": rollback_authority_ceiling()["authority"],
        "rollback": {
            "successor_journal_retained_on_rollback": True,
            "dual_claim_authority": False,
        },
        "content_digest": "",
    }
    fragment["content_digest"] = content_digest(
        fragment, omit_fields=("content_digest",)
    )
    return fragment
