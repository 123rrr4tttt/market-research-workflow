"""C8 family assembly: installable pure route handlers plus the C8.3 bridge.

``build_postgres_c8_delivery_assembly`` is reused byte-for-byte when the caller
supplies its exact dependencies; otherwise C8.3 stays unwired.  C8.1/C8.2 are
installed as pure RuntimeHandler route closures only when deterministic
c81/c82 payloads are supplied.  The route handlers never write a database and
never call admission/export.  C8.4 declares the exact ``c8.graph.projector``
identity without inventing a per-run source key or a PostgreSQL write.  When
the run owner supplies a per-run source key, the builder constructs one
read-only projector contract, registers it in the family ``ProjectorRegistry``
and installs C8.4; without a key, C8.4 stays ``PROJECTOR_WIRING_DECLARED``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import Engine

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    C8AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    ProjectorRegistry,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
    validate_projector_contract,
)
from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_graph import (
    GRAPH_CONTEXT_PROJECTION,
    GRAPH_PROJECTION_SCHEMA,
)
from app.successor_runtime.capabilities.c8_program import (
    C8_1_KIND,
    C8_2_COMPOSE_KIND,
    C8_2_STAGE_KIND,
    C8_3_KIND,
    C8_DELIVERY_INTENT_TYPE,
    C8_RESEARCH_ARTIFACT_TYPE,
    DELIVERY_INTERNAL_EXPORT_KIND,
    C8CapabilityBundle,
    C8DemandReadInput,
    C8ReportStageInput,
    C8WritingComposeInput,
    build_c8_bundle,
    build_c8_catalog,
    build_c8_delivery_bridge_bundle,
    build_c8_delivery_bridge_program,
    compile_c8_delivery_bridge_program,
    exact_contract_ref,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_writing import (
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
    C8_3ExportTokenStateRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.c8_graph_projector import (
    C8_GRAPH_PROJECTOR_ID,
    C8_GRAPH_PROJECTOR_VERSION,
    C8_GRAPH_SOURCE_KIND,
    C8_GRAPH_VALUE_SCHEMA,
)
from app.successor_runtime.substrate.postgres.c8_production import (
    build_postgres_c8_delivery_assembly,
)
from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    build_c8_delivery_activation_catalog,
)

C8_FAMILY_ID = "C8"

C8_1_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_typed_knowledge.py"
C8_2_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_writing.py"
C8_3_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_report.py"
C8_4_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_graph.py"
C8_ROUTE_ASSEMBLY_ROLLBACK_REF = (
    "main/backend/app/successor_runtime/assembly/c8_assembly.py"
)

C8_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.successor.deployment-catalog.c8.v1")
C8_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.successor.c8.authority.v1")
C8_1_INTERPRETER_PROFILE_DIGEST = sha256_hex("successor.c8.c8-1.v1")
C8_2_INTERPRETER_PROFILE_DIGEST = sha256_hex("successor.c8.c8-2.v1")
C8_2_ROUTE_OPERATION_KINDS = (C8_2_COMPOSE_KIND, C8_2_STAGE_KIND)
_C8_3_EXPORT_TOKEN_OPERATION_REF = "c8.report.export_token_state.v1"
_C8_3_EXPORT_TOKEN_OPERATION_DIGEST = sha256_hex(
    "mrw.successor.c8-3.report-export-token-state.operation.v1"
)
_C8_3_EXPORT_TOKEN_INTERPRETER_DIGEST = sha256_hex(
    "successor.c8.report-export-token-state.v1"
)
_C8_3_EXPORT_TOKEN_AUTHORITY_DIGEST = sha256_hex(
    "mrw.successor.c8-3.report-export-token-state.authority.v1"
)
_C8_3_EXPORT_TOKEN_HANDLER_MODULE = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "c8_export_token_state_handler.py"
)

C8_REHEARSAL_PROJECT_KEY = "mrw-successor-c8-local"
C8_REHEARSAL_ITEM_KEY = "ki:successor-c8-demand-read"
C8_REHEARSAL_STATEMENT = (
    "MRW functorial successor C8 local-offline typed knowledge item."
)
C8_REHEARSAL_SELECTION_HASH = "selection:successor-c8-local"
C8_REHEARSAL_SELECTION_TEXT = "successor runtime local-offline writing selection"
C8_REHEARSAL_FIELDS = ("canonical_statement", "evidence_refs")

C8_3_DELIVERY_PROJECT_KEY = "mrw-successor-c8-3-local"
C8_3_DELIVERY_PROGRAM_ID = "program:successor-c8-3-local"
C8_3_DELIVERY_REPORT_ID = "report:successor-c8-3-local"
C8_3_DELIVERY_TOPIC = "LOCAL_OFFLINE C8.3 delivery bridge closure"
C8_3_DELIVERY_AUTHORITY_DIGEST = sha256_hex("mrw.successor.c8-3.delivery-authority.v1")
C8_3_DELIVERY_RESOURCE_POLICY_DIGEST = sha256_hex(
    "mrw.successor.c8-3.resource-policy.v1"
)
C8_3_DELIVERY_NODE_PROFILE_SELECTOR = sha256_hex("mrw.successor.c8-3.node-profile.v1")

C8_4_DECLARED_LOSS = (
    "c8.graph.node-edge-filtering.v1",
    "c8.graph.text-truncation.v1",
    "c8.graph.redaction.v1",
    "c8.graph.casefold-and-duplicate-collapse.v1",
    "c8.graph.omitted-fields.v1",
)


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


class C8_1DemandReadRouteHandler(RuntimeHandler):
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
                f"C8.1 payload lacks required closure field {exc.args[0]!r}"
            ) from exc
        self._items = tuple(items)
        if (
            not self._items
            or not self._item_key
            or not self._fields
            or not self._project_key
        ):
            raise ValueError(
                "C8.1 payload requires non-empty items/item_key/fields/project_key"
            )
        if not all(isinstance(item, c8.KnowledgeItem) for item in self._items):
            raise ValueError("C8.1 payload items must be KnowledgeItem values")
        registry = payload.get("registry")
        if registry is not None and not isinstance(registry, c8.ReadHandleRegistry):
            raise ValueError("C8.1 payload registry must be a ReadHandleRegistry")
        self._registry = registry if registry is not None else c8.ReadHandleRegistry()
        require_assembly_digest(
            deployment_catalog_digest,
            "C8.1 deployment catalog digest",
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
        except c8.C8ProjectionError as exc:
            raise DefiniteInterpreterFailure("C8_1_DEMAND_READ_FAILED") from exc
        return InterpreterOutcome.succeeded(content_digest(read))


class C8_2WritingComposeStageRouteHandler(RuntimeHandler):
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
                f"C8.2 payload lacks required closure field {exc.args[0]!r}"
            ) from exc
        if not isinstance(read, c8.KnowledgeRead):
            raise TypeError("C8.2 payload read must be a KnowledgeRead")
        if not self._selection_hash or not self._selection_text:
            raise ValueError("C8.2 payload requires non-empty selection inputs")
        self._read = read
        require_assembly_digest(
            deployment_catalog_digest,
            "C8.2 deployment catalog digest",
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
        except c8.UnavailableProjection as exc:
            raise DefiniteInterpreterFailure("C8_2_WRITING_STAGE_FAILED") from exc
        return InterpreterOutcome.succeeded(content_digest(artifact))


def _unwired_c8_1_cell() -> CellBinding:
    return CellBinding(
        cell_id="C8.1",
        family_id=C8_FAMILY_ID,
        status="UNWIRED_DECLARED",
        operation_contract_refs=("c8.typed_knowledge.demand_read.v1",),
        recovery_binding_ref=(
            "c8.typed_knowledge.recovery.v1#route-back-to-legacy-repository-"
            "read-handle-retained;no-dual-write"
        ),
        required_wiring=(
            "c81_payload demand-read 纯 route closure",
            "admission_not_called/export_not_executed 保持",
        ),
        note=(
            "缺 c81_payload 的 demand_read 纯 route closure"
            "（item(s)/item_key/fields/project_key/registry）；"
            "admission/export authority closed"
        ),
    )


def _installed_c8_1_cell(handler: C8_1DemandReadRouteHandler) -> CellBinding:
    return CellBinding(
        cell_id="C8.1",
        family_id=C8_FAMILY_ID,
        status="INSTALLED",
        operation_contract_refs=("c8.typed_knowledge.demand_read.v1",),
        handler_binding_digest=handler.handler_binding_digest,
        recovery_binding_ref=(
            "c8.typed_knowledge.recovery.v1#route-back-to-legacy-repository-"
            "read-handle-retained;no-dual-write"
        ),
        required_wiring=("admission_not_called/export_not_executed 保持",),
        note=(
            "LOCAL_OFFLINE C8.1 demand_read pure route handler installed; "
            "read-only; no PostgreSQL write adopted"
        ),
    )


def _unwired_c8_2_cell() -> CellBinding:
    return CellBinding(
        cell_id="C8.2",
        family_id=C8_FAMILY_ID,
        status="UNWIRED_DECLARED",
        operation_contract_refs=("c8.writing.compose.v1", "c8.writing.stage.v1"),
        recovery_binding_ref=(
            "c8.writing.recovery.v1#retained-staged-values-no-authority-reversal"
        ),
        required_wiring=(
            "c82_payload compose+stage 纯 route closure",
            "admission_not_called/export_not_executed 保持",
        ),
        note=(
            "缺 c82_payload 的 compose_writing_handoff + stage_writing_artifact "
            "纯 route closure（read/handoff 输入）；"
            "admission/export authority closed"
        ),
    )


def _installed_c8_2_cell(handler: C8_2WritingComposeStageRouteHandler) -> CellBinding:
    return CellBinding(
        cell_id="C8.2",
        family_id=C8_FAMILY_ID,
        status="INSTALLED",
        operation_contract_refs=("c8.writing.compose.v1", "c8.writing.stage.v1"),
        handler_binding_digest=handler.handler_binding_digest,
        recovery_binding_ref=(
            "c8.writing.recovery.v1#retained-staged-values-no-authority-reversal"
        ),
        required_wiring=("admission_not_called/export_not_executed 保持",),
        note=(
            "LOCAL_OFFLINE C8.2 compose+stage pure route handler installed; "
            "no PostgreSQL write adopted"
        ),
    )


def _unwired_c8_3_cell() -> CellBinding:
    return CellBinding(
        cell_id="C8.3",
        family_id=C8_FAMILY_ID,
        status="UNWIRED_DECLARED",
        operation_contract_refs=(
            "c8.report.stage.v1",
            "c8.report.admission.v1",
            "c8.report.delivery.v1",
        ),
        recovery_binding_ref=(
            "c8.report.admission.recovery.v1#verification-and-receipt-readback-only;"
            "no-repeat-export"
        ),
        required_wiring=(
            "app 层调用方/挂载",
            "admission/export authority gate 保持关闭",
        ),
        note=(
            "build_postgres_c8_delivery_assembly exists but no app caller "
            "instantiates it; admission/export authority gate stays closed"
        ),
    )


def _installed_c8_3_cell(
    *,
    bundle: C8CapabilityBundle,
    delivery_assembly: Any,
) -> CellBinding:
    """Resolve the exact C8.3 handler binding from the delivery assembly."""

    matches = tuple(
        operation for operation in bundle.operations if operation.ref.kind == C8_3_KIND
    )
    if len(matches) != 1:
        raise ValueError(
            f"C8 capability bundle must contain one exact {C8_3_KIND} operation"
        )
    operation_digest = matches[0].ref.contract_digest
    handlers = tuple(
        handler
        for handler in delivery_assembly.handlers
        if getattr(handler, "operation_contract_digest", None) == operation_digest
    )
    if len(handlers) != 1:
        raise ValueError(
            "C8 delivery assembly must contain one exact C8.3 handler "
            "for the C8_3_KIND operation"
        )
    return CellBinding(
        cell_id="C8.3",
        family_id=C8_FAMILY_ID,
        status="INSTALLED",
        operation_contract_refs=(
            "c8.report.stage.v1",
            "c8.report.admission.v1",
            "c8.report.delivery.v1",
        ),
        handler_binding_digest=handlers[0].handler_binding_digest,
        recovery_binding_ref=(
            "c8.report.admission.recovery.v1#verification-and-receipt-readback-only;"
            "no-repeat-export"
        ),
        required_wiring=(
            "app 层调用方/挂载",
            "admission/export authority gate 保持关闭",
        ),
        note=(
            "reuses build_postgres_c8_delivery_assembly unchanged; exact "
            "C8.3 handler binding digest from the installed bridge"
        ),
    )


def _installed_c8_3_export_token_cell(
    handler: C8_3ExportTokenStateRuntimeHandler,
) -> CellBinding:
    """Install C8.3 through the typed export/token-state successor route."""

    return CellBinding(
        cell_id="C8.3",
        family_id=C8_FAMILY_ID,
        status="INSTALLED",
        operation_contract_refs=(
            "c8.report.stage.v1",
            "c8.report.admission.v1",
            "c8.report.delivery.v1",
            _C8_3_EXPORT_TOKEN_OPERATION_REF,
        ),
        handler_binding_digest=handler.handler_binding_digest,
        recovery_binding_ref=(
            "c8.report.admission.recovery.v1#verification-and-receipt-readback-only;"
            "no-repeat-export"
        ),
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


def _c8_operation_contract_digest(kind: str) -> str:
    return exact_contract_ref(
        build_c8_catalog(build_c8_bundle()),
        kind=kind,
    ).contract_digest


def _build_c8_1_route_handler(
    *,
    project_scope_digest: str,
    payload: Mapping[str, Any],
) -> C8_1DemandReadRouteHandler:
    binding = successor_binding(
        operation_contract_digest=_c8_operation_contract_digest(C8_1_KIND),
        interpreter_profile_digest=C8_1_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=C8_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return C8_1DemandReadRouteHandler(
        payload=payload,
        binding=binding,
        deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
    )


def _build_c8_2_route_handler(
    *,
    project_scope_digest: str,
    payload: Mapping[str, Any],
) -> C8_2WritingComposeStageRouteHandler:
    catalog = build_c8_catalog(build_c8_bundle())
    for kind in C8_2_ROUTE_OPERATION_KINDS:
        exact_contract_ref(catalog, kind=kind)
    binding = successor_binding(
        operation_contract_digest=exact_contract_ref(
            catalog,
            kind=C8_2_COMPOSE_KIND,
        ).contract_digest,
        interpreter_profile_digest=C8_2_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=C8_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return C8_2WritingComposeStageRouteHandler(
        payload=payload,
        binding=binding,
        deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
    )


def _c8_3_delivery_value_ref(
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


def build_deterministic_c8_delivery_closure(
    project_scope_digest: str,
) -> dict[str, Any]:
    """Build the deterministic LOCAL_OFFLINE C8.3 delivery-bridge closure.

    Returns exactly the ``bundle``, ``activation_catalog`` and
    ``delivery_interpreter`` dependencies required by
    ``build_postgres_c8_delivery_assembly``.  Assembly construction performs
    no database, provider or filesystem write; bridge execution stays closed
    under the I1 authority ceiling.
    """

    require_assembly_digest(project_scope_digest, "C8.3 delivery project scope digest")
    first = build_first_specimen_bundle()
    delivery_operation = first.operation_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    delivery_codec = first.codec_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    bundle = build_c8_delivery_bridge_bundle(delivery_operation, delivery_codec)
    catalog = build_c8_catalog(bundle)
    stage_payload = C8ReportStageInput(
        project_key=C8_3_DELIVERY_PROJECT_KEY,
        report_id=C8_3_DELIVERY_REPORT_ID,
        topic=C8_3_DELIVERY_TOPIC,
        source_keys=("knowledge:successor-c8-3-local",),
    )
    program = normalize_program(
        build_c8_delivery_bridge_program(
            delivery_operation=delivery_operation,
            delivery_codec=delivery_codec,
            delivery_payload_ref=_c8_3_delivery_value_ref(
                program_id=C8_3_DELIVERY_PROGRAM_ID,
                project_key=C8_3_DELIVERY_PROJECT_KEY,
                suffix="internal-export-input",
                object_type=ObjectType("InternalExportInput.v1"),
                codec_id=delivery_codec.codec_id,
            ),
            artifact_input_ref=_c8_3_delivery_value_ref(
                program_id=C8_3_DELIVERY_PROGRAM_ID,
                project_key=C8_3_DELIVERY_PROJECT_KEY,
                suffix="research-artifact",
                object_type=C8_RESEARCH_ARTIFACT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            intent_input_ref=_c8_3_delivery_value_ref(
                program_id=C8_3_DELIVERY_PROGRAM_ID,
                project_key=C8_3_DELIVERY_PROJECT_KEY,
                suffix="delivery-intent",
                object_type=C8_DELIVERY_INTENT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            stage_payload=stage_payload,
            catalog=catalog,
            program_id=C8_3_DELIVERY_PROGRAM_ID,
            project_key=C8_3_DELIVERY_PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=project_scope_digest,
        )
    )
    plan = compile_c8_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=OperationContractRegistry(catalog, bundle.operations),
    )
    eligibility = QueueEligibility(
        project_key=C8_3_DELIVERY_PROJECT_KEY,
        capability_id="report.c8.3.v1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=C8_3_DELIVERY_RESOURCE_POLICY_DIGEST,
        concurrency_key="report.c8.3.v1",
    )
    activation_catalog = build_c8_delivery_activation_catalog(
        plan,
        interpreter_profile_digest=bundle.profiles["C8.3"][
            "interpreter"
        ].profile_digest,
        deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=C8_3_DELIVERY_AUTHORITY_DIGEST,
        resource_policy_digest=C8_3_DELIVERY_RESOURCE_POLICY_DIGEST,
        required_node_profile_selector=C8_3_DELIVERY_NODE_PROFILE_SELECTOR,
        fairness_key=C8_3_DELIVERY_PROJECT_KEY,
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


def build_deterministic_c8_payloads(project_scope_digest: str) -> dict[str, Any]:
    """Build deterministic LOCAL_OFFLINE C8.1/C8.2 payloads.

    The payloads carry enough typed values for the pure route handlers to run
    without any database, provider or legacy import.
    """

    require_assembly_digest(project_scope_digest, "C8 payload project scope digest")
    item_body = c8.KnowledgeItem(
        key=C8_REHEARSAL_ITEM_KEY,
        project_key=C8_REHEARSAL_PROJECT_KEY,
        canonical_statement=C8_REHEARSAL_STATEMENT,
        primary_type_node_key="tn:successor-runtime",
        evidence_refs=("ev:successor-c8-1",),
        topic_cluster_keys=("tc:successor-runtime",),
        review_state="human_confirmed",
        quality_grade="gold",
        locale="zh",
        visibility_scope="downstream_ready",
    )
    item = dataclasses.replace(
        item_body,
        canonical_ref=c8.derived_canonical_ref(item_body),
    )
    registry = c8.ReadHandleRegistry()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=C8_REHEARSAL_FIELDS,
        project_key=C8_REHEARSAL_PROJECT_KEY,
        registry=registry,
    )
    c81_payload: dict[str, Any] = {
        "schema": "mrw.successor.c8.c81-payload.v1",
        "LOCAL_OFFLINE": True,
        "note": "LOCAL_OFFLINE deterministic demand-read closure; no DB/provider write",
        "project_scope_digest": project_scope_digest,
        "project_key": C8_REHEARSAL_PROJECT_KEY,
        "item_key": item.key,
        "fields": C8_REHEARSAL_FIELDS,
        "items": (item,),
        "registry": registry,
        "input": C8DemandReadInput(
            project_key=C8_REHEARSAL_PROJECT_KEY,
            item_key=item.key,
            fields=C8_REHEARSAL_FIELDS,
        ),
    }
    c82_payload: dict[str, Any] = {
        "schema": "mrw.successor.c8.c82-payload.v1",
        "LOCAL_OFFLINE": True,
        "note": (
            "LOCAL_OFFLINE deterministic compose+stage closure; no DB/provider write"
        ),
        "project_scope_digest": project_scope_digest,
        "project_key": C8_REHEARSAL_PROJECT_KEY,
        "read": read,
        "selection_hash": C8_REHEARSAL_SELECTION_HASH,
        "selection_text": C8_REHEARSAL_SELECTION_TEXT,
        "input": C8WritingComposeInput(
            project_key=C8_REHEARSAL_PROJECT_KEY,
            knowledge_item_key=item.key,
            selection_hash=C8_REHEARSAL_SELECTION_HASH,
            selection_text=C8_REHEARSAL_SELECTION_TEXT,
            demand_fields=C8_REHEARSAL_FIELDS,
        ),
    }
    return {"c81_payload": c81_payload, "c82_payload": c82_payload}


def build_c8_assembly(
    *,
    engine: Engine,
    project_scope_digest: str,
    options: C8AssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
) -> FamilyAssembly:
    """Build the C8 family assembly with optional route/bridge installation.

    C8.4 stays ``PROJECTOR_WIRING_DECLARED`` until the run owner supplies a
    per-run source key; with a key it registers one read-only projector
    contract in the family registry and becomes ``INSTALLED``.
    """

    require_assembly_digest(project_scope_digest, "C8 project scope digest")
    c8_options = options or C8AssemblyOptions()
    c8_3_cell = _unwired_c8_3_cell()
    handlers: list[Any] = []
    recovery_handlers: list[Any] = []
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
        c8_3_cell = _installed_c8_3_cell(
            bundle=c8_options.bundle,
            delivery_assembly=delivery_assembly,
        )
        handlers.extend(delivery_assembly.handlers)
        recovery_handlers.extend(delivery_assembly.recovery_handlers)

    export_store = c8_options.export_token_store
    export_command = c8_options.export_token_command
    if (export_store is None) != (export_command is None):
        raise ValueError(
            "C8.3 export/token-state wiring requires both export_token_store "
            "and export_token_command"
        )
    export_token_installed = export_store is not None
    if export_token_installed:
        export_binding = successor_binding(
            operation_contract_digest=_C8_3_EXPORT_TOKEN_OPERATION_DIGEST,
            interpreter_profile_digest=_C8_3_EXPORT_TOKEN_INTERPRETER_DIGEST,
            deployment_catalog_digest=C8_DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=project_scope_digest,
            authority_requirement_digest=_C8_3_EXPORT_TOKEN_AUTHORITY_DIGEST,
        )
        export_handler = C8_3ExportTokenStateRuntimeHandler(
            store=export_store,
            command=export_command,
            handler_binding_digest=export_binding.binding_digest,
            interpreter_profile_digest=export_binding.interpreter_profile_digest,
            operation_contract_digest=export_binding.operation_contract_digest,
            deployment_catalog_digest=export_binding.deployment_catalog_digest,
        )
        if c8_3_cell.status == "UNWIRED_DECLARED":
            c8_3_cell = _installed_c8_3_export_token_cell(export_handler)
        else:
            c8_3_cell = dataclasses.replace(
                c8_3_cell,
                operation_contract_refs=c8_3_cell.operation_contract_refs
                + (_C8_3_EXPORT_TOKEN_OPERATION_REF,),
                note=(
                    c8_3_cell.note
                    + "; C8.3 typed report-export/token-state successor route "
                    "additionally installed; no credential value stored"
                ),
            )
        handlers.append(export_handler)

    c8_1_cell = _unwired_c8_1_cell()
    if c8_options.c81_payload is not None:
        if not isinstance(c8_options.c81_payload, Mapping):
            raise ValueError("C8.1 options c81_payload must be a mapping")
        c8_1_handler = _build_c8_1_route_handler(
            project_scope_digest=project_scope_digest,
            payload=c8_options.c81_payload,
        )
        c8_1_cell = _installed_c8_1_cell(c8_1_handler)
        handlers.append(c8_1_handler)

    c8_2_cell = _unwired_c8_2_cell()
    if c8_options.c82_payload is not None:
        if not isinstance(c8_options.c82_payload, Mapping):
            raise ValueError("C8.2 options c82_payload must be a mapping")
        c8_2_handler = _build_c8_2_route_handler(
            project_scope_digest=project_scope_digest,
            payload=c8_options.c82_payload,
        )
        c8_2_cell = _installed_c8_2_cell(c8_2_handler)
        handlers.append(c8_2_handler)

    c8_4_wiring = ProjectorWiring(
        cell_id="C8.4",
        projector_id=C8_GRAPH_PROJECTOR_ID,
        projector_version=C8_GRAPH_PROJECTOR_VERSION,
        source_kind=C8_GRAPH_SOURCE_KIND,
        projection_id=GRAPH_CONTEXT_PROJECTION,
        projection_schema_ref=C8_GRAPH_VALUE_SCHEMA,
        declared_loss=C8_4_DECLARED_LOSS,
        note=(
            "capability schema: "
            f"{GRAPH_PROJECTION_SCHEMA}; exact per-run source key "
            "is supplied by the runner"
        ),
    )
    c8_4_source_key = (projector_source_keys or {}).get("C8.4")
    if c8_4_source_key is None:
        c8_4_status = "PROJECTOR_WIRING_DECLARED"
        c8_4_binding_digest = None
        c8_4_required_wiring: tuple[str, ...] = (
            "C8.4 RuntimeHandler/注册",
            "declared-loss projection 记账",
        )
        c8_4_note = (
            "缺 per-run source_ref/source_incarnation 与 ProjectorRegistry "
            "注册；no PostgreSQL write adopted（authority 关闭）"
        )
        c8_4_registry = None
    else:
        c8_4_contract = c8_4_wiring.to_contract(c8_4_source_key)
        c8_4_validation = validate_projector_contract(c8_4_contract)
        if not c8_4_validation.valid:
            raise ValueError(
                "C8.4 projector contract invalid: "
                + "; ".join(item.message for item in c8_4_validation.violations)
            )
        c8_4_binding_digest = c8_4_wiring.registration_digest(c8_4_contract)
        c8_4_registry = ProjectorRegistry(
            revision=0,
            incarnation=PROJECTOR_REGISTRY_INCARNATION,
            projectors=(c8_4_contract,),
        )
        c8_4_status = "INSTALLED"
        c8_4_required_wiring = ()
        c8_4_note = (
            "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED: "
            "per-run source_ref/source_incarnation bound；no PostgreSQL "
            "write adopted"
        )

    cells = (
        c8_1_cell,
        c8_2_cell,
        c8_3_cell,
        CellBinding(
            cell_id="C8.4",
            family_id=C8_FAMILY_ID,
            status=c8_4_status,
            operation_contract_refs=("c8.graph.project.v1",),
            handler_binding_digest=c8_4_binding_digest,
            recovery_binding_ref=(
                "c8.graph.recovery.v1#offset-cas-keeps-old-active-generation;"
                "rebuild-from-source-closure"
            ),
            required_wiring=c8_4_required_wiring,
            note=c8_4_note,
        ),
    )
    c8_4_wiring_tuple = (c8_4_wiring,)
    c8_3_rollback_refs = (C8_3_ROLLBACK_REF,)
    if export_token_installed:
        c8_3_rollback_refs += (_C8_3_EXPORT_TOKEN_HANDLER_MODULE,)
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id="C8.1",
            status="PRESENT",
            binding_refs=(C8_1_ROLLBACK_REF, C8_ROUTE_ASSEMBLY_ROLLBACK_REF),
        ),
        RollbackBindingDeclaration(
            cell_id="C8.2",
            status="PRESENT",
            binding_refs=(C8_2_ROLLBACK_REF, C8_ROUTE_ASSEMBLY_ROLLBACK_REF),
        ),
        RollbackBindingDeclaration(
            cell_id="C8.3",
            status="PRESENT",
            binding_refs=c8_3_rollback_refs,
        ),
        RollbackBindingDeclaration(
            cell_id="C8.4",
            status="PRESENT",
            binding_refs=(C8_4_ROLLBACK_REF,),
        ),
    )
    return FamilyAssembly(
        family_id=C8_FAMILY_ID,
        cells=cells,
        handlers=tuple(handlers),
        recovery_handlers=tuple(recovery_handlers),
        projector_wiring=c8_4_wiring_tuple,
        projector_registry=c8_4_registry,
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "C8_1_ROLLBACK_REF",
    "C8_2_ROLLBACK_REF",
    "C8_3_ROLLBACK_REF",
    "C8_4_DECLARED_LOSS",
    "C8_4_ROLLBACK_REF",
    "C8_FAMILY_ID",
    "C8_1DemandReadRouteHandler",
    "C8_2WritingComposeStageRouteHandler",
    "build_c8_assembly",
    "build_deterministic_c8_delivery_closure",
    "build_deterministic_c8_payloads",
]
