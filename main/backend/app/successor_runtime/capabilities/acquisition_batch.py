"""Frozen typed contracts and deterministic rules for acquisition batching.

This module owns the canonical vocabulary for the two acquisition operations:
authenticated request refs, attempt and cancellation receipts, and the
pure deterministic batching rules shared by collect consumers.

The module is capability-boundary only: it never imports service packages and
never performs network, database, provider or credential work.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Literal,
    NoReturn,
)
from typing import TypeGuard

from functorial_kit import Failure, define_failure_family

from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "ACQUISITION_BATCH_FAILURES",
    "AUTHENTICATED_COLLECT_SCOPE_TYPE",
    "COLLECT_ATTEMPT_RECEIPT_TYPE",
    "ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER",
    "COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF",
    "COLLECT_REQUEST_TYPE",
    "CollectAttemptReceipt",
    "CollectCancellationReceipt",
    "CollectRequestRef",
    "build_collect_request_ref",
    "collect_contract_failure",
    "per_batch_limit_for",
    "receipt_implies_completed",
    "resolve_auto_batch_fail_fast",
    "resolve_auto_batch_parallelism",
    "raise_collect_contract_failure",
    "raise_collect_programmer_defect",
    "should_auto_batch",
    "split_query_terms",
]
ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER = "acquisition.batch.execute_element.v2"
ACQUISITION_BATCH_FAILURES = define_failure_family(
    "acquisition.batch.failure",
    ("INVALID_INPUT",),
)
COLLECT_REQUEST_SCHEMA_REF = "mrw.acquisition.request-ref.v2"
COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF = "mrw.acquisition.attempt-receipt.v2"
COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF = "mrw.acquisition.cancellation-receipt.v2"
COLLECT_REQUEST_TYPE = ObjectType("CollectRequest.v1")
AUTHENTICATED_COLLECT_SCOPE_TYPE = ObjectType("AuthenticatedCollectScope.v1")
COLLECT_ATTEMPT_RECEIPT_TYPE = ObjectType("CollectAttemptReceipt.v1")
COLLECT_AUTO_BATCH_CHANNELS = frozenset({"search.market", "search.policy"})
_OBSERVED_AT = re.compile("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z$")


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


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject_collect_contract(f"{field_name} is required", ValueError, site="_require_non_empty_string")
    return value.strip()


def _require_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _reject_collect_contract(
            f"{field_name} must be a non-negative int", ValueError, site="_require_non_negative_int"
        )
    return value


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
    "kit:non-authoritative derived_as=view fact_source=normalized_collect_request_inputs witness=test:test_policy_materialization_is_bounded_ordered_and_replayable",
]:
    return CollectRequestRef(
        schema_version=COLLECT_REQUEST_SCHEMA_REF,
        request_id=request_id,
        project_key=project_key,
        channel=channel,
        request_digest="",
    )


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


@dataclass(frozen=True, slots=True)
class CollectCancellationReceipt:
    """Typed cancellation receipt emitted by fail-fast batch aborts."""

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
