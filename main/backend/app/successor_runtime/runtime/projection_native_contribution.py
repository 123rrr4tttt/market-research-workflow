"""Authored C9 native-contribution rule over existing facade and offset authority.

The three C9 facts stay separate: facade transport/validation, the frontend
observation projection, and the projector offset anchor/CAS identity.  The
existing modules remain the authorities; this rule owns no transport, database,
scheduler, cache or second projector consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import (
    ContributionObject,
    contribution_failures,
)
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.runtime import facade_contracts as facade
from app.successor_runtime.runtime.ports import ProjectScopeRef
from mrw_functorial_kit.core.projection_semantics import (
    projection_projection_loss_kinds,
    projection_projection_source_schemas,
    projection_projector_outcomes,
    projection_runtime_event_kinds,
    projection_search_segment_kinds,
    projection_session_statuses,
    projection_processing_failures,
)
from mrw_functorial_kit.core.w06_semantics import (
    projection_evidence_surface_failures,
)

from .ports import projection_offsets as offsets

__all__ = [
    "PROJECTION_READ_MODEL_SLOT_ID",
    "PROJECTION_COMMAND_QUERY_SLOT_ID",
    "PROJECTION_CLIENT_CONTRACT_SLOT_ID",
    "PROJECTION_NATIVE_CONTRIBUTION_RULE",
    "PROJECTION_NATIVE_RULE_ID",
    "PROJECTION_NATIVE_VERIFICATION_INPUTS",
    "PROJECTION_PROCESSING_FAILURES",
    "PROJECTION_FAMILY_ID",
    "PROJECTION_COMMAND_QUERY_CELL_ID",
    "PROJECTION_CLIENT_CONTRACT_CELL_ID",
    "PROJECTION_READ_MODEL_CELL_ID",
    "PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX",
    "PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX",
    "ASSEMBLY_CELL_IDS",
    "ProjectionAnchorSlot",
    "ProjectionFacadeSlot",
    "ProjectionFrontendSlot",
    "ProjectionNativeBinding",
    "ProjectionNativeDefinition",
    "ProjectionNativeSource",
    "ProjectionObservationContext",
    "DEFAULT_PROJECTION_NATIVE_SOURCE",
    "NON_DEFAULT_PROJECTION_NATIVE_SOURCE",
    "compile_projection_native_contribution",
]

PROJECTION_NATIVE_RULE_ID = "mrw.projection.query-rebuild.native-rule.v2"
PROJECTION_NATIVE_VERIFICATION_INPUTS = (
    "mrw.projection.facade-dto-validation",
    "mrw.projection.client-observation",
    "mrw.projection.offset-anchor-cas",
    "mrw.projection.authority-separation",
)
PROJECTION_PROCESSING_FAILURES = projection_processing_failures
PROJECTION_FAMILY_ID = "mrw.projection"
PROJECTION_COMMAND_QUERY_CELL_ID = "projection.command-query.v2"
PROJECTION_CLIENT_CONTRACT_CELL_ID = "projection.client-contract.v2"
PROJECTION_READ_MODEL_CELL_ID = "projection.read-model.v2"
PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX = ".source-views"
PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX = ".source-anchor"
PROJECTION_COMMAND_QUERY_SLOT_ID = PROJECTION_COMMAND_QUERY_CELL_ID
PROJECTION_CLIENT_CONTRACT_SLOT_ID = PROJECTION_CLIENT_CONTRACT_CELL_ID
PROJECTION_READ_MODEL_SLOT_ID = PROJECTION_READ_MODEL_CELL_ID
ASSEMBLY_CELL_IDS = (
    PROJECTION_COMMAND_QUERY_CELL_ID,
    PROJECTION_CLIENT_CONTRACT_CELL_ID,
    PROJECTION_READ_MODEL_CELL_ID,
)
PROJECTION_FRONTEND_STATES = (
    "NOT_STARTED",
    "IN_FLIGHT",
    "SUCCEEDED",
    "FAILED",
    "OUTCOME_UNKNOWN",
    "REJECTED_TYPED",
)
PROJECTION_FRONTEND_REJECTION_CODES = (
    "INVALID_INPUT",
    "NOT_FOUND",
    "CONFLICT",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "RATE_LIMITED",
    "SCOPE_RESOLUTION_FAILED",
)
PROJECTION_FRONTEND_CONTRACT_REF = "main/frontend-modern/src/lib/api/domains/successor-runtime.ts:deriveSuccessorUiObservation"


@dataclass(frozen=True, slots=True)
class ProjectionFacadeSlot:
    """Facade DTO authority slot; validation-only and never executable."""

    api_status: facade.ApiStatusKindV2
    project_key: str
    resolved_schema: str
    project_registry_revision: int
    incarnation: str
    scope_digest: str
    trace_id: str
    command_id: str
    command_kind: str
    description: str
    actor_ref: str
    idempotency_key: str
    expected_base_token: str | None
    query_id: str
    query_kind: Literal["projection_snapshot"]


@dataclass(frozen=True, slots=True)
class ProjectionFrontendSlot:
    """Disposable frontend read-model authority slot."""

    states: tuple[str, ...] = PROJECTION_FRONTEND_STATES
    rejection_codes: tuple[str, ...] = PROJECTION_FRONTEND_REJECTION_CODES
    contract_ref: str = PROJECTION_FRONTEND_CONTRACT_REF


@dataclass(frozen=True, slots=True)
class ProjectionAnchorSlot:
    """Exact projector/source identity and CAS transition authority slot."""

    projection_id: str
    projection_schema_ref: str
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str
    projection_offset_id: str
    offset_ref: str
    projection_generation: int
    offset_revision: int
    projection_revision: int
    source_revision: int
    source_digest: str


@dataclass(frozen=True, slots=True)
class ProjectionNativeSource:
    """One authored C9 fact with three independently typed slots."""

    contribution_id: str
    family_id: str
    cell_ids: tuple[str, str, str]
    projection_contract: str
    owner: str
    facade: ProjectionFacadeSlot
    frontend: ProjectionFrontendSlot
    anchor: ProjectionAnchorSlot
    rollback_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectionNativeDefinition:
    """Lowered C9 authority view preserving the three slot identities."""

    source: ProjectionNativeSource
    facade_command: facade.FacadeCommandV2
    facade_query: facade.FacadeQueryV2
    facade_validation: facade.ValidationResult
    frontend_projection: tuple[tuple[str, str, str], ...]
    current_offset: offsets.ProjectionOffset
    next_offset: offsets.ProjectionOffset
    cas_expectation: offsets.OffsetExpectation

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    @property
    def slot_ids(self) -> tuple[str, str, str]:
        return self.source.cell_ids

    @property
    def projector_key(self) -> offsets.ProjectorKey:
        return offsets.ProjectorKey(
            projector_id=self.source.anchor.projector_id,
            projector_version=self.source.anchor.projector_version,
            source_kind=self.source.anchor.source_kind,
            source_ref=self.source.anchor.source_ref,
            source_incarnation=self.source.anchor.source_incarnation,
        )

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        owner = self.source.owner
        base = self.source.contribution_id
        facade_id = f"{base}.command-query"
        frontend_id = f"{base}.client-contract"
        anchor_id = f"{base}.read-model"
        source_views_id = f"{base}{PROJECTION_SOURCE_VIEWS_OBJECT_SUFFIX}"
        source_anchor_id = f"{base}{PROJECTION_SOURCE_ANCHOR_OBJECT_SUFFIX}"
        return (
            ContributionObject(facade_id, "Port", owner, (facade_id,)),
            ContributionObject(frontend_id, "Projection", owner, (frontend_id,)),
            ContributionObject(anchor_id, "Contract", owner, (anchor_id,)),
            ContributionObject(
                source_views_id,
                "Projection",
                owner,
                (anchor_id, source_anchor_id),
            ),
            ContributionObject(
                source_anchor_id,
                "Anchor",
                owner,
                (anchor_id,),
            ),
        )

_SCOPE_FIELDS = (
    "project_key",
    "resolved_schema",
    "project_registry_revision",
    "incarnation",
    "scope_digest",
    "trace_id",
    "command_id",
    "command_kind",
    "description",
    "actor_ref",
    "idempotency_key",
    "query_id",
)


def _definition_issues(source: ProjectionNativeSource, definition: ProjectionNativeDefinition) -> tuple[NativeBindingIssue, ...]:
    anchor = source.anchor
    key_identity = offsets.ProjectorKey(
        projector_id=anchor.projector_id,
        projector_version=anchor.projector_version,
        source_kind=anchor.source_kind,
        source_ref=anchor.source_ref,
        source_incarnation=anchor.source_incarnation,
    )
    checks: tuple[tuple[bool, str, str], ...] = (
        (source.family_id == PROJECTION_FAMILY_ID, "$.source.family_id", "projection family identity drift"),
        (source.cell_ids == ASSEMBLY_CELL_IDS, "$.source.cell_ids", "projection cell identity drift"),
        (
            source.projection_contract == anchor.projection_id,
            "$.source.projection_contract",
            "projection contract identity drift",
        ),
        (bool(source.owner), "$.source.owner", "owner is empty"),
        (bool(source.rollback_refs), "$.source.rollback_refs", "rollback authority is empty"),
        (source.facade.api_status in facade.API_STATUS_KINDS_V2, "$.source.facade.api_status", "invalid facade status"),
        (source.frontend.states == PROJECTION_FRONTEND_STATES, "$.source.frontend.states", "frontend state union drift"),
        (
            source.frontend.rejection_codes == PROJECTION_FRONTEND_REJECTION_CODES,
            "$.source.frontend.rejection_codes",
            "typed rejection union drift",
        ),
        (
            source.frontend.contract_ref == PROJECTION_FRONTEND_CONTRACT_REF,
            "$.source.frontend.contract_ref",
            "frontend authority drift",
        ),
        (definition.facade_validation.valid, "$.facade.dto", "facade DTO failed authority validation"),
        (
            definition.facade_command.execute is False,
            "$.facade.command.execute",
            "facade command must remain non-executable",
        ),
        (definition.facade_query.read_only is True, "$.facade.query.read_only", "facade query must remain read-only"),
        (
            tuple(definition.frontend_projection)
            == ((definition.source.frontend.contract_ref, "states", "|".join(definition.source.frontend.states)),),
            "$.frontend.projection",
            "frontend projection identity drift",
        ),
        (definition.projector_key == key_identity, "$.anchor.key", "projector key identity drift"),
        (
            definition.current_offset.key == definition.projector_key,
            "$.anchor.current_offset",
            "offset is not bound to the source projector key",
        ),
        (
            definition.next_offset.key == definition.projector_key,
            "$.anchor.next_offset",
            "offset is not bound to the source projector key",
        ),
        (
            definition.cas_expectation.expected_revision == anchor.offset_revision,
            "$.anchor.expectation",
            "CAS expectation revision drift",
        ),
    )
    return tuple(NativeBindingIssue(path, message) for valid, path, message in checks if not valid)


def _scope(slot: ProjectionFacadeSlot) -> ProjectScopeRef:
    return ProjectScopeRef(
        project_key=slot.project_key,
        resolved_schema=slot.resolved_schema,
        project_registry_revision=slot.project_registry_revision,
        incarnation=slot.incarnation,
        scope_digest=slot.scope_digest,
    )


def lower_projection_native_source(source: ProjectionNativeSource) -> ProjectionNativeDefinition | Failure:
    slot = source.facade
    scope = _scope(slot)
    meta = facade.CommandMetaV2(
        project_key=slot.project_key,
        trace_id=slot.trace_id,
        command_id=slot.command_id,
        project_scope_ref=scope,
    )
    command = facade.FacadeCommandV2(
        command_id=slot.command_id,
        command_kind=slot.command_kind,
        description=slot.description,
        project_scope_ref=scope,
        actor_ref=slot.actor_ref,
        idempotency_key=slot.idempotency_key,
        expected_base_token=slot.expected_base_token,
        meta=meta,
    )
    query = facade.FacadeQueryV2(
        query_id=slot.query_id,
        query_kind=slot.query_kind,
        project_scope_ref=scope,
        actor_ref=slot.actor_ref,
        meta=facade.QueryMetaV2(
            project_key=slot.project_key,
            trace_id=slot.trace_id,
            query_id=slot.query_id,
            project_scope_ref=scope,
        ),
    )
    validation = facade.validate_command_v2(command)
    key = offsets.ProjectorKey(
        projector_id=source.anchor.projector_id,
        projector_version=source.anchor.projector_version,
        source_kind=source.anchor.source_kind,
        source_ref=source.anchor.source_ref,
        source_incarnation=source.anchor.source_incarnation,
    )
    current = offsets.ProjectionOffset(
        projection_offset_id=source.anchor.projection_offset_id,
        key=key,
        projection_generation=source.anchor.projection_generation,
        source_revision=source.anchor.source_revision,
        source_digest=source.anchor.source_digest,
        offset_ref=source.anchor.offset_ref,
        revision=source.anchor.offset_revision,
    )
    next_offset = offsets.ProjectionOffset(
        projection_offset_id=current.projection_offset_id,
        key=key,
        projection_generation=current.projection_generation,
        source_revision=current.source_revision,
        source_digest=current.source_digest,
        offset_ref=current.offset_ref,
        revision=current.revision + 1,
    )
    expectation = offsets.OffsetExpectation(
        expected_revision=current.revision,
        expected_generation=current.projection_generation,
        expected_source_revision=current.source_revision,
        expected_source_digest=current.source_digest,
    )
    definition = ProjectionNativeDefinition(
        source=source,
        facade_command=command,
        facade_query=query,
        facade_validation=validation,
        frontend_projection=((source.frontend.contract_ref, "states", "|".join(source.frontend.states)),),
        current_offset=current,
        next_offset=next_offset,
        cas_expectation=expectation,
    )
    issues = _definition_issues(source, definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C9 definition is invalid",
            {"issues": tuple({"code": "invalid_spec", "path": i.path, "message": i.message} for i in issues)},
        )
    return definition


def project_projection_native_definition(definition: ProjectionNativeDefinition) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        vocabularies=(
            projection_projector_outcomes,
            projection_runtime_event_kinds,
            projection_session_statuses,
            projection_search_segment_kinds,
            projection_projection_loss_kinds,
            projection_projection_source_schemas,
        ),
        failures=(
            PROJECTION_PROCESSING_FAILURES,
            projection_evidence_surface_failures,
        ),
    )


@dataclass(frozen=True, slots=True)
class ProjectionObservationContext:
    """Pure frontend-observation input; it is not a runtime completion claim."""

    phase: Literal["not_started", "in_flight", "settled"]
    client_error: bool = False
    envelope_status: facade.ApiStatusKindV2 | None = None
    typed_rejection: bool = False


@dataclass(frozen=True, slots=True)
class ProjectionNativeBinding:
    """Project adapter binding over the three authoritative slots."""

    definition: ProjectionNativeDefinition

    def derive_frontend_observation(self, context: ProjectionObservationContext) -> str | Failure:
        if context.phase not in ("not_started", "in_flight", "settled"):
            return contribution_failures.fail("CONTRIBUTION_INVALID", "invalid projection observation phase")
        if context.phase == "not_started" and not context.client_error:
            return "NOT_STARTED"
        if context.phase == "in_flight":
            return "IN_FLIGHT"
        if context.client_error:
            return "FAILED"
        if context.envelope_status is None:
            return contribution_failures.fail(
                "CONTRIBUTION_INVALID", "settled observation requires envelope or client error"
            )
        if context.envelope_status == "waiting":
            return "IN_FLIGHT"
        if context.envelope_status == "ok":
            return "SUCCEEDED"
        if context.typed_rejection:
            return "REJECTED_TYPED"
        return "OUTCOME_UNKNOWN"

    def validate_anchor_transition(
        self,
        next_offset: offsets.ProjectionOffset,
        expectation: offsets.OffsetExpectation,
        *,
        stored_offset: offsets.ProjectionOffset | None = None,
    ) -> offsets.ValidationResult:
        return offsets.validate_offset_advance(
            stored_offset or self.definition.current_offset, expectation, next_offset
        )


def assemble_projection_native_definition(
    definition: ProjectionNativeDefinition,
    context: object,
) -> ProjectionNativeBinding | Failure:
    del context
    return ProjectionNativeBinding(definition=definition)


def validate_projection_native_binding(
    definition: ProjectionNativeDefinition,
    candidate: object,
) -> BindingAccepted[ProjectionNativeBinding] | BindingRejected:
    if not isinstance(candidate, ProjectionNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected ProjectionNativeBinding"),))
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.definition.slot_ids == (PROJECTION_COMMAND_QUERY_SLOT_ID, PROJECTION_CLIENT_CONTRACT_SLOT_ID, PROJECTION_READ_MODEL_SLOT_ID),
                "$.binding.slot_ids",
                "slot order/identity drift",
            ),
            (
                candidate.definition.facade_command.execute is False,
                "$.binding.facade.execute",
                "facade authority became executable",
            ),
            (
                candidate.definition.facade_query.read_only is True,
                "$.binding.facade.read_only",
                "query authority became mutable",
            ),
            (
                candidate.validate_anchor_transition(
                    candidate.definition.next_offset, candidate.definition.cas_expectation
                ).valid,
                "$.binding.anchor.baseline",
                "baseline CAS transition failed",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def _issue_tuple(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple(NativeBindingIssue(path, message) for valid, path, message in checks if not valid)


def verify_projection_native_definition(
    definition: ProjectionNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    del native

    def _run() -> Failure | None:
        issues = _definition_issues(definition.source, definition)
        if not issues:
            return None
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "; ".join(f"{issue.path}: {issue.message}" for issue in issues),
        )

    witness = define_law_witness(
        f"test_projection_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=PROJECTION_NATIVE_RULE_ID,
        inputs=PROJECTION_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=PROJECTION_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


PROJECTION_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    ProjectionNativeSource,
    ProjectionNativeDefinition,
    object,
    ProjectionNativeBinding,
](
    lower=lower_projection_native_source,
    project=project_projection_native_definition,
    assemble=assemble_projection_native_definition,
    validate_binding=validate_projection_native_binding,
    verification=verify_projection_native_definition,
)


def compile_projection_native_contribution(source: ProjectionNativeSource) -> object:
    return compile_native_contribution(source, PROJECTION_NATIVE_CONTRIBUTION_RULE)


_SCOPE_DIGEST = "0" * 64
_ROLLBACK_REFS = (
    "main/backend/app/successor_runtime/runtime/facade_contracts.py",
    "main/frontend-modern/src/lib/api/domains/successor-runtime.ts",
    "main/backend/app/successor_runtime/substrate/projections/registry.py",
)


def _source(
    contribution_id: str,
    *,
    project_key: str,
    command_id: str,
    query_id: str,
    projection_id: str,
    source_ref: str,
    projector_id: str,
    projector_version: str,
    source_kind: str,
    source_incarnation: str,
    offset_id: str,
    offset_ref: str,
) -> ProjectionNativeSource:
    return ProjectionNativeSource(
        contribution_id=contribution_id,
        family_id=PROJECTION_FAMILY_ID,
        cell_ids=ASSEMBLY_CELL_IDS,
        projection_contract=projection_id,
        owner="projection.material-closure.v2",
        facade=ProjectionFacadeSlot(
            api_status="ok",
            project_key=project_key,
            resolved_schema=f"{project_key}_projection",
            project_registry_revision=1,
            incarnation="incarnation:projection-native:v2",
            scope_digest=_SCOPE_DIGEST,
            trace_id=f"trace:{command_id}",
            command_id=command_id,
            command_kind="rebuild_projection",
            description="Material projection validation-only command authority",
            actor_ref="actor:material-projection-native-owner",
            idempotency_key=f"idem:material-projections:{command_id}",
            expected_base_token=None,
            query_id=query_id,
            query_kind="projection_snapshot",
        ),
        frontend=ProjectionFrontendSlot(),
        anchor=ProjectionAnchorSlot(
            projection_id=projection_id,
            projection_schema_ref=(
                facade.MATERIAL_PROJECTION_CANDIDATE_SCHEMA
                if projection_id == facade.MATERIAL_PROJECTION_CLOSURE_ID
                else f"{projection_id}.schema"
            ),
            projector_id=projector_id,
            projector_version=projector_version,
            source_kind=source_kind,
            source_ref=source_ref,
            source_incarnation=source_incarnation,
            projection_offset_id=offset_id,
            offset_ref=offset_ref,
            projection_generation=1,
            offset_revision=2,
            projection_revision=3,
            source_revision=4,
            source_digest="1" * 64,
        ),
        rollback_refs=_ROLLBACK_REFS,
    )


DEFAULT_PROJECTION_NATIVE_SOURCE = _source(
    "mrw.projection.material-closure.native.v2",
    project_key="material-projection-default",
    command_id="command:material-projection-default",
    query_id="query:material-projection-default",
    projection_id=facade.MATERIAL_PROJECTION_CLOSURE_ID,
    source_ref="projection:material-projection-default:source",
    projector_id=facade.MATERIAL_PROJECTION_PROJECTOR_ID,
    projector_version=facade.MATERIAL_PROJECTION_PROJECTOR_VERSION,
    source_kind=facade.MATERIAL_PROJECTION_SOURCE_KIND,
    source_incarnation="incarnation:material-projection:v2",
    offset_id="offset:material-projection-default:v2",
    offset_ref="offset:material-projection-default:rev2",
)

NON_DEFAULT_PROJECTION_NATIVE_SOURCE = _source(
    "mrw.projection.query-rebuild.native.fixture.v2",
    project_key="projection-native-fixture",
    command_id="command:projection-fixture",
    query_id="query:projection-fixture",
    projection_id="projection.native-fixture.v2",
    source_ref="document:projection-native-fixture",
    projector_id="projection.native-fixture.projector",
    projector_version="0.2.0",
    source_kind="projection_native_fixture",
    source_incarnation="incarnation:projection-native-fixture:v2",
    offset_id="offset:projection-fixture:v2",
    offset_ref="offset:projection-fixture:rev2",
)
