from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections.abc import Callable, Mapping
import json
from typing import Literal, NoReturn, Protocol, TypeAlias, TypedDict

from functorial_kit.core.failure import Failure

from mrw_functorial_kit.core.provider_port_failures import (
    CollectRuntimeFailureCode,
    CrawlerRuntimeFailureCode,
    collect_runtime_failures,
)
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities.checksum import content_digest

from .delivery import DeliveryObservation

FLOW_COLLECT = "collect"
FLOW_SOURCE_COLLECT = "source_collect"
ALLOWED_COLLECT_FLOWS = {FLOW_COLLECT, FLOW_SOURCE_COLLECT}
COLLECT_BATCH_FOLD_SCHEMA_REF = "mrw.collect.batch-fold.v1"

CollectJsonValue: TypeAlias = (
    None | bool | int | float | str
    | list["CollectJsonValue"]
    | dict[str, "CollectJsonValue"]
)
CollectJsonObject: TypeAlias = dict[str, CollectJsonValue]
SourceLibraryCompatResponse: TypeAlias = dict[str, CollectJsonValue]

CollectStatus: TypeAlias = Literal[
    "completed",
    "accepted",
    "partial",
    "failed",
    "cancelled",
    "unknown",
]
CollectFailureFamily: TypeAlias = Literal["crawler.runtime.failure"]


def _empty_string_list() -> list[str]:
    return []


def _empty_collect_json_object() -> CollectJsonObject:
    return {}


def _empty_collect_failure_list() -> list[CollectFailure]:
    return []


@dataclass(slots=True)
class CollectRequest:
    contract_version: str = "collect.request.v1"
    flow: str = FLOW_COLLECT
    channel: str = ""
    project_key: str | None = None
    query_terms: list[str] = field(default_factory=_empty_string_list)
    urls: list[str] = field(default_factory=_empty_string_list)
    limit: int | None = None
    provider: str | None = None
    language: str | None = None
    scope: str | None = None
    item_key: str | None = None
    resource_id: str | None = None
    platforms: list[str] | None = None
    options: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    source_context: CollectJsonObject = field(default_factory=_empty_collect_json_object)


class CollectFailure(TypedDict, total=False):
    code: (
        CollectRuntimeFailureCode
        | CrawlerRuntimeFailureCode
        | Literal[
            "collect_effect_not_registered",
            "element_rejected",
            "runner_unavailable",
            "successor_effect_gateway_unavailable",
            "url_pool_execution_failed",
        ]
    )
    family: CollectFailureFamily
    message: str
    context: Mapping[str, CollectJsonValue]
    query_terms: list[str] | tuple[str, ...]
    exception_type: str | None
    error_digest: str


@dataclass(slots=True)
class CollectResult:
    flow: str = FLOW_COLLECT
    channel: str = ""
    status: CollectStatus = "completed"
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[CollectFailure] = field(default_factory=_empty_collect_failure_list)
    items: list[CollectJsonObject] | None = None
    meta: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    display_meta: CollectJsonObject = field(default_factory=_empty_collect_json_object)
    provider_job_id: str | None = None
    provider_type: str | None = None
    provider_status: str | None = None
    attempt_count: int | None = None


@dataclass(frozen=True, slots=True)
class CollectBatchCounts:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0

    def to_plain(self) -> CollectJsonObject:
        return {"inserted": self.inserted, "updated": self.updated, "skipped": self.skipped}


def collect_failure_to_plain(error: CollectFailure) -> CollectJsonObject:
    value: CollectJsonObject = {}
    for field_name in ("code", "message", "family", "exception_type", "error_digest"):
        if field_name in error:
            value[field_name] = error.get(field_name)
    if (context := error.get("context")) is not None:
        value["context"] = dict(context)
    if (query_terms := error.get("query_terms")) is not None:
        value["query_terms"] = list(query_terms)
    return value


@dataclass(frozen=True, slots=True)
class CollectBatchRow:
    element_id: str
    input_index: int
    query_terms: tuple[str, ...]
    observation: DeliveryObservation | None
    counts: CollectBatchCounts | None = None
    links: tuple[str, ...] = ()
    errors: tuple[CollectFailure, ...] = ()
    receipt: acquisition.CollectAttemptReceipt | None = None
    result_status: Literal["succeeded", "failed"] = "failed"
    execution_state: Literal["attempted", "attempted_unknown", "not_attempted"] = "not_attempted"

    def to_plain(self) -> CollectJsonObject:
        value: CollectJsonObject = {
            "element_id": self.element_id,
            "input_index": self.input_index,
            "query_terms": list(self.query_terms),
            "observation": None if self.observation is None else asdict(self.observation),
            "result_status": self.result_status,
            "execution_state": self.execution_state,
        }
        if self.counts is not None:
            value["counts"] = self.counts.to_plain()
        value["links"] = list(self.links)
        value["errors"] = [collect_failure_to_plain(error) for error in self.errors]
        if self.receipt is not None:
            value["receipt"] = self.receipt.to_plain()
        return value


