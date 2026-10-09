"""Canonical contracts for installed single-item batch dispatch."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Literal,
    SupportsIndex,
    SupportsInt,
    Mapping,
    NoReturn,
    TypeGuard,
)

from functorial_kit import Failure

from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)

from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonObject,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import (
    PayloadCodec,
    codec_digest,
    dataclass_codec,
)
from app.successor_runtime.capabilities.profiles import (
    OperationProfiles,
    build_operation_profiles,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    OperationContractRef,
    OperationContract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "BATCH_TASK_OWNER",
    "BATCH_TASK_AUTHORITY_SCHEMA",
    "BATCH_TASK_BUDGET_PROFILE",
    "BATCH_TASK_CATALOG_ID",
    "BATCH_TASK_DEADLINE_POLICY",
    "BATCH_TASK_FAILURE_UNION",
    "BATCH_TASK_IDEMPOTENCY_PROFILE",
    "BATCH_TASK_SECURITY_PROFILE",
    "DISPATCH_SINGLE_KIND",
    "DISPATCH_SINGLE_OPERATION_ID",
    "DISPATCH_SINGLE_OWNER",
    "DISPATCH_SINGLE_PAYLOAD_SCHEMA",
    "DISPATCH_SINGLE_ACK_SCHEMA",
    "DISPATCH_SINGLE_PAYLOAD_CODEC_ID",
    "DISPATCH_SINGLE_ACK_CODEC_ID",
    "DISPATCH_SINGLE_SEMANTIC_IDENTITY",
    "DISPATCH_SINGLE_OBSERVATION_PROFILE",
    "DISPATCH_SINGLE_PAYLOAD_TYPE",
    "DISPATCH_SINGLE_ACK_TYPE",
    "AgentBatchSubmissionItem",
    "BatchTaskSingleDispatchAck",
    "BatchTaskSingleDispatchPayload",
    "agent_batch_contract_failure",
    "build_batch_task_single_dispatch_catalog",
    "build_batch_task_single_dispatch_ack_codec",
    "build_batch_task_single_dispatch_contract",
    "build_batch_task_single_dispatch_payload_codec",
    "build_batch_task_single_dispatch_profiles",
    "build_batch_task_single_dispatch_registry",
    "derive_dispatch_task_id",
    "derive_dispatch_run_id",
    "agent_batch_hex64_failure",
    "raise_agent_batch_contract_failure",
]


BATCH_TASK_OWNER = "batch.task.v2"
BATCH_TASK_CATALOG_ID = "mrw.batch.task.operations.v2"
BATCH_TASK_AUTHORITY_SCHEMA = "mrw.batch.task.authority.v2"
BATCH_TASK_IDEMPOTENCY_PROFILE = "mrw.batch.task.idempotency.v2"
BATCH_TASK_SECURITY_PROFILE = "mrw.batch.task.security.pure.v2"
BATCH_TASK_FAILURE_UNION = "mrw.batch.task.failures.v2"
BATCH_TASK_BUDGET_PROFILE = "mrw.batch.task.budget.v2"
BATCH_TASK_DEADLINE_POLICY = "mrw.batch.task.deadline.v2"

_BATCH_TASK_CONTRACT_WITNESS = (
    "test:test_w06_retained_failure_lifts_preserve_public_abi"
)
_BATCH_TASK_CONTRACT_CONTEXT_KEYS = frozenset(
    {"capability", "public_exception", "public_message", "site", "witness"}
)


def _failure(
    code: str,
    message: str,
    *,
    site: str = "batch.task",
    public_exception: str = "ValueError",
    public_message: str | None = None,
) -> Failure:
    return successor_capability_contract_failures.fail(
        code,
        message,
        {
            "capability": BATCH_TASK_OWNER,
            "public_exception": public_exception,
            "public_message": message if public_message is None else public_message,
            "site": site,
            "witness": _BATCH_TASK_CONTRACT_WITNESS,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    """Lift one complete typed failure at the retained public ABI boundary."""

    context = failure.context or {}
    if (
        failure.family != successor_capability_contract_failures.name
        or _BATCH_TASK_CONTRACT_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=batch.task.v2 class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_retained_failure_lifts_preserve_public_abi
        raise TypeError("contract lift context is incomplete or inconsistent")
    # kit:boundary owner=batch.task.v2 class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_w06_retained_failure_lifts_preserve_public_abi
    raise exception_type(str(context["public_message"]))


agent_batch_contract_failure = _failure
raise_agent_batch_contract_failure = _raise_contract_failure


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _is_object_mapping(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_string_key_mapping(value: object) -> TypeGuard[dict[str, object]]:
    if not _is_object_mapping(value):
        return False
    return all(isinstance(key, str) for key in value)


def _is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _is_int_convertible(
    value: object,
) -> TypeGuard[str | bytes | bytearray | SupportsInt | SupportsIndex]:
    return isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex))


def _is_dataclass_type(value: object) -> TypeGuard[type]:
    return isinstance(value, type) and dataclasses.is_dataclass(value)


def _new_object_mapping() -> dict[str, object]:
    return {}


def _hex64_failure(value: str, field_name: str) -> Failure | None:
    if _HEX64.fullmatch(value) is None:
        return _failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            site=f"digest/{field_name}",
        )
    return None


agent_batch_hex64_failure = _hex64_failure


DISPATCH_SINGLE_KIND = "batch.task.dispatch_single.v2"
DISPATCH_SINGLE_OPERATION_ID = DISPATCH_SINGLE_KIND
DISPATCH_SINGLE_OWNER = BATCH_TASK_OWNER
DISPATCH_SINGLE_PAYLOAD_SCHEMA = "mrw.batch.task-dispatch.payload.v2"
DISPATCH_SINGLE_ACK_SCHEMA = "mrw.batch.task-dispatch.ack.v2"
DISPATCH_SINGLE_PAYLOAD_CODEC_ID = "mrw.batch.task-dispatch.payload.codec.v2"
DISPATCH_SINGLE_ACK_CODEC_ID = "mrw.batch.task-dispatch.ack.codec.v2"
DISPATCH_SINGLE_CATALOG_ID = BATCH_TASK_CATALOG_ID
DISPATCH_SINGLE_CATALOG_VERSION = "1.0.0"
DISPATCH_SINGLE_SEMANTIC_IDENTITY = "batch.task.dispatch-single"
DISPATCH_SINGLE_OBSERVATION_PROFILE = "mrw.batch.task-dispatch.observation.v2"
DISPATCH_SINGLE_PAYLOAD_TYPE = ObjectType(
    "BatchTaskSingleDispatchPayload.v1",
    codec_id=DISPATCH_SINGLE_PAYLOAD_CODEC_ID,
)
DISPATCH_SINGLE_ACK_TYPE = ObjectType(
    "BatchTaskSingleDispatchAck.v1",
    codec_id=DISPATCH_SINGLE_ACK_CODEC_ID,
)
def _normalize_terms(value: object) -> tuple[str, ...]:
    out: list[str] = []
    raw = value
    if isinstance(raw, str):
        raw = [raw]
    if _is_object_sequence(raw):
        for item in raw:
            text = str("" if not item else item).strip()
            if text and text not in out:
                out.append(text)
    return tuple(out)


def _normalize_string_list(value: object) -> tuple[str, ...]:
    if not _is_object_sequence(value):
        return ()
    out: list[str] = []
    for item in value:
        text = str("" if not item else item).strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _normalize_int(value: object, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value) if _is_int_convertible(value) else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _normalize_days_back(value: object) -> int | None:
    try:
        parsed = int(value) if _is_int_convertible(value) else 0
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return min(parsed, 365)


def _normalize_override_params(value: object) -> dict[str, object]:
    if _is_object_mapping(value):
        return {str(key): item for key, item in value.items()}
    return {}


def _submission_item_failure(item: AgentBatchSubmissionItem) -> Failure | None:
    if not str(item.job_id or "").strip():
        return _failure(
            "schema_contract_invalid", "AgentBatchSubmissionItem.job_id is required"
        )
    return None


@dataclass(frozen=True, slots=True)
class AgentBatchSubmissionItem:
    job_id: str
    channel: str
    query_terms: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    max_items: int = 20
    provider: str = "auto"
    language: str = "zh"
    days_back: int | None = None
    item_key: str | None = None
    scope: str | None = None
    platforms: tuple[str, ...] = ()
    override_params: Mapping[str, object] = field(default_factory=_new_object_mapping)
    lane: str = "main"
    workflow_run_id: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        failure = _submission_item_failure(self)
        if failure is not None:
            _raise_contract_failure(failure)
        object.__setattr__(
            self, "query_terms", tuple(_normalize_terms(self.query_terms))
        )
        object.__setattr__(self, "urls", tuple(_normalize_string_list(self.urls)))
        object.__setattr__(
            self, "platforms", tuple(_normalize_string_list(self.platforms))
        )
        object.__setattr__(
            self,
            "max_items",
            _normalize_int(self.max_items, 20, min_value=1, max_value=100),
        )
        object.__setattr__(
            self, "provider", str(self.provider or "auto").strip() or "auto"
        )
        object.__setattr__(self, "language", str(self.language or "zh").strip() or "zh")
        object.__setattr__(self, "days_back", _normalize_days_back(self.days_back))
        object.__setattr__(self, "item_key", str(self.item_key or "").strip() or None)
        object.__setattr__(self, "scope", str(self.scope or "").strip() or None)
        object.__setattr__(
            self, "override_params", _normalize_override_params(self.override_params)
        )


def _dispatch_single_item_failure(item: AgentBatchSubmissionItem) -> Failure | None:
    channel = str(item.channel or "").strip().lower()
    if channel not in {"search.market", "source_library"}:
        return _failure(
            "schema_contract_invalid",
            f"unsupported dispatch item channel {channel!r}",
        )
    if channel == "search.market" and not item.query_terms:
        return _failure(
            "schema_contract_invalid",
            "search.market dispatch item requires query_terms",
        )
    if channel == "source_library" and not str(item.item_key or "").strip():
        return _failure(
            "schema_contract_invalid",
            "source_library dispatch item requires item_key",
        )
    return None


def _dispatch_single_payload_identity_failure(
    payload: BatchTaskSingleDispatchPayload,
) -> Failure | None:
    if payload.schema_version != DISPATCH_SINGLE_PAYLOAD_SCHEMA:
        return _failure("schema_contract_invalid", "unsupported dispatch payload schema")
    if payload.operation_kind != DISPATCH_SINGLE_KIND:
        return _failure(
            "schema_contract_invalid", "unsupported dispatch payload operation kind"
        )
    if not payload.dispatch_id or not payload.project_key or not payload.capability_id:
        return _failure(
            "schema_contract_invalid",
            "dispatch payload requires id/project/capability identity",
        )
    failure = _dispatch_single_item_failure(payload.item)
    if failure is not None:
        return failure
    return _hex64_failure(
        payload.scope_digest, "BatchTaskSingleDispatchPayload.scope_digest"
    )


def _dispatch_single_payload_digest_failure(
    payload: BatchTaskSingleDispatchPayload,
) -> Failure | None:
    failure = _hex64_failure(
        payload.payload_digest, "BatchTaskSingleDispatchPayload.payload_digest"
    )
    if failure is not None:
        return failure
    expected = content_digest(payload, omit_fields=("payload_digest",))
    if payload.payload_digest != expected:
        return _failure(
            "digest_contract_invalid",
            "BatchTaskSingleDispatchPayload.payload_digest does not match content",
        )
    return None


@dataclass(frozen=True, slots=True)
class BatchTaskSingleDispatchPayload:
    """Exact single-item dispatch payload (batch.task.dispatch_single.v2).

    Reuses ``AgentBatchSubmissionItem`` as the single domain item and carries the
    exact project scope plus routing context.  It never self-reports actor role
    or permissions: those are derived from the task contract and bound by server
    admission.
    """

    schema_version: Literal["mrw.batch.task-dispatch.payload.v2"]
    operation_kind: Literal["batch.task.dispatch_single.v2"]
    dispatch_id: str
    project_key: str
    resolved_schema: str
    registry_revision: int
    scope_incarnation: str
    scope_digest: str
    capability_id: str
    item: AgentBatchSubmissionItem
    lane: str
    queue: str | None = None
    trace_id: str | None = None
    workflow_run_id: str | None = None
    runtime_readback: Mapping[str, object] = field(default_factory=_new_object_mapping)
    payload_digest: str = ""

    def __post_init__(self) -> None:
        failure = _dispatch_single_payload_identity_failure(self)
        if failure is not None:
            _raise_contract_failure(failure)
        object.__setattr__(self, "lane", str(self.lane or "main").strip() or "main")
        object.__setattr__(self, "queue", str(self.queue or "").strip() or None)
        object.__setattr__(
            self, "trace_id", str(self.trace_id or "").strip() or None
        )
        object.__setattr__(
            self, "workflow_run_id", str(self.workflow_run_id or "").strip() or None
        )
        object.__setattr__(self, "runtime_readback", dict(self.runtime_readback or {}))
        if self.payload_digest == "":
            object.__setattr__(
                self,
                "payload_digest",
                content_digest(self, omit_fields=("payload_digest",)),
            )
        else:
            failure = _dispatch_single_payload_digest_failure(self)
            if failure is not None:
                _raise_contract_failure(failure)


def _dispatch_single_ack_failure(ack: BatchTaskSingleDispatchAck) -> Failure | None:
    if not ack.dispatch_id or not ack.celery_task_id:
        return _failure(
            "schema_contract_invalid",
            "dispatch ack requires dispatch and celery task identity",
        )
    channel = str(ack.channel or "").strip().lower()
    if channel not in {"search.market", "source_library"}:
        return _failure(
            "schema_contract_invalid", f"unsupported dispatch ack channel {channel!r}"
        )
    if not ack.queue:
        return _failure("schema_contract_invalid", "dispatch ack requires queue")
    return None


def _dispatch_single_ack_digest_failure(
    ack: BatchTaskSingleDispatchAck,
) -> Failure | None:
    failure = _hex64_failure(ack.ack_digest, "BatchTaskSingleDispatchAck.ack_digest")
    if failure is not None:
        return failure
    expected = content_digest(ack, omit_fields=("ack_digest",))
    if ack.ack_digest != expected:
        return _failure(
            "digest_contract_invalid",
            "BatchTaskSingleDispatchAck.ack_digest does not match content",
        )
    return None


@dataclass(frozen=True, slots=True)
class BatchTaskSingleDispatchAck:
    """Typed ACK for a single dispatch: real celery task id plus dispatch params.

    It records the Celery apply result and the original routing context.  It is
    not a business terminal state; acceptance/terminal state stays with the
    eventual worker readback.
    """

    schema_version: Literal["mrw.batch.task-dispatch.ack.v2"]
    operation_kind: Literal["batch.task.dispatch_single.v2"]
    dispatch_id: str
    channel: str
    celery_task_id: str
    lane: str
    queue: str
    trace_id: str | None = None
    workflow_run_id: str | None = None
    runtime_readback: Mapping[str, object] = field(default_factory=_new_object_mapping)
    ack_digest: str = ""

    def __post_init__(self) -> None:
        failure = _dispatch_single_ack_failure(self)
        if failure is not None:
            _raise_contract_failure(failure)
        object.__setattr__(self, "channel", str(self.channel or "").strip().lower())
        object.__setattr__(self, "lane", str(self.lane or "main").strip() or "main")
        object.__setattr__(self, "queue", str(self.queue or "").strip())
        object.__setattr__(
            self, "trace_id", str(self.trace_id or "").strip() or None
        )
        object.__setattr__(
            self, "workflow_run_id", str(self.workflow_run_id or "").strip() or None
        )
        object.__setattr__(self, "runtime_readback", dict(self.runtime_readback or {}))
        if self.ack_digest == "":
            object.__setattr__(
                self,
                "ack_digest",
                content_digest(self, omit_fields=("ack_digest",)),
            )
        else:
            failure = _dispatch_single_ack_digest_failure(self)
            if failure is not None:
                _raise_contract_failure(failure)


def _decode_nested(
    dto_cls: type,
    value: Mapping[str, object],
    *,
    _seen: set[type] | None = None,
) -> object:
    """Decode a dataclass payload while restoring nested dataclass fields."""
    import typing

    def decode_sequence_item(item_cls: type | None, item: object) -> object:
        if (
            item_cls is not None
            and _is_dataclass_type(item_cls)
            and _is_string_key_mapping(item)
        ):
            return _decode_nested(item_cls, dict(item), _seen=seen)
        return item

    seen: set[type] = _seen if _seen is not None else set()
    restored: dict[str, object] = {}
    hints = typing.get_type_hints(dto_cls)
    for field_def in dataclasses.fields(dto_cls):
        if field_def.name not in value:
            continue
        field_type = hints.get(field_def.name, field_def.type)
        origin = typing.get_origin(field_type)
        args = typing.get_args(field_type)
        raw = value[field_def.name]
        if origin in (tuple, list):
            item_cls: type | None = args[0] if args else None
            if not _is_object_sequence(raw):
                _raise_contract_failure(
                    _failure(
                        "codec_input_invalid",
                        "dataclass sequence field requires a sequence",
                    ),
                    TypeError,
                )
            items = tuple(raw)
            restored[field_def.name] = (
                tuple(
                    decode_sequence_item(item_cls, item)
                    for item in items
                )
                if origin is tuple
                else [
                    decode_sequence_item(item_cls, item)
                    for item in items
                ]
            )
        elif _is_string_key_mapping(raw) and _is_dataclass_type(field_type):
            restored[field_def.name] = _decode_nested(field_type, raw, _seen=seen)
        else:
            restored[field_def.name] = raw
    return dto_cls(**restored)


def build_batch_task_single_dispatch_profiles() -> Annotated[OperationProfiles, 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    """Exact single-item dispatch operation profiles via the shared rule."""

    return build_operation_profiles(
        identity="batch.task.dispatch-single",
        version="1.0.0",
        semantic={
            "reads": ("AgentBatchSubmissionItem.v1", "BatchTaskSingleDispatchPayload.v1"),
            "creates": ("BatchTaskSingleDispatchAck.v1",),
            "creates_relations": (),
            "declared_loss": (),
            "observation_profile_ref": DISPATCH_SINGLE_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": True,
            "irreversible": False,
            "cancellation_points": ("claim_time",),
            "internal_export_only": False,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": BATCH_TASK_IDEMPOTENCY_PROFILE,
        },
        resource={
            "resource_classes": ("NETWORK_IO",),
            "concurrency_key": "batch.task.dispatch-single",
            "budget_units": "units",
            "default_soft_limit_seconds": 5,
            "default_hard_limit_seconds": 30,
            "node_profile_selector": "any",
            "budget_ref": BATCH_TASK_BUDGET_PROFILE,
            "deadline_policy_ref": BATCH_TASK_DEADLINE_POLICY,
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": (
                "DISPATCH_ITEM_UNSUPPORTED",
                "DISPATCH_SKILL_UNAVAILABLE",
                "DISPATCH_QUEUE_INVALID",
                "DISPATCH_CELERY_APPLY_FAILED",
            ),
            "retryable": False,
            "degraded_acceptable": False,
            "unknown_outcome_supported": True,
            "readback_or_compensation": "readback",
            "failure_union_ref": BATCH_TASK_FAILURE_UNION,
            "retryable_failure_kinds": (),
            "readback_profile_ref": DISPATCH_SINGLE_OBSERVATION_PROFILE,
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": DISPATCH_SINGLE_OWNER,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "interpreter_profile_id": "batch.task.dispatch-single.native",
            "supported_contract_kinds": (DISPATCH_SINGLE_KIND,),
            "supported_contract_refs": (),
            "dependency_digest": content_digest(
                {
                    "interpreter": "batch.task.dispatch-single.native",
                    "version": "1.0.0",
                    "boundary": "single-item skill dispatch; no legacy service import",
                }
            ),
            "security_profile_ref": BATCH_TASK_SECURITY_PROFILE,
            "resource_profile_ref": "batch.task.dispatch-single.resource@1.0.0",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "claim_time",
            "idempotency_profile_ref": BATCH_TASK_IDEMPOTENCY_PROFILE,
            "authoritative_readback_profile_ref": None,
            "receipt_codec_ref": DISPATCH_SINGLE_ACK_CODEC_ID,
        },
        observation={
            "observation_profile_id": DISPATCH_SINGLE_OBSERVATION_PROFILE,
            "dimensions": ("dispatch_id", "channel", "celery_task_id", "lane", "queue"),
            "compatible_with_legacy": False,
            "observation_schema_ref": DISPATCH_SINGLE_OBSERVATION_PROFILE,
        },
    )


def build_batch_task_single_dispatch_contract() -> Annotated[OperationContract, 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    """Independent EFFECTFUL contract for single-item skill dispatch."""

    return build_batch_task_single_dispatch_profiles().contract(
        kind=DISPATCH_SINGLE_KIND,
        contract_version="1.0.0",
        input_type=DISPATCH_SINGLE_PAYLOAD_TYPE,
        output_type=DISPATCH_SINGLE_ACK_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=DISPATCH_SINGLE_OWNER,
    )


def derive_dispatch_task_id(
    *,
    project_scope_digest: str,
    capability_id: str,
    dispatch_id: str,
) -> str:
    """Server-derived deterministic broker task id for one single dispatch."""

    return sha256_hex(
        canonical_json(
            {
                "schema": "mrw.batch.dispatch-task.v1",
                "project_scope_digest": project_scope_digest,
                "capability_id": capability_id,
                "dispatch_id": dispatch_id,
            }
        ).encode("utf-8")
    )


def derive_dispatch_run_id(
    *,
    project_scope_digest: str,
    actor_id: str,
    logical_request_id: str,
) -> str:
    """Deterministic server run identity from scope + actor + logical request."""

    return sha256_hex(
        canonical_json(
            {
                "schema": "mrw.batch.dispatch-run.v1",
                "project_scope_digest": project_scope_digest,
                "actor_id": actor_id,
                "logical_request_id": logical_request_id,
            }
        ).encode("utf-8")
    )


def build_batch_task_single_dispatch_payload_codec(
    contract_ref: OperationContractRef,
) -> Annotated[PayloadCodec[BatchTaskSingleDispatchPayload], 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    """Exact payload codec restoring the nested single item and routing context."""

    base_codec = dataclass_codec(
        codec_id=DISPATCH_SINGLE_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=DISPATCH_SINGLE_PAYLOAD_TYPE.type_id,
        dto_cls=BatchTaskSingleDispatchPayload,
    )

    def encode(value: object) -> CanonicalJsonObject:
        if not isinstance(value, BatchTaskSingleDispatchPayload):
            _raise_contract_failure(
                _failure(
                    "codec_contract_invalid",
                    "dispatch payload codec expected BatchTaskSingleDispatchPayload",
                    site="dispatch_codec/encode",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        return base_codec.encode_payload(value)

    def decode(value: CanonicalJsonObject) -> BatchTaskSingleDispatchPayload:
        decoded = _decode_nested(BatchTaskSingleDispatchPayload, value)
        if not isinstance(decoded, BatchTaskSingleDispatchPayload):
            _raise_contract_failure(
                _failure(
                    "codec_contract_invalid",
                    "dispatch payload codec returned an invalid payload type",
                    site="dispatch_codec/decode",
                    public_exception="TypeError",
                ),
                TypeError,
            )
        return decoded

    return PayloadCodec(
        codec_id=DISPATCH_SINGLE_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=DISPATCH_SINGLE_PAYLOAD_TYPE.type_id,
        encode=encode,
        decode=decode,
        codec_digest=codec_digest(
            codec_id=DISPATCH_SINGLE_PAYLOAD_CODEC_ID,
            codec_version="1",
            contract_ref=contract_ref,
            payload_type_id=DISPATCH_SINGLE_PAYLOAD_TYPE.type_id,
        ),
    )


def build_batch_task_single_dispatch_ack_codec(
    contract_ref: OperationContractRef,
) -> Annotated[PayloadCodec[BatchTaskSingleDispatchAck], 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    """Flat typed ACK codec for the single-item dispatch output."""

    return dataclass_codec(
        codec_id=DISPATCH_SINGLE_ACK_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=DISPATCH_SINGLE_ACK_TYPE.type_id,
        dto_cls=BatchTaskSingleDispatchAck,
    )


def build_batch_task_single_dispatch_catalog(
    contract: OperationContract | None = None,
) -> Annotated[OperationContractCatalogSnapshot, 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    operation = contract or build_batch_task_single_dispatch_contract()
    return OperationContractCatalogSnapshot(
        catalog_id=DISPATCH_SINGLE_CATALOG_ID,
        catalog_version=DISPATCH_SINGLE_CATALOG_VERSION,
        entries=(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            ),
        ),
    )


def build_batch_task_single_dispatch_registry(
    contract: OperationContract | None = None,
) -> Annotated[OperationContractRegistry, 'kit:non-authoritative derived_as=view fact_source=batch_task_dispatch_definition witness=test:test_dispatch_single_program_compiles_to_one_effect_step']:
    operation = contract or build_batch_task_single_dispatch_contract()
    return OperationContractRegistry(
        build_batch_task_single_dispatch_catalog(operation),
        (operation,),
    )
