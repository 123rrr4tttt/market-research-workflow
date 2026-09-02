"""Production assembly for the complete P0-C first-specimen handler family."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Engine

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    Clock,
    DefiniteInterpreterFailure,
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
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

from .captured_values import PostgresCapturedValueReplayAdapter
from .composition_root import (
    InstalledMaterialReadHandler,
    PostgresMaterialReadHandler,
    compose_postgres_first_specimen_runtime,
)
from .first_specimen_activation import (
    FirstSpecimenActivationCatalog,
    PostgresFirstSpecimenActivationBindingAdapter,
    PostgresFirstSpecimenActivationPort,
)
from .first_specimen_delivery_gate import (
    FirstSpecimenDeliveryGateRequest,
    PostgresFirstSpecimenDeliveryGate,
)
from .first_specimen_delivery_handler import (
    DELIVERY_OPERATION,
    FirstSpecimenDeliveryEffectStore,
    InstalledFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryReplay,
)
from .first_specimen_handlers import (
    SUPPORTED_SEMANTIC_OPERATIONS,
    FirstSpecimenEffectOutputStore,
    InstalledFirstSpecimenEffectHandler,
    PostgresFirstSpecimenEffectHandler,
    PostgresFirstSpecimenEffectReplay,
)
from .first_specimen_reconciliation_handler import (
    InstalledFirstSpecimenReconciliationHandler,
    PostgresFirstSpecimenLocalReconciliationHandler,
    PostgresFirstSpecimenReconciliationHandler,
)
from .first_specimen_terminal import (
    PostgresFirstSpecimenTerminalHook,
    PostgresVerifyAdmitHandler,
)
from .node_adapter import runtime_uow_factory
from .unit_of_work import RuntimeUnitOfWork


class FirstSpecimenOperationHandler(RuntimeHandler):
    """One exact handler digest realizing effect and optional admission roles."""

    def __init__(
        self,
        *,
        effect: RuntimeHandler,
        verify_admit: RuntimeHandler | None,
        operation_contract_digest: str,
    ) -> None:
        self.effect = effect
        self.verify_admit = verify_admit
        self.handler_binding_digest = effect.handler_binding_digest
        self.interpreter_profile_digest = effect.interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        if (
            getattr(effect, "operation_contract_digest", None)
            != operation_contract_digest
        ):
            raise ValueError("effect handler operation contract drift")
        if verify_admit is not None and (
            verify_admit.handler_binding_digest != self.handler_binding_digest
            or verify_admit.interpreter_profile_digest
            != self.interpreter_profile_digest
            or getattr(verify_admit, "operation_contract_digest", None)
            != operation_contract_digest
        ):
            raise ValueError("effect/admission handler installation drift")

    def execute(
        self,
        assignment: object,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        kind = getattr(assignment, "assignment_kind", None)
        if kind is AssignmentKind.INTERPRET:
            return self.effect.execute(assignment, claim, context)  # type: ignore[arg-type]
        if kind is AssignmentKind.VERIFY_ADMIT and self.verify_admit is not None:
            return self.verify_admit.execute(assignment, claim, context)  # type: ignore[arg-type]
        raise DefiniteInterpreterFailure("ASSIGNMENT_ROLE_NOT_INSTALLED")


@dataclass(frozen=True, slots=True)
class PostgresFirstSpecimenAssembly:
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


def build_postgres_first_specimen_assembly(
    *,
    engine: Engine,
    activation_catalog: FirstSpecimenActivationCatalog,
    delivery_interpreter: InternalExportInterpreter,
) -> PostgresFirstSpecimenAssembly:
    """Build the immutable handler suite and terminal/activation composition."""

    bundle = build_first_specimen_bundle()
    returns_registry = build_first_specimen_return_contract_registry()
    uow_factory = runtime_uow_factory(engine)
    activation_bindings = PostgresFirstSpecimenActivationBindingAdapter()
    semantic_store = FirstSpecimenEffectOutputStore(
        uow_factory,
        replay=PostgresFirstSpecimenEffectReplay(activation_bindings),
    )
    delivery_store = FirstSpecimenDeliveryEffectStore(
        uow_factory,
        replay=PostgresFirstSpecimenDeliveryReplay(),
        interpreter=delivery_interpreter,
    )
    material_replay = PostgresCapturedValueReplayAdapter(
        uow_factory,
        activation_bindings,
    )
    activation = PostgresFirstSpecimenActivationPort(activation_catalog)
    terminal = PostgresFirstSpecimenTerminalHook(
        bundle=bundle,
        activation=activation,
    )

    handlers: list[FirstSpecimenOperationHandler] = []
    recovery_handlers: list[RuntimeHandler] = []
    for operation in bundle.operations:
        kind = operation.ref.kind
        entry = activation_catalog.entry_for(operation.ref.contract_digest)
        if (kind == DELIVERY_OPERATION) != entry.external_gate_required:
            raise ValueError(
                "only delivery.internal_export.v1 requires the external approval gate"
            )
        binding = entry.interpreter_binding
        profile = binding.interpreter_profile_digest
        if kind == "material.read_canonical_ref.v1":
            effect: RuntimeHandler = PostgresMaterialReadHandler(
                InstalledMaterialReadHandler(
                    handler_binding_digest=binding.binding_digest,
                    interpreter_profile_digest=profile,
                    operation_contract_digest=operation.ref.contract_digest,
                ),
                material_replay,
            )
        elif kind in SUPPORTED_SEMANTIC_OPERATIONS:
            effect = PostgresFirstSpecimenEffectHandler(
                InstalledFirstSpecimenEffectHandler.bind(
                    operation_kind=kind,
                    handler_binding_digest=binding.binding_digest,
                    interpreter_profile_digest=profile,
                ),
                semantic_store,
            )
        elif kind == DELIVERY_OPERATION:
            effect = PostgresFirstSpecimenDeliveryHandler(
                InstalledFirstSpecimenDeliveryHandler.bind(
                    handler_binding_digest=binding.binding_digest,
                    interpreter_profile_digest=profile,
                ),
                delivery_store,
            )
        else:  # pragma: no cover - frozen bundle exhaustiveness
            raise ValueError(f"unsupported first-specimen operation: {kind}")

        returns = returns_registry.resolve_required(operation.return_contract_ref)
        verify = (
            PostgresVerifyAdmitHandler(
                uow_factory=uow_factory,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=profile,
                operation_contract_digest=operation.ref.contract_digest,
            )
            if returns.admission_required
            else None
        )
        handlers.append(
            FirstSpecimenOperationHandler(
                effect=effect,
                verify_admit=verify,
                operation_contract_digest=operation.ref.contract_digest,
            )
        )
        if kind == DELIVERY_OPERATION:
            readback = InternalExportReadbackFacade(
                operation_contract_ref=operation.ref,
                blob_store=delivery_interpreter.blob_store,
            )
            recovery_handlers.append(
                PostgresFirstSpecimenReconciliationHandler(
                    InstalledFirstSpecimenReconciliationHandler(
                        recovery_binding=entry.recovery_binding,
                        operation_contract_digest=operation.ref.contract_digest,
                    ),
                    uow_factory,
                    readback=readback,
                    recover_verify_admit=terminal.recover_admission,
                )
            )
        else:
            recovery_handlers.append(
                PostgresFirstSpecimenLocalReconciliationHandler(
                    InstalledFirstSpecimenReconciliationHandler(
                        recovery_binding=entry.recovery_binding,
                        operation_contract_digest=operation.ref.contract_digest,
                    ),
                    uow_factory,
                    recover_verify_admit=terminal.recover_admission,
                )
            )

    return PostgresFirstSpecimenAssembly(
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


__all__ = [
    "FirstSpecimenOperationHandler",
    "PostgresFirstSpecimenAssembly",
    "build_postgres_first_specimen_assembly",
]
