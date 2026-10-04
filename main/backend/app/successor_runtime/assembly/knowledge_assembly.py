"""C8 family assembly: installable pure route handlers plus the C8.3 bridge.

KNOWLEDGE_REPORT_KINDostgres_c8_delivery_assembly`` is reused byte-for-byte when the caller
supplies its exact dependencies; otherwise C8.3 stays unwired.  C8.1/C8.2 are
installed as pure RuntimeHandler route closures only when deterministic
c81/c82 payloads are supplied.  The route handlers never write a database and
never call admission/export.  The graph-projection cell declares the exact
``knowledge.graph.projector`` identity without inventing a per-run source key
or a PostgreSQL write.  When
the run owner supplies a per-run source key, the builder constructs one
read-only projector contract, registers it in the family ``ProjectorRegistry``
and installs C8.4; without a key, C8.4 stays ``PROJECTOR_WIRING_DECLARED``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Annotated, Any, TYPE_CHECKING

from sqlalchemy.engine import Engine
from functorial_kit.core.failure import Failure

from app.successor_runtime.assembly.base import (
    KnowledgeAssemblyOptions,
    CellBinding,
    FamilyAssembly,
    ProjectorSourceKey,
    ProjectorWiring,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.capabilities import knowledge_common as knowledge
from app.successor_runtime.capabilities.knowledge_common import (
    KNOWLEDGE_READ_CELL_ID,
    KNOWLEDGE_WRITING_CELL_ID,
    KNOWLEDGE_REPORT_CELL_ID,
    KNOWLEDGE_GRAPH_PROJECTION_CELL_ID,
)
from app.successor_runtime.capabilities.knowledge_report_contribution import (
    KNOWLEDGE_REPORT_ROLLBACK_REF as _C8_3_NATIVE_ROLLBACK_REF,
)
from app.successor_runtime.capabilities.knowledge_graph_projection_contribution import (
    KNOWLEDGE_GRAPH_PROJECTION_DECLARED_LOSS,
    KNOWLEDGE_GRAPH_PROJECTION_ROLLBACK_REF,
    KnowledgeGraphProjectionAssemblyContext,
)
from app.successor_runtime.capabilities.knowledge_native_contribution import KnowledgeNativeAssemblyContext
from app.successor_runtime.capabilities.knowledge_writing_contribution import KNOWLEDGE_WRITING_ROLLBACK_REFS as _C8_2_NATIVE_ROLLBACK_REFS
from app.successor_runtime.capabilities.typed_knowledge_contribution import KNOWLEDGE_READ_ROLLBACK_REFS as _C8_1_NATIVE_ROLLBACK_REFS
from app.successor_runtime.capabilities.knowledge_program import (
    KNOWLEDGE_READ_KIND,
    KNOWLEDGE_WRITING_COMPOSE_KIND,
    KNOWLEDGE_WRITING_STAGE_KIND,
    KNOWLEDGE_REPORT_KIND,
    KNOWLEDGE_DELIVERY_INTENT_TYPE,
    KNOWLEDGE_RESEARCH_ARTIFACT_TYPE,
    DELIVERY_INTERNAL_EXPORT_KIND,
    KnowledgeCapabilityBundle,
    KnowledgeDemandReadInput,
    KnowledgeReportStageInput,
    KnowledgeWritingComposeInput,
    build_knowledge_bundle,
    build_knowledge_catalog,
    build_knowledge_delivery_bridge_bundle,
    build_knowledge_delivery_bridge_program,
    compile_knowledge_delivery_bridge_program,
    compose_default_knowledge_graph_projection_contributions,
    compose_default_knowledge_native_contributions,
    exact_contract_ref,
    validate_knowledge_graph_projection_contributions,
    validate_knowledge_native_contributions,
)
from app.successor_runtime.capabilities.typed_knowledge import demand_read
from app.successor_runtime.capabilities.knowledge_writing import (
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    ObjectType,
)
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
from app.successor_runtime.substrate.postgres.c8_export_token_state_handler import (
    KnowledgeReportExportTokenStateRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.c8_production import (
    build_postgres_c8_delivery_assembly,
)
from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    build_c8_delivery_activation_catalog,
)

if TYPE_CHECKING:
    from app.successor_runtime.capabilities.knowledge_program import KnowledgeNativeContribution

KNOWLEDGE_FAMILY_ID = "mrw.knowledge"
ASSEMBLY_CELL_IDS = (
    KNOWLEDGE_READ_CELL_ID,
    KNOWLEDGE_WRITING_CELL_ID,
    KNOWLEDGE_REPORT_CELL_ID,
    KNOWLEDGE_GRAPH_PROJECTION_CELL_ID,
)

KNOWLEDGE_READ_ROLLBACK_REF = _C8_1_NATIVE_ROLLBACK_REFS[0]
KNOWLEDGE_WRITING_ROLLBACK_REF = _C8_2_NATIVE_ROLLBACK_REFS[0]
KNOWLEDGE_REPORT_ROLLBACK_REF = _C8_3_NATIVE_ROLLBACK_REF
KNOWLEDGE_ROUTE_ASSEMBLY_ROLLBACK_REF = (
    "main/backend/app/successor_runtime/assembly/c8_assembly.py"
)

KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.knowledge.deployment-catalog.v2")
KNOWLEDGE_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.knowledge.authority.v2")
KNOWLEDGE_READ_INTERPRETER_PROFILE_DIGEST = sha256_hex("knowledge.read.interpreter.v2")
KNOWLEDGE_WRITING_INTERPRETER_PROFILE_DIGEST = sha256_hex("knowledge.writing.interpreter.v2")
KNOWLEDGE_WRITING_ROUTE_OPERATION_KINDS = (KNOWLEDGE_WRITING_COMPOSE_KIND, KNOWLEDGE_WRITING_STAGE_KIND)
KNOWLEDGE_DEMAND_READ_FAILURE_CODE = "DEMAND_READ_UNAVAILABLE"
KNOWLEDGE_WRITING_STAGE_FAILURE_CODE = "WRITING_STAGE_INVALID"
_KNOWLEDGE_REPORT__EXPORT_TOKEN_OPERATION_REF = "knowledge.report.export-token-state.v2"
_KNOWLEDGE_REPORT__EXPORT_TOKEN_OPERATION_DIGEST = sha256_hex(
    "mrw.knowledge.report-export-token-state.operation.v2"
)
_KNOWLEDGE_REPORT__EXPORT_TOKEN_INTERPRETER_DIGEST = sha256_hex(
    "knowledge.report.export-token-state.interpreter.v2"
)
_KNOWLEDGE_REPORT__EXPORT_TOKEN_AUTHORITY_DIGEST = sha256_hex(
    "mrw.knowledge.report-export-token-state.authority.v2"
)
_KNOWLEDGE_REPORT__EXPORT_TOKEN_HANDLER_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "c8_export_token_state_handler.py"
)

KNOWLEDGE_REHEARSAL_PROJECT_KEY = "mrw-knowledge-local"
KNOWLEDGE_REHEARSAL_ITEM_KEY = "ki:knowledge-demand-read"
KNOWLEDGE_REHEARSAL_STATEMENT = (
    "MRW knowledge local-offline typed knowledge item."
)
KNOWLEDGE_REHEARSAL_SELECTION_HASH = "selection:knowledge-local"
KNOWLEDGE_REHEARSAL_SELECTION_TEXT = "successor runtime local-offline writing selection"
KNOWLEDGE_REHEARSAL_FIELDS = ("canonical_statement", "evidence_refs")

KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY = "mrw-knowledge-report-local"
KNOWLEDGE_REPORT_DELIVERY_PROGRAM_ID = "program:knowledge-report-local"
KNOWLEDGE_REPORT_DELIVERY_REPORT_ID = "report:knowledge-report-local"
KNOWLEDGE_REPORT_DELIVERY_TOPIC = "LOCAL_OFFLINE knowledge.report.v2 delivery bridge closure"
KNOWLEDGE_REPORT_DELIVERY_AUTHORITY_DIGEST = sha256_hex("mrw.knowledge.report.delivery-authority.v2")
KNOWLEDGE_REPORT_DELIVERY_RESOURCE_POLICY_DIGEST = sha256_hex(
    "mrw.knowledge.report.resource-policy.v2"
)
KNOWLEDGE_REPORT_DELIVERY_NODE_PROFILE_SELECTOR = sha256_hex("mrw.knowledge.report.node-profile.v2")


def _validate_exact_binding(
    cell_label: str,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    handler: Any,
) -> None:
    if claim.assignment_digest != assignment.assignment_digest:
        raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.claim_authority_epoch != assignment.claim_authority_epoch:
        raise DefiniteInterpreterFailure("CLAIM_AUTHORITY_EPOCH_DRIFT")
    if (
        assignment.handler_binding_digest != handler.handler_binding_digest
        or assignment.operation_contract_digest != handler.operation_contract_digest
    ):
        raise DefiniteInterpreterFailure(f"EXACT_{cell_label}_HANDLER_BINDING_DRIFT")
    if assignment.deployment_catalog_digest != handler.deployment_catalog_digest:
        raise DefiniteInterpreterFailure(f"EXACT_{cell_label}_DEPLOYMENT_CATALOG_DRIFT")


class KnowledgeDemandReadRouteHandler(RuntimeHandler):
    """Pure C8.1 demand-read route handler over a deterministic payload closure.

    The handler captures no database, provider or store.  ``execute`` validates
    the exact claim/assignment binding and then runs the pure ``demand_read``
    closure against the payload's in-memory items and registry.
    """

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        binding: Any,
        deployment_catalog_digest: str,
    ) -> None:
        try:
            items = payload["items"]
            self._item_key = str(payload["item_key"])
            self._fields = tuple(payload["fields"])
            self._project_key = str(payload["project_key"])
        except KeyError as exc:
            raise ValueError(
                f"{KNOWLEDGE_READ_CELL_ID} payload lacks required closure field {exc.args[0]!r}"
            ) from exc
        self._items = tuple(items)
        if (
            not self._items
            or not self._item_key
            or not self._fields
            or not self._project_key
        ):
            raise ValueError(
                f"{KNOWLEDGE_READ_CELL_ID} payload requires non-empty "
                "items/item_key/fields/project_key"
            )
        if not all(isinstance(item, knowledge.KnowledgeItem) for item in self._items):
            raise ValueError(
                f"{KNOWLEDGE_READ_CELL_ID} payload items must be KnowledgeItem values"
            )
        registry = payload.get("registry")
        if registry is not None and not isinstance(registry, knowledge.ReadHandleRegistry):
            raise ValueError(
                f"{KNOWLEDGE_READ_CELL_ID} payload registry must be a ReadHandleRegistry"
            )
        self._registry = registry if registry is not None else knowledge.ReadHandleRegistry()
        require_assembly_digest(
            deployment_catalog_digest,
            f"{KNOWLEDGE_READ_CELL_ID} deployment catalog digest",
        )
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _validate_exact_binding("C8_1", assignment, claim, self)
        try:
            read = demand_read(
                self._items,
                item_key=self._item_key,
                fields=self._fields,
                project_key=self._project_key,
                registry=self._registry,
            )
        except knowledge.KnowledgeProjectionError as exc:
            raise DefiniteInterpreterFailure(
                KNOWLEDGE_DEMAND_READ_FAILURE_CODE
            ) from exc
        return InterpreterOutcome.succeeded(content_digest(read))


class KnowledgeWritingComposeStageRouteHandler(RuntimeHandler):
    """Pure C8.2 ordered compose+stage route handler over a deterministic closure."""

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        binding: Any,
        deployment_catalog_digest: str,
    ) -> None:
        try:
            read = payload["read"]
            self._selection_hash = str(payload["selection_hash"])
            self._selection_text = str(payload["selection_text"])
        except KeyError as exc:
            raise ValueError(
                f"{KNOWLEDGE_WRITING_CELL_ID} payload lacks required closure field {exc.args[0]!r}"
            ) from exc
        if not isinstance(read, knowledge.KnowledgeRead):
            raise TypeError(f"{KNOWLEDGE_WRITING_CELL_ID} payload read must be a KnowledgeRead")
        if not self._selection_hash or not self._selection_text:
            raise ValueError(
                f"{KNOWLEDGE_WRITING_CELL_ID} payload requires non-empty selection inputs"
            )
        self._read = read
        require_assembly_digest(
            deployment_catalog_digest,
            f"{KNOWLEDGE_WRITING_CELL_ID} deployment catalog digest",
        )
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _validate_exact_binding("C8_2", assignment, claim, self)
        try:
            handoff = compose_writing_handoff(
                self._read,
                selection_hash=self._selection_hash,
                selection_text=self._selection_text,
            )
            artifact = stage_writing_artifact(project_writing_card(handoff))
        except knowledge.UnavailableProjection as exc:
            raise DefiniteInterpreterFailure(
                KNOWLEDGE_WRITING_STAGE_FAILURE_CODE
            ) from exc
        return InterpreterOutcome.succeeded(content_digest(artifact))


def _installed_knowledge_report__cell(
    *,
    bundle: KnowledgeCapabilityBundle,
    delivery_assembly: Any,
    declared: CellBinding,
) -> CellBinding:
    """Resolve the exact C8.3 handler binding from the delivery assembly."""

    matches = tuple(
        operation for operation in bundle.operations if operation.ref.kind == KNOWLEDGE_REPORT_KIND
    )
    if len(matches) != 1:
        raise ValueError(
            f"knowledge capability bundle must contain one exact {KNOWLEDGE_REPORT_KIND} operation"
        )
    operation_digest = matches[0].ref.contract_digest
    handlers = tuple(
        handler
        for handler in delivery_assembly.handlers
        if getattr(handler, "operation_contract_digest", None) == operation_digest
    )
    if len(handlers) != 1:
        raise ValueError(
            "knowledge assembly must contain one exact knowledge.report.v2 handler "
            f"for the {KNOWLEDGE_REPORT_KIND} operation"
        )
    return dataclasses.replace(
        declared,
        status="INSTALLED",
        handler_binding_digest=handlers[0].handler_binding_digest,
        note=(
            "reuses build_postgres_c8_delivery_assembly unchanged; exact "
            "knowledge.report.v2 handler binding digest from the installed bridge"
        ),
    )


def _installed_knowledge_report__export_token_cell(
    handler: KnowledgeReportExportTokenStateRuntimeHandler,
    declared: CellBinding,
) -> CellBinding:
    """Install C8.3 through the typed export/token-state successor route."""

    return dataclasses.replace(
        declared,
        status="INSTALLED",
        operation_contract_refs=declared.operation_contract_refs
        + (_KNOWLEDGE_REPORT__EXPORT_TOKEN_OPERATION_REF,),
        handler_binding_digest=handler.handler_binding_digest,
        required_wiring=(
            "successor export/token-state store command closure",
            "admission/export authority gate 保持关闭",
        ),
        note=(
            "C8.3 typed report-export/token-state successor route installed; "
            "one-time claim/revoke/expiry/recovery with actor digest; "
            "no credential value stored; no live export/canonical authority"
        ),
    )


def _knowledge_operation_contract_digest(
    kind: str,
    *,
    native_composition: tuple[KnowledgeNativeContribution, ...] | None = None,
) -> str:
    return exact_contract_ref(
        build_knowledge_catalog(build_knowledge_bundle(native_composition=native_composition)),
        kind=kind,
    ).contract_digest


def _build_knowledge_read__route_handler(
    *,
    project_scope_digest: str,
    payload: Mapping[str, Any],
    native_composition: tuple[KnowledgeNativeContribution, ...] | None = None,
) -> KnowledgeDemandReadRouteHandler:
    binding = successor_binding(
        operation_contract_digest=_knowledge_operation_contract_digest(
            KNOWLEDGE_READ_KIND,
            native_composition=native_composition,
        ),
        interpreter_profile_digest=KNOWLEDGE_READ_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=KNOWLEDGE_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return KnowledgeDemandReadRouteHandler(
        payload=payload,
        binding=binding,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    )


def _build_knowledge_writing__route_handler(
    *,
    project_scope_digest: str,
    payload: Mapping[str, Any],
    native_composition: tuple[KnowledgeNativeContribution, ...] | None = None,
) -> KnowledgeWritingComposeStageRouteHandler:
    catalog = build_knowledge_catalog(build_knowledge_bundle(native_composition=native_composition))
    for kind in KNOWLEDGE_WRITING_ROUTE_OPERATION_KINDS:
        exact_contract_ref(catalog, kind=kind)
    binding = successor_binding(
        operation_contract_digest=exact_contract_ref(
            catalog,
            kind=KNOWLEDGE_WRITING_COMPOSE_KIND,
        ).contract_digest,
        interpreter_profile_digest=KNOWLEDGE_WRITING_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=KNOWLEDGE_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return KnowledgeWritingComposeStageRouteHandler(
        payload=payload,
        binding=binding,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
    )


def _knowledge_report__delivery_value_ref(
    *,
    program_id: str,
    project_key: str,
    suffix: str,
    object_type: ObjectType,
    codec_id: str,
) -> ValueRef:
    """One deterministic program value ref for the C8.3 delivery bridge."""

    value_id = f"{program_id}:payload:{suffix}"
    storage_ref = f"project-value:{value_id}"
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=sha256_hex(storage_ref),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=storage_ref,
        byte_size=1,
        provenance_digest=sha256_hex(f"provenance:{storage_ref}"),
    )


def build_deterministic_knowledge_delivery_closure(
    project_scope_digest: str,
) -> Annotated[
    dict[str, Any],
    "kit:prepared-command effect_boundary=successor_runtime.c8_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the deterministic LOCAL_OFFLINE C8.3 delivery-bridge closure.

    Returns exactly the ``bundle``, ``activation_catalog`` and
    ``delivery_interpreter`` dependencies required by
    ``build_postgres_c8_delivery_assembly``.  Assembly construction performs
    no database, provider or filesystem write; bridge execution stays closed
    under the I1 authority ceiling.
    """

    require_assembly_digest(
        project_scope_digest,
        f"{KNOWLEDGE_REPORT_CELL_ID} delivery project scope digest",
    )
    first = build_first_specimen_bundle()
    delivery_operation = first.operation_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    delivery_codec = first.codec_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    bundle = build_knowledge_delivery_bridge_bundle(delivery_operation, delivery_codec)
    catalog = build_knowledge_catalog(bundle)
    stage_payload = KnowledgeReportStageInput(
        project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
        report_id=KNOWLEDGE_REPORT_DELIVERY_REPORT_ID,
        topic=KNOWLEDGE_REPORT_DELIVERY_TOPIC,
        source_keys=("knowledge:report-local",),
    )
    program = normalize_program(
        build_knowledge_delivery_bridge_program(
            delivery_operation=delivery_operation,
            delivery_codec=delivery_codec,
            delivery_payload_ref=_knowledge_report__delivery_value_ref(
                program_id=KNOWLEDGE_REPORT_DELIVERY_PROGRAM_ID,
                project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
                suffix="internal-export-input",
                object_type=ObjectType("InternalExportInput.v1"),
                codec_id=delivery_codec.codec_id,
            ),
            artifact_input_ref=_knowledge_report__delivery_value_ref(
                program_id=KNOWLEDGE_REPORT_DELIVERY_PROGRAM_ID,
                project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
                suffix="research-artifact",
                object_type=KNOWLEDGE_RESEARCH_ARTIFACT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            intent_input_ref=_knowledge_report__delivery_value_ref(
                program_id=KNOWLEDGE_REPORT_DELIVERY_PROGRAM_ID,
                project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
                suffix="delivery-intent",
                object_type=KNOWLEDGE_DELIVERY_INTENT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            stage_payload=stage_payload,
            catalog=catalog,
            program_id=KNOWLEDGE_REPORT_DELIVERY_PROGRAM_ID,
            project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=project_scope_digest,
        )
    )
    plan = compile_knowledge_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=OperationContractRegistry(catalog, bundle.operations),
    )
    eligibility = QueueEligibility(
        project_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
        capability_id="knowledge.report.v2",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=KNOWLEDGE_REPORT_DELIVERY_RESOURCE_POLICY_DIGEST,
        concurrency_key="knowledge.report.v2",
    )
    activation_catalog = build_c8_delivery_activation_catalog(
        plan,
        interpreter_profile_digest=bundle.profiles["knowledge.report.v2"][
            "interpreter"
        ].profile_digest,
        deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=KNOWLEDGE_REPORT_DELIVERY_AUTHORITY_DIGEST,
        resource_policy_digest=KNOWLEDGE_REPORT_DELIVERY_RESOURCE_POLICY_DIGEST,
        required_node_profile_selector=KNOWLEDGE_REPORT_DELIVERY_NODE_PROFILE_SELECTOR,
        fairness_key=KNOWLEDGE_REPORT_DELIVERY_PROJECT_KEY,
        queue_eligibility=eligibility,
    )
    delivery_interpreter = InternalExportInterpreter(
        operation_contract_ref=delivery_operation.ref,
        blob_store=ProjectBlobStore(),
    )
    return {
        "bundle": bundle,
        "activation_catalog": activation_catalog,
        "delivery_interpreter": delivery_interpreter,
    }


def build_deterministic_knowledge_payloads(project_scope_digest: str) -> Annotated[
    dict[str, Any],
    "kit:prepared-command effect_boundary=successor_runtime.c8_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build deterministic LOCAL_OFFLINE C8.1/C8.2 payloads.

    The payloads carry enough typed values for the pure route handlers to run
    without any database, provider or legacy import.
    """

    require_assembly_digest(project_scope_digest, "knowledge payload project scope digest")
    item_body = knowledge.KnowledgeItem(
        key=KNOWLEDGE_REHEARSAL_ITEM_KEY,
        project_key=KNOWLEDGE_REHEARSAL_PROJECT_KEY,
        canonical_statement=KNOWLEDGE_REHEARSAL_STATEMENT,
        primary_type_node_key="tn:successor-runtime",
        evidence_refs=("evidence:knowledge-read-local",),
        topic_cluster_keys=("tc:successor-runtime",),
        review_state="human_confirmed",
        quality_grade="gold",
        locale="zh",
        visibility_scope="downstream_ready",
    )
    item = dataclasses.replace(
        item_body,
        canonical_ref=knowledge.derived_canonical_ref(item_body),
    )
    registry = knowledge.ReadHandleRegistry()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=KNOWLEDGE_REHEARSAL_FIELDS,
        project_key=KNOWLEDGE_REHEARSAL_PROJECT_KEY,
        registry=registry,
    )
    c81_payload: dict[str, Any] = {
        "schema": "mrw.knowledge.demand-read-payload.v2",
        "LOCAL_OFFLINE": True,
        "note": "LOCAL_OFFLINE deterministic demand-read closure; no DB/provider write",
        "project_scope_digest": project_scope_digest,
        "project_key": KNOWLEDGE_REHEARSAL_PROJECT_KEY,
        "item_key": item.key,
        "fields": KNOWLEDGE_REHEARSAL_FIELDS,
        "items": (item,),
        "registry": registry,
        "input": KnowledgeDemandReadInput(
            project_key=KNOWLEDGE_REHEARSAL_PROJECT_KEY,
            item_key=item.key,
            fields=KNOWLEDGE_REHEARSAL_FIELDS,
        ),
    }
    c82_payload: dict[str, Any] = {
        "schema": "mrw.knowledge.writing-compose-stage-payload.v2",
        "LOCAL_OFFLINE": True,
        "note": (
            "LOCAL_OFFLINE deterministic compose+stage closure; no DB/provider write"
        ),
        "project_scope_digest": project_scope_digest,
        "project_key": KNOWLEDGE_REHEARSAL_PROJECT_KEY,
        "read": read,
        "selection_hash": KNOWLEDGE_REHEARSAL_SELECTION_HASH,
        "selection_text": KNOWLEDGE_REHEARSAL_SELECTION_TEXT,
        "input": KnowledgeWritingComposeInput(
            project_key=KNOWLEDGE_REHEARSAL_PROJECT_KEY,
            knowledge_item_key=item.key,
            selection_hash=KNOWLEDGE_REHEARSAL_SELECTION_HASH,
            selection_text=KNOWLEDGE_REHEARSAL_SELECTION_TEXT,
            demand_fields=KNOWLEDGE_REHEARSAL_FIELDS,
        ),
    }
    return {"c81_payload": c81_payload, "c82_payload": c82_payload}


def build_knowledge_assembly(
    *,
    engine: Engine,
    project_scope_digest: str,
    options: KnowledgeAssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.c8_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the C8 family assembly with optional route/bridge installation.

    C8.1--C8.3 CellBinding and rollback declarations come from their native
    contributions.  C8.3 remains authority-closed unless its existing delivery
    dependencies are supplied.  C8.4 stays ``PROJECTOR_WIRING_DECLARED`` until
    the run owner supplies a per-run source key; with a key it registers one
    read-only projector contract in the family registry and becomes
    ``INSTALLED``.
    """

    require_assembly_digest(project_scope_digest, "knowledge project scope digest")
    c8_options = options or KnowledgeAssemblyOptions()
    selected_native_composition = c8_options.native_composition
    native_contributions = (
        compose_default_knowledge_native_contributions()
        if selected_native_composition is None
        else validate_knowledge_native_contributions(selected_native_composition)
    )
    native_bindings = []
    for native in native_contributions:
        native_binding = native.assemble(KnowledgeNativeAssemblyContext())
        if isinstance(native_binding, Failure):
            raise ValueError(
                f"native knowledge contribution {native.projection.id} invalid: "
                f"{native_binding.message}"
            )
        native_bindings.append(native_binding)
    native_bindings_by_cell = {
        native_binding.cell_id: native_binding for native_binding in native_bindings
    }
    c8_1_binding = native_bindings_by_cell[KNOWLEDGE_READ_CELL_ID]
    c8_2_binding = native_bindings_by_cell[KNOWLEDGE_WRITING_CELL_ID]
    c8_3_binding = native_bindings_by_cell[KNOWLEDGE_REPORT_CELL_ID]

    handlers: list[Any] = []
    recovery_handlers: list[Any] = []
    c8_3_cell = c8_3_binding.declared_cell()
    if all(
        value is not None
        for value in (
            c8_options.bundle,
            c8_options.activation_catalog,
            c8_options.delivery_interpreter,
        )
    ):
        delivery_assembly = build_postgres_c8_delivery_assembly(
            engine=engine,
            bundle=c8_options.bundle,
            activation_catalog=c8_options.activation_catalog,
            delivery_interpreter=c8_options.delivery_interpreter,
        )
        c8_3_cell = _installed_knowledge_report__cell(
            bundle=c8_options.bundle,
            delivery_assembly=delivery_assembly,
            declared=c8_3_cell,
        )
        handlers.extend(delivery_assembly.handlers)
        recovery_handlers.extend(delivery_assembly.recovery_handlers)

    export_store = c8_options.export_token_store
    export_command = c8_options.export_token_command
    if (export_store is None) != (export_command is None):
        raise ValueError(
            "knowledge.report.v2 export/token-state wiring requires both export_token_store "
            "and export_token_command"
        )
    export_token_installed = export_store is not None
    if export_token_installed:
        export_binding = successor_binding(
            operation_contract_digest=_KNOWLEDGE_REPORT__EXPORT_TOKEN_OPERATION_DIGEST,
            interpreter_profile_digest=_KNOWLEDGE_REPORT__EXPORT_TOKEN_INTERPRETER_DIGEST,
            deployment_catalog_digest=KNOWLEDGE_DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=project_scope_digest,
            authority_requirement_digest=_KNOWLEDGE_REPORT__EXPORT_TOKEN_AUTHORITY_DIGEST,
        )
        export_handler = KnowledgeReportExportTokenStateRuntimeHandler(
            store=export_store,
            command=export_command,
            handler_binding_digest=export_binding.binding_digest,
            interpreter_profile_digest=export_binding.interpreter_profile_digest,
            operation_contract_digest=export_binding.operation_contract_digest,
            deployment_catalog_digest=export_binding.deployment_catalog_digest,
        )
        if c8_3_cell.status == "UNWIRED_DECLARED":
            c8_3_cell = _installed_knowledge_report__export_token_cell(
                export_handler,
                declared=c8_3_binding.declared_cell(),
            )
        else:
            c8_3_cell = dataclasses.replace(
                c8_3_cell,
                operation_contract_refs=c8_3_cell.operation_contract_refs
                + (_KNOWLEDGE_REPORT__EXPORT_TOKEN_OPERATION_REF,),
                note=(
                    c8_3_cell.note
                    + "; knowledge.report.v2 typed report-export/token-state successor route "
                    "additionally installed; no credential value stored"
                ),
            )
        handlers.append(export_handler)

    c8_1_cell = c8_1_binding.declared_cell()
    if c8_options.c81_payload is not None:
        if not isinstance(c8_options.c81_payload, Mapping):
            raise ValueError("knowledge.read.v2 options c81_payload must be a mapping")
        c8_1_handler = _build_knowledge_read__route_handler(
            project_scope_digest=project_scope_digest,
            payload=c8_options.c81_payload,
            native_composition=selected_native_composition,
        )
        c8_1_cell = c8_1_binding.installed_cell(c8_1_handler.handler_binding_digest)
        handlers.append(c8_1_handler)

    c8_2_cell = c8_2_binding.declared_cell()
    if c8_options.c82_payload is not None:
        if not isinstance(c8_options.c82_payload, Mapping):
            raise ValueError("knowledge.writing.v2 options c82_payload must be a mapping")
        c8_2_handler = _build_knowledge_writing__route_handler(
            project_scope_digest=project_scope_digest,
            payload=c8_options.c82_payload,
            native_composition=selected_native_composition,
        )
        c8_2_cell = c8_2_binding.installed_cell(c8_2_handler.handler_binding_digest)
        handlers.append(c8_2_handler)

    graph_composition = c8_options.graph_projection_composition
    graph_native_contributions = (
        compose_default_knowledge_graph_projection_contributions()
        if graph_composition is None
        else validate_knowledge_graph_projection_contributions(graph_composition)
    )
    graph_bindings = []
    for native in graph_native_contributions:
        graph_binding = native.assemble(KnowledgeGraphProjectionAssemblyContext())
        if isinstance(graph_binding, Failure):
            raise ValueError(
                f"native graph contribution {native.projection.id} invalid: "
                f"{graph_binding.message}"
            )
        graph_bindings.append(graph_binding)

    graph_cells: list[CellBinding] = []
    graph_wirings: list[ProjectorWiring] = []
    graph_rollback_bindings: list[Any] = []
    projector_registry = None
    for graph_binding in graph_bindings:
        source_key = (projector_source_keys or {}).get(graph_binding.cell_id)
        if source_key is None:
            graph_cells.append(graph_binding.unbound_cell())
        else:
            installed = graph_binding.install(source_key)
            if installed is None:
                raise ValueError(
                    f"{graph_binding.cell_id} has a source key but no projector wiring"
                )
            installed_cell, installed_registry = installed
            graph_cells.append(installed_cell)
            if projector_registry is None:
                projector_registry = installed_registry
            else:
                projector_registry = dataclasses.replace(
                    projector_registry,
                    projectors=(
                        projector_registry.projectors + installed_registry.projectors
                    ),
                )
        if graph_binding.projector_wiring is not None:
            graph_wirings.append(graph_binding.assembly_projector_wiring())
        graph_rollback_bindings.append(graph_binding.assembly_rollback_binding())

    cells = (c8_1_cell, c8_2_cell, c8_3_cell, *graph_cells)
    observed_cell_ids = tuple(cell.cell_id for cell in cells)
    if observed_cell_ids[: len(ASSEMBLY_CELL_IDS)] != ASSEMBLY_CELL_IDS:
        raise ValueError(
            "knowledge assembly lost or reordered an authored cell: "
            f"expected prefix {ASSEMBLY_CELL_IDS}, observed {observed_cell_ids}"
        )
    c8_3_rollback = c8_3_binding.assembly_rollback_binding()
    if export_token_installed:
        c8_3_rollback = dataclasses.replace(
            c8_3_rollback,
            binding_refs=c8_3_rollback.binding_refs
            + (_KNOWLEDGE_REPORT__EXPORT_TOKEN_HANDLER_MODULE,),
        )
    rollback_bindings = (
        c8_1_binding.assembly_rollback_binding(),
        c8_2_binding.assembly_rollback_binding(),
        c8_3_rollback,
        *graph_rollback_bindings,
    )
    return FamilyAssembly(
        family_id=KNOWLEDGE_FAMILY_ID,
        cells=cells,
        handlers=tuple(handlers),
        recovery_handlers=tuple(recovery_handlers),
        projector_wiring=tuple(graph_wirings),
        projector_registry=projector_registry,
        rollback_bindings=tuple(rollback_bindings),
    )


__all__ = [
    "ASSEMBLY_CELL_IDS",
    "KNOWLEDGE_READ_ROLLBACK_REF",
    "KNOWLEDGE_WRITING_ROLLBACK_REF",
    "KNOWLEDGE_REPORT_ROLLBACK_REF",
    "KNOWLEDGE_GRAPH_PROJECTION_DECLARED_LOSS",
    "KNOWLEDGE_GRAPH_PROJECTION_ROLLBACK_REF",
    "KNOWLEDGE_FAMILY_ID",
    "KnowledgeDemandReadRouteHandler",
    "KnowledgeWritingComposeStageRouteHandler",
    "KNOWLEDGE_DEMAND_READ_FAILURE_CODE",
    "KNOWLEDGE_WRITING_STAGE_FAILURE_CODE",
    "build_knowledge_assembly",
    "build_deterministic_knowledge_delivery_closure",
    "build_deterministic_knowledge_payloads",
]
