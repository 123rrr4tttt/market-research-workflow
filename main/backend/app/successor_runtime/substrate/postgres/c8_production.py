"""C8 family-local PostgreSQL production trust-root composition.

This module is the single assembly root for production C8 authority.  It owns
module-private production seals, no-overwrite witness registries and opaque
nominal production handles; ordinary callers cannot construct, mint or inject
an authority token, registry, verifier, loss profile, active projection state,
receipt digest or canonical commit ref.  Every production operation starts
from a durable locator, exact-reads the current PostgreSQL state, deep-freezes
and recomputes content, and issues a fresh process-local witness.  Fresh
sessions re-issue witnesses from durable locators; old process witnesses are
never treated as persisted authority.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import MetaData
from sqlalchemy.engine import Connection, Engine

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_consumer import (
    consume_graph_projection,
)
from app.successor_runtime.capabilities.c8_program import (
    C8_3_KIND,
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    C8_VERIFY_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
    C8CapabilityBundle,
)
from app.successor_runtime.capabilities.c8_report import (
    build_report_admission_intent_v2,
    build_report_delivery_intent_v2,
    build_report_stage,
    confirm_report_admission_readback,
    prepare_report_export,
    verify_report_stage,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import (
    IssuedKnowledgeRead,
    StrictReadHandleRegistry,
    strict_issued_demand_read,
)
from app.successor_runtime.capabilities.c8_writing import (
    compose_markdown_draft,
    validate_citation_closure,
)
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionCoordinator,
    AdmissionRegistration,
    ExactAdmissionRegistry,
)
from app.successor_runtime.runtime.node import (
    Clock,
    DeploymentBinding,
    NodeIdentity,
    RuntimeHandler,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import ControlPlaneScope, RuntimeScope
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
    InternalExportReadbackFacade,
)
from app.successor_runtime.substrate.postgres.c8_artifact_handler import (
    C8ArtifactReadback,
    C8BridgeEffectHandler,
    C8BridgeEffectStore,
    C8BridgeHandlerInstallation,
    admit_artifact,
    read_staged_artifact,
    readback_artifact,
    stage_artifact,
    verify_artifact,
)
from app.successor_runtime.substrate.postgres.c8_graph_projector import (
    project_graph_generation as project_graph_generation_db,
)
from app.successor_runtime.substrate.postgres.c8_graph_projector import (
    read_active_graph,
)
from app.successor_runtime.substrate.postgres.c8_material_handler import (
    C8StoredKnowledgeValue,
    form_knowledge_candidate,
    read_canonical_material,
    read_staged_knowledge_value,
    stage_knowledge_value,
)
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    compose_postgres_first_specimen_runtime,
)
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    FirstSpecimenActivationCatalog,
    PostgresFirstSpecimenActivationPort,
)
from app.successor_runtime.substrate.postgres.first_specimen_assembly import (
    FirstSpecimenOperationHandler,
)
from app.successor_runtime.substrate.postgres.first_specimen_delivery_gate import (
    FirstSpecimenDeliveryGateRequest,
    PostgresFirstSpecimenDeliveryGate,
)
from app.successor_runtime.substrate.postgres.first_specimen_delivery_handler import (
    FirstSpecimenDeliveryEffectStore,
    InstalledFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryReplay,
)
from app.successor_runtime.substrate.postgres.first_specimen_reconciliation_handler import (
    InstalledFirstSpecimenReconciliationHandler,
    PostgresFirstSpecimenLocalReconciliationHandler,
    PostgresFirstSpecimenReconciliationHandler,
)
from app.successor_runtime.substrate.postgres.first_specimen_terminal import (
    PostgresFirstSpecimenTerminalHook,
    PostgresVerifyAdmitHandler,
)
from app.successor_runtime.substrate.postgres.models import (
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
from app.successor_runtime.substrate.postgres.research_admission import (
    PostgresCommitIntentAdapter,
    ResearchAdmissionHandler,
    ResearchAdmissionMode,
    commit_binding_from_assignment,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork

__all__ = [
    "PRODUCTION_AUTHORITY_ID",
    "C8DeliveryUnavailableError",
    "C8PostgresDeliveryAssembly",
    "C8ProductionRoot",
    "C8ProductionTrustRootError",
    "ProductionAdmissionResult",
    "ProductionGraphReadHandle",
    "ProductionGraphWriteResult",
    "ProductionKnowledgeHandle",
    "ProductionMaterialHandle",
    "ProductionVerifierHandle",
    "ProductionWritingResult",
    "build_postgres_c8_delivery_assembly",
]

PRODUCTION_AUTHORITY_ID = "c8.production.v1"
PRODUCTION_AUTHORITY_DIGEST = c8.c8_canonical_digest(
    {"authority_id": PRODUCTION_AUTHORITY_ID}
)
_PRODUCTION_SEAL = object()

FAMILY_LOSS_PROFILE = c8.GraphLossProfile(
    profile_id="mrw.c8.graph-loss.v1",
    filter=("blocked",),
    truncation=("long",),
    redaction=("secret",),
    casefold=True,
    duplicate_collapse=True,
    omitted_fields=("internal_note",),
)


class C8ProductionTrustRootError(RuntimeError):
    """Base fail-closed production trust-root error."""


class C8DeliveryUnavailableError(C8ProductionTrustRootError):
    """Internal delivery attempt is typed unavailable in this milestone."""


class _ProductionAuthority:
    __slots__ = ("_secret", "authority_digest", "authority_id")

    def __init__(self) -> None:
        self.authority_id = PRODUCTION_AUTHORITY_ID
        self.authority_digest = PRODUCTION_AUTHORITY_DIGEST
        self._secret = _PRODUCTION_SEAL


class _ProductionCapability:
    __slots__ = (
        "_secret",
        "authority_digest",
        "authority_id",
        "registry_digest",
        "registry_id",
    )

    def __init__(
        self,
        *,
        registry_id: str,
        registry_digest: str,
        authority_id: str,
        authority_digest: str,
        _secret: object,
    ) -> None:
        self.registry_id = registry_id
        self.registry_digest = registry_digest
        self.authority_id = authority_id
        self.authority_digest = authority_digest
        self._secret = _secret


class _ProductionWitness:
    """Opaque process-local witness; not persisted or deserialized."""

    __slots__ = ("_secret",)

    def __init__(self, *, _secret: object) -> None:
        self._secret = _secret


class ProductionMaterialWitness(_ProductionWitness):
    __slots__ = ("attestation_digest", "material_identity")

    def __init__(
        self,
        *,
        material_identity: str,
        attestation_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.material_identity = material_identity
        self.attestation_digest = attestation_digest


class ProductionVerifierWitness(_ProductionWitness):
    __slots__ = ("object_digest", "verification_id")

    def __init__(
        self,
        *,
        verification_id: str,
        object_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.verification_id = verification_id
        self.object_digest = object_digest


class ProductionLossWitness(_ProductionWitness):
    __slots__ = ("profile_digest", "profile_id")

    def __init__(
        self,
        *,
        profile_id: str,
        profile_digest: str,
        _secret: object,
    ) -> None:
        super().__init__(_secret=_secret)
        self.profile_id = profile_id
        self.profile_digest = profile_digest


class _ProductionRegistry:
    """Module-private no-overwrite registry bound to the production seal."""

    def __init__(self, registry_prefix: str) -> None:
        self._authority = _ProductionAuthority()
        self.authority_id = self._authority.authority_id
        self.authority_digest = self._authority.authority_digest
        self.registry_id = f"{registry_prefix}.{self.authority_id}"
        self.registry_digest = c8.c8_canonical_digest(
            {
                "registry_id": self.registry_id,
                "authority_id": self.authority_id,
                "authority_digest": self.authority_digest,
            }
        )
        self._entries: dict[str, object] = {}

    def _capability(self) -> _ProductionCapability:
        return _ProductionCapability(
            registry_id=self.registry_id,
            registry_digest=self.registry_digest,
            authority_id=self.authority_id,
            authority_digest=self.authority_digest,
            _secret=self._authority._secret,
        )

    def _check_capability(self, capability: object) -> None:
        if capability._secret is not self._authority._secret:
            raise C8ProductionTrustRootError(
                "production registration capability is not authentic"
            )
        if (
            capability.registry_id != self.registry_id
            or capability.registry_digest != self.registry_digest
            or capability.authority_id != self.authority_id
            or capability.authority_digest != self.authority_digest
        ):
            raise C8ProductionTrustRootError(
                "production registration capability is not bound to this registry"
            )

    def register(self, key: str, value: object, capability: object) -> object:
        self._check_capability(capability)
        existing = self._entries.get(key)
        if existing is not None:
            if existing != value:
                raise C8ProductionTrustRootError(
                    "production registry key rebinding rejected"
                )
            return existing
        self._entries[key] = value
        return value

    def resolve(self, key: str) -> object | None:
        return self._entries.get(key)


class _ProductionMaterialIssuanceRegistry(_ProductionRegistry):
    def __init__(self) -> None:
        super().__init__("c8.material-issuance")
        self._witnesses: dict[str, ProductionMaterialWitness] = {}

    def register_material(
        self,
        material: c8.CanonicalMaterialRead,
        capability: object,
    ) -> ProductionMaterialWitness:
        c8.validate_canonical_material(material)
        existing = self._entries.get(material.material_identity)
        if existing is not None:
            if existing != material:
                raise C8ProductionTrustRootError(
                    "material registry key rebinding rejected"
                )
            return self._witnesses[material.material_identity]
        witness = ProductionMaterialWitness(
            material_identity=material.material_identity,
            attestation_digest=material.attestation_digest,
            _secret=self._authority._secret,
        )
        self._entries[material.material_identity] = material
        self._witnesses[material.material_identity] = witness
        return witness

    def resolve(self, material_identity: str) -> c8.CanonicalMaterialRead | None:
        value = self._entries.get(material_identity)
        return value if isinstance(value, c8.CanonicalMaterialRead) else None


class _ProductionVerifierRegistry(_ProductionRegistry):
    def __init__(self) -> None:
        super().__init__("c8.report-verifier")

    def register_verification(
        self,
        verification: c8.ReportVerification,
        capability: object,
    ) -> ProductionVerifierWitness:
        self._check_capability(capability)
        if verification.state != "VERIFIED":
            raise C8ProductionTrustRootError(
                "only verified report stages are registered"
            )
        existing = self._entries.get(verification.verification_id)
        if existing is not None and existing != verification:
            raise C8ProductionTrustRootError("verifier registry key rebinding rejected")
        if existing is None:
            self._entries[verification.verification_id] = verification
        return ProductionVerifierWitness(
            verification_id=verification.verification_id,
            object_digest=verification.object_digest,
            _secret=self._authority._secret,
        )

    def resolve(self, verification_id: str) -> c8.ReportVerification | None:
        value = self._entries.get(verification_id)
        return value if isinstance(value, c8.ReportVerification) else None


class _ProductionLossProfileRegistry(_ProductionRegistry):
    def __init__(self) -> None:
        super().__init__("c8.graph-loss-profile")

    def register_profile(
        self,
        profile: c8.GraphLossProfile,
        capability: object,
    ) -> ProductionLossWitness:
        self._check_capability(capability)
        existing = self._entries.get(profile.profile_id)
        if existing is not None and existing != profile:
            raise C8ProductionTrustRootError(
                "loss profile registry key rebinding rejected"
            )
        if existing is None:
            self._entries[profile.profile_id] = profile
        return ProductionLossWitness(
            profile_id=profile.profile_id,
            profile_digest=profile.profile_digest,
            _secret=self._authority._secret,
        )

    def resolve(self, profile_id: str) -> c8.GraphLossProfile | None:
        value = self._entries.get(profile_id)
        return value if isinstance(value, c8.GraphLossProfile) else None


@dataclass(frozen=True, slots=True)
class ProductionMaterialHandle:
    material: c8.CanonicalMaterialRead
    witness: object
    locator: str
    root_id: object
    _secret: object


@dataclass(frozen=True, slots=True)
class ProductionKnowledgeHandle:
    issued_read: IssuedKnowledgeRead
    stored_value: C8StoredKnowledgeValue
    material_locator: str
    root_id: object
    _secret: object


@dataclass(frozen=True, slots=True)
class ProductionWritingResult:
    artifact_id: str
    artifact: c8.ResearchDraftArtifact
    root_id: object
    _secret: object


@dataclass(frozen=True, slots=True)
class ProductionVerifierHandle:
    verification: c8.ReportVerification
    witness: object
    artifact_id: str
    artifact_digest: str
    root_id: object
    _secret: object


@dataclass(frozen=True, slots=True)
class ProductionAdmissionResult:
    artifact: c8.ResearchDraftArtifact
    readback: c8.ReportAdmissionReadback
    artifact_readback: C8ArtifactReadback


@dataclass(frozen=True, slots=True)
class ProductionGraphWriteResult:
    generation: c8.GraphProjectionGeneration
    loss_profile_registry_id: str
    loss_profile_registry_digest: str
    authority_id: str
    authority_digest: str
    active_value_ref: str
    generation_number: int


@dataclass(frozen=True, slots=True)
class ProductionGraphReadHandle:
    generation_id: str
    offset: str
    provenance_digest: str
    locator: str
    graph_id: str
    root_id: object
    _secret: object


def _require_seal(handle: object) -> None:
    secret = getattr(handle, "_secret", None)
    if secret is not _PRODUCTION_SEAL:
        raise C8ProductionTrustRootError(
            "handle was not issued by this production trust root"
        )


def _require_root(handle: object, root_id: object) -> None:
    if getattr(handle, "root_id", None) is not root_id:
        raise C8ProductionTrustRootError(
            "handle was not issued by this production trust root"
        )


@dataclass(frozen=True, slots=True)
class C8PostgresDeliveryAssembly:
    """C8-specific handlers on the existing PostgreSQL RuntimeNode kernel."""

    engine: Engine
    activation: PostgresFirstSpecimenActivationPort
    terminal_hook: PostgresFirstSpecimenTerminalHook
    delivery_gate: PostgresFirstSpecimenDeliveryGate
    handlers: tuple[FirstSpecimenOperationHandler, ...]
    recovery_handlers: tuple[RuntimeHandler, ...]

    def activate_initial(
        self,
        *,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
    ) -> object:
        with RuntimeUnitOfWork(engine=self.engine) as uow:
            receipt = self.activation.activate_after_terminal(
                connection=uow.connection,
                scope=scope,
                run_id=run_id,
                observed_at=observed_at,
            )
            uow.commit()
            return receipt

    def compose_node(
        self,
        *,
        identity: NodeIdentity,
        profile: RuntimeNodeProfile,
        deployment: DeploymentBinding,
        protocol: RuntimeNodeProtocol,
        control_scope: ControlPlaneScope,
        clock: Clock | None = None,
    ) -> RuntimeNode:
        return compose_postgres_first_specimen_runtime(
            engine=self.engine,
            identity=identity,
            profile=profile,
            deployment=deployment,
            protocol=protocol,
            control_scope=control_scope,
            installations=(),
            additional_handlers=self.handlers + self.recovery_handlers,
            terminal_hook=self.terminal_hook,
            clock=clock,
        ).node

    def admit_delivery(self, request: FirstSpecimenDeliveryGateRequest) -> object:
        return self.delivery_gate.admit(request)


def build_postgres_c8_delivery_assembly(
    *,
    engine: Engine,
    bundle: C8CapabilityBundle,
    activation_catalog: FirstSpecimenActivationCatalog,
    delivery_interpreter: InternalExportInterpreter,
) -> C8PostgresDeliveryAssembly:
    """Install the exact five-entry C8 bridge on a real RuntimeNode."""

    bridge_kinds = (
        C8_3_KIND,
        C8_VERIFY_KIND,
        C8_ADMISSION_KIND,
        C8_DELIVERY_INTENT_PREPARE_KIND,
        DELIVERY_INTERNAL_EXPORT_KIND,
    )

    def operation_for(kind: str) -> object:
        matches = tuple(item for item in bundle.operations if item.ref.kind == kind)
        if len(matches) != 1:
            raise C8ProductionTrustRootError(
                f"C8 delivery assembly lacks one exact operation: {kind}"
            )
        return matches[0]

    operations = tuple(operation_for(kind) for kind in bridge_kinds)
    if len({item.ref.contract_digest for item in operations}) != 5:
        raise C8ProductionTrustRootError(
            "C8 delivery assembly requires five distinct exact operation refs"
        )
    uow_factory = runtime_uow_factory(engine)
    activation = PostgresFirstSpecimenActivationPort(
        activation_catalog,
        trace_prefix="trace:c8:delivery-bridge:activation",
    )
    c8_effects = C8BridgeEffectStore(uow_factory)
    delivery_effects = FirstSpecimenDeliveryEffectStore(
        uow_factory,
        replay=PostgresFirstSpecimenDeliveryReplay(),
        interpreter=delivery_interpreter,
    )

    def admission_factory(
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> AdmissionCoordinator:
        registrations = tuple(
            AdmissionRegistration(
                operation_contract_ref=operation.ref,
                handler=ResearchAdmissionHandler(
                    connection=connection,
                    tables=tables,
                    operation_contract_ref=operation.ref,
                    mode=mode,
                ),
            )
            for operation, mode in (
                (
                    operation_for(C8_ADMISSION_KIND),
                    ResearchAdmissionMode.ARTIFACT_OBJECT,
                ),
                (
                    operation_for(DELIVERY_INTERNAL_EXPORT_KIND),
                    ResearchAdmissionMode.DELIVERY_RECEIPT_EXTERNAL_REF,
                ),
            )
        )
        return AdmissionCoordinator(
            registry=ExactAdmissionRegistry(registrations),
            commit_intents=PostgresCommitIntentAdapter(
                CommitIntentRepository(connection, scope)
            ),
            commit_binding_factory=commit_binding_from_assignment,
        )

    terminal = PostgresFirstSpecimenTerminalHook(
        bundle=bundle,
        activation=activation,
        admission_factory=admission_factory,
    )
    handlers: list[FirstSpecimenOperationHandler] = []
    recovery_handlers: list[RuntimeHandler] = []
    for operation in operations:
        entry = activation_catalog.entry_for(operation.ref.contract_digest)
        binding = entry.interpreter_binding
        profile = binding.interpreter_profile_digest
        if operation.ref.kind == DELIVERY_INTERNAL_EXPORT_KIND:
            effect: RuntimeHandler = PostgresFirstSpecimenDeliveryHandler(
                InstalledFirstSpecimenDeliveryHandler.bind(
                    handler_binding_digest=binding.binding_digest,
                    interpreter_profile_digest=profile,
                ),
                delivery_effects,
            )
        else:
            effect = C8BridgeEffectHandler(
                C8BridgeHandlerInstallation(
                    operation_kind=operation.ref.kind,
                    operation_contract_digest=operation.ref.contract_digest,
                    handler_binding_digest=binding.binding_digest,
                    interpreter_profile_digest=profile,
                    output_type=operation.output_type,
                    admission_required=(operation.ref.kind == C8_ADMISSION_KIND),
                ),
                c8_effects,
            )
        verify = (
            PostgresVerifyAdmitHandler(
                uow_factory=uow_factory,
                operation_contract_digest=operation.ref.contract_digest,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=profile,
            )
            if operation.ref.kind in {C8_ADMISSION_KIND, DELIVERY_INTERNAL_EXPORT_KIND}
            else None
        )
        handlers.append(
            FirstSpecimenOperationHandler(
                effect=effect,
                verify_admit=verify,
                operation_contract_digest=operation.ref.contract_digest,
            )
        )
        recovery_installation = InstalledFirstSpecimenReconciliationHandler(
            recovery_binding=entry.recovery_binding,
            operation_contract_digest=operation.ref.contract_digest,
        )
        if operation.ref.kind == DELIVERY_INTERNAL_EXPORT_KIND:
            readback = InternalExportReadbackFacade(
                operation_contract_ref=operation.ref,
                blob_store=delivery_interpreter.blob_store,
            )
            recovery_handlers.append(
                PostgresFirstSpecimenReconciliationHandler(
                    recovery_installation,
                    uow_factory,
                    readback=readback,
                    recover_verify_admit=terminal.recover_admission,
                )
            )
        else:
            recovery_handlers.append(
                PostgresFirstSpecimenLocalReconciliationHandler(
                    recovery_installation,
                    uow_factory,
                    recover_verify_admit=terminal.recover_admission,
                )
            )
    return C8PostgresDeliveryAssembly(
        engine=engine,
        activation=activation,
        terminal_hook=terminal,
        delivery_gate=PostgresFirstSpecimenDeliveryGate(
            engine=engine,
            activation_catalog=activation_catalog,
        ),
        handlers=tuple(handlers),
        recovery_handlers=tuple(recovery_handlers),
    )


class C8ProductionRoot:
    """Production composition root; factory accepts only store/scope deps."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        tables: ProjectTables | None = None,
    ) -> None:
        self._connection = connection
        self._scope = scope
        self._tables = tables or project_tables(
            MetaData(), scope.project_scope.resolved_schema
        )
        self._material_registry = _ProductionMaterialIssuanceRegistry()
        self._verifier_registry = _ProductionVerifierRegistry()
        self._loss_registry = _ProductionLossProfileRegistry()
        self._material_capability = self._material_registry._capability()
        self._verifier_capability = self._verifier_registry._capability()
        self._loss_capability = self._loss_registry._capability()
        self._material_handles: dict[str, ProductionMaterialHandle] = {}
        self._knowledge_handles: dict[str, ProductionKnowledgeHandle] = {}
        self._verifier_handles: dict[str, ProductionVerifierHandle] = {}
        self._graph_handles: dict[str, ProductionGraphReadHandle] = {}
        self._writing_by_artifact: dict[str, ProductionWritingResult] = {}
        self._writing_by_verification: dict[str, str] = {}
        self._root_id = object()
        self._family_loss_witness = self._loss_registry.register_profile(
            FAMILY_LOSS_PROFILE,
            self._loss_capability,
        )

    @property
    def authority_id(self) -> str:
        return PRODUCTION_AUTHORITY_ID

    @property
    def authority_digest(self) -> str:
        return PRODUCTION_AUTHORITY_DIGEST

    def read_material(
        self,
        *,
        candidate_id: str | None = None,
        object_id: str | None = None,
    ) -> ProductionMaterialHandle:
        """Exact-read the C7 head/value and issue an opaque material witness."""

        material = read_canonical_material(
            self._connection,
            scope=self._scope,
            candidate_id=candidate_id,
            object_id=object_id,
        )
        witness = self._material_registry.register_material(
            material,
            self._material_capability,
        )
        locator = candidate_id or object_id or material.candidate_id
        handle = ProductionMaterialHandle(
            material=material,
            witness=witness,
            locator=locator,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        self._material_handles[material.material_identity] = handle
        return handle

    def _resolve_material(
        self,
        handle: ProductionMaterialHandle,
    ) -> c8.CanonicalMaterialRead:
        _require_seal(handle)
        _require_root(handle, self._root_id)
        if handle.material.material_identity not in self._material_handles:
            raise C8ProductionTrustRootError(
                "material handle was not issued by this root"
            )
        registered = self._material_registry.resolve(handle.material.material_identity)
        if registered is None or registered != handle.material:
            raise C8ProductionTrustRootError(
                "material is not a registered exact production entry"
            )
        current = read_canonical_material(
            self._connection,
            scope=self._scope,
            candidate_id=handle.material.candidate_id,
        )
        if current != handle.material:
            raise C8ProductionTrustRootError(
                "material drifted from the exact durable read"
            )
        return current

    def stage_knowledge(
        self,
        material_handle: ProductionMaterialHandle,
        *,
        formation_profile: c8.FormationProfile,
        candidate_id: str,
        canonical_statement: str,
        primary_type_node_key: str,
        evidence_refs: tuple[str, ...],
        fields: tuple[str, ...],
    ) -> ProductionKnowledgeHandle:
        """Form, stage and exact-read one bounded knowledge witness."""

        material = self._resolve_material(material_handle)
        candidate = form_knowledge_candidate(
            material,
            formation_profile=formation_profile,
            candidate_id=candidate_id,
            canonical_statement=canonical_statement,
            primary_type_node_key=primary_type_node_key,
            evidence_refs=evidence_refs,
        )
        stored_value = stage_knowledge_value(
            self._connection,
            scope=self._scope,
            material=material,
            candidate=candidate,
        )
        strict_registry = StrictReadHandleRegistry(self._material_registry)
        issued_read = strict_issued_demand_read(
            material,
            material_handle.witness,
            candidate,
            strict_registry,
            fields=fields,
            object_key=candidate.candidate_id,
        )
        handle = ProductionKnowledgeHandle(
            issued_read=issued_read,
            stored_value=stored_value,
            material_locator=material_handle.locator,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        self._knowledge_handles[issued_read.handle.handle_id] = handle
        return handle

    def _resolve_knowledge(
        self,
        handle: ProductionKnowledgeHandle,
    ) -> IssuedKnowledgeRead:
        _require_seal(handle)
        _require_root(handle, self._root_id)
        handle_id = handle.issued_read.handle.handle_id
        stored = self._knowledge_handles.get(handle_id)
        if stored is None or stored != handle:
            raise C8ProductionTrustRootError(
                "knowledge handle was not issued by this root"
            )
        registered = self._material_registry.resolve(
            handle.issued_read.handle.canonical_identity
        )
        if registered is None:
            raise C8ProductionTrustRootError(
                "knowledge handle material drifted from the exact registry"
            )
        c8.validate_typed_knowledge_candidate(
            handle.issued_read.candidate,
            material=registered,
            project_key=handle.issued_read.handle.project_key,
        )
        read_staged_knowledge_value(
            self._connection,
            scope=self._scope,
            material=registered,
            candidate=handle.issued_read.candidate,
            expected_value=handle.stored_value,
        )
        return handle.issued_read

    def compose_and_stage_writing(
        self,
        *,
        artifact_id: str,
        knowledge_handles: tuple[ProductionKnowledgeHandle, ...],
        citation_ids: tuple[str, ...],
        spec: c8.WritingCompositionSpec,
        run_id: str,
        step_id: str,
        qualifier_ref: str,
    ) -> ProductionWritingResult:
        """Resolve handle IDs in the root and stage deterministic Markdown."""

        if not knowledge_handles:
            raise C8ProductionTrustRootError(
                "writing requires at least one production knowledge handle"
            )
        reads: list[IssuedKnowledgeRead] = []
        for handle in knowledge_handles:
            read = self._resolve_knowledge(handle)
            reads.append(read)
        if len({read.handle.handle_id for read in reads}) != len(reads):
            raise C8ProductionTrustRootError(
                "writing requires distinct production knowledge handles"
            )
        if len(citation_ids) != len(set(citation_ids)):
            raise C8ProductionTrustRootError(
                "citation ids must be unique in the root-composed closure"
            )
        refs: list[c8.CitationRef] = []
        for position, citation_id in enumerate(citation_ids, start=1):
            matches = [
                read for read in reads if citation_id in read.candidate.evidence_refs
            ]
            if len(matches) != 1:
                raise C8ProductionTrustRootError(
                    f"citation id is not an issued knowledge handle: {citation_id}"
                )
            read = matches[0]
            refs.append(
                c8.CitationRef(
                    citation_id=citation_id,
                    source_identity=read.handle.canonical_identity,
                    source_digest=read.handle.canonical_digest,
                    position=position,
                    source_revision=read.handle.revision,
                    source_incarnation=read.handle.incarnation,
                    handle_id=read.handle.handle_id,
                    fields_digest=read.handle.fields_digest,
                )
            )
        closure = c8.CitationClosure(tuple(refs))
        validate_citation_closure(
            closure,
            duplicate_policy=spec.duplicate_policy,
            ceiling=spec.citation_ceiling,
        )
        artifact = compose_markdown_draft(
            artifact_id=artifact_id,
            reads=tuple(reads),
            citation_closure=closure,
            spec=spec,
        )
        stage_artifact(
            self._connection,
            scope=self._scope,
            artifact=artifact,
            run_id=run_id,
            step_id=step_id,
            qualifier_ref=qualifier_ref,
        )
        handle = ProductionWritingResult(
            artifact_id=artifact.artifact_id,
            artifact=artifact,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        existing = self._writing_by_artifact.get(artifact.artifact_id)
        if existing is not None:
            if existing.artifact != artifact:
                raise C8ProductionTrustRootError(
                    "writing registry key rebinding rejected"
                )
            handle = existing
        else:
            self._writing_by_artifact[artifact.artifact_id] = handle
        return handle

    def _require_writing(
        self,
        handle: ProductionWritingResult,
    ) -> c8.ResearchDraftArtifact:
        _require_seal(handle)
        _require_root(handle, self._root_id)
        stored = self._writing_by_artifact.get(handle.artifact_id)
        if stored is None or stored != handle:
            raise C8ProductionTrustRootError(
                "writing handle was not issued by this root"
            )
        durable = read_staged_artifact(
            self._connection,
            scope=self._scope,
            artifact_id=handle.artifact_id,
        )
        if durable != handle.artifact:
            raise C8ProductionTrustRootError(
                "writing drifted from the durable staged artifact read"
            )
        return durable

    def reissue_writing(
        self,
        artifact_id: str,
    ) -> ProductionWritingResult:
        """Re-issue a writing handle from the durable staged locator."""

        artifact = read_staged_artifact(
            self._connection,
            scope=self._scope,
            artifact_id=artifact_id,
        )
        handle = ProductionWritingResult(
            artifact_id=artifact_id,
            artifact=artifact,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        existing = self._writing_by_artifact.get(artifact_id)
        if existing is not None:
            if existing.artifact != artifact:
                raise C8ProductionTrustRootError(
                    "writing registry key rebinding rejected"
                )
            return existing
        self._writing_by_artifact[artifact_id] = handle
        return handle

    def verify_report(
        self,
        writing: ProductionWritingResult,
        *,
        citation_closure: c8.CitationClosure | None = None,
        stage_id: str | None = None,
    ) -> ProductionVerifierHandle:
        """Deterministic stage readback plus a verifier-owned witness."""

        artifact = self._require_writing(writing)
        closure = citation_closure or artifact.citation_closure
        if closure != artifact.citation_closure:
            raise C8ProductionTrustRootError(
                "report verification citation closure must equal the artifact"
            )
        stage = build_report_stage(
            stage_id=stage_id or f"stage:{artifact.artifact_id}",
            project_key=artifact.project_key,
            artifact=artifact,
            citation_closure=closure,
        )
        verification = verify_report_stage(
            stage,
            citation_closure=closure,
            artifact=artifact,
        )
        if verification.state != "VERIFIED":
            raise C8ProductionTrustRootError(
                verification.failure_reason or "report verification failed"
            )
        stamped = dataclasses.replace(
            verification,
            authority_kind=self._verifier_registry.authority_id,
            authority_digest=self._verifier_registry.authority_digest,
            verifier_registry_id=self._verifier_registry.registry_id,
            verifier_registry_digest=self._verifier_registry.registry_digest,
            object_digest="",
        )
        witness = self._verifier_registry.register_verification(
            stamped,
            self._verifier_capability,
        )
        registered = self._verifier_registry.resolve(stamped.verification_id)
        if registered is None:
            raise C8ProductionTrustRootError(
                "production verifier registration did not store verification"
            )
        verify_artifact(
            self._connection,
            scope=self._scope,
            artifact=artifact,
            verification=registered,
        )
        handle = ProductionVerifierHandle(
            verification=registered,
            witness=witness,
            artifact_id=artifact.artifact_id,
            artifact_digest=artifact.artifact_digest,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        self._verifier_handles[registered.verification_id] = handle
        self._writing_by_verification[registered.verification_id] = artifact.artifact_id
        return handle

    def _resolve_verifier(
        self,
        handle: ProductionVerifierHandle,
    ) -> c8.ReportVerification:
        _require_seal(handle)
        _require_root(handle, self._root_id)
        registered_handle = self._verifier_handles.get(
            handle.verification.verification_id
        )
        if registered_handle is None or registered_handle != handle:
            raise C8ProductionTrustRootError(
                "verifier handle was not issued by this root"
            )
        registered = self._verifier_registry.resolve(
            handle.verification.verification_id
        )
        if registered is None or registered != handle.verification:
            raise C8ProductionTrustRootError(
                "verifier handle is not a registered exact production entry"
            )
        if registered.state != "VERIFIED":
            raise C8ProductionTrustRootError(
                "report admission requires a verified exact verification"
            )
        return registered

    def admit_report(
        self,
        verifier_handle: ProductionVerifierHandle,
        *,
        run_id: str,
        step_id: str,
    ) -> ProductionAdmissionResult:
        """Admit the production-verified report without caller authority refs."""

        verification = self._resolve_verifier(verifier_handle)
        artifact_id = self._writing_by_verification.get(verification.verification_id)
        if artifact_id is None:
            raise C8ProductionTrustRootError(
                "admission requires a root-issued writing result"
            )
        writing = self._writing_by_artifact.get(artifact_id)
        if writing is None:
            raise C8ProductionTrustRootError(
                "admission requires a root-issued writing handle"
            )
        artifact = self._require_writing(writing)
        artifact_readback = admit_artifact(
            self._connection,
            scope=self._scope,
            artifact=artifact,
            verification=verification,
            run_id=run_id,
            step_id=step_id,
        )
        intent = build_report_admission_intent_v2(verification)
        readback = confirm_report_admission_readback(
            intent,
            witness=verifier_handle.witness,
            verifier_registry=self._verifier_registry,
            verification=verification,
            authority_epoch=1,
        )
        return ProductionAdmissionResult(
            artifact=artifact,
            readback=readback,
            artifact_readback=artifact_readback,
        )

    def readback_admission(
        self,
        verifier_handle: ProductionVerifierHandle,
    ) -> ProductionAdmissionResult:
        verification = self._resolve_verifier(verifier_handle)
        artifact_id = self._writing_by_verification.get(verification.verification_id)
        if artifact_id is None:
            raise C8ProductionTrustRootError(
                "readback requires a root-issued writing result"
            )
        writing = self._writing_by_artifact.get(artifact_id)
        if writing is None:
            raise C8ProductionTrustRootError(
                "readback requires a root-issued writing handle"
            )
        artifact = self._require_writing(writing)
        artifact_readback = readback_artifact(
            self._connection,
            scope=self._scope,
            artifact=artifact,
            verification=verification,
        )
        intent = build_report_admission_intent_v2(verification)
        readback = confirm_report_admission_readback(
            intent,
            witness=verifier_handle.witness,
            verifier_registry=self._verifier_registry,
            verification=verification,
            authority_epoch=1,
        )
        return ProductionAdmissionResult(
            artifact=artifact,
            readback=readback,
            artifact_readback=artifact_readback,
        )

    def prepare_internal_export(
        self,
        admission: ProductionAdmissionResult,
        *,
        export_format: str = "markdown",
    ) -> c8.ReportExportPreparation:
        """Prepare an internal export only from an admitted readback."""

        return prepare_report_export(
            admission.readback,
            export_format=export_format,
        )

    def build_internal_delivery_intent(
        self,
        preparation: c8.ReportExportPreparation,
        *,
        approval_digest: str,
        approval_epoch: int,
    ) -> c8.ReportDeliveryIntent:
        """Build a non-executing internal delivery intent only."""

        return build_report_delivery_intent_v2(
            preparation,
            approval_digest=approval_digest,
            approval_epoch=approval_epoch,
            external=False,
        )

    def build_external_delivery_intent(
        self,
        preparation: c8.ReportExportPreparation,
        *,
        approval_digest: str,
        approval_epoch: int,
    ) -> c8.ReportDeliveryIntent:
        """Always reject external delivery."""

        try:
            return build_report_delivery_intent_v2(
                preparation,
                approval_digest=approval_digest,
                approval_epoch=approval_epoch,
                external=True,
            )
        except c8.UnavailableProjection as exc:
            raise C8ProductionTrustRootError(str(exc)) from exc

    def attempt_internal_delivery(
        self,
        intent: c8.ReportDeliveryIntent,
    ) -> c8.ReportDeliveryIntent:
        """Reject the obsolete direct-effect path.

        Delivery is realized only through :meth:`build_delivery_assembly`, the
        PostgreSQL human gate, a claimed RuntimeAssignment and RuntimeNode.
        """

        raise C8DeliveryUnavailableError(
            "direct C8 delivery is typed unavailable and forbidden; use "
            "build_delivery_assembly(), PostgresFirstSpecimenDeliveryGate and "
            "a claimed RuntimeNode"
        )

    def build_delivery_assembly(
        self,
        *,
        bundle: C8CapabilityBundle,
        activation_catalog: FirstSpecimenActivationCatalog,
        delivery_interpreter: InternalExportInterpreter,
    ) -> C8PostgresDeliveryAssembly:
        """Bind this root to the shared approval/runtime/delivery owners."""

        return build_postgres_c8_delivery_assembly(
            engine=self._connection.engine,
            bundle=bundle,
            activation_catalog=activation_catalog,
            delivery_interpreter=delivery_interpreter,
        )

    def project_graph(
        self,
        *,
        graph_id: str,
        generation: int,
        occurrences: tuple[c8.GraphOccurrence, ...],
        provenance_digest: str,
        source_ref: str,
        source_incarnation: str,
        source_digest: str,
        source_revision: int,
        projector_id: str = "c8.graph.projector",
        projector_version: str = "1",
        expected_offset_revision: int | None = None,
        expected_generation: int | None = None,
    ) -> ProductionGraphWriteResult:
        """Project canonical knowledge through the fixed family loss catalog."""

        result = project_graph_generation_db(
            self._connection,
            scope=self._scope,
            graph_id=graph_id,
            generation=generation,
            occurrences=occurrences,
            loss_profile=FAMILY_LOSS_PROFILE,
            loss_profile_registry=self._loss_registry,
            loss_witness=self._family_loss_witness,
            provenance_digest=provenance_digest,
            source_ref=source_ref,
            source_incarnation=source_incarnation,
            source_digest=source_digest,
            source_revision=source_revision,
            projector_id=projector_id,
            projector_version=projector_version,
            expected_offset_revision=expected_offset_revision,
            expected_generation=expected_generation,
        )
        return ProductionGraphWriteResult(
            generation=result.generation,
            loss_profile_registry_id=self._loss_registry.registry_id,
            loss_profile_registry_digest=self._loss_registry.registry_digest,
            authority_id=self._loss_registry.authority_id,
            authority_digest=self._loss_registry.authority_digest,
            active_value_ref=result.active_value_ref,
            generation_number=generation,
        )

    def issue_active_graph_handle(
        self,
        *,
        graph_id: str,
        source_ref: str,
        source_incarnation: str,
        projector_id: str = "c8.graph.projector",
        projector_version: str = "1",
    ) -> ProductionGraphReadHandle:
        """Issue an active handle from offset+generation in one transaction."""

        generation = read_active_graph(
            self._connection,
            scope=self._scope,
            graph_id=graph_id,
            source_ref=source_ref,
            source_incarnation=source_incarnation,
            projector_id=projector_id,
            projector_version=projector_version,
        )
        self._require_active_generation(generation)
        handle = ProductionGraphReadHandle(
            generation_id=generation.generation_id,
            offset=generation.offset,
            provenance_digest=generation.provenance_digest,
            locator=f"{graph_id}:{source_ref}",
            graph_id=graph_id,
            root_id=self._root_id,
            _secret=_PRODUCTION_SEAL,
        )
        self._graph_handles[handle.generation_id] = handle
        return handle

    def _require_active_generation(
        self,
        generation: c8.GraphProjectionGeneration,
    ) -> None:
        if generation.authority_kind != PRODUCTION_AUTHORITY_ID:
            raise C8ProductionTrustRootError(
                "active graph generation is not production authority"
            )
        if generation.authority_digest != PRODUCTION_AUTHORITY_DIGEST:
            raise C8ProductionTrustRootError(
                "active graph generation authority digest drift"
            )
        if (
            generation.loss_profile_registry_id != self._loss_registry.registry_id
            or generation.loss_profile_registry_digest
            != self._loss_registry.registry_digest
        ):
            raise C8ProductionTrustRootError(
                "active graph generation loss registry digest drift"
            )

    def consume_graph(
        self,
        active_handle: ProductionGraphReadHandle,
        *,
        consumer_id: str,
        source_ref: str,
        source_incarnation: str,
        request_claim_support: bool = False,
        projector_id: str = "c8.graph.projector",
        projector_version: str = "1",
    ) -> c8.GraphConsumerResult:
        """Re-read the active offset/value and reject stale handles."""

        _require_seal(active_handle)
        _require_root(active_handle, self._root_id)
        stored = self._graph_handles.get(active_handle.generation_id)
        if stored is None or stored != active_handle:
            raise C8ProductionTrustRootError(
                "active graph handle was not issued by this root"
            )
        generation = read_active_graph(
            self._connection,
            scope=self._scope,
            graph_id=active_handle.graph_id,
            source_ref=source_ref,
            source_incarnation=source_incarnation,
            projector_id=projector_id,
            projector_version=projector_version,
        )
        self._require_active_generation(generation)
        if (
            generation.generation_id != active_handle.generation_id
            or generation.offset != active_handle.offset
            or generation.provenance_digest != active_handle.provenance_digest
        ):
            raise C8ProductionTrustRootError(
                "active graph handle is stale for the current offset/value"
            )
        return consume_graph_projection(
            consumer_id=consumer_id,
            projection=generation,
            project_key=self._scope.project_scope.project_key,
            active_read_handle=active_handle,
            request_claim_support=request_claim_support,
        )
