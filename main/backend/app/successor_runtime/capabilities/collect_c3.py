"""Frozen typed contracts for the C3 collect batch-traverse and result-fold atoms.

This module owns the canonical vocabulary for the C3.1 and C3.2 cells:
authenticated request refs, the finite ordered batch plan, element identity,
element outcomes, attempt receipts, the ordered outcome sequence and the
aggregate outcome union.  It also owns the pure deterministic plan rules and
the pure ordered fold used by both the successor interpreter and the legacy
parity adapter.

The module is capability-boundary only: it never imports legacy service
packages and never performs network, database, provider or credential work.
Raw legacy dictionaries stay at the codec/parity boundary.
"""

from __future__ import annotations

import dataclasses
import math
import re
import types
import typing
from dataclasses import dataclass, field, fields
from typing import (
    Any,
    Literal,
    TypeAlias,
    get_args,
    get_origin,
)

from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, codec_digest
from app.successor_runtime.capabilities.contracts import OperationContract
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    FrozenJsonValue,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AUTHENTICATED_COLLECT_SCOPE_TYPE",
    "COLLECT_AGGREGATE_OUTCOME_TYPE",
    "COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF",
    "COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF",
    "COLLECT_ATTEMPT_RECEIPT_TYPE",
    "COLLECT_BATCH_ELEMENT_TYPE",
    "COLLECT_BATCH_PLAN_TYPE",
    "COLLECT_C3_1_KIND",
    "COLLECT_C3_1_OPERATION_ID",
    "COLLECT_C3_1_OWNER",
    "COLLECT_C3_1_PAYLOAD_CODEC_ID",
    "COLLECT_C3_1_PAYLOAD_SCHEMA",
    "COLLECT_C3_1_PAYLOAD_TYPE",
    "COLLECT_C3_1_RESULT_TYPE",
    "COLLECT_C3_1_SEMANTIC_IDENTITY",
    "COLLECT_C3_2_KIND",
    "COLLECT_C3_2_OPERATION_ID",
    "COLLECT_C3_2_OWNER",
    "COLLECT_C3_2_PAYLOAD_CODEC_ID",
    "COLLECT_C3_2_PAYLOAD_SCHEMA",
    "COLLECT_C3_2_PAYLOAD_TYPE",
    "COLLECT_C3_2_SEMANTIC_IDENTITY",
    "COLLECT_C3_CATALOG_VERSION",
    "COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF",
    "COLLECT_ELEMENT_OUTCOME_TYPE",
    "COLLECT_FOLD_OBSERVATION_PROFILE",
    "COLLECT_FOLD_RESOURCE_CEILING",
    "COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF",
    "COLLECT_FOLD_RESULT_TYPE",
    "COLLECT_RECEIPT_DEDUPE_STABLE_FIRST_REF",
    "COLLECT_REQUEST_TYPE",
    "COLLECT_TRAVERSAL_OBSERVATION_PROFILE",
    "COLLECT_TRAVERSAL_RESULT_TYPE",
    "CollectAggregateCounts",
    "CollectAggregateFailed",
    "CollectAggregateOutcome",
    "CollectAggregatePartial",
    "CollectAggregateSucceeded",
    "CollectAttemptReceipt",
    "CollectBatchElement",
    "CollectBatchElementPayload",
    "CollectBatchPlan",
    "CollectC3CapabilityBundle",
    "CollectCancellationReceipt",
    "CollectCounts",
    "CollectElementError",
    "CollectElementFailed",
    "CollectElementOutcome",
    "CollectElementSucceeded",
    "CollectFoldContractFailure",
    "CollectFoldPayload",
    "CollectFoldResourceCeiling",
    "CollectLegacyRequestSnapshot",
    "CollectRequestRef",
    "CollectResourcePolicy",
    "CollectTraversalBypassed",
    "CollectTraversalObservation",
    "CollectTraversalResult",
    "CollectTraversalSingleton",
    "FrozenJsonValue",
    "OrderedCollectElementOutcomeSequence",
    "OrderedTraversalAborted",
    "OrderedTraversalCompleted",
    "build_collect_batch_plan",
    "build_collect_c3_bundle",
    "build_collect_c3_catalog",
    "build_collect_c3_registry",
    "build_collect_fold_payload",
    "build_collect_request_ref",
    "collect_batch_element_payload_from_dicts",
    "collect_claim_route",
    "collect_fold_payload_from_dicts",
    "collect_request_ref_from_dict",
    "collect_runtime_mode",
    "deployment_catalog_digest",
    "fold_ordered_results",
    "per_batch_limit_for",
    "receipt_implies_completed",
    "require_fold_ceiling",
    "resolve_auto_batch_fail_fast",
    "resolve_auto_batch_parallelism",
    "should_auto_batch",
    "split_query_terms",
]


COLLECT_C3_1_KIND = "collect.execute_batch_element.v1"
COLLECT_C3_2_KIND = "collect.fold_ordered_results.v1"
COLLECT_C3_1_OWNER = "collect.c3_1.v1"
COLLECT_C3_2_OWNER = "collect.c3_2.v1"
COLLECT_C3_1_OPERATION_ID = "collect.execute_batch_element"
COLLECT_C3_2_OPERATION_ID = "collect.fold_ordered_results"
COLLECT_C3_1_PAYLOAD_SCHEMA = "mrw.successor.collect.c3-1.payload.v1"
COLLECT_C3_2_PAYLOAD_SCHEMA = "mrw.successor.collect.c3-2.payload.v1"
COLLECT_C3_1_PAYLOAD_CODEC_ID = "mrw.successor.collect.c3-1.payload.codec.v1"
COLLECT_C3_2_PAYLOAD_CODEC_ID = "mrw.successor.collect.c3-2.payload.codec.v1"
COLLECT_C3_1_CATALOG_ID = "mrw.functorial-successor.collect.c3-1.operations"
COLLECT_C3_2_CATALOG_ID = "mrw.functorial-successor.collect.c3-2.operations"
COLLECT_C3_CATALOG_VERSION = "1.0.0"
COLLECT_TRAVERSAL_OBSERVATION_PROFILE = "collect.batch_traverse.ordered_observation.v1"
COLLECT_FOLD_OBSERVATION_PROFILE = "collect.result_fold.receipt_preservation.v1"
COLLECT_C3_1_SEMANTIC_IDENTITY = "collect.execute-batch-element"
COLLECT_C3_2_SEMANTIC_IDENTITY = "collect.fold-ordered-results"

COLLECT_REQUEST_SCHEMA_REF = "mrw.successor.collect.c3.request-ref.v1"
COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF = (
    "mrw.successor.collect.c3.legacy-request-snapshot.v1"
)
COLLECT_RESOURCE_POLICY_SCHEMA_REF = "mrw.successor.collect.c3.resource-policy.v1"
COLLECT_BATCH_ELEMENT_SCHEMA_REF = "mrw.successor.collect.c3.batch-element.v1"
COLLECT_BATCH_PLAN_SCHEMA_REF = "mrw.successor.collect.c3.batch-plan.v1"
COLLECT_ELEMENT_OUTCOME_SCHEMA_REF = "mrw.successor.collect.c3.element-outcome.v1"
COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF = "mrw.successor.collect.c3.attempt-receipt.v1"
COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF = "mrw.successor.collect.c3.aggregate-outcome.v1"
COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF = (
    "mrw.successor.collect.c3.traversal-observation.v1"
)
COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF = (
    "mrw.successor.collect.c3.cancellation-receipt.v1"
)
COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF = (
    "mrw.successor.collect.c3-2.resource-ceiling.v1"
)
COLLECT_RECEIPT_DEDUPE_STABLE_FIRST_REF = (
    "mrw.successor.collect.c3-2.receipt-dedupe.stable-first.v1"
)
DEPLOYMENT_CATALOG_SCHEMA_REF = "mrw.successor.collect.c3.deployment-catalog.v1"

COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF = (
    "mrw.successor.collect.c3-2.aggregation.accumulate.v1"
)
COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF = (
    "mrw.successor.collect.c3-2.aggregation.fail_fast_partial.v1"
)
COLLECT_AGGREGATION_POLICY_REFS = frozenset(
    {
        COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF,
    }
)

COLLECT_REQUEST_TYPE = ObjectType("CollectRequest.v1")
AUTHENTICATED_COLLECT_SCOPE_TYPE = ObjectType("AuthenticatedCollectScope.v1")
COLLECT_BATCH_ELEMENT_TYPE = ObjectType("CollectBatchElement.v1")
COLLECT_BATCH_PLAN_TYPE = ObjectType("CollectBatchPlan.v1")
COLLECT_ELEMENT_OUTCOME_TYPE = ObjectType("CollectElementOutcome.v1")
COLLECT_ATTEMPT_RECEIPT_TYPE = ObjectType("CollectAttemptReceipt.v1")
ORDERED_COLLECT_ELEMENT_OUTCOME_SEQUENCE_TYPE = ObjectType(
    "OrderedCollectElementOutcomeSequence.v1"
)
COLLECT_AGGREGATE_OUTCOME_TYPE = ObjectType("CollectAggregateOutcome.v1")
COLLECT_TRAVERSAL_RESULT_TYPE = ObjectType("CollectTraversalResult.v1")
COLLECT_C3_1_PAYLOAD_TYPE = ObjectType("CollectBatchElementPayload.v1")
COLLECT_C3_2_PAYLOAD_TYPE = ObjectType("CollectFoldPayload.v1")
COLLECT_C3_1_RESULT_TYPE = COLLECT_ELEMENT_OUTCOME_TYPE
COLLECT_FOLD_RESULT_TYPE = COLLECT_AGGREGATE_OUTCOME_TYPE

TraversalPolicy = Literal["STATIC_SHAPE", "MATERIALIZED_SHAPE"]
FailurePolicy = Literal["ACCUMULATE", "FAIL_FAST_WITH_PARTIAL_OBSERVATION"]
PlanDisposition = Literal["BYPASSED", "SINGLETON_IDENTITY", "TRAVERSE"]

