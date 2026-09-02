"""Pure, declared-loss terminal/compat projection contracts for C2.4.

The projector is a read-only derivation over an admitted runtime-journal
closure.  It emits the terminal output, a lossy compatibility projection and
a summary projection; none of them can issue commands, admit documents or act
as completion authority.  Status/stats/reason are derived, mode is observed
for successor sources, and no raw payload bytes are copied into the outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from app.successor_runtime.capabilities import source_library_c2_shared as c2_shared
from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)

__all__ = [
    "C2_4_FAILURE_CODES",
    "DECLARED_LOSS_PROFILE_REF",
    "SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA",
    "SOURCE_LIBRARY_C2_4_PROJECTOR_ID",
    "SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION",
    "SOURCE_LIBRARY_C2_4_SUMMARY_SCHEMA",
    "SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA",
    "SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE",
    "ProjectedTerminal",
    "ProjectedWithLoss",
    "ProjectionRejected",
    "ProjectionResult",
    "ProjectionStale",
    "SourceCollectionProjectionSource",
    "SourceLibraryCompatProjection",
    "SourceLibrarySummaryProjection",
    "SourceLibraryTerminalOutputV2",
    "TerminalErrorProjection",
    "TerminalItemProjection",
    "TerminalMetaProjection",
    "TerminalRequestProjection",
    "TerminalResultsProjection",
    "TerminalStatsProjection",
    "build_source_library_c2_4_profiles",
    "project_source_collection",
]


SOURCE_LIBRARY_C2_4_PROJECTOR_ID = "successor.source_library.c2_4.terminal_compat.v1"
SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION = "1.0.0"
SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA = "source_library.terminal_output.v2"
SOURCE_LIBRARY_C2_4_COMPAT_SCHEMA = "source_library.compat_projection.v1"
SOURCE_LIBRARY_C2_4_SUMMARY_SCHEMA = "source_library.summary_projection.v1"
SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA = (
    "mrw.successor.source-library.c2-4.projection-source.v1"
)
SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE = (
    "mrw.successor.source-library.c2-4.observation.v1"
)
DECLARED_LOSS_PROFILE_REF = "source_library.c2_4.compat.loss.v1"

ALLOWED_SOURCE_MODES = frozenset(
    {"protocol_search", "provider_harvest", "site_search", "url_execution"}
)

C2_4_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "MALFORMED_OBSERVATION",
        "UNSUPPORTED_VERSION",
        "PROJECTOR_ERROR",
        "SOURCE_STALE",
        "OFFSET_STALE",
    }
)


@dataclass(frozen=True, slots=True)
class SourceCollectionProjectionSource:
    """One admitted runtime-journal closure for terminal projection."""

    source_kind: Literal["RUNTIME_JOURNAL"]
    source_ref: str
    run_id: str
    run_incarnation: str
    source_revision: int
    source_incarnation: str
    source_digest: str
    project_key: str
    project_scope_digest: str
    source_mode: str
    collection_outcome: c2_shared.SourceCollectionOutcome
    record_refs: tuple[c2_shared.CapturedSourceRecordRef, ...]
    ordered_failures: tuple[c2_shared.OrderedFailure, ...]
    provider_handoff: c2_shared.ProviderHandoff | None
    observed_at: str
    schema_version: str = SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA

    def __post_init__(self) -> None:
        if self.source_kind != "RUNTIME_JOURNAL":
            raise ValueError(
                "SourceCollectionProjectionSource.source_kind must be RUNTIME_JOURNAL"
            )
        if self.schema_version != SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA:
            raise ValueError(
                "SourceCollectionProjectionSource.schema_version is not frozen"
            )
        if not self.run_id.strip() or not self.run_incarnation.strip():
            raise ValueError(
                "SourceCollectionProjectionSource run identity is required"
            )
        if self.source_ref != f"runtime-run:{self.run_id}":
            raise ValueError(
                "SourceCollectionProjectionSource.source_ref does not bind run_id"
            )
        if self.source_mode not in ALLOWED_SOURCE_MODES:
            raise ValueError(f"unsupported observed source_mode {self.source_mode!r}")
        require_hex64(
            self.project_scope_digest,
            "SourceCollectionProjectionSource.project_scope_digest",
        )
        expected = _source_closure_digest(self)
        if self.source_digest == "":
            object.__setattr__(self, "source_digest", expected)
        else:
            require_hex64(
                self.source_digest,
                "SourceCollectionProjectionSource.source_digest",
            )
            if self.source_digest != expected:
                raise ValueError(
                    "SourceCollectionProjectionSource.source_digest does not match closure"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "run_id": self.run_id,
            "run_incarnation": self.run_incarnation,
            "source_revision": self.source_revision,
            "source_incarnation": self.source_incarnation,
            "source_digest": self.source_digest,
            "project_key": self.project_key,
            "project_scope_digest": self.project_scope_digest,
            "source_mode": self.source_mode,
            "collection_outcome": _outcome_to_plain(self.collection_outcome),
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "ordered_failures": [
                failure.to_plain() for failure in self.ordered_failures
            ],
            "provider_handoff": (
                self.provider_handoff.to_plain()
                if self.provider_handoff is not None
                else None
            ),
            "observed_at": self.observed_at,
        }


def _outcome_to_plain(outcome: c2_shared.SourceCollectionOutcome) -> dict[str, Any]:
    return outcome.to_plain()


def _source_closure_digest(source: SourceCollectionProjectionSource) -> str:
    return content_digest(
        {
            "schema": SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA,
            "source_ref": source.source_ref,
            "run_id": source.run_id,
            "run_incarnation": source.run_incarnation,
            "source_revision": source.source_revision,
            "source_incarnation": source.source_incarnation,
            "project_key": source.project_key,
            "project_scope_digest": source.project_scope_digest,
            "source_mode": source.source_mode,
            "collection_outcome_digest": getattr(
                source.collection_outcome, "outcome_digest", ""
            ),
            "record_refs": [ref.to_plain() for ref in source.record_refs],
            "ordered_failures": [
                failure.to_plain() for failure in source.ordered_failures
            ],
            "provider_handoff": (
                source.provider_handoff.to_plain()
                if source.provider_handoff is not None
                else None
            ),
            "observed_at": source.observed_at,
        }
    )


@dataclass(frozen=True, slots=True)
class TerminalItemProjection:
    item_key: str
    item_type: str | None
    managed_by: str | None

    def to_plain(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "item_type": self.item_type,
            "managed_by": self.managed_by,
        }


@dataclass(frozen=True, slots=True)
class TerminalRequestProjection:
    project_key: str | None
    query_terms: tuple[str, ...]
    time_window: dict[str, Any]
    paging: dict[str, Any]
    limits: dict[str, Any]

    def to_plain(self) -> dict[str, Any]:
        return {
            "project_key": self.project_key,
            "query_terms": list(self.query_terms),
            "time_window": dict(self.time_window),
            "paging": dict(self.paging),
            "limits": dict(self.limits),
        }


@dataclass(frozen=True, slots=True)
class TerminalErrorProjection:
    source: str
    message: str
    url: str | None = None

    def to_plain(self) -> dict[str, Any]:
        return {"source": self.source, "message": self.message, "url": self.url}


@dataclass(frozen=True, slots=True)
class TerminalStatsProjection:
    records: int
    errors: int
    partial_failures: int
    accepted_jobs: int

    def to_plain(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "errors": self.errors,
            "partial_failures": self.partial_failures,
            "accepted_jobs": self.accepted_jobs,
        }


@dataclass(frozen=True, slots=True)
class TerminalResultsProjection:
    record_refs: tuple[c2_shared.CapturedSourceRecordRef, ...]
    stats: TerminalStatsProjection

    def to_plain(self) -> dict[str, Any]:
        return {
            "record_refs": [ref.to_plain() for ref in self.record_refs],
            "stats": self.stats.to_plain(),
        }


@dataclass(frozen=True, slots=True)
class TerminalMetaProjection:
    reason_code: str
    retryable: bool
    provider: str | None
    provider_job_id: str | None
    warnings: tuple[str, ...]
    raw_snapshot_ref: str | None
    legacy_result_ref: str | None
    projector_version: str

    def to_plain(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "retryable": self.retryable,
            "provider": self.provider,
            "provider_job_id": self.provider_job_id,
            "warnings": list(self.warnings),
            "raw_snapshot_ref": self.raw_snapshot_ref,
            "legacy_result_ref": self.legacy_result_ref,
            "projector_version": self.projector_version,
        }


@dataclass(frozen=True, slots=True)
class SourceLibraryTerminalOutputV2:
    contract_version: Literal["source_library.terminal_output.v2"]
    status: Literal["ok", "partial", "error"]
    source_mode: str
    item: TerminalItemProjection
    request: TerminalRequestProjection
    results: TerminalResultsProjection
    errors: tuple[TerminalErrorProjection, ...]
    meta: TerminalMetaProjection
    source_digest: str
    projector_version: str = SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION
    projection_digest: str = ""

    def __post_init__(self) -> None:
        require_hex64(self.source_digest, "SourceLibraryTerminalOutputV2.source_digest")
        expected = content_digest(
            {
                "contract_version": self.contract_version,
                "status": self.status,
                "source_mode": self.source_mode,
                "item": self.item.to_plain(),
                "request": self.request.to_plain(),
                "results": self.results.to_plain(),
                "errors": [error.to_plain() for error in self.errors],
                "meta": self.meta.to_plain(),
                "source_digest": self.source_digest,
                "projector_version": self.projector_version,
            }
        )
        if self.projection_digest == "":
            object.__setattr__(self, "projection_digest", expected)
        else:
            require_hex64(
                self.projection_digest,
                "SourceLibraryTerminalOutputV2.projection_digest",
            )
            if self.projection_digest != expected:
                raise ValueError(
                    "SourceLibraryTerminalOutputV2.projection_digest does not match"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "source_mode": self.source_mode,
            "item": self.item.to_plain(),
            "request": self.request.to_plain(),
            "results": self.results.to_plain(),
            "errors": [error.to_plain() for error in self.errors],
            "meta": self.meta.to_plain(),
            "source_digest": self.source_digest,
            "projector_version": self.projector_version,
            "projection_digest": self.projection_digest,
        }


@dataclass(frozen=True, slots=True)
class SourceLibraryCompatProjection:
    contract_version: Literal["source_library.compat_projection.v1"]
    status: Literal["declared_loss"] = "declared_loss"
    loss_profile_ref: str = DECLARED_LOSS_PROFILE_REF
    legacy_result_ref: str | None = None
    raw_snapshot_ref: str | None = None
    inferred_fields: tuple[str, ...] = ()
    compat_digest: str = ""

    def __post_init__(self) -> None:
        expected = content_digest(
            {
                "contract_version": self.contract_version,
                "status": self.status,
                "loss_profile_ref": self.loss_profile_ref,
                "legacy_result_ref": self.legacy_result_ref,
                "raw_snapshot_ref": self.raw_snapshot_ref,
                "inferred_fields": list(self.inferred_fields),
            }
        )
        if self.compat_digest == "":
            object.__setattr__(self, "compat_digest", expected)
        else:
            require_hex64(
                self.compat_digest, "SourceLibraryCompatProjection.compat_digest"
            )
            if self.compat_digest != expected:
                raise ValueError(
                    "SourceLibraryCompatProjection.compat_digest does not match"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "loss_profile_ref": self.loss_profile_ref,
            "legacy_result_ref": self.legacy_result_ref,
            "raw_snapshot_ref": self.raw_snapshot_ref,
            "inferred_fields": list(self.inferred_fields),
            "compat_digest": self.compat_digest,
        }


@dataclass(frozen=True, slots=True)
class SourceLibrarySummaryProjection:
    contract_version: Literal["source_library.summary_projection.v1"]
    status: str
    source_mode: str
    records_count: int
    errors_count: int
    partial_failures: int
    is_authority: bool = False
    projection_digest: str = ""

    def __post_init__(self) -> None:
        expected = content_digest(
            {
                "contract_version": self.contract_version,
                "status": self.status,
                "source_mode": self.source_mode,
                "records_count": self.records_count,
                "errors_count": self.errors_count,
                "partial_failures": self.partial_failures,
                "is_authority": self.is_authority,
            }
        )
        if self.projection_digest == "":
            object.__setattr__(self, "projection_digest", expected)
        else:
            require_hex64(
                self.projection_digest,
                "SourceLibrarySummaryProjection.projection_digest",
            )
            if self.projection_digest != expected:
                raise ValueError(
                    "SourceLibrarySummaryProjection.projection_digest does not match"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "source_mode": self.source_mode,
            "records_count": self.records_count,
            "errors_count": self.errors_count,
            "partial_failures": self.partial_failures,
            "is_authority": self.is_authority,
            "projection_digest": self.projection_digest,
        }


@dataclass(frozen=True, slots=True)
class ProjectedTerminal:
    terminal: SourceLibraryTerminalOutputV2
    compat: SourceLibraryCompatProjection
    summary: SourceLibrarySummaryProjection


@dataclass(frozen=True, slots=True)
class ProjectedWithLoss:
    terminal: SourceLibraryTerminalOutputV2
    compat: SourceLibraryCompatProjection
    summary: SourceLibrarySummaryProjection
    loss_profile_ref: str = DECLARED_LOSS_PROFILE_REF


@dataclass(frozen=True, slots=True)
class ProjectionRejected:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ProjectionStale:
    expected_digest: str
    observed_digest: str
    message: str = "projection source revision/digest is stale"


ProjectionResult: TypeAlias = (
    ProjectedTerminal | ProjectedWithLoss | ProjectionRejected | ProjectionStale
)


def _derive_status(outcome: c2_shared.SourceCollectionOutcome) -> tuple[str, str]:
    kind = outcome.kind
    if kind == "completed":
        return "ok", "ok"
    if kind == "partially_completed":
        return "partial", "partial_records"
    if kind == "provider_accepted":
        return "partial", "accepted"
    if kind == "cancelled":
        return "error", "cancelled"
    if kind == "outcome_unknown":
        return "error", "outcome_unknown"
    return "error", "fetch_errors"


def project_source_collection(
    source: SourceCollectionProjectionSource,
    *,
    projector_version: str = SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
) -> ProjectionResult:
    """Project one admitted journal closure into terminal/compat/summary."""

    if source.schema_version != SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA:
        return ProjectionRejected(
            code="UNSUPPORTED_VERSION",
            message=f"unsupported projection source schema {source.schema_version!r}",
        )
    if source.source_mode not in ALLOWED_SOURCE_MODES:
        return ProjectionRejected(
            code="MALFORMED_OBSERVATION",
            message=f"source mode {source.source_mode!r} is not an observed mode",
        )
    try:
        outcome = source.collection_outcome
        terminal = getattr(outcome, "terminal", None)
        status, reason_code = _derive_status(outcome)
        observed_records = len(source.record_refs)
        records_count = observed_records
        if terminal is not None and hasattr(terminal, "records_count"):
            records_count = max(observed_records, int(terminal.records_count))
        errors = tuple(
            TerminalErrorProjection(
                source=failure.source,
                message=failure.message,
                url=None,
            )
            for failure in source.ordered_failures
        )
        errors_count = len(errors)
        partial_failures = sum(
            1 for failure in source.ordered_failures if failure.order_index >= 0
        )
        accepted_jobs = 1 if getattr(outcome, "kind", "") == "provider_accepted" else 0
        provider = (
            source.provider_handoff.provider
            if source.provider_handoff is not None
            else None
        )
        provider_job_id = (
            source.provider_handoff.provider_job_id
            if source.provider_handoff is not None
            else None
        )
        item = TerminalItemProjection(
            item_key=source.run_id,
            item_type=None,
            managed_by=None,
        )
        request = TerminalRequestProjection(
            project_key=source.project_key,
            query_terms=(),
            time_window={},
            paging={},
            limits={},
        )
        stats = TerminalStatsProjection(
            records=records_count,
            errors=errors_count,
            partial_failures=partial_failures,
            accepted_jobs=accepted_jobs,
        )
        meta = TerminalMetaProjection(
            reason_code=reason_code,
            retryable=False,
            provider=provider,
            provider_job_id=provider_job_id,
            warnings=(),
            raw_snapshot_ref=None,
            legacy_result_ref=None,
            projector_version=projector_version,
        )
        terminal_output = SourceLibraryTerminalOutputV2(
            contract_version="source_library.terminal_output.v2",
            status=status,  # type: ignore[arg-type]
            source_mode=source.source_mode,
            item=item,
            request=request,
            results=TerminalResultsProjection(
                record_refs=source.record_refs,
                stats=stats,
            ),
            errors=errors,
            meta=meta,
            source_digest=source.source_digest,
            projector_version=projector_version,
        )
        compat = SourceLibraryCompatProjection(
            contract_version="source_library.compat_projection.v1",
            status="declared_loss",
            loss_profile_ref=DECLARED_LOSS_PROFILE_REF,
            legacy_result_ref=None,
            raw_snapshot_ref=None,
            inferred_fields=(
                "legacy_result",
                "raw_snapshot",
                "status",
                "stats",
                "reason_code",
            ),
        )
        summary = SourceLibrarySummaryProjection(
            contract_version="source_library.summary_projection.v1",
            status=status,
            source_mode=source.source_mode,
            records_count=records_count,
            errors_count=errors_count,
            partial_failures=partial_failures,
            is_authority=False,
        )
        return ProjectedWithLoss(
            terminal=terminal_output,
            compat=compat,
            summary=summary,
            loss_profile_ref=DECLARED_LOSS_PROFILE_REF,
        )
    except (TypeError, ValueError, AttributeError) as exc:
        return ProjectionRejected(
            code="PROJECTOR_ERROR",
            message=f"terminal projection failed: {exc}",
        )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "mrw.successor.source-library.c2-4.semantic.v1",
        "semantic_profile_version": "1.0.0",
        "reads": (SOURCE_COLLECTION_PROJECTION_SOURCE_SCHEMA,),
        "creates": (
            SOURCE_LIBRARY_C2_4_TERMINAL_SCHEMA,
            SOURCE_LIBRARY_C2_4_COMPAT_SCHEMA,
            SOURCE_LIBRARY_C2_4_SUMMARY_SCHEMA,
        ),
        "creates_relations": (),
        "declared_loss": (DECLARED_LOSS_PROFILE_REF,),
        "observation_profile_ref": SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "mrw.successor.source-library.c2-4.effect.v1",
        "effect_profile_version": "1.0.0",
        "execution_class": "PROJECTION",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "source_digest",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "mrw.successor.source-library.c2-4.resource.v1",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu",),
        "concurrency_key": "project",
        "budget_units": "projection",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": "mrw.functorial-successor.budget.c2-4.v1",
        "deadline_policy_ref": "mrw.functorial-successor.deadline.c2-4.v1",
        "node_profile_requirements": ("bounded_record_refs", "no_raw_bytes"),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "mrw.successor.source-library.c2-4.failure.v1",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(C2_4_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "rebuild_from_source",
        "failure_union_ref": "mrw.functorial-successor.failures.c2-4.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "mrw.successor.source-library.c2-4.authority.v1",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": "source_library.c2_4.v1",
        "revalidation_points": ("read_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
        "interpreter_profile_version": SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
        "supported_contract_kinds": ("source_library.project_terminal_compat.v1",),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "projector": SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
                "version": SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
                "declared_loss": DECLARED_LOSS_PROFILE_REF,
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": "mrw.successor.source-library.c2-4.resource.v1",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "none",
        "idempotency_profile_ref": "source_digest",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "observed_source_mode",
            "derived_status",
            "derived_stats",
            "derived_reason_code",
            "record_refs",
            "ordered_failures",
            "provider_handoff",
            "declared_loss",
            "projection_digest",
        ),
        "compatible_with_legacy": False,
        "observation_schema_ref": SOURCE_LIBRARY_TERMINAL_OBSERVATION_PROFILE,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


def build_source_library_c2_4_profiles() -> dict[str, object]:
    return {
        "semantic": _semantic_profile(),
        "effect": _effect_profile(),
        "resource": _resource_profile(),
        "failure": _failure_profile(),
        "authority": _authority_profile(),
        "interpreter": _interpreter_profile(),
        "observation": _observation_profile(),
    }