@dataclass(frozen=True, slots=True)
class CollectBatchFold:
    rows: tuple[CollectBatchRow, ...]
    counts: CollectBatchCounts
    links: tuple[str, ...]
    errors: tuple[CollectFailure, ...]
    receipts: tuple[acquisition.CollectAttemptReceipt, ...]
    attempted_count: int
    failed_count: int
    receipt_conflict: bool
    request_ref: acquisition.CollectRequestRef | None
    cancellation: acquisition.CollectCancellationReceipt | None
    sequence_digest: str


def fold_collect_batch_rows(
    rows: tuple[CollectBatchRow, ...],
    *,
    request_ref: acquisition.CollectRequestRef | None = None,
    cancellation: acquisition.CollectCancellationReceipt | None = None,
) -> CollectBatchFold:
    ordered = tuple(rows)
    attempted = tuple(row for row in ordered if row.execution_state != "not_attempted")
    counts = CollectBatchCounts(*(
        sum(getattr(row.counts, name) for row in attempted if row.counts is not None)
        for name in ("inserted", "updated", "skipped")
    ))
    links = tuple(dict.fromkeys(link for row in attempted for link in row.links if link))
    errors = tuple(error for row in attempted for error in row.errors)
    receipts: list[acquisition.CollectAttemptReceipt] = []
    receipt_digests: set[str] = set()
    jobs: dict[str, str] = {}
    conflict = False
    for row in attempted:
        receipt = row.receipt
        if receipt is None:
            continue
        previous = jobs.get(receipt.provider_job_id)
        conflict = conflict or (previous is not None and previous != receipt.receipt_digest)
        jobs[receipt.provider_job_id] = receipt.receipt_digest
        if receipt.receipt_digest not in receipt_digests:
            receipt_digests.add(receipt.receipt_digest)
            receipts.append(receipt)
    return CollectBatchFold(
        rows=ordered,
        counts=counts,
        links=links,
        errors=errors,
        receipts=tuple(receipts),
        attempted_count=len(attempted),
        failed_count=sum(row.result_status == "failed" for row in attempted),
        receipt_conflict=conflict,
        request_ref=request_ref,
        cancellation=cancellation,
        sequence_digest=content_digest({
            "schema": COLLECT_BATCH_FOLD_SCHEMA_REF,
            "request_ref": None if request_ref is None else request_ref.to_plain(),
            "rows": [row.to_plain() for row in ordered],
            "cancellation": None if cancellation is None else cancellation.to_plain(),
        }),
    )


class CollectAdapter(Protocol):
    def run(self, request: CollectRequest) -> CollectResult:
        ...


CollectRunner: TypeAlias = Callable[[CollectRequest], CollectResult]
CollectEffectGateway: TypeAlias = Callable[[CollectRequest], CollectResult]


class SourceLibraryCompatProjector(Protocol):
    def __call__(self, result: CollectResult) -> SourceLibraryCompatResponse:
        ...


def _compat_projector_failure(message: str, *, site: str) -> Failure:
    return collect_runtime_failures.fail(
        "compat_projector_contract_invalid",
        message,
        {"operation": "collect.runtime.compat_projector", "site": site},
    )


def _raise_compat_projector_failure(
    failure: Failure,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    if cause is not None:
        # kit:boundary owner=collect_runtime.contracts.compat_projector class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_compat_response_rejects_non_json_and_non_object_payloads
        raise TypeError(failure.message) from cause
    # kit:boundary owner=collect_runtime.contracts.compat_projector class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_compat_response_rejects_non_json_and_non_object_payloads
    raise TypeError(failure.message)


def source_library_compat_response(value: object) -> SourceLibraryCompatResponse:
    """Validate the adapter-owned projection at its single composition seam."""

    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        _raise_compat_projector_failure(
            _compat_projector_failure(
                "source-library compatibility response must be JSON",
                site="source_library_compat_response.encode",
            ),
            cause=exc,
        )
    decoded: CollectJsonValue = json.loads(encoded)
    if not isinstance(decoded, dict):
        _raise_compat_projector_failure(
            _compat_projector_failure(
                "source-library compatibility response must be a JSON object",
                site="source_library_compat_response.decode",
            )
        )
    return decoded