COLLECT_AUTO_BATCH_CHANNELS = frozenset({"search.market", "search.policy"})
COLLECT_ELEMENT_ERROR_CODES = frozenset(
    {
        "auto_batch_execution_failed",
        "element_rejected",
        "runner_unavailable",
    }
)
_LEGACY_OBSERVATION_REF = re.compile(r"^legacy:[0-9a-f]{64}$")
_OBSERVED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def collect_runtime_mode(
    raw: str | None,
) -> Literal["legacy", "shadow", "canary", "on"]:
    """Fail-closed rollback route for ``SUCCESSOR_RUNTIME_COLLECT``."""

    value = str(raw or "").strip().lower()
    if value == "shadow":
        return "shadow"
    if value == "canary":
        return "canary"
    if value in {"on", "successor"}:
        return "on"
    return "legacy"


def collect_claim_route(mode: str) -> Literal["legacy", "shadow", "successor"]:
    """Route one logical run to at most one claim authority."""

    normalized = str(mode or "").strip().lower()
    if normalized == "shadow":
        return "shadow"
    if normalized in {"canary", "on", "successor"}:
        return "successor"
    return "legacy"


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive int")
    return value


def _require_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative int")
    return value


def _require_string_tuple(
    value: Any, field_name: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    items = tuple(str(item) for item in (value or ()))
    if not allow_empty and not items:
        raise ValueError(f"{field_name} must contain at least one string")
    return items


@dataclass(frozen=True, slots=True)
class VersionedSchema:
    """Explicit schema ref, per-field requiredness map and pinned digest."""

    schema_ref: str
    field_requiredness: tuple[tuple[str, bool], ...]
    schema_digest: str = ""

    def __post_init__(self) -> None:
        _require_non_empty_string(self.schema_ref, "VersionedSchema.schema_ref")
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
                "schema": "mrw.successor.collect.c3.schema.v1",
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


COLLECT_REQUEST_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_REQUEST_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("request_id", True),
        ("project_key", True),
        ("channel", True),
        ("request_digest", True),
    ),
)
COLLECT_REQUEST_SNAPSHOT_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("flow", True),
        ("channel", True),
        ("project_key", False),
        ("query_terms", True),
        ("urls", True),
        ("limit", False),
        ("options", True),
        ("source_context", True),
        ("snapshot_digest", True),
    ),
)
COLLECT_RESOURCE_POLICY_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_RESOURCE_POLICY_SCHEMA_REF,
    field_requiredness=(
        ("schema_ref", True),
        ("max_parallelism", True),
        ("deadline_seconds", False),
        ("cancellation", True),
        ("backpressure", True),
        ("provider_concurrency_key", True),
        ("policy_digest", True),
    ),
)
COLLECT_BATCH_ELEMENT_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_BATCH_ELEMENT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("element_id", True),
        ("input_index", True),
        ("query_terms", True),
        ("per_batch_limit", True),
        ("traversal_policy", True),
        ("failure_policy", True),
        ("element_digest", True),
    ),
)
COLLECT_BATCH_PLAN_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_BATCH_PLAN_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("plan_id", True),
        ("request_ref", True),
        ("disposition", True),
        ("traversal_policy", True),
        ("failure_policy", True),
        ("elements", True),
        ("per_batch_limit", True),
        ("requested_parallelism", True),
        ("effective_parallelism", True),
        ("batches_total", True),
        ("plan_digest", True),
    ),
)
COLLECT_ELEMENT_OUTCOME_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("element_id", True),
        ("input_index", True),
        ("status", True),
        ("counts", True),
        ("errors", False),
        ("error", False),
        ("links", True),
        ("receipt", False),
        ("legacy_observation_ref", True),
        ("outcome_digest", True),
    ),
)
COLLECT_ATTEMPT_RECEIPT_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("receipt_kind", True),
        ("provider_type", True),
        ("provider_job_id", True),
        ("provider_status", False),
        ("attempt_count", True),
        ("observed_at", True),
        ("raw_digest", True),
        ("authoritative_readback", True),
        ("receipt_digest", True),
    ),
)
COLLECT_AGGREGATE_OUTCOME_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("kind", True),
        ("ordered_outcomes", True),
        ("aggregate_counts", True),
        ("errors", False),
        ("receipts", True),
        ("links", True),
        ("reason", False),
        ("unconsumed_outcomes", False),
        ("aggregate_digest", True),
    ),
)
COLLECT_TRAVERSAL_OBSERVATION_SCHEMA = VersionedSchema(
    schema_ref=COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("observation_profile", True),
        ("request_ref", True),
        ("traversal_policy", True),
        ("failure_policy", True),
        ("ordered_outcomes", True),
        ("requested_parallelism", True),
        ("effective_parallelism", True),
        ("cancellation_observed", True),
        ("observation_digest", True),
    ),
)


@dataclass(frozen=True, slots=True)
class CollectRequestRef:
    """Explicit parent request reference bound to one project scope."""

    schema_version: Literal["mrw.successor.collect.c3.request-ref.v1"]
    request_id: str
    project_key: str
    channel: str
    request_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_REQUEST_SCHEMA_REF:
            raise ValueError(
                "CollectRequestRef.schema_version is not the frozen schema"
            )
        object.__setattr__(
            self, "request_id", _require_non_empty_string(self.request_id, "request_id")
        )
        object.__setattr__(
            self,
            "project_key",
            _require_non_empty_string(self.project_key, "project_key"),
        )
        object.__setattr__(
            self, "channel", _require_non_empty_string(self.channel, "channel")
        )
        expected = content_digest(
            {
                "schema": COLLECT_REQUEST_SCHEMA_REF,
                "request_id": self.request_id,
                "project_key": self.project_key,
                "channel": self.channel,
            }
        )
        if self.request_digest == "":
            object.__setattr__(self, "request_digest", expected)
        else:
            require_hex64(self.request_digest, "CollectRequestRef.request_digest")
            if self.request_digest != expected:
                raise ValueError(
                    "CollectRequestRef.request_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "project_key": self.project_key,
            "channel": self.channel,
            "request_digest": self.request_digest,
        }


def build_collect_request_ref(
    *,
    request_id: str,
    project_key: str,
    channel: str,
) -> CollectRequestRef:
    return CollectRequestRef(
        schema_version=COLLECT_REQUEST_SCHEMA_REF,
        request_id=request_id,
        project_key=project_key,
        channel=channel,
        request_digest="",
    )


def collect_request_ref_from_dict(value: dict[str, Any]) -> CollectRequestRef:
    return CollectRequestRef(
        schema_version=COLLECT_REQUEST_SCHEMA_REF,
        request_id=value["request_id"],
        project_key=value["project_key"],
        channel=value["channel"],
        request_digest=value.get("request_digest", ""),
    )


