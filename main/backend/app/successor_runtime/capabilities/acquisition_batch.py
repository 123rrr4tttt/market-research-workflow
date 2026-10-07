"""Frozen typed contracts for acquisition batch traversal and result fold.

This module owns the canonical vocabulary for the two acquisition operations:
authenticated request refs, the finite ordered batch plan, element identity,
element outcomes, attempt receipts, the ordered outcome sequence and the
aggregate outcome union.  It also owns the pure deterministic plan rules and
the pure ordered fold used by the collect runtime and policy materializer.

The module is capability-boundary only: it never imports service packages and
never performs network, database, provider or credential work.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Any,
    Literal,
    NoReturn,
    TypeAlias,
)
from typing import TypeGuard

from functorial_kit import Failure, define_failure_family

from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
    freeze_json_object,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "ACQUISITION_BATCH_FAILURES",
    "AUTHENTICATED_COLLECT_SCOPE_TYPE",
    "COLLECT_AGGREGATE_OUTCOME_TYPE",
    "COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF",
    "COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF",
    "COLLECT_ATTEMPT_RECEIPT_TYPE",
    "COLLECT_BATCH_ELEMENT_TYPE",
    "COLLECT_BATCH_PLAN_TYPE",
    "ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER",
    "COLLECT_ELEMENT_OUTCOME_TYPE",
    "COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF",
    "COLLECT_ELEMENT_OUTCOME_TYPE",
    "COLLECT_FOLD_OBSERVATION_PROFILE",
    "COLLECT_FOLD_RESOURCE_CEILING",
    "COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF",
    "COLLECT_FOLD_RESULT_TYPE",
    "COLLECT_RECEIPT_DEDUPE_STABLE_FIRST_REF",
    "COLLECT_REQUEST_TYPE",
    "COLLECT_TRAVERSAL_OBSERVATION_PROFILE",
    "COLLECT_TRAVERSAL_RESULT_SCHEMA_REF",
    "COLLECT_TRAVERSAL_RESULT_TYPE",
    "CollectAggregateCounts",
    "CollectAggregateFailed",
    "CollectAggregateOutcome",
    "CollectAggregatePartial",
    "CollectAggregateSucceeded",
    "CollectAttemptReceipt",
    "CollectBatchElement",
    "CollectBatchPlan",
    "CollectCancellationReceipt",
    "CollectCounts",
    "CollectElementError",
    "CollectElementFailed",
    "CollectElementOutcome",
    "CollectElementSucceeded",
    "CollectFoldContractFailure",
    "CollectFoldResourceCeiling",
    "CollectLegacyRequestSnapshot",
    "CollectRequestRef",
    "CollectResourcePolicy",
    "CollectTraversalBypassed",
    "CollectTraversalObservation",
    "CollectTraversalResult",
    "CollectTraversalSingleton",
    "OrderedCollectElementOutcomeSequence",
    "OrderedTraversalAborted",
    "OrderedTraversalCompleted",
    "build_collect_batch_plan",
    "build_collect_request_ref",
    "collect_contract_failure",
    "collect_request_ref_from_dict",
    "CollectPlanBuildResult",
    "fold_ordered_results",
    "per_batch_limit_for",
    "receipt_implies_completed",
    "require_fold_ceiling",
    "resolve_auto_batch_fail_fast",
    "resolve_auto_batch_parallelism",
    "raise_collect_contract_failure",
    "raise_collect_programmer_defect",
    "should_auto_batch",
    "split_query_terms",
    "try_build_collect_batch_plan",
]
CollectPlanBuildResult: TypeAlias = "CollectBatchPlan | Failure"
ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER = "acquisition.batch.execute_element.v2"
COLLECT_TRAVERSAL_OBSERVATION_PROFILE = "acquisition.batch.execute_element.ordered_observation.v2"
COLLECT_FOLD_OBSERVATION_PROFILE = "acquisition.batch.fold_ordered_results.receipt_preservation.v2"
ACQUISITION_BATCH_FAILURES = define_failure_family(
    "acquisition.batch.failure",
    ("INVALID_INPUT",),
)
COLLECT_REQUEST_SCHEMA_REF = "mrw.acquisition.request-ref.v2"
COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF = "mrw.acquisition.legacy-request-snapshot.v2"
COLLECT_RESOURCE_POLICY_SCHEMA_REF = "mrw.acquisition.resource-policy.v2"
COLLECT_BATCH_ELEMENT_SCHEMA_REF = "mrw.acquisition.batch-element.v2"
COLLECT_BATCH_PLAN_SCHEMA_REF = "mrw.acquisition.batch-plan.v2"
COLLECT_ELEMENT_OUTCOME_SCHEMA_REF = "mrw.acquisition.element-outcome.v2"
COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF = "mrw.acquisition.attempt-receipt.v2"
COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF = "mrw.acquisition.aggregate-outcome.v2"
ORDERED_OUTCOME_SEQUENCE_SCHEMA_REF = "mrw.acquisition.ordered-result-fold.input.v2"
COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF = "mrw.acquisition.batch.execute_element.observation.v2"
COLLECT_TRAVERSAL_RESULT_SCHEMA_REF = "mrw.acquisition.batch.execute_element.result.v2"
COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF = "mrw.acquisition.cancellation-receipt.v2"
COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF = "mrw.acquisition.fold_ordered_results.resource-ceiling.v2"
COLLECT_RECEIPT_DEDUPE_STABLE_FIRST_REF = "mrw.acquisition.fold_ordered_results.receipt-dedupe.stable-first.v2"
COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF = "mrw.acquisition.fold_ordered_results.aggregation.accumulate.v2"
COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF = "mrw.acquisition.fold_ordered_results.aggregation.fail_fast_partial.v2"
COLLECT_AGGREGATION_POLICY_REFS = frozenset(
    {COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF, COLLECT_AGGREGATION_POLICY_FAIL_FAST_REF}
)
COLLECT_REQUEST_TYPE = ObjectType("CollectRequest.v1")
AUTHENTICATED_COLLECT_SCOPE_TYPE = ObjectType("AuthenticatedCollectScope.v1")
COLLECT_BATCH_ELEMENT_TYPE = ObjectType("CollectBatchElement.v1")
COLLECT_BATCH_PLAN_TYPE = ObjectType("CollectBatchPlan.v1")
COLLECT_ELEMENT_OUTCOME_TYPE = ObjectType("CollectElementOutcome.v1")
COLLECT_ATTEMPT_RECEIPT_TYPE = ObjectType("CollectAttemptReceipt.v1")
ORDERED_COLLECT_ELEMENT_OUTCOME_SEQUENCE_TYPE = ObjectType("OrderedCollectElementOutcomeSequence.v1")
COLLECT_AGGREGATE_OUTCOME_TYPE = ObjectType("CollectAggregateOutcome.v1")
COLLECT_TRAVERSAL_RESULT_TYPE = ObjectType("CollectTraversalResult.v1")
COLLECT_FOLD_RESULT_TYPE = COLLECT_AGGREGATE_OUTCOME_TYPE
TraversalPolicy = Literal["STATIC_SHAPE", "MATERIALIZED_SHAPE"]
FailurePolicy = Literal["ACCUMULATE", "FAIL_FAST_WITH_PARTIAL_OBSERVATION"]
PlanDisposition = Literal["BYPASSED", "SINGLETON_IDENTITY", "TRAVERSE"]
COLLECT_AUTO_BATCH_CHANNELS = frozenset({"search.market", "search.policy"})
COLLECT_ELEMENT_ERROR_CODES = frozenset({"auto_batch_execution_failed", "element_rejected", "runner_unavailable"})
_LEGACY_OBSERVATION_REF = re.compile("^legacy:[0-9a-f]{64}$")
_OBSERVED_AT = re.compile("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z$")


def _freeze(value: FrozenJsonObject | dict[str, Any]) -> FrozenJsonObject:
    if isinstance(value, dict):
        return freeze_json_object(value)
    return freeze_json_object(dict(value))


_ACQUISITION_BATCH_CONTRACT_WITNESS = "test:test_acquisition_contract_failures_use_canonical_value"
_ACQUISITION_BATCH_CONTRACT_CONTEXT_KEYS = frozenset(
    {"operation", "owner", "public_exception", "public_message", "site", "domain_outcome", "reason_code", "witness"}
)


def collect_contract_failure(
    *,
    code: str,
    reason_code: str | None = None,
    message: str,
    operation: str,
    site: str,
    domain_outcome: Literal["INVALID_INPUT"],
    public_exception: str = "ValueError",
    owner: str = ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER,
) -> Failure:
    """Build the one canonical acquisition contract-failure value."""
    resolved_reason_code = reason_code or code
    resolved_code = "INVALID_INPUT" if code in {
        "schema_contract_invalid",
        "codec_contract_invalid",
    } else code
    return ACQUISITION_BATCH_FAILURES.fail(
        resolved_code,
        message,
        {
            "operation": operation,
            "owner": owner,
            "public_exception": public_exception,
            "public_message": message,
            "site": site,
            "domain_outcome": domain_outcome,
            "reason_code": resolved_reason_code,
            "witness": _ACQUISITION_BATCH_CONTRACT_WITNESS,
        },
    )


def raise_collect_contract_failure(failure: Failure, exception_type: type[Exception]) -> NoReturn:
    """Lift one canonical failure at a legacy exception boundary."""
    context = failure.context or {}
    if (
        not ACQUISITION_BATCH_FAILURES.matches(failure)
        or _ACQUISITION_BATCH_CONTRACT_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        raise_collect_programmer_defect("acquisition contract lift context is invalid", TypeError)
    # kit:boundary owner=acquisition.public_contract class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=acquisition.batch.failure witness=test:test_acquisition_compatibility_lift_preserves_exception_abi
    raise exception_type(str(context["public_message"]))


def raise_collect_programmer_defect(message: str, exception_type: type[Exception]) -> NoReturn:
    """Retain an internal invariant exception outside the contract family."""
    # kit:boundary owner=acquisition.programmer_defect class=PROGRAMMER_DEFECT failure_family=none witness=test:test_acquisition_programmer_defect_lift_preserves_exception_abi
    raise exception_type(message)


def _reject_collect_contract(message: str, exception_type: type[Exception], *, site: str) -> NoReturn:
    """Build a typed rejection before crossing a legacy constructor boundary."""
    raise_collect_contract_failure(
        collect_contract_failure(
            code="INVALID_INPUT",
            reason_code="schema_contract_invalid",
            message=message,
            operation="collect.validate_contract",
            site=site,
            domain_outcome="INVALID_INPUT",
            public_exception=exception_type.__name__,
        ),
        exception_type,
    )


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _require_optional_string(value: object, field_name: str, *, site: str) -> str | None:
    if value is not None and not isinstance(value, str):
        _reject_collect_contract(
            f"{field_name} must be a string or None",
            ValueError,
            site=site,
        )
    return value


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject_collect_contract(f"{field_name} is required", ValueError, site="_require_non_empty_string")
    return value.strip()


def _require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _reject_collect_contract(f"{field_name} must be a positive int", ValueError, site="_require_positive_int")
    return value


def _require_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _reject_collect_contract(
            f"{field_name} must be a non-negative int", ValueError, site="_require_non_negative_int"
        )
    return value


def _require_string_tuple(value: Any, field_name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    items = tuple((str(item) for item in value or ()))
    if not allow_empty and (not items):
        _reject_collect_contract(
            f"{field_name} must contain at least one string", ValueError, site="_require_string_tuple"
        )
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
            tuple(((str(name), bool(required)) for name, required in self.field_requiredness)),
        )
        expected = content_digest(
            {
                "schema": "mrw.acquisition.schema.v2",
                "schema_ref": self.schema_ref,
                "field_requiredness": self.field_requiredness,
            }
        )
        if self.schema_digest == "":
            object.__setattr__(self, "schema_digest", expected)
        else:
            require_hex64(self.schema_digest, "VersionedSchema.schema_digest")
            if self.schema_digest != expected:
                _reject_collect_contract(
                    "VersionedSchema.schema_digest does not match content",
                    ValueError,
                    site="VersionedSchema.__post_init__",
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "field_requiredness": [[name, required] for name, required in self.field_requiredness],
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

    schema_version: Literal["mrw.acquisition.request-ref.v2"]
    request_id: str
    project_key: str
    channel: str
    request_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_REQUEST_SCHEMA_REF:
            _reject_collect_contract(
                "CollectRequestRef.schema_version is not the frozen schema",
                ValueError,
                site="CollectRequestRef.__post_init__",
            )
        object.__setattr__(self, "request_id", _require_non_empty_string(self.request_id, "request_id"))
        object.__setattr__(self, "project_key", _require_non_empty_string(self.project_key, "project_key"))
        object.__setattr__(self, "channel", _require_non_empty_string(self.channel, "channel"))
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
                _reject_collect_contract(
                    "CollectRequestRef.request_digest does not match content",
                    ValueError,
                    site="CollectRequestRef.__post_init__",
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
    *, request_id: str, project_key: str, channel: str
) -> Annotated[
    CollectRequestRef,
    "kit:non-authoritative derived_as=view fact_source=normalized_collect_request_inputs witness=test:test_w05_collect_authority_metadata",
]:
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

    schema_version: Literal["mrw.acquisition.legacy-request-snapshot.v2"]
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
            _reject_collect_contract(
                "CollectLegacyRequestSnapshot.schema_version is not the frozen schema",
                ValueError,
                site="CollectLegacyRequestSnapshot.__post_init__",
            )
        object.__setattr__(self, "flow", _require_non_empty_string(self.flow, "flow"))
        object.__setattr__(self, "channel", _require_non_empty_string(self.channel, "channel"))
        if self.project_key is not None:
            object.__setattr__(self, "project_key", _require_non_empty_string(self.project_key, "project_key"))
        object.__setattr__(self, "query_terms", _require_string_tuple(self.query_terms, "query_terms"))
        object.__setattr__(self, "urls", _require_string_tuple(self.urls, "urls"))
        if self.limit is not None:
            object.__setattr__(self, "limit", _require_positive_int(self.limit, "limit"))
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
            require_hex64(self.snapshot_digest, "CollectLegacyRequestSnapshot.snapshot_digest")
            if self.snapshot_digest != expected:
                _reject_collect_contract(
                    "CollectLegacyRequestSnapshot.snapshot_digest does not match content",
                    ValueError,
                    site="CollectLegacyRequestSnapshot.__post_init__",
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

    schema_ref: Literal["mrw.acquisition.resource-policy.v2"]
    max_parallelism: int
    deadline_seconds: int | None
    cancellation: Literal["COORDINATED", "NONE"]
    backpressure: bool
    provider_concurrency_key: str
    policy_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_ref != COLLECT_RESOURCE_POLICY_SCHEMA_REF:
            _reject_collect_contract(
                "CollectResourcePolicy.schema_ref is not the frozen schema",
                ValueError,
                site="CollectResourcePolicy.__post_init__",
            )
        object.__setattr__(self, "max_parallelism", _require_positive_int(self.max_parallelism, "max_parallelism"))
        if self.deadline_seconds is not None:
            object.__setattr__(
                self, "deadline_seconds", _require_positive_int(self.deadline_seconds, "deadline_seconds")
            )
        if self.cancellation not in {"COORDINATED", "NONE"}:
            _reject_collect_contract(
                f"unsupported cancellation policy {self.cancellation!r}",
                ValueError,
                site="CollectResourcePolicy.__post_init__",
            )
        object.__setattr__(
            self,
            "provider_concurrency_key",
            _require_non_empty_string(self.provider_concurrency_key, "provider_concurrency_key"),
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
                _reject_collect_contract(
                    "CollectResourcePolicy.policy_digest does not match content",
                    ValueError,
                    site="CollectResourcePolicy.__post_init__",
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
    """One stable finite ordered batch element inside an acquisition plan."""

    schema_version: Literal["mrw.acquisition.batch-element.v2"]
    element_id: str
    input_index: int
    query_terms: tuple[str, ...]
    per_batch_limit: int
    traversal_policy: TraversalPolicy
    failure_policy: FailurePolicy
    element_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_BATCH_ELEMENT_SCHEMA_REF:
            _reject_collect_contract(
                "CollectBatchElement.schema_version is not the frozen schema",
                ValueError,
                site="CollectBatchElement.__post_init__",
            )
        object.__setattr__(self, "element_id", _require_non_empty_string(self.element_id, "element_id"))
        object.__setattr__(self, "input_index", _require_non_negative_int(self.input_index, "input_index"))
        object.__setattr__(
            self, "query_terms", _require_string_tuple(self.query_terms, "query_terms", allow_empty=False)
        )
        object.__setattr__(self, "per_batch_limit", _require_positive_int(self.per_batch_limit, "per_batch_limit"))
        if self.traversal_policy not in {"STATIC_SHAPE", "MATERIALIZED_SHAPE"}:
            _reject_collect_contract(
                f"unsupported traversal policy {self.traversal_policy!r}",
                ValueError,
                site="CollectBatchElement.__post_init__",
            )
        if self.failure_policy not in {"ACCUMULATE", "FAIL_FAST_WITH_PARTIAL_OBSERVATION"}:
            _reject_collect_contract(
                f"unsupported failure policy {self.failure_policy!r}",
                ValueError,
                site="CollectBatchElement.__post_init__",
            )
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
                _reject_collect_contract(
                    "CollectBatchElement.element_digest does not match content",
                    ValueError,
                    site="CollectBatchElement.__post_init__",
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

    schema_version: Literal["mrw.acquisition.batch-plan.v2"]
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
            _reject_collect_contract(
                "CollectBatchPlan.schema_version is not the frozen schema",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        object.__setattr__(self, "plan_id", _require_non_empty_string(self.plan_id, "plan_id"))
        object.__setattr__(self, "elements", tuple(self.elements))
        if self.disposition == "TRAVERSE" and len(self.elements) < 2:
            _reject_collect_contract(
                "TRAVERSE plan requires at least two elements", ValueError, site="CollectBatchPlan.__post_init__"
            )
        if self.disposition == "SINGLETON_IDENTITY" and len(self.elements) != 1:
            _reject_collect_contract(
                "SINGLETON_IDENTITY plan requires exactly one element",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        if self.disposition == "BYPASSED" and self.elements:
            _reject_collect_contract(
                "BYPASSED plan must not carry elements", ValueError, site="CollectBatchPlan.__post_init__"
            )
        object.__setattr__(self, "per_batch_limit", _require_positive_int(self.per_batch_limit, "per_batch_limit"))
        object.__setattr__(
            self, "requested_parallelism", _require_positive_int(self.requested_parallelism, "requested_parallelism")
        )
        object.__setattr__(
            self, "effective_parallelism", _require_positive_int(self.effective_parallelism, "effective_parallelism")
        )
        object.__setattr__(self, "batches_total", _require_non_negative_int(self.batches_total, "batches_total"))
        if self.batches_total != len(self.elements):
            _reject_collect_contract(
                "CollectBatchPlan.batches_total must equal len(elements)",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        if tuple((element.input_index for element in self.elements)) != tuple(range(len(self.elements))):
            _reject_collect_contract(
                "CollectBatchPlan element input_index must be contiguous 0-based unique",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        if any(
            (
                element.traversal_policy != self.traversal_policy
                or element.failure_policy != self.failure_policy
                or element.per_batch_limit != self.per_batch_limit
                for element in self.elements
            )
        ):
            _reject_collect_contract(
                "CollectBatchPlan elements must share traversal/failure policy and per-batch limit",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        if any((not element.element_id.startswith(self.plan_id + ":element:") for element in self.elements)):
            _reject_collect_contract(
                "CollectBatchPlan element ids must bind the parent plan identity",
                ValueError,
                site="CollectBatchPlan.__post_init__",
            )
        ceiling = max(1, len(self.elements))
        if self.effective_parallelism > min(self.requested_parallelism, ceiling):
            _reject_collect_contract(
                "effective parallelism exceeds requested parallelism or element count",
                ValueError,
                site="CollectBatchPlan.__post_init__",
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
                _reject_collect_contract(
                    "CollectBatchPlan.plan_digest does not match content",
                    ValueError,
                    site="CollectBatchPlan.__post_init__",
                )

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
    return [clean[index : index + chunk_size] for index in range(0, len(clean), chunk_size)]


def per_batch_limit_for(limit: Any, batch_count: int) -> int:
    """Deterministic rewrite of legacy per-batch limit calculation."""
    try:
        requested = max(1, int(limit or 20))
    except (TypeError, ValueError):
        requested = 20
    return max(10, math.ceil(requested / max(1, batch_count)))


def _option_value(request: object, name: str, default: object) -> object:

    def as_mapping(value: object) -> dict[str, object]:
        if value is None:
            return {}
        if _is_object_mapping(value):
            return {str(key): item for key, item in value.items()}
        if _is_object_tuple(value):
            result: dict[str, object] = {}
            for pair in value:
                if not _is_object_tuple(pair) or len(pair) != 2:
                    return {}
                key, item = pair
                if not isinstance(key, str):
                    return {}
                result[key] = item
            return result
        return {}

    options = as_mapping(getattr(request, "options", None))
    source_context = as_mapping(getattr(request, "source_context", None))
    if name in options:
        return options[name]
    if name in source_context:
        return source_context[name]
    return default


def resolve_auto_batch_parallelism(request: Any) -> int:
    """Deterministic rewrite of legacy ``runtime._resolve_auto_batch_parallelism``."""
    raw = _option_value(request, "batch_parallelism", 1)
    if not isinstance(raw, (str, int, float)):
        return 1
    try:
        return max(1, int(raw))
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
) -> Annotated[
    CollectBatchPlan,
    "kit:non-authoritative derived_as=view fact_source=CollectLegacyRequestSnapshot+ordered_element_policy witness=test:test_w05_collect_authority_metadata",
]:
    """Pure finite ordered plan rules; never mutates the request in place."""
    result = try_build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id=plan_id,
        resource_policy=resource_policy,
        authority_scope_ref=authority_scope_ref,
        traversal_policy=traversal_policy,
        static_elements=static_elements,
    )
    if isinstance(result, Failure):
        raise_collect_contract_failure(result, ValueError)
    return result


def try_build_collect_batch_plan(
    *,
    request_ref: CollectRequestRef,
    snapshot: CollectLegacyRequestSnapshot,
    plan_id: str,
    resource_policy: CollectResourcePolicy,
    authority_scope_ref: str,
    traversal_policy: TraversalPolicy = "MATERIALIZED_SHAPE",
    static_elements: tuple[CollectBatchElement, ...] | None = None,
) -> CollectPlanBuildResult:
    """Total plan construction; contract rejections are canonical kit failures."""
    try:
        return _construct_collect_batch_plan(
            request_ref=request_ref,
            snapshot=snapshot,
            plan_id=plan_id,
            resource_policy=resource_policy,
            authority_scope_ref=authority_scope_ref,
            traversal_policy=traversal_policy,
            static_elements=static_elements,
        )
    except (TypeError, ValueError) as exc:
        return collect_contract_failure(
            code="INVALID_INPUT",
            reason_code="schema_contract_invalid",
            message=str(exc),
            operation="collect.build_batch_plan",
            site="try_build_collect_batch_plan",
            domain_outcome="INVALID_INPUT",
        )


def _construct_collect_batch_plan(
    *,
    request_ref: CollectRequestRef,
    snapshot: CollectLegacyRequestSnapshot,
    plan_id: str,
    resource_policy: CollectResourcePolicy,
    authority_scope_ref: str,
    traversal_policy: TraversalPolicy = "MATERIALIZED_SHAPE",
    static_elements: tuple[CollectBatchElement, ...] | None = None,
) -> Annotated[
    CollectBatchPlan,
    "kit:non-authoritative derived_as=view fact_source=CollectLegacyRequestSnapshot+ordered_element_policy witness=test:test_w05_collect_authority_metadata",
]:
    """Ordered construction core invoked by the total plan boundary."""
    _require_non_empty_string(authority_scope_ref, "authority_scope_ref")
    if not should_auto_batch(snapshot):
        return CollectBatchPlan(
            schema_version=COLLECT_BATCH_PLAN_SCHEMA_REF,
            plan_id=plan_id,
            request_ref=request_ref,
            disposition="BYPASSED",
            traversal_policy=traversal_policy,
            failure_policy="FAIL_FAST_WITH_PARTIAL_OBSERVATION"
            if resolve_auto_batch_fail_fast(snapshot)
            else "ACCUMULATE",
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
        if tuple((element.query_terms for element in static_elements)) != tuple(derived_terms):
            _reject_collect_contract(
                "STATIC_SHAPE elements do not match the derived finite ordered shape",
                ValueError,
                site="_construct_collect_batch_plan",
            )
        if tuple((element.input_index for element in static_elements)) != tuple(range(len(static_elements))):
            _reject_collect_contract(
                "STATIC_SHAPE elements must use 0-based contiguous input_index",
                ValueError,
                site="_construct_collect_batch_plan",
            )
        elements = tuple(static_elements)
    else:
        elements = tuple(
            (
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
        object.__setattr__(self, "inserted", _require_non_negative_int(self.inserted, "inserted"))
        object.__setattr__(self, "updated", _require_non_negative_int(self.updated, "updated"))
        object.__setattr__(self, "skipped", _require_non_negative_int(self.skipped, "skipped"))

    def to_plain(self) -> dict[str, Any]:
        return {"inserted": self.inserted, "updated": self.updated, "skipped": self.skipped}


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
            _reject_collect_contract(
                f"unregistered collect element error code {self.code!r}",
                ValueError,
                site="CollectElementError.__post_init__",
            )
        _require_non_empty_string(self.message, "CollectElementError.message")
        object.__setattr__(self, "query_terms", _require_string_tuple(self.query_terms, "query_terms"))
        _require_optional_string(
            self.exception_type,
            "CollectElementError.exception_type",
            site="CollectElementError.__post_init__",
        )
        expected = content_digest(
            {
                "schema": "mrw.acquisition.element-error.v2",
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
                _reject_collect_contract(
                    "CollectElementError.error_digest does not match content",
                    ValueError,
                    site="CollectElementError.__post_init__",
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

    schema_version: Literal["mrw.acquisition.attempt-receipt.v2"]
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
            _reject_collect_contract(
                "CollectAttemptReceipt.schema_version is not the frozen schema",
                ValueError,
                site="CollectAttemptReceipt.__post_init__",
            )
        if self.receipt_kind not in {"DISPATCH_ACKNOWLEDGEMENT", "AUTHORITATIVE_READBACK"}:
            _reject_collect_contract(
                f"unsupported receipt kind {self.receipt_kind!r}",
                ValueError,
                site="CollectAttemptReceipt.__post_init__",
            )
        object.__setattr__(self, "provider_type", _require_non_empty_string(self.provider_type, "provider_type"))
        object.__setattr__(self, "provider_job_id", _require_non_empty_string(self.provider_job_id, "provider_job_id"))
        if self.provider_status is not None:
            object.__setattr__(
                self, "provider_status", _require_non_empty_string(self.provider_status, "provider_status")
            )
        object.__setattr__(self, "attempt_count", _require_non_negative_int(self.attempt_count, "attempt_count"))
        if _OBSERVED_AT.fullmatch(str(self.observed_at or "")) is None:
            _reject_collect_contract(
                "CollectAttemptReceipt.observed_at must be UTC ISO-8601",
                ValueError,
                site="CollectAttemptReceipt.__post_init__",
            )
        require_hex64(self.raw_digest, "CollectAttemptReceipt.raw_digest")
        if self.authoritative_readback != (self.receipt_kind == "AUTHORITATIVE_READBACK"):
            _reject_collect_contract(
                "authoritative_readback must match receipt_kind exactly",
                ValueError,
                site="CollectAttemptReceipt.__post_init__",
            )
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
                _reject_collect_contract(
                    "CollectAttemptReceipt.receipt_digest does not match content",
                    ValueError,
                    site="CollectAttemptReceipt.__post_init__",
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


def _require_optional_collect_attempt_receipt(
    value: object,
    *,
    site: str,
) -> CollectAttemptReceipt | None:
    if value is not None and not isinstance(value, CollectAttemptReceipt):
        _reject_collect_contract(
            "element receipt must be CollectAttemptReceipt or None",
            ValueError,
            site=site,
        )
    return value


@dataclass(frozen=True, slots=True)
class CollectCancellationReceipt:
    """Typed cancellation receipt emitted by fail-fast traversal aborts."""

    schema_version: Literal["mrw.acquisition.cancellation-receipt.v2"]
    code: Literal["FAIL_FAST_CANCELLED"]
    message: str
    trigger_input_index: int
    observed: Literal["SERIAL_EXECUTION", "PARALLEL_COMPLETION"]
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF:
            _reject_collect_contract(
                "CollectCancellationReceipt.schema_version is not the frozen schema",
                ValueError,
                site="CollectCancellationReceipt.__post_init__",
            )
        if self.code != "FAIL_FAST_CANCELLED":
            _reject_collect_contract(
                f"unsupported cancellation code {self.code!r}",
                ValueError,
                site="CollectCancellationReceipt.__post_init__",
            )
        _require_non_empty_string(self.message, "CollectCancellationReceipt.message")
        object.__setattr__(
            self, "trigger_input_index", _require_non_negative_int(self.trigger_input_index, "trigger_input_index")
        )
        if self.observed not in {"SERIAL_EXECUTION", "PARALLEL_COMPLETION"}:
            _reject_collect_contract(
                f"unsupported cancellation observation {self.observed!r}",
                ValueError,
                site="CollectCancellationReceipt.__post_init__",
            )
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
            require_hex64(self.receipt_digest, "CollectCancellationReceipt.receipt_digest")
            if self.receipt_digest != expected:
                _reject_collect_contract(
                    "CollectCancellationReceipt.receipt_digest does not match content",
                    ValueError,
                    site="CollectCancellationReceipt.__post_init__",
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
    schema_version: Literal["mrw.acquisition.element-outcome.v2"]
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
            _reject_collect_contract(
                "CollectElementSucceeded.status must be 'succeeded'",
                ValueError,
                site="CollectElementSucceeded.__post_init__",
            )
        expected = content_digest(self._digest_payload())
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectElementSucceeded.outcome_digest")
            if self.outcome_digest != expected:
                _reject_collect_contract(
                    "CollectElementSucceeded.outcome_digest does not match content",
                    ValueError,
                    site="CollectElementSucceeded.__post_init__",
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_ELEMENT_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "element outcome schema_version is not the frozen schema",
                ValueError,
                site="CollectElementSucceeded._validate_common",
            )
        _require_non_empty_string(self.element_id, "element_id")
        _require_non_negative_int(self.input_index, "input_index")
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        _require_legacy_observation_ref(self.legacy_observation_ref)
        _require_optional_collect_attempt_receipt(
            self.receipt,
            site="CollectElementSucceeded._validate_common",
        )

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
        return {**self._digest_payload(), "schema_version": self.schema_version, "outcome_digest": self.outcome_digest}


@dataclass(frozen=True, slots=True)
class CollectElementFailed:
    schema_version: Literal["mrw.acquisition.element-outcome.v2"]
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
            _reject_collect_contract(
                "CollectElementFailed.status must be 'failed'", ValueError, site="CollectElementFailed.__post_init__"
            )
        if not isinstance(self.error, CollectElementError):
            _reject_collect_contract(
                "CollectElementFailed requires a typed error", TypeError, site="CollectElementFailed.__post_init__"
            )
        expected = content_digest(self._digest_payload())
        if self.outcome_digest == "":
            object.__setattr__(self, "outcome_digest", expected)
        else:
            require_hex64(self.outcome_digest, "CollectElementFailed.outcome_digest")
            if self.outcome_digest != expected:
                _reject_collect_contract(
                    "CollectElementFailed.outcome_digest does not match content",
                    ValueError,
                    site="CollectElementFailed.__post_init__",
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_ELEMENT_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "element outcome schema_version is not the frozen schema",
                ValueError,
                site="CollectElementFailed._validate_common",
            )
        _require_non_empty_string(self.element_id, "element_id")
        _require_non_negative_int(self.input_index, "input_index")
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        _require_legacy_observation_ref(self.legacy_observation_ref)
        _require_optional_collect_attempt_receipt(
            self.receipt,
            site="CollectElementFailed._validate_common",
        )

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
        return {**self._digest_payload(), "schema_version": self.schema_version, "outcome_digest": self.outcome_digest}


def _require_legacy_observation_ref(value: Any) -> None:
    if not isinstance(value, str) or _LEGACY_OBSERVATION_REF.fullmatch(value) is None:
        _reject_collect_contract(
            "legacy_observation_ref must match legacy:<64 lowercase hex>",
            ValueError,
            site="_require_legacy_observation_ref",
        )


CollectElementOutcome: TypeAlias = CollectElementSucceeded | CollectElementFailed


@dataclass(frozen=True, slots=True)
class OrderedCollectElementOutcomeSequence:
    """Input-index ordered outcome sequence; never reorders failures."""

    schema_version: Literal["mrw.acquisition.ordered-result-fold.input.v2"]
    parent_request_ref: CollectRequestRef
    outcomes: tuple[CollectElementOutcome, ...]
    sequence_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        indexes = tuple((outcome.input_index for outcome in self.outcomes))
        if tuple(sorted(indexes)) != indexes or len(set(indexes)) != len(indexes):
            _reject_collect_contract(
                "outcome sequence input indexes must be strictly increasing",
                ValueError,
                site="OrderedCollectElementOutcomeSequence.__post_init__",
            )
        expected = content_digest(
            {
                "schema": "mrw.acquisition.ordered-result-fold.input.v2",
                "parent_request_ref": self.parent_request_ref.to_plain(),
                "outcomes": [outcome.to_plain() for outcome in self.outcomes],
            }
        )
        if self.sequence_digest == "":
            object.__setattr__(self, "sequence_digest", expected)
        else:
            require_hex64(self.sequence_digest, "OrderedCollectElementOutcomeSequence.sequence_digest")
            if self.sequence_digest != expected:
                _reject_collect_contract(
                    "OrderedCollectElementOutcomeSequence.sequence_digest does not match content",
                    ValueError,
                    site="OrderedCollectElementOutcomeSequence.__post_init__",
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
    schema_version: Literal["mrw.acquisition.aggregate-outcome.v2"]
    kind: Literal["succeeded"] = "succeeded"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        self._validate_common()
        if self.aggregate_digest == "":
            object.__setattr__(self, "aggregate_digest", content_digest(self._digest_payload()))
        else:
            require_hex64(self.aggregate_digest, "CollectAggregateSucceeded.aggregate_digest")
            if self.aggregate_digest != content_digest(self._digest_payload()):
                _reject_collect_contract(
                    "CollectAggregateSucceeded.aggregate_digest does not match content",
                    ValueError,
                    site="CollectAggregateSucceeded.__post_init__",
                )

    def _validate_common(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "aggregate schema_version is not the frozen schema",
                ValueError,
                site="CollectAggregateSucceeded._validate_common",
            )
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": None if self.ordered_outcomes is None else self.ordered_outcomes.to_plain(),
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
    schema_version: Literal["mrw.acquisition.aggregate-outcome.v2"]
    kind: Literal["partial"] = "partial"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    errors: tuple[CollectElementError, ...] = ()
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "aggregate schema_version is not the frozen schema",
                ValueError,
                site="CollectAggregatePartial.__post_init__",
            )
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        if self.aggregate_digest == "":
            object.__setattr__(self, "aggregate_digest", content_digest(self._digest_payload()))
        else:
            require_hex64(self.aggregate_digest, "CollectAggregatePartial.aggregate_digest")
            if self.aggregate_digest != content_digest(self._digest_payload()):
                _reject_collect_contract(
                    "CollectAggregatePartial.aggregate_digest does not match content",
                    ValueError,
                    site="CollectAggregatePartial.__post_init__",
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": None if self.ordered_outcomes is None else self.ordered_outcomes.to_plain(),
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
    schema_version: Literal["mrw.acquisition.aggregate-outcome.v2"]
    kind: Literal["failed"] = "failed"
    ordered_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_counts: CollectCounts = field(default_factory=CollectCounts)
    errors: tuple[CollectElementError, ...] = ()
    receipts: tuple[CollectAttemptReceipt, ...] = ()
    links: tuple[str, ...] = ()
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "aggregate schema_version is not the frozen schema",
                ValueError,
                site="CollectAggregateFailed.__post_init__",
            )
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "receipts", tuple(self.receipts))
        object.__setattr__(self, "links", _require_string_tuple(self.links, "links"))
        if self.aggregate_digest == "":
            object.__setattr__(self, "aggregate_digest", content_digest(self._digest_payload()))
        else:
            require_hex64(self.aggregate_digest, "CollectAggregateFailed.aggregate_digest")
            if self.aggregate_digest != content_digest(self._digest_payload()):
                _reject_collect_contract(
                    "CollectAggregateFailed.aggregate_digest does not match content",
                    ValueError,
                    site="CollectAggregateFailed.__post_init__",
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "ordered_outcomes": None if self.ordered_outcomes is None else self.ordered_outcomes.to_plain(),
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
    schema_version: Literal["mrw.acquisition.aggregate-outcome.v2"]
    kind: Literal["contract_failure"] = "contract_failure"
    reason: str = ""
    unconsumed_outcomes: OrderedCollectElementOutcomeSequence | None = None
    aggregate_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF:
            _reject_collect_contract(
                "aggregate schema_version is not the frozen schema",
                ValueError,
                site="CollectFoldContractFailure.__post_init__",
            )
        _require_non_empty_string(self.reason, "CollectFoldContractFailure.reason")
        if self.aggregate_digest == "":
            object.__setattr__(self, "aggregate_digest", content_digest(self._digest_payload()))
        else:
            require_hex64(self.aggregate_digest, "CollectFoldContractFailure.aggregate_digest")
            if self.aggregate_digest != content_digest(self._digest_payload()):
                _reject_collect_contract(
                    "CollectFoldContractFailure.aggregate_digest does not match content",
                    ValueError,
                    site="CollectFoldContractFailure.__post_init__",
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
            "kind": self.kind,
            "reason": self.reason,
            "unconsumed_outcomes": None if self.unconsumed_outcomes is None else self.unconsumed_outcomes.to_plain(),
        }

    def to_plain(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "schema_version": self.schema_version,
            "aggregate_digest": self.aggregate_digest,
        }


CollectAggregateOutcome: TypeAlias = (
    CollectAggregateSucceeded | CollectAggregatePartial | CollectAggregateFailed | CollectFoldContractFailure
)


@dataclass(frozen=True, slots=True)
class CollectFoldResourceCeiling:
    """Bounded pure-CPU envelope for the ordered result fold."""

    schema_ref: Literal["mrw.acquisition.fold_ordered_results.resource-ceiling.v2"]
    max_outcomes: int
    max_payload_bytes: int
    max_receipts: int
    ceiling_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_ref != COLLECT_FOLD_RESOURCE_CEILING_SCHEMA_REF:
            _reject_collect_contract(
                "CollectFoldResourceCeiling.schema_ref is not the frozen schema",
                ValueError,
                site="CollectFoldResourceCeiling.__post_init__",
            )
        for name in ("max_outcomes", "max_payload_bytes", "max_receipts"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                _reject_collect_contract(
                    f"CollectFoldResourceCeiling.{name} must be positive",
                    ValueError,
                    site="CollectFoldResourceCeiling.__post_init__",
                )
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
            require_hex64(self.ceiling_digest, "CollectFoldResourceCeiling.ceiling_digest")
            if self.ceiling_digest != expected:
                _reject_collect_contract(
                    "CollectFoldResourceCeiling.ceiling_digest does not match content",
                    ValueError,
                    site="CollectFoldResourceCeiling.__post_init__",
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


def require_fold_ceiling(outcomes: OrderedCollectElementOutcomeSequence) -> str | None:
    """Return a rejection message when the bounded fold envelope is exceeded."""
    ceiling = COLLECT_FOLD_RESOURCE_CEILING
    if len(outcomes.outcomes) > ceiling.max_outcomes:
        return f"fold outcomes {len(outcomes.outcomes)} exceed ceiling {ceiling.max_outcomes}"
    payload_bytes = len(canonical_json(outcomes.to_plain()).encode("utf-8"))
    if payload_bytes > ceiling.max_payload_bytes:
        return f"fold payload bytes {payload_bytes} exceed ceiling {ceiling.max_payload_bytes}"
    receipts = sum((1 for outcome in outcomes.outcomes if outcome.receipt is not None))
    if receipts > ceiling.max_receipts:
        return f"fold receipts {receipts} exceed ceiling {ceiling.max_receipts}"
    return None


def fold_ordered_results(
    outcomes: OrderedCollectElementOutcomeSequence, *, aggregation_policy_ref: str, observation_profile_ref: str
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
            reason="fail-fast partial observation is decided by the ordered traversal; fold only summarizes already observed outcomes",
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
                continue
            prior_digest = job_id_to_receipt_digest.get(receipt.provider_job_id)
            if prior_digest is not None and prior_digest != receipt.receipt_digest:
                return CollectFoldContractFailure(
                    schema_version=COLLECT_AGGREGATE_OUTCOME_SCHEMA_REF,
                    reason=f"duplicate provider_job_id with divergent receipt digest {receipt.provider_job_id!r}",
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

    schema_version: Literal["mrw.acquisition.batch.execute_element.observation.v2"]
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
            _reject_collect_contract(
                "CollectTraversalObservation.schema_version is not the frozen schema",
                ValueError,
                site="CollectTraversalObservation.__post_init__",
            )
        _require_non_empty_string(self.observation_profile, "observation_profile")
        object.__setattr__(self, "ordered_outcomes", tuple(self.ordered_outcomes))
        object.__setattr__(
            self, "requested_parallelism", _require_positive_int(self.requested_parallelism, "requested_parallelism")
        )
        object.__setattr__(
            self, "effective_parallelism", _require_positive_int(self.effective_parallelism, "effective_parallelism")
        )
        expected = content_digest(self._digest_payload())
        if self.observation_digest == "":
            object.__setattr__(self, "observation_digest", expected)
        else:
            require_hex64(self.observation_digest, "CollectTraversalObservation.observation_digest")
            if self.observation_digest != expected:
                _reject_collect_contract(
                    "CollectTraversalObservation.observation_digest does not match content",
                    ValueError,
                    site="CollectTraversalObservation.__post_init__",
                )

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "schema": COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
            "observation_profile": self.observation_profile,
            "request_ref": self.request_ref.to_plain(),
            "traversal_policy": self.traversal_policy,
            "failure_policy": self.failure_policy,
            "ordered_outcomes": [outcome.to_plain() for outcome in self.ordered_outcomes],
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
    schema_version: Literal["mrw.acquisition.batch.execute_element.result.v2"]
    kind: Literal["completed"] = "completed"
    observation: CollectTraversalObservation | None = None

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "observation": None if self.observation is None else self.observation.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class OrderedTraversalAborted:
    schema_version: Literal["mrw.acquisition.batch.execute_element.result.v2"]
    kind: Literal["aborted"] = "aborted"
    partial_outcomes: tuple[CollectElementOutcome, ...] = ()
    cause: CollectElementError | None = None
    cancellation_receipt: CollectCancellationReceipt | None = None
    cancellation_observed: bool = False
    request_ref: CollectRequestRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "partial_outcomes", tuple(self.partial_outcomes))
        if not isinstance(self.cause, CollectElementError):
            _reject_collect_contract(
                "OrderedTraversalAborted requires a typed cause",
                TypeError,
                site="OrderedTraversalAborted.__post_init__",
            )
        if not isinstance(self.cancellation_receipt, CollectCancellationReceipt):
            _reject_collect_contract(
                "OrderedTraversalAborted requires a typed cancellation receipt",
                TypeError,
                site="OrderedTraversalAborted.__post_init__",
            )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "partial_outcomes": [outcome.to_plain() for outcome in self.partial_outcomes],
            "cause": self.cause.to_plain() if self.cause is not None else None,
            "cancellation_receipt": None if self.cancellation_receipt is None else self.cancellation_receipt.to_plain(),
            "cancellation_observed": self.cancellation_observed,
            "request_ref": None if self.request_ref is None else self.request_ref.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class CollectTraversalBypassed:
    schema_version: Literal["mrw.acquisition.batch.execute_element.result.v2"]
    request_ref: CollectRequestRef
    kind: Literal["bypassed"] = "bypassed"

    def to_plain(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "kind": self.kind, "request_ref": self.request_ref.to_plain()}


@dataclass(frozen=True, slots=True)
class CollectTraversalSingleton:
    schema_version: Literal["mrw.acquisition.batch.execute_element.result.v2"]
    observation: CollectTraversalObservation
    kind: Literal["singleton"] = "singleton"

    def to_plain(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "kind": self.kind, "observation": self.observation.to_plain()}


CollectTraversalResult: TypeAlias = (
    OrderedTraversalCompleted | OrderedTraversalAborted | CollectTraversalBypassed | CollectTraversalSingleton
)