@dataclass(frozen=True, slots=True)
class CollectLegacyRequestSnapshot:
    """Lossless-enough frozen view used by the legacy parity adapter."""

    schema_version: Literal["mrw.successor.collect.c3.legacy-request-snapshot.v1"]
    flow: str
    channel: str
    project_key: str | None
    query_terms: tuple[str, ...]
    urls: tuple[str, ...]
    limit: int | None
    options: FrozenJsonObject
    source_context: FrozenJsonObject
    snapshot_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF:
            raise ValueError(
                "CollectLegacyRequestSnapshot.schema_version is not the frozen schema"
            )
        object.__setattr__(self, "flow", _require_non_empty_string(self.flow, "flow"))
        object.__setattr__(
            self, "channel", _require_non_empty_string(self.channel, "channel")
        )
        if self.project_key is not None:
            object.__setattr__(
                self,
                "project_key",
                _require_non_empty_string(self.project_key, "project_key"),
            )
        object.__setattr__(
            self, "query_terms", _require_string_tuple(self.query_terms, "query_terms")
        )
        object.__setattr__(self, "urls", _require_string_tuple(self.urls, "urls"))
        if self.limit is not None:
            object.__setattr__(
                self, "limit", _require_positive_int(self.limit, "limit")
            )
        object.__setattr__(self, "options", _freeze(self.options))
        object.__setattr__(self, "source_context", _freeze(self.source_context))
        expected = content_digest(
            {
                "schema": COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
                "flow": self.flow,
                "channel": self.channel,
                "project_key": self.project_key,
                "query_terms": self.query_terms,
                "urls": self.urls,
                "limit": self.limit,
                "options": dict(self.options),
                "source_context": dict(self.source_context),
            }
        )
        if self.snapshot_digest == "":
            object.__setattr__(self, "snapshot_digest", expected)
        else:
            require_hex64(
                self.snapshot_digest, "CollectLegacyRequestSnapshot.snapshot_digest"
            )
            if self.snapshot_digest != expected:
                raise ValueError(
                    "CollectLegacyRequestSnapshot.snapshot_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "flow": self.flow,
            "channel": self.channel,
            "project_key": self.project_key,
            "query_terms": list(self.query_terms),
            "urls": list(self.urls),
            "limit": self.limit,
            "options": dict(self.options),
            "source_context": dict(self.source_context),
            "snapshot_digest": self.snapshot_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectResourcePolicy:
    """Explicit bounded resource policy; never grants authority."""

    schema_ref: Literal["mrw.successor.collect.c3.resource-policy.v1"]
    max_parallelism: int
    deadline_seconds: int | None
    cancellation: Literal["COORDINATED", "NONE"]
    backpressure: bool
    provider_concurrency_key: str
    policy_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_ref != COLLECT_RESOURCE_POLICY_SCHEMA_REF:
            raise ValueError(
                "CollectResourcePolicy.schema_ref is not the frozen schema"
            )
        object.__setattr__(
            self,
            "max_parallelism",
            _require_positive_int(self.max_parallelism, "max_parallelism"),
        )
        if self.deadline_seconds is not None:
            object.__setattr__(
                self,
                "deadline_seconds",
                _require_positive_int(self.deadline_seconds, "deadline_seconds"),
            )
        if self.cancellation not in {"COORDINATED", "NONE"}:
            raise ValueError(f"unsupported cancellation policy {self.cancellation!r}")
        object.__setattr__(
            self,
            "provider_concurrency_key",
            _require_non_empty_string(
                self.provider_concurrency_key, "provider_concurrency_key"
            ),
        )
        expected = content_digest(
            {
                "schema": COLLECT_RESOURCE_POLICY_SCHEMA_REF,
                "max_parallelism": self.max_parallelism,
                "deadline_seconds": self.deadline_seconds,
                "cancellation": self.cancellation,
                "backpressure": self.backpressure,
                "provider_concurrency_key": self.provider_concurrency_key,
            }
        )
        if self.policy_digest == "":
            object.__setattr__(self, "policy_digest", expected)
        else:
            require_hex64(self.policy_digest, "CollectResourcePolicy.policy_digest")
            if self.policy_digest != expected:
                raise ValueError(
                    "CollectResourcePolicy.policy_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "max_parallelism": self.max_parallelism,
            "deadline_seconds": self.deadline_seconds,
            "cancellation": self.cancellation,
            "backpressure": self.backpressure,
            "provider_concurrency_key": self.provider_concurrency_key,
            "policy_digest": self.policy_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectBatchElement:
    """One stable finite ordered batch element inside a C3.1 plan."""

    schema_version: Literal["mrw.successor.collect.c3.batch-element.v1"]
    element_id: str
    input_index: int
    query_terms: tuple[str, ...]
    per_batch_limit: int
    traversal_policy: TraversalPolicy
    failure_policy: FailurePolicy
    element_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_BATCH_ELEMENT_SCHEMA_REF:
            raise ValueError(
                "CollectBatchElement.schema_version is not the frozen schema"
            )
        object.__setattr__(
            self, "element_id", _require_non_empty_string(self.element_id, "element_id")
        )
        object.__setattr__(
            self,
            "input_index",
            _require_non_negative_int(self.input_index, "input_index"),
        )
        object.__setattr__(
            self,
            "query_terms",
            _require_string_tuple(self.query_terms, "query_terms", allow_empty=False),
        )
        object.__setattr__(
            self,
            "per_batch_limit",
            _require_positive_int(self.per_batch_limit, "per_batch_limit"),
        )
        if self.traversal_policy not in {"STATIC_SHAPE", "MATERIALIZED_SHAPE"}:
            raise ValueError(f"unsupported traversal policy {self.traversal_policy!r}")
        if self.failure_policy not in {
            "ACCUMULATE",
            "FAIL_FAST_WITH_PARTIAL_OBSERVATION",
        }:
            raise ValueError(f"unsupported failure policy {self.failure_policy!r}")
        expected = content_digest(
            {
                "schema": COLLECT_BATCH_ELEMENT_SCHEMA_REF,
                "element_id": self.element_id,
                "input_index": self.input_index,
                "query_terms": self.query_terms,
                "per_batch_limit": self.per_batch_limit,
                "traversal_policy": self.traversal_policy,
                "failure_policy": self.failure_policy,
            }
        )
        if self.element_digest == "":
            object.__setattr__(self, "element_digest", expected)
        else:
            require_hex64(self.element_digest, "CollectBatchElement.element_digest")
            if self.element_digest != expected:
                raise ValueError(
                    "CollectBatchElement.element_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "element_id": self.element_id,
            "input_index": self.input_index,
            "query_terms": list(self.query_terms),
            "per_batch_limit": self.per_batch_limit,
            "traversal_policy": self.traversal_policy,
            "failure_policy": self.failure_policy,
            "element_digest": self.element_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectBatchPlan:
    """Frozen finite ordered batch plan; never mutates in place."""

    schema_version: Literal["mrw.successor.collect.c3.batch-plan.v1"]
    plan_id: str
    request_ref: CollectRequestRef
    disposition: PlanDisposition
    traversal_policy: TraversalPolicy
    failure_policy: FailurePolicy
    elements: tuple[CollectBatchElement, ...]
    per_batch_limit: int
    requested_parallelism: int
    effective_parallelism: int
    batches_total: int
    plan_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_BATCH_PLAN_SCHEMA_REF:
            raise ValueError("CollectBatchPlan.schema_version is not the frozen schema")
        object.__setattr__(
            self, "plan_id", _require_non_empty_string(self.plan_id, "plan_id")
        )
        object.__setattr__(self, "elements", tuple(self.elements))
        if self.disposition == "TRAVERSE" and len(self.elements) < 2:
            raise ValueError("TRAVERSE plan requires at least two elements")
        if self.disposition == "SINGLETON_IDENTITY" and len(self.elements) != 1:
            raise ValueError("SINGLETON_IDENTITY plan requires exactly one element")
        if self.disposition == "BYPASSED" and self.elements:
            raise ValueError("BYPASSED plan must not carry elements")
        object.__setattr__(
            self,
            "per_batch_limit",
            _require_positive_int(self.per_batch_limit, "per_batch_limit"),
        )
        object.__setattr__(
            self,
            "requested_parallelism",
            _require_positive_int(self.requested_parallelism, "requested_parallelism"),
        )
        object.__setattr__(
            self,
            "effective_parallelism",
            _require_positive_int(self.effective_parallelism, "effective_parallelism"),
        )
        object.__setattr__(
            self,
            "batches_total",
            _require_non_negative_int(self.batches_total, "batches_total"),
        )
        if self.batches_total != len(self.elements):
            raise ValueError("CollectBatchPlan.batches_total must equal len(elements)")
        if tuple(element.input_index for element in self.elements) != tuple(
            range(len(self.elements))
        ):
            raise ValueError(
                "CollectBatchPlan element input_index must be contiguous 0-based unique"
            )
        if any(
            element.traversal_policy != self.traversal_policy
            or element.failure_policy != self.failure_policy
            or element.per_batch_limit != self.per_batch_limit
            for element in self.elements
        ):
            raise ValueError(
                "CollectBatchPlan elements must share traversal/failure policy and per-batch limit"
            )
        if any(
            not element.element_id.startswith(self.plan_id + ":element:")
            for element in self.elements
        ):
            raise ValueError(
                "CollectBatchPlan element ids must bind the parent plan identity"
            )
        ceiling = max(1, len(self.elements))
        if self.effective_parallelism > min(self.requested_parallelism, ceiling):
            raise ValueError(
                "effective parallelism exceeds requested parallelism or element count"
            )
        expected = content_digest(
            {
                "schema": COLLECT_BATCH_PLAN_SCHEMA_REF,
                "plan_id": self.plan_id,
                "request_ref": self.request_ref.to_plain(),
                "disposition": self.disposition,
                "traversal_policy": self.traversal_policy,
                "failure_policy": self.failure_policy,
                "elements": [element.to_plain() for element in self.elements],
                "per_batch_limit": self.per_batch_limit,
                "requested_parallelism": self.requested_parallelism,
                "effective_parallelism": self.effective_parallelism,
                "batches_total": self.batches_total,
            }
        )
        if self.plan_digest == "":
            object.__setattr__(self, "plan_digest", expected)
        else:
            require_hex64(self.plan_digest, "CollectBatchPlan.plan_digest")
            if self.plan_digest != expected:
                raise ValueError("CollectBatchPlan.plan_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "request_ref": self.request_ref.to_plain(),
            "disposition": self.disposition,
            "traversal_policy": self.traversal_policy,
            "failure_policy": self.failure_policy,
            "elements": [element.to_plain() for element in self.elements],
            "per_batch_limit": self.per_batch_limit,
            "requested_parallelism": self.requested_parallelism,
            "effective_parallelism": self.effective_parallelism,
            "batches_total": self.batches_total,
            "plan_digest": self.plan_digest,
        }


def should_auto_batch(request: Any) -> bool:
    """Deterministic rewrite of legacy ``runtime._should_auto_batch``."""

    channel = str(getattr(request, "channel", "") or "").strip()
    if channel not in COLLECT_AUTO_BATCH_CHANNELS:
        return False
    terms = _view_terms(getattr(request, "query_terms", ()))
    qn = len([item for item in terms if item])
    try:
        lim = int(getattr(request, "limit", None) or 0)
    except (TypeError, ValueError):
        lim = 0
    return qn >= 6 or lim >= 60


def _view_terms(value: Any) -> list[str]:
    if isinstance(value, str):
        raw: Any = [value]
    else:
        raw = value or ()
    return [str(item).strip() for item in raw if str(item).strip()]


def split_query_terms(terms: Any) -> list[list[str]]:
    """Deterministic rewrite of legacy ``runtime._split_query_terms``."""

    clean = _view_terms(terms)
    if not clean:
        return [[]]
    chunk_size = 4 if len(clean) >= 8 else 5
    return [
        clean[index : index + chunk_size] for index in range(0, len(clean), chunk_size)
    ]


def per_batch_limit_for(limit: Any, batch_count: int) -> int:
    """Deterministic rewrite of legacy per-batch limit calculation."""

    try:
        requested = max(1, int(limit or 20))
    except (TypeError, ValueError):
        requested = 20
    return max(10, math.ceil(requested / max(1, batch_count)))


def _option_value(request: Any, name: str, default: Any) -> Any:
    def as_mapping(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        if isinstance(value, tuple) and all(
            isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], str)
            for pair in value
        ):
            return {str(key): item for key, item in value}
        return {}

    options = as_mapping(getattr(request, "options", None))
    source_context = as_mapping(getattr(request, "source_context", None))
    if isinstance(options, dict) and name in options:
        return options[name]
    if isinstance(source_context, dict) and name in source_context:
        return source_context[name]
    return default


def resolve_auto_batch_parallelism(request: Any) -> int:
    """Deterministic rewrite of legacy ``runtime._resolve_auto_batch_parallelism``."""

    try:
        return max(1, int(_option_value(request, "batch_parallelism", 1)))
    except (TypeError, ValueError):
        return 1


def resolve_auto_batch_fail_fast(request: Any) -> bool:
    """Deterministic rewrite of legacy ``runtime._resolve_auto_batch_fail_fast``."""

    raw = _option_value(request, "batch_fail_fast", False)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def build_collect_batch_plan(
    *,
    request_ref: CollectRequestRef,
    snapshot: CollectLegacyRequestSnapshot,
    plan_id: str,
    resource_policy: CollectResourcePolicy,
    authority_scope_ref: str,
    traversal_policy: TraversalPolicy = "MATERIALIZED_SHAPE",
    static_elements: tuple[CollectBatchElement, ...] | None = None,
) -> CollectBatchPlan:
    """Pure finite ordered plan rules; never mutates the request in place."""

    _require_non_empty_string(authority_scope_ref, "authority_scope_ref")
    if not should_auto_batch(snapshot):
        return CollectBatchPlan(
            schema_version=COLLECT_BATCH_PLAN_SCHEMA_REF,
            plan_id=plan_id,
            request_ref=request_ref,
            disposition="BYPASSED",
            traversal_policy=traversal_policy,
            failure_policy=(
                "FAIL_FAST_WITH_PARTIAL_OBSERVATION"
                if resolve_auto_batch_fail_fast(snapshot)
                else "ACCUMULATE"
            ),
            elements=(),
            per_batch_limit=1,
            requested_parallelism=1,
            effective_parallelism=1,
            batches_total=0,
            plan_digest="",
        )

    term_batches = split_query_terms(snapshot.query_terms)
    per_limit = per_batch_limit_for(snapshot.limit, len(term_batches))
    fail_fast = resolve_auto_batch_fail_fast(snapshot)
    failure_policy = "FAIL_FAST_WITH_PARTIAL_OBSERVATION" if fail_fast else "ACCUMULATE"
    requested = resolve_auto_batch_parallelism(snapshot)
    ceiling = max(1, len(term_batches))
    effective = min(requested, ceiling, resource_policy.max_parallelism)

    if static_elements is not None:
        derived_terms = [tuple(batch) for batch in term_batches]
        if tuple(element.query_terms for element in static_elements) != tuple(
            derived_terms
        ):
            raise ValueError(
                "STATIC_SHAPE elements do not match the derived finite ordered shape"
            )
        if tuple(element.input_index for element in static_elements) != tuple(
            range(len(static_elements))
        ):
            raise ValueError(
                "STATIC_SHAPE elements must use 0-based contiguous input_index"
            )
        elements = tuple(static_elements)
    else:
        elements = tuple(
            CollectBatchElement(
                schema_version=COLLECT_BATCH_ELEMENT_SCHEMA_REF,
                element_id=f"{plan_id}:element:{index}",
                input_index=index,
                query_terms=tuple(batch),
                per_batch_limit=per_limit,
                traversal_policy=traversal_policy,
                failure_policy=failure_policy,
                element_digest="",
            )
            for index, batch in enumerate(term_batches)
        )

    disposition: PlanDisposition
    if len(elements) <= 1:
        disposition = "SINGLETON_IDENTITY"
    else:
        disposition = "TRAVERSE"
    return CollectBatchPlan(
        schema_version=COLLECT_BATCH_PLAN_SCHEMA_REF,
        plan_id=plan_id,
        request_ref=request_ref,
        disposition=disposition,
        traversal_policy=traversal_policy,
        failure_policy=failure_policy,
        elements=elements,
        per_batch_limit=per_limit,
        requested_parallelism=requested,
        effective_parallelism=effective,
        batches_total=len(elements),
        plan_digest="",
    )


@dataclass(frozen=True, slots=True)
class CollectCounts:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inserted", _require_non_negative_int(self.inserted, "inserted")
        )
        object.__setattr__(
            self, "updated", _require_non_negative_int(self.updated, "updated")
        )
        object.__setattr__(
            self, "skipped", _require_non_negative_int(self.skipped, "skipped")
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
        }


CollectAggregateCounts = CollectCounts


@dataclass(frozen=True, slots=True)
class CollectElementError:
    code: str
    message: str
    query_terms: tuple[str, ...] = ()
    exception_type: str | None = None
    error_digest: str = ""

    def __post_init__(self) -> None:
        if self.code not in COLLECT_ELEMENT_ERROR_CODES:
            raise ValueError(f"unregistered collect element error code {self.code!r}")
        _require_non_empty_string(self.message, "CollectElementError.message")
        object.__setattr__(
            self, "query_terms", _require_string_tuple(self.query_terms, "query_terms")
        )
        if self.exception_type is not None and not isinstance(self.exception_type, str):
            raise ValueError(
                "CollectElementError.exception_type must be a string or None"
            )
        expected = content_digest(
            {
                "schema": "mrw.successor.collect.c3.element-error.v1",
                "code": self.code,
                "message": self.message,
                "query_terms": self.query_terms,
                "exception_type": self.exception_type,
            }
        )
        if self.error_digest == "":
            object.__setattr__(self, "error_digest", expected)
        else:
            require_hex64(self.error_digest, "CollectElementError.error_digest")
            if self.error_digest != expected:
                raise ValueError(
                    "CollectElementError.error_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "query_terms": list(self.query_terms),
            "exception_type": self.exception_type,
            "error_digest": self.error_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectAttemptReceipt:
    """Per-element attempt receipt; queued acknowledgements are never completion."""

    schema_version: Literal["mrw.successor.collect.c3.attempt-receipt.v1"]
    receipt_kind: Literal["DISPATCH_ACKNOWLEDGEMENT", "AUTHORITATIVE_READBACK"]
    provider_type: str
    provider_job_id: str
    provider_status: str | None
    attempt_count: int
    observed_at: str
    raw_digest: str
    authoritative_readback: bool
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF:
            raise ValueError(
                "CollectAttemptReceipt.schema_version is not the frozen schema"
            )
        if self.receipt_kind not in {
            "DISPATCH_ACKNOWLEDGEMENT",
            "AUTHORITATIVE_READBACK",
        }:
            raise ValueError(f"unsupported receipt kind {self.receipt_kind!r}")
        object.__setattr__(
            self,
            "provider_type",
            _require_non_empty_string(self.provider_type, "provider_type"),
        )
        object.__setattr__(
            self,
            "provider_job_id",
            _require_non_empty_string(self.provider_job_id, "provider_job_id"),
        )
        if self.provider_status is not None:
            object.__setattr__(
                self,
                "provider_status",
                _require_non_empty_string(self.provider_status, "provider_status"),
            )
        object.__setattr__(
            self,
            "attempt_count",
            _require_non_negative_int(self.attempt_count, "attempt_count"),
        )
        if _OBSERVED_AT.fullmatch(str(self.observed_at or "")) is None:
            raise ValueError("CollectAttemptReceipt.observed_at must be UTC ISO-8601")
        require_hex64(self.raw_digest, "CollectAttemptReceipt.raw_digest")
        if self.authoritative_readback != (
            self.receipt_kind == "AUTHORITATIVE_READBACK"
        ):
            raise ValueError("authoritative_readback must match receipt_kind exactly")
        expected = content_digest(
            {
                "schema": COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
                "receipt_kind": self.receipt_kind,
                "provider_type": self.provider_type,
                "provider_job_id": self.provider_job_id,
                "provider_status": self.provider_status,
                "attempt_count": self.attempt_count,
                "observed_at": self.observed_at,
                "raw_digest": self.raw_digest,
                "authoritative_readback": self.authoritative_readback,
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "CollectAttemptReceipt.receipt_digest")
            if self.receipt_digest != expected:
                raise ValueError(
                    "CollectAttemptReceipt.receipt_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_kind": self.receipt_kind,
            "provider_type": self.provider_type,
            "provider_job_id": self.provider_job_id,
            "provider_status": self.provider_status,
            "attempt_count": self.attempt_count,
            "observed_at": self.observed_at,
            "raw_digest": self.raw_digest,
            "authoritative_readback": self.authoritative_readback,
            "receipt_digest": self.receipt_digest,
        }


def receipt_implies_completed(receipt: CollectAttemptReceipt | None) -> bool:
    """A dispatch acknowledgement never implies authoritative completion."""

    return receipt is not None and receipt.receipt_kind == "AUTHORITATIVE_READBACK"


@dataclass(frozen=True, slots=True)
class CollectCancellationReceipt:
    """Typed cancellation receipt emitted by fail-fast traversal aborts."""

    schema_version: Literal["mrw.successor.collect.c3.cancellation-receipt.v1"]
    code: Literal["FAIL_FAST_CANCELLED"]
    message: str
    trigger_input_index: int
    observed: Literal["SERIAL_EXECUTION", "PARALLEL_COMPLETION"]
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF:
            raise ValueError(
                "CollectCancellationReceipt.schema_version is not the frozen schema"
            )
        if self.code != "FAIL_FAST_CANCELLED":
            raise ValueError(f"unsupported cancellation code {self.code!r}")
        _require_non_empty_string(self.message, "CollectCancellationReceipt.message")
        object.__setattr__(
            self,
            "trigger_input_index",
            _require_non_negative_int(self.trigger_input_index, "trigger_input_index"),
        )
        if self.observed not in {"SERIAL_EXECUTION", "PARALLEL_COMPLETION"}:
            raise ValueError(f"unsupported cancellation observation {self.observed!r}")
        expected = content_digest(
            {
                "schema": COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
                "code": self.code,
                "message": self.message,
                "trigger_input_index": self.trigger_input_index,
                "observed": self.observed,
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(
                self.receipt_digest, "CollectCancellationReceipt.receipt_digest"
            )
            if self.receipt_digest != expected:
                raise ValueError(
                    "CollectCancellationReceipt.receipt_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "message": self.message,
            "trigger_input_index": self.trigger_input_index,
            "observed": self.observed,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectElementSucceeded:
    schema_version: Literal["mrw.successor.collect.c3.element-outcome.v1"]
    element_id: str
    input_index: int
    status: Literal["succeeded"] = "succeeded"
    counts: CollectCounts = field(default_factory=CollectCounts)
    links: tuple[str, ...] = ()
    receipt: CollectAttemptReceipt | None = None
    legacy_observation_ref: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        self._validate_common()
        if self.status != "succeeded":
            raise ValueError("CollectElementSucceeded.status must be 'succeeded'")
        expected = content_digest(self._digest_payload())
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectElementSucceeded.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectElementSucceeded.outcome_digest does not match content"
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_ELEMENT_OUTCOME_SCHEMA_REF:
            raise ValueError("element outcome schema_version is not the frozen schema")
        _require_non_empty_string(self.element_id, "element_id")
        _require_non_negative_int(self.input_index, "input_index")
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        _require_legacy_observation_ref(self.legacy_observation_ref)
        if self.receipt is not None and not isinstance(
            self.receipt, CollectAttemptReceipt
        ):
            raise ValueError("element receipt must be CollectAttemptReceipt or None")

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            "element_id": self.element_id,
            "input_index": self.input_index,
            "status": self.status,
            "counts": self.counts.to_plain(),
            "links": self.links,
            "receipt": None if self.receipt is None else self.receipt.to_plain(),
            "legacy_observation_ref": self.legacy_observation_ref,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "outcome_digest": self.outcome_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectElementFailed:
    schema_version: Literal["mrw.successor.collect.c3.element-outcome.v1"]
    element_id: str
    input_index: int
    status: Literal["failed"] = "failed"
    error: CollectElementError | None = None
    counts: CollectCounts = field(default_factory=CollectCounts)
    links: tuple[str, ...] = ()
    receipt: CollectAttemptReceipt | None = None
    legacy_observation_ref: str = ""
    outcome_digest: str = ""

    def __post_init__(self) -> None:
        self._validate_common()
        if self.status != "failed":
            raise ValueError("CollectElementFailed.status must be 'failed'")
        if not isinstance(self.error, CollectElementError):
            raise TypeError("CollectElementFailed requires a typed error")
        expected = content_digest(self._digest_payload())
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectElementFailed.outcome_digest")
            if self.outcome_digest != expected:
                raise ValueError(
                    "CollectElementFailed.outcome_digest does not match content"
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_ELEMENT_OUTCOME_SCHEMA_REF:
            raise ValueError("element outcome schema_version is not the frozen schema")
        _require_non_empty_string(self.element_id, "element_id")
        _require_non_negative_int(self.input_index, "input_index")
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        _require_legacy_observation_ref(self.legacy_observation_ref)
        if self.receipt is not None and not isinstance(
            self.receipt, CollectAttemptReceipt
        ):
            raise ValueError("element receipt must be CollectAttemptReceipt or None")

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            "element_id": self.element_id,
            "input_index": self.input_index,
            "status": self.status,
            "error": None if self.error is None else self.error.to_plain(),
            "counts": self.counts.to_plain(),
            "links": self.links,
            "receipt": None if self.receipt is None else self.receipt.to_plain(),
            "legacy_observation_ref": self.legacy_observation_ref,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "outcome_digest": self.outcome_digest,
        }


def _require_legacy_observation_ref(value: Any) -> None:
    if not isinstance(value, str) or _LEGACY_OBSERVATION_REF.fullmatch(value) is None:
        raise ValueError("legacy_observation_ref must match legacy:<64 lowercase hex>")


CollectElementOutcome: TypeAlias = CollectElementSucceeded | CollectElementFailed


@dataclass(frozen=True, slots=True)
class OrderedCollectElementOutcomeSequence:
    """Input-index ordered outcome sequence; never reorders failures."""

    schema_version: Literal["mrw.successor.collect.c3.outcome-sequence.v1"]
    parent_request_ref: CollectRequestRef
    outcomes: tuple[CollectElementOutcome, ...]
    sequence_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        indexes = tuple(outcome.input_index for outcome in self.outcomes)
        if tuple(sorted(indexes)) != indexes or len(set(indexes)) != len(indexes):
            raise ValueError(
                "outcome sequence input indexes must be strictly increasing"
            )
        expected = content_digest(
            {
                "schema": "mrw.successor.collect.c3.outcome-sequence.v1",
                "parent_request_ref": self.parent_request_ref.to_plain(),
                "outcomes": [outcome.to_plain() for outcome in self.outcomes],
            }
        )
        if self.sequence_digest == "":
            object.__setattr__(self, "sequence_digest", expected)
        else:
            require_hex64(
                self.sequence_digest,
                "OrderedCollectElementOutcomeSequence.sequence_digest",
            )
            if self.sequence_digest != expected:
                raise ValueError(
                    "OrderedCollectElementOutcomeSequence.sequence_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parent_request_ref": self.parent_request_ref.to_plain(),
            "outcomes": [outcome.to_plain() for outcome in self.outcomes],
            "sequence_digest": self.sequence_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectAggregateSucceeded:
    schema_version: Literal["mrw.successor.collect.c3.aggregate-outcome.v1"]
    kind: Literal["succeeded"] = "succeeded"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        self._validate_common()
        if self.aggregate_digest == "":
            object.__setattr__(
                self, "aggregate_digest", content_digest(self._digest_payload())
            )
        else:
            require_hex64(
                self.aggregate_digest, "CollectAggregateSucceeded.aggregate_digest"
            )
            if self.aggregate_digest != content_digest(self._digest_payload()):
                raise ValueError(
                    "CollectAggregateSucceeded.aggregate_digest does not match content"
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            raise ValueError("aggregate schema_version is not the frozen schema")
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": (
                None
                if self.ordered_outcomes is None
                else self.ordered_outcomes.to_plain()
            ),
            "aggregate_counts": self.aggregate_counts.to_plain(),
            "receipts": [receipt.to_plain() for receipt in self.receipts],
            "links": self.links,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "aggregate_digest": self.aggregate_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectAggregatePartial:
    schema_version: Literal["mrw.successor.collect.c3.aggregate-outcome.v1"]
    kind: Literal["partial"] = "partial"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    errors: tuple[CollectElementError, ...] = ()
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            raise ValueError("aggregate schema_version is not the frozen schema")
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        if self.aggregate_digest == "":
            object.__setattr__(
                self, "aggregate_digest", content_digest(self._digest_payload())
            )
        else:
            require_hex64(
                self.aggregate_digest, "CollectAggregatePartial.aggregate_digest"
            )
            if self.aggregate_digest != content_digest(self._digest_payload()):
                raise ValueError(
                    "CollectAggregatePartial.aggregate_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": (
                None
                if self.ordered_outcomes is None
                else self.ordered_outcomes.to_plain()
            ),
            "aggregate_counts": self.aggregate_counts.to_plain(),
            "errors": [error.to_plain() for error in self.errors],
            "receipts": [receipt.to_plain() for receipt in self.receipts],
            "links": self.links,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "aggregate_digest": self.aggregate_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectAggregateFailed:
    schema_version: Literal["mrw.successor.collect.c3.aggregate-outcome.v1"]
    kind: Literal["failed"] = "failed"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    errors: tuple[CollectElementError, ...] = ()
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            raise ValueError("aggregate schema_version is not the frozen schema")
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        if self.aggregate_digest == "":
            object.__setattr__(
                self, "aggregate_digest", content_digest(self._digest_payload())
            )
        else:
            require_hex64(
                self.aggregate_digest, "CollectAggregateFailed.aggregate_digest"
            )
            if self.aggregate_digest != content_digest(self._digest_payload()):
                raise ValueError(
                    "CollectAggregateFailed.aggregate_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": (
                None
                if self.ordered_outcomes is None
                else self.ordered_outcomes.to_plain()
            ),
            "aggregate_counts": self.aggregate_counts.to_plain(),
            "errors": [error.to_plain() for error in self.errors],
            "receipts": [receipt.to_plain() for receipt in self.receipts],
            "links": self.links,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "aggregate_digest": self.aggregate_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectFoldContractFailure:
    schema_version: Literal["mrw.successor.collect.c3.aggregate-outcome.v1"]
    kind: Literal["contract_failure"] = "contract_failure"
    reason: str = ""
    unconsumed_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            raise ValueError("aggregate schema_version is not the frozen schema")
        _require_non_empty_string(self.reason, "CollectFoldContractFailure.reason")
        if self.aggregate_digest == "":
            object.__setattr__(
                self, "aggregate_digest", content_digest(self._digest_payload())
            )
        else:
            require_hex64(
                self.aggregate_digest, "CollectFoldContractFailure.aggregate_digest"
            )
            if self.aggregate_digest != content_digest(self._digest_payload()):
                raise ValueError(
                    "CollectFoldContractFailure.aggregate_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "reason": self.reason,
            "unconsumed_outcomes": (
                None
                if self.unconsumed_outcomes is None
                else self.unconsumed_outcomes.to_plain()
            ),
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "aggregate_digest": self.aggregate_digest,
        }


CollectAggregateOutcome: TypeAlias = (
    CollectAggregateSucceeded
    | CollectAggregatePartial
    | CollectAggregateFailed
    | CollectFoldContractFailure
)


@dataclass(frozen=True, slots=True)
class CollectFoldResourceCeiling:
    """Bounded pure-CPU envelope for the ordered result fold."""

    schema_ref: Literal["mrw.successor.collect.c3-2.resource-ceiling.v1"]
    max_outcomes: int
    max_payload_bytes: int
    max_receipts: int
    ceiling_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_ref != COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF:
            raise ValueError(
                "CollectFoldResourceCeiling.schema_ref is not the frozen schema"
            )
        for name in ("max_outcomes", "max_payload_bytes", "max_receipts"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"CollectFoldResourceCeiling.{name} must be positive")
        expected = content_digest(
            {
                "schema": COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF,
                "max_outcomes": self.max_outcomes,
                "max_payload_bytes": self.max_payload_bytes,
                "max_receipts": self.max_receipts,
            }
        )
        if self.ceiling_digest == "":
            object.__setattr__(self, "ceiling_digest", expected)
        else:
            require_hex64(
                self.ceiling_digest, "CollectFoldResourceCeiling.ceiling_digest"
            )
            if self.ceiling_digest != expected:
                raise ValueError(
                    "CollectFoldResourceCeiling.ceiling_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "max_outcomes": self.max_outcomes,
            "max_payload_bytes": self.max_payload_bytes,
            "max_receipts": self.max_receipts,
            "ceiling_digest": self.ceiling_digest,
        }


COLLECT_FOLD_RESOURCE_CEILING = CollectFoldResourceCeiling(
    schema_ref=COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF,
    max_outcomes=256,
    max_payload_bytes=256 * 1024,
    max_receipts=1024,
)


def require_fold_ceiling(
    outcomes: OrderedCollectElementOutcomeSequence,
) -> str | None:
    """Return a rejection message when the bounded fold envelope is exceeded."""

    ceiling = COLLECT_FOLD_RESOURCE_CEILING
    if len(outcomes.outcomes) > ceiling.max_outcomes:
        return (
            f"fold outcomes {len(outcomes.outcomes)} exceed ceiling "
            f"{ceiling.max_outcomes}"
        )
    payload_bytes = len(canonical_json(outcomes.to_plain()).encode("utf-8"))
    if payload_bytes > ceiling.max_payload_bytes:
        return (
            f"fold payload bytes {payload_bytes} exceed ceiling "
            f"{ceiling.max_payload_bytes}"
        )
    receipts = sum(1 for outcome in outcomes.outcomes if outcome.receipt is not None)
    if receipts > ceiling.max_receipts:
        return f"fold receipts {receipts} exceed ceiling {ceiling.max_receipts}"
    return None


def fold_ordered_results(
    outcomes: OrderedCollectElementOutcomeSequence,
    *,
    aggregation_policy_ref: str,
    observation_profile_ref: str,
) -> CollectAggregateOutcome:
    """Deterministic left-to-right fold in input-index order.

    No commutative monoid is claimed: error order, first-seen links, provider
    status order and receipts are observable and retained.
    """

    _require_non_empty_string(observation_profile_ref, "observation_profile_ref")
    ceiling_message = require_fold_ceiling(outcomes)
    if ceiling_message is not None:
        return CollectFoldContractFailure(
            schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            reason=ceiling_message,
            unconsumed_outcomes=outcomes,
            aggregate_digest="",
        )
    if aggregation_policy_ref not in COLLECT_AGGREGATION_POLICY_REFS:
        return CollectFoldContractFailure(
            schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            reason=f"unsupported aggregation_policy_ref {aggregation_policy_ref!r}",
            unconsumed_outcomes=outcomes,
            aggregate_digest="",
        )
    if aggregation_policy_ref == COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF:
        return CollectFoldContractFailure(
            schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            reason=(
                "fail-fast partial observation is decided by the ordered traversal; "
                "fold only summarizes already observed outcomes"
            ),
            unconsumed_outcomes=outcomes,
            aggregate_digest="",
        )

    counts = CollectCounts()
    errors: list[CollectElementError] = []
    receipts: list[CollectAttemptReceipt] = []
    links: list[str] = []
    links_seen: set[str] = set()
    job_ids: list[str] = []
    job_ids_seen: set[str] = set()
    receipt_digests_seen: set[str] = set()
    job_id_to_receipt_digest: dict[str, str] = {}
    failed = 0

    for outcome in outcomes.outcomes:
        counts = CollectCounts(
            inserted=counts.inserted + outcome.counts.inserted,
            updated=counts.updated + outcome.counts.updated,
            skipped=counts.skipped + outcome.counts.skipped,
        )
        if isinstance(outcome, CollectElementFailed):
            failed += 1
            if outcome.error is not None:
                errors.append(outcome.error)
        for link in outcome.links:
            if link and link not in links_seen:
                links_seen.add(link)
                links.append(link)
        if outcome.receipt is not None:
            receipt = outcome.receipt
            if receipt.receipt_digest in receipt_digests_seen:
                # Stable-first dedupe: identical receipts are kept once.
                continue
            prior_digest = job_id_to_receipt_digest.get(receipt.provider_job_id)
            if prior_digest is not None and prior_digest != receipt.receipt_digest:
                return CollectFoldContractFailure(
                    schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
                    reason=(
                        "duplicate provider_job_id with divergent receipt digest "
                        f"{receipt.provider_job_id!r}"
                    ),
                    unconsumed_outcomes=outcomes,
                    aggregate_digest="",
                )
            receipt_digests_seen.add(receipt.receipt_digest)
            job_id_to_receipt_digest[receipt.provider_job_id] = receipt.receipt_digest
            receipts.append(receipt)
            if receipt.provider_job_id not in job_ids_seen:
                job_ids_seen.add(receipt.provider_job_id)
                job_ids.append(receipt.provider_job_id)

    if failed == 0:
        return CollectAggregateSucceeded(
            schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            ordered_outcomes=outcomes,
            aggregate_counts=counts,
            receipts=tuple(receipts),
            links=tuple(links),
            aggregate_digest="",
        )
    if failed < len(outcomes.outcomes):
        return CollectAggregatePartial(
            schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            ordered_outcomes=outcomes,
            aggregate_counts=counts,
            errors=tuple(errors),
            receipts=tuple(receipts),
            links=tuple(links),
            aggregate_digest="",
        )
    return CollectAggregateFailed(
        schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
        ordered_outcomes=outcomes,
        aggregate_counts=counts,
        errors=tuple(errors),
        receipts=tuple(receipts),
        links=tuple(links),
        aggregate_digest="",
    )


@dataclass(frozen=True, slots=True)
class CollectTraversalObservation:
    """Ordered traversal observation; parallel effect traces are not compared."""

    schema_version: Literal["mrw.successor.collect.c3.traversal-observation.v1"]
    observation_profile: str
    request_ref: CollectRequestRef
    traversal_policy: TraversalPolicy
    failure_policy: FailurePolicy
    ordered_outcomes: tuple[CollectElementOutcome, ...]
    requested_parallelism: int
    effective_parallelism: int
    cancellation_observed: bool
    observation_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF:
            raise ValueError(
                "CollectTraversalObservation.schema_version is not the frozen schema"
            )
        _require_non_empty_string(self.observation_profile, "observation_profile")
        object.__setattr__(self, "ordered_outcomes", tuple(self.ordered_outcomes))
        object.__setattr__(
            self,
            "requested_parallelism",
            _require_positive_int(self.requested_parallelism, "requested_parallelism"),
        )
        object.__setattr__(
            self,
            "effective_parallelism",
            _require_positive_int(self.effective_parallelism, "effective_parallelism"),
        )
        expected = content_digest(self._digest_payload())
        if self.observation_digest == "":
            object.__setattr__(self, "observation_digest", expected)
        else:
            require_hex64(
                self.observation_digest,
                "CollectTraversalObservation.observation_digest",
            )
            if self.observation_digest != expected:
                raise ValueError(
                    "CollectTraversalObservation.observation_digest does not match content"
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
            "observation_profile": self.observation_profile,
            "request_ref": self.request_ref.to_plain(),
            "traversal_policy": self.traversal_policy,
            "failure_policy": self.failure_policy,
            "ordered_outcomes": [
                outcome.to_plain() for outcome in self.ordered_outcomes
            ],
            "requested_parallelism": self.requested_parallelism,
            "effective_parallelism": self.effective_parallelism,
            "cancellation_observed": self.cancellation_observed,
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "observation_digest": self.observation_digest,
        }


@dataclass(frozen=True, slots=True)
class OrderedTraversalCompleted:
    schema_version: Literal["mrw.successor.collect.c3.traversal-result.v1"]
    kind: Literal["completed"] = "completed"
    observation: CollectTraversalObservation | None = None

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "observation": (
                None if self.observation is None else self.observation.to_plain()
            ),
        }


@dataclass(frozen=True, slots=True)
class OrderedTraversalAborted:
    schema_version: Literal["mrw.successor.collect.c3.traversal-result.v1"]
    kind: Literal["aborted"] = "aborted"
    partial_outcomes: tuple[CollectElementOutcome, ...] = ()
    cause: CollectElementError | None = None
    cancellation_receipt: CollectCancellationReceipt | None = None
    cancellation_observed: bool = False
    request_ref: CollectRequestRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "partial_outcomes", tuple(self.partial_outcomes))
        if not isinstance(self.cause, CollectElementError):
            raise TypeError("OrderedTraversalAborted requires a typed cause")
        if not isinstance(self.cancellation_receipt, CollectCancellationReceipt):
            raise TypeError(
                "OrderedTraversalAborted requires a typed cancellation receipt"
            )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "partial_outcomes": [
                outcome.to_plain() for outcome in self.partial_outcomes
            ],
            "cause": self.cause.to_plain() if self.cause is not None else None,
            "cancellation_receipt": (
                None
                if self.cancellation_receipt is None
                else self.cancellation_receipt.to_plain()
            ),
            "cancellation_observed": self.cancellation_observed,
            "request_ref": (
                None if self.request_ref is None else self.request_ref.to_plain()
            ),
        }


@dataclass(frozen=True, slots=True)
class CollectTraversalBypassed:
    schema_version: Literal["mrw.successor.collect.c3.traversal-result.v1"]
    request_ref: CollectRequestRef
    kind: Literal["bypassed"] = "bypassed"

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "request_ref": self.request_ref.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class CollectTraversalSingleton:
    schema_version: Literal["mrw.successor.collect.c3.traversal-result.v1"]
    observation: CollectTraversalObservation
    kind: Literal["singleton"] = "singleton"

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "observation": self.observation.to_plain(),
        }


CollectTraversalResult: TypeAlias = (
    OrderedTraversalCompleted
    | OrderedTraversalAborted
    | CollectTraversalBypassed
    | CollectTraversalSingleton
)


@dataclass(frozen=True, slots=True)
class CollectBatchElementPayload:
    """Exact-bound C3.1 Atom payload; raw dictionaries stay at the codec edge."""

    schema_version: Literal["mrw.successor.collect.c3-1.payload.v1"]
    operation_kind: Literal["collect.execute_batch_element.v1"]
    parent_request_ref: CollectRequestRef
    request_snapshot: CollectLegacyRequestSnapshot
    element: CollectBatchElement
    resource_policy: CollectResourcePolicy
    authority_scope_ref: str
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_C3_1_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != COLLECT_C3_1_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        object.__setattr__(
            self,
            "authority_scope_ref",
            _require_non_empty_string(self.authority_scope_ref, "authority_scope_ref"),
        )
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(
                self.payload_digest, "CollectBatchElementPayload.payload_digest"
            )
            if self.payload_digest != expected:
                raise ValueError(
                    "CollectBatchElementPayload.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "parent_request_ref": self.parent_request_ref.to_plain(),
            "request_snapshot": self.request_snapshot.to_plain(),
            "element": self.element.to_plain(),
            "resource_policy": self.resource_policy.to_plain(),
            "authority_scope_ref": self.authority_scope_ref,
            "payload_digest": self.payload_digest,
        }


@dataclass(frozen=True, slots=True)
class CollectFoldPayload:
    """Exact-bound C3.2 Atom payload over already observed outcomes."""

    schema_version: Literal["mrw.successor.collect.c3-2.payload.v1"]
    operation_kind: Literal["collect.fold_ordered_results.v1"]
    parent_request_ref: CollectRequestRef
    ordered_outcomes: OrderedCollectElementOutcomeSequence
    aggregation_policy_ref: str
    observation_profile_ref: str
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_C3_2_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != COLLECT_C3_2_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        _require_non_empty_string(self.aggregation_policy_ref, "aggregation_policy_ref")
        _require_non_empty_string(
            self.observation_profile_ref, "observation_profile_ref"
        )
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "CollectFoldPayload.payload_digest")
            if self.payload_digest != expected:
                raise ValueError(
                    "CollectFoldPayload.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "parent_request_ref": self.parent_request_ref.to_plain(),
            "ordered_outcomes": self.ordered_outcomes.to_plain(),
            "aggregation_policy_ref": self.aggregation_policy_ref,
            "observation_profile_ref": self.observation_profile_ref,
            "payload_digest": self.payload_digest,
        }


def _snapshot_from_dict(value: dict[str, Any]) -> CollectLegacyRequestSnapshot:
    return CollectLegacyRequestSnapshot(
        schema_version=COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow=value.get("flow", "collect"),
        channel=value["channel"],
        project_key=value.get("project_key"),
        query_terms=tuple(value.get("query_terms") or ()),
        urls=tuple(value.get("urls") or ()),
        limit=value.get("limit"),
        options=freeze_json_object(dict(value.get("options") or {})),
        source_context=freeze_json_object(dict(value.get("source_context") or {})),
        snapshot_digest="",
    )


def collect_batch_element_payload_from_dicts(
    *,
    request_ref: dict[str, Any] | CollectRequestRef,
    request_snapshot: dict[str, Any] | CollectLegacyRequestSnapshot,
    element: dict[str, Any] | CollectBatchElement,
    resource_policy: dict[str, Any] | CollectResourcePolicy,
    authority_scope_ref: str,
) -> CollectBatchElementPayload:
    ref = (
        request_ref
        if isinstance(request_ref, CollectRequestRef)
        else collect_request_ref_from_dict(request_ref)
    )
    snapshot = (
        request_snapshot
        if isinstance(request_snapshot, CollectLegacyRequestSnapshot)
        else _snapshot_from_dict(request_snapshot)
    )
    element_obj = (
        element
        if isinstance(element, CollectBatchElement)
        else CollectBatchElement(
            schema_version=COLLECT_BATCH_ELEMENT_SCHEMA_REF,
            element_id=element["element_id"],
            input_index=element["input_index"],
            query_terms=tuple(element["query_terms"]),
            per_batch_limit=element["per_batch_limit"],
            traversal_policy=element.get("traversal_policy", "MATERIALIZED_SHAPE"),
            failure_policy=element.get("failure_policy", "ACCUMULATE"),
            element_digest="",
        )
    )
    policy = (
        resource_policy
        if isinstance(resource_policy, CollectResourcePolicy)
        else CollectResourcePolicy(
            schema_ref=COLLECT_RESOURCE_POLICY_SCHEMA_REF,
            max_parallelism=resource_policy["max_parallelism"],
            deadline_seconds=resource_policy.get("deadline_seconds"),
            cancellation=resource_policy.get("cancellation", "NONE"),
            backpressure=bool(resource_policy.get("backpressure", False)),
            provider_concurrency_key=resource_policy["provider_concurrency_key"],
            policy_digest="",
        )
    )
    return CollectBatchElementPayload(
        schema_version=COLLECT_C3_1_PAYLOAD_SCHEMA,
        operation_kind=COLLECT_C3_1_KIND,
        parent_request_ref=ref,
        request_snapshot=snapshot,
        element=element_obj,
        resource_policy=policy,
        authority_scope_ref=authority_scope_ref,
        payload_digest="",
    )


def build_collect_fold_payload(
    *,
    parent_request_ref: CollectRequestRef,
    ordered_outcomes: OrderedCollectElementOutcomeSequence,
    aggregation_policy_ref: str = COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
    observation_profile_ref: str = COLLECT_FOLD_OBSERVATION_PROFILE,
) -> CollectFoldPayload:
    return CollectFoldPayload(
        schema_version=COLLECT_C3_2_PAYLOAD_SCHEMA,
        operation_kind=COLLECT_C3_2_KIND,
        parent_request_ref=parent_request_ref,
        ordered_outcomes=ordered_outcomes,
        aggregation_policy_ref=aggregation_policy_ref,
        observation_profile_ref=observation_profile_ref,
        payload_digest="",
    )


def collect_fold_payload_from_dicts(
    *,
    parent_request_ref: dict[str, Any] | CollectRequestRef,
    ordered_outcomes: dict[str, Any],
    aggregation_policy_ref: str = COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
    observation_profile_ref: str = COLLECT_FOLD_OBSERVATION_PROFILE,
) -> CollectFoldPayload:
    ref = (
        parent_request_ref
        if isinstance(parent_request_ref, CollectRequestRef)
        else collect_request_ref_from_dict(parent_request_ref)
    )
    outcomes = [
        _outcome_from_dict(item) for item in ordered_outcomes.get("outcomes", [])
    ]
    sequence = OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=ref,
        outcomes=tuple(outcomes),
        sequence_digest="",
    )
    return CollectFoldPayload(
        schema_version=COLLECT_C3_2_PAYLOAD_SCHEMA,
        operation_kind=COLLECT_C3_2_KIND,
        parent_request_ref=ref,
        ordered_outcomes=sequence,
        aggregation_policy_ref=aggregation_policy_ref,
        observation_profile_ref=observation_profile_ref,
        payload_digest="",
    )


def _outcome_from_dict(value: dict[str, Any]) -> CollectElementOutcome:
    status = value.get("status")
    counts = CollectCounts(
        inserted=value.get("counts", {}).get("inserted", 0),
        updated=value.get("counts", {}).get("updated", 0),
        skipped=value.get("counts", {}).get("skipped", 0),
    )
    receipt_raw = value.get("receipt")
    receipt = (
        None
        if receipt_raw is None
        else CollectAttemptReceipt(
            schema_version=COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind=receipt_raw["receipt_kind"],
            provider_type=receipt_raw["provider_type"],
            provider_job_id=receipt_raw["provider_job_id"],
            provider_status=receipt_raw.get("provider_status"),
            attempt_count=receipt_raw["attempt_count"],
            observed_at=receipt_raw["observed_at"],
            raw_digest=receipt_raw["raw_digest"],
            authoritative_readback=bool(receipt_raw["authoritative_readback"]),
            receipt_digest="",
        )
    )
    common = {
        "element_id": value["element_id"],
        "input_index": value["input_index"],
        "counts": counts,
        "links": tuple(value.get("links") or ()),
        "receipt": receipt,
        "legacy_observation_ref": value["legacy_observation_ref"],
    }
    if status == "succeeded":
        return CollectElementSucceeded(
            schema_version=COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            **common,
            outcome_digest="",
        )
    if status == "failed":
        error_raw = value.get("error") or {}
        error = CollectElementError(
            code=error_raw["code"],
            message=error_raw["message"],
            query_terms=tuple(error_raw.get("query_terms") or ()),
            exception_type=error_raw.get("exception_type"),
            error_digest="",
        )
        return CollectElementFailed(
            schema_version=COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            **common,
            error=error,
            outcome_digest="",
        )
    raise ValueError(f"unsupported element outcome status {status!r}")


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
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        if not isinstance(value, dict):
            return value
        if isinstance(value, dict):
            candidates = tuple(
                candidate
                for candidate in get_args(hint)
                if dataclasses.is_dataclass(candidate)
            )
            status = value.get("status")
            kind = value.get("kind")
            if status is not None:
                for candidate in candidates:
                    if getattr(candidate, "status", None) == status:
                        return _decode_plain(candidate, value)
            if kind is not None:
                for candidate in candidates:
                    if getattr(candidate, "kind", None) == kind:
                        try:
                            return _decode_plain(candidate, value)
                        except (TypeError, ValueError):
                            continue
            for candidate in candidates:
                try:
                    return _decode_plain(candidate, value)
                except (TypeError, ValueError):
                    continue
        raise ValueError(
            f"cannot rebuild union value {hint} from {type(value).__name__}"
        )
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
    hints = typing.get_type_hints(cls)
    kwargs = {
        item.name: _rebuild_value(value[item.name], hints.get(item.name, item.type))
        for item in fields(cls)
    }
    return cls(**kwargs)


def _payload_codec(
    contract_ref: Any,
    *,
    codec_id: str,
    payload_cls: type[Any],
    payload_type: ObjectType,
) -> PayloadCodec:
    codec_version = "1"

    def encode(value: Any) -> dict[str, Any]:
        if not isinstance(value, payload_cls):
            raise TypeError(
                f"{codec_id} codec expected {payload_cls.__name__}, got {type(value).__name__}"
            )
        result = _plain(value)
        if not isinstance(result, dict):
            raise TypeError("payload codec produced a non-object encoding")
        return result

    def decode(value: dict[str, Any]) -> Any:
        if not isinstance(value, dict):
            raise TypeError("payload codec requires a JSON object")
        return _decode_plain(payload_cls, value)

    return PayloadCodec(
        codec_id=codec_id,
        codec_version=codec_version,
        contract_ref=contract_ref,
        payload_type_id=payload_type.type_id,
        encode=encode,
        decode=decode,
        codec_digest=codec_digest(
            codec_id=codec_id,
            codec_version=codec_version,
            contract_ref=contract_ref,
            payload_type_id=payload_type.type_id,
        ),
    )


def _profile_ref(
    profile_id: str, profile_version: str, digest: str
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile(
    *,
    operation_kind: str,
    owner: str,
    reads: tuple[str, ...],
    creates: tuple[str, ...],
    observation: str,
) -> SemanticProfile:
    values = {
        "semantic_profile_id": f"{operation_kind}.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": reads,
        "creates": creates,
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": observation,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile(
    *,
    operation_kind: str,
    execution_class: str,
    network_required: bool,
    irreversible: bool,
    external_visibility: str,
    internal_export_only: bool,
) -> EffectProfile:
    values = {
        "effect_profile_id": f"{operation_kind}.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": execution_class,
        "external_visibility": external_visibility,
        "network_required": network_required,
        "irreversible": irreversible,
        "cancellation_points": ("element_boundary", "step_boundary"),
        "internal_export_only": internal_export_only,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "logical_request_id",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile(
    *, operation_kind: str, concurrency_key: str, units: int
) -> ResourceProfile:
    values = {
        "resource_profile_id": f"{operation_kind}.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu", "network"),
        "concurrency_key": concurrency_key,
        "budget_units": "element",
        "default_soft_limit_seconds": 120,
        "default_hard_limit_seconds": 300,
        "node_profile_selector": "any",
        "budget_ref": "mrw.functorial-successor.budget.collect-c3.v1",
        "deadline_policy_ref": "mrw.functorial-successor.deadline.collect-c3.v1",
        "node_profile_requirements": ("any",),
        "units": units,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile(
    *, operation_kind: str, typed_failures: tuple[str, ...], retryable: bool
) -> FailureProfile:
    values = {
        "failure_profile_id": f"{operation_kind}.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": typed_failures,
        "retryable": retryable,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "none",
        "failure_union_ref": f"mrw.functorial-successor.failures.{operation_kind}.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile(*, operation_kind: str, owner: str) -> AuthorityProfile:
    values = {
        "authority_profile_id": f"{operation_kind}.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": owner,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile(
    *, interpreter_id: str, supported_kind: str, donor: str
) -> InterpreterProfile:
    values = {
        "interpreter_profile_id": interpreter_id,
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (supported_kind,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": interpreter_id,
                "version": "1.0.0",
                "donor": donor,
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": f"{supported_kind}.resource",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "element_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile(
    *, profile_id: str, dimensions: tuple[str, ...], schema_ref: str
) -> ObservationProfile:
    values = {
        "observation_profile_id": profile_id,
        "observation_profile_version": "1.0.0",
        "dimensions": dimensions,
        "compatible_with_legacy": True,
        "observation_schema_ref": schema_ref,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class CollectC3CapabilityBundle:
    bundle_id: str
    operation_c3_1: OperationContract
    operation_c3_2: OperationContract
    codecs: tuple[PayloadCodec, PayloadCodec]
    profiles: dict[str, object]

    def payload_codec_c3_1(self) -> PayloadCodec:
        return self.codecs[0]

    def payload_codec_c3_2(self) -> PayloadCodec:
        return self.codecs[1]


def build_collect_c3_bundle() -> CollectC3CapabilityBundle:
    common_failures = (
        "INVALID_INPUT",
        "ASSIGNMENT_BINDING_MISMATCH",
        "INTERPRETER_UNAVAILABLE",
        "TRAVERSAL_COMPILE_PENDING",
        "FOLD_CONTRACT_FAILURE",
    )
    semantic_1 = _semantic_profile(
        operation_kind=COLLECT_C3_1_KIND,
        owner=COLLECT_C3_1_OWNER,
        reads=(
            "CollectRequest.v1",
            "CollectBatchElement.v1",
            "CollectResourcePolicy.v1",
        ),
        creates=("CollectTraversalResult.v1",),
        observation=COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
    )
    effect_1 = _effect_profile(
        operation_kind=COLLECT_C3_1_KIND,
        execution_class="EFFECTFUL",
        network_required=True,
        irreversible=True,
        external_visibility="INTERNAL_ONLY",
        internal_export_only=True,
    )
    resource_1 = _resource_profile(
        operation_kind=COLLECT_C3_1_KIND,
        concurrency_key="project:provider",
        units=1,
    )
    failure_1 = _failure_profile(
        operation_kind=COLLECT_C3_1_KIND,
        typed_failures=common_failures
        + (
            "ELEMENT_EXECUTION_FAILED",
            "ORDERED_TRAVERSAL_ABORTED",
            "RESOURCE_POLICY_EXCEEDED",
        ),
        retryable=True,
    )
    authority_1 = _authority_profile(
        operation_kind=COLLECT_C3_1_KIND, owner=COLLECT_C3_1_OWNER
    )
    interpreter_1 = _interpreter_profile(
        interpreter_id="successor.collect_runtime.batch_traverse.v1",
        supported_kind=COLLECT_C3_1_KIND,
        donor="collect_runtime._split_query_terms+_run_auto_batch",
    )
    observation_1 = _observation_profile(
        profile_id=COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        dimensions=(
            "schema_version",
            "observation_profile",
            "request_ref",
            "traversal_policy",
            "failure_policy",
            "ordered_outcomes",
            "requested_parallelism",
            "effective_parallelism",
            "cancellation_observed",
            "observation_digest",
        ),
        schema_ref=COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
    )

    semantic_2 = _semantic_profile(
        operation_kind=COLLECT_C3_2_KIND,
        owner=COLLECT_C3_2_OWNER,
        reads=("OrderedCollectElementOutcomeSequence.v1",),
        creates=("CollectAggregateOutcome.v1",),
        observation=COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    effect_2 = _effect_profile(
        operation_kind=COLLECT_C3_2_KIND,
        execution_class="PURE_TRANSFORM",
        network_required=False,
        irreversible=False,
        external_visibility="NONE",
        internal_export_only=False,
    )
    resource_2 = _resource_profile(
        operation_kind=COLLECT_C3_2_KIND,
        concurrency_key="project",
        units=1,
    )
    failure_2 = _failure_profile(
        operation_kind=COLLECT_C3_2_KIND,
        typed_failures=common_failures
        + ("AGGREGATE_ALL_FAILED", "QUEUED_ACK_NOT_COMPLETION"),
        retryable=False,
    )
    authority_2 = _authority_profile(
        operation_kind=COLLECT_C3_2_KIND, owner=COLLECT_C3_2_OWNER
    )
    interpreter_2 = _interpreter_profile(
        interpreter_id="successor.collect_runtime.result_fold.v1",
        supported_kind=COLLECT_C3_2_KIND,
        donor="collect_runtime._merge_collect_results",
    )
    observation_2 = _observation_profile(
        profile_id=COLLECT_FOLD_OBSERVATION_PROFILE,
        dimensions=(
            "schema_version",
            "ordered_outcomes",
            "aggregate_counts",
            "errors",
            "receipts",
            "links",
            "aggregate_digest",
        ),
        schema_ref=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
    )

    operation_1 = make_operation_contract(
        kind=COLLECT_C3_1_KIND,
        contract_version="1.0.0",
        input_type=COLLECT_C3_1_PAYLOAD_TYPE,
        output_type=COLLECT_C3_1_RESULT_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic_1.semantic_profile_id,
            semantic_1.semantic_profile_version,
            semantic_1.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect_1.effect_profile_id,
            effect_1.effect_profile_version,
            effect_1.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource_1.resource_profile_id,
            resource_1.resource_profile_version,
            resource_1.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure_1.failure_profile_id,
            failure_1.failure_profile_version,
            failure_1.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority_1.authority_profile_id,
            authority_1.authority_profile_version,
            authority_1.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter_1.interpreter_profile_id,
            interpreter_1.interpreter_profile_version,
            interpreter_1.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation_1.observation_profile_id,
            observation_1.observation_profile_version,
            observation_1.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=COLLECT_C3_1_OWNER,
    )
    operation_2 = make_operation_contract(
        kind=COLLECT_C3_2_KIND,
        contract_version="1.0.0",
        input_type=COLLECT_C3_2_PAYLOAD_TYPE,
        output_type=COLLECT_FOLD_RESULT_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic_2.semantic_profile_id,
            semantic_2.semantic_profile_version,
            semantic_2.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect_2.effect_profile_id,
            effect_2.effect_profile_version,
            effect_2.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource_2.resource_profile_id,
            resource_2.resource_profile_version,
            resource_2.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure_2.failure_profile_id,
            failure_2.failure_profile_version,
            failure_2.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority_2.authority_profile_id,
            authority_2.authority_profile_version,
            authority_2.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter_2.interpreter_profile_id,
            interpreter_2.interpreter_profile_version,
            interpreter_2.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation_2.observation_profile_id,
            observation_2.observation_profile_version,
            observation_2.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=COLLECT_C3_2_OWNER,
    )
    codec_1 = _payload_codec(
        operation_1.ref,
        codec_id=COLLECT_C3_1_PAYLOAD_CODEC_ID,
        payload_cls=CollectBatchElementPayload,
        payload_type=COLLECT_C3_1_PAYLOAD_TYPE,
    )
    codec_2 = _payload_codec(
        operation_2.ref,
        codec_id=COLLECT_C3_2_PAYLOAD_CODEC_ID,
        payload_cls=CollectFoldPayload,
        payload_type=COLLECT_C3_2_PAYLOAD_TYPE,
    )
    return CollectC3CapabilityBundle(
        bundle_id="mrw.functorial-successor.collect.c3",
        operation_c3_1=operation_1,
        operation_c3_2=operation_2,
        codecs=(codec_1, codec_2),
        profiles={
            "semantic.c3_1": semantic_1,
            "effect.c3_1": effect_1,
            "resource.c3_1": resource_1,
            "failure.c3_1": failure_1,
            "authority.c3_1": authority_1,
            "interpreter.c3_1": interpreter_1,
            "observation.c3_1": observation_1,
            "semantic.c3_2": semantic_2,
            "effect.c3_2": effect_2,
            "resource.c3_2": resource_2,
            "failure.c3_2": failure_2,
            "authority.c3_2": authority_2,
            "interpreter.c3_2": interpreter_2,
            "observation.c3_2": observation_2,
        },
    )


def build_collect_c3_catalog(
    bundle: CollectC3CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=COLLECT_C3_1_CATALOG_ID,
        catalog_version=COLLECT_C3_CATALOG_VERSION,
        entries=(
            (
                bundle.operation_c3_1.ref.kind,
                bundle.operation_c3_1.ref.contract_version,
                bundle.operation_c3_1.ref.contract_digest,
                bundle.operation_c3_1.owner_capability_id,
            ),
            (
                bundle.operation_c3_2.ref.kind,
                bundle.operation_c3_2.ref.contract_version,
                bundle.operation_c3_2.ref.contract_digest,
                bundle.operation_c3_2.owner_capability_id,
            ),
        ),
    )


def build_collect_c3_registry(
    bundle: CollectC3CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_collect_c3_catalog(bundle),
        (bundle.operation_c3_1, bundle.operation_c3_2),
    )


def deployment_catalog_digest() -> str:
    """Immutable deployment catalog identity distinct from operation catalogs."""

    return content_digest(
        {
            "schema": DEPLOYMENT_CATALOG_SCHEMA_REF,
            "capability_family": "collect-c3",
            "canonical_owner_c3_1": COLLECT_C3_1_OWNER,
            "canonical_owner_c3_2": COLLECT_C3_2_OWNER,
            "operation_c3_1": COLLECT_C3_1_KIND,
            "operation_c3_2": COLLECT_C3_2_KIND,
            "legacy_interpreter_c3_1": "legacy.collect_runtime.batch_traverse.v1",
            "successor_interpreter_c3_1": "successor.collect_runtime.batch_traverse.v1",
            "legacy_interpreter_c3_2": "legacy.collect_runtime.result_fold.v1",
            "successor_interpreter_c3_2": "successor.collect_runtime.result_fold.v1",
        }
    )
