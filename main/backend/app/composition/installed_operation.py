from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from typing import Generic, Protocol, TypeVar, runtime_checkable

from functorial_kit.contributions import Contribution, ContributionObject
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (BindingAccepted, BindingRejected, NativeBindingIssue,
                                                NativeContribution, NativeContributionSpec,
                                                ProjectedContributionSpec, define_native_contribution)
from sqlalchemy.engine import Engine

from app.successor_runtime.capabilities import (
    acquisition_url as url, batch_business as wait, batch_task as dispatch,
    batch_task_interpreters as dispatch_interpreters, retrieval_candidate_native as candidate,
    retrieval_material_native as leaf, workflow_native_contribution as workflow)
from app.successor_runtime.capabilities.codecs import PayloadCodec
from app.successor_runtime.capabilities.profiles import OperationProfiles
from app.successor_runtime.capabilities.retrieval_native_catalog import retrieval_candidate_native
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import OperationContract, OperationContractRef
from app.successor_runtime.runtime.assignments import InterpreterBinding, RuntimeAssignment
from app.successor_runtime.runtime.node import RuntimeHandler
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.runtime_activation import ActivationCatalogEntry

Source = TypeVar("Source")
Input = TypeVar("Input")
Output = TypeVar("Output")
Dispatch = Callable[[dispatch.BatchTaskSingleDispatchPayload], dispatch.BatchTaskSingleDispatchAck]
InstalledOperationContext = tuple[
    Engine,
    RuntimeScope,
    ActivationCatalogEntry,
    Dispatch,
    wait.BrokerBusinessReadback,
]


@dataclass(frozen=True, slots=True)
class InstalledOperationView(Generic[Source, Input, Output]):
    source: Source
    contract: OperationContract
    profiles: OperationProfiles
    input_codec: PayloadCodec[Input]
    output_codec: PayloadCodec[Output]
    interpreter_profile_digest: str
    authority_requirement_digest: str


class InstalledOperationDefinition(Protocol):
    @property
    def contract(self) -> OperationContract: ...
    @property
    def profiles(self) -> OperationProfiles: ...
    @property
    def interpreter_profile_digest(self) -> str: ...
    @property
    def authority_requirement_digest(self) -> str: ...


class InstalledOperation(Protocol):
    @property
    def definition(self) -> InstalledOperationDefinition: ...
    @property
    def projection(self) -> Contribution[object, object]: ...
    def assemble(self, context: InstalledOperationContext) -> RuntimeHandler | Failure: ...


@runtime_checkable
class _CodecObservation(Protocol):
    @property
    def codec_id(self) -> str: ...
    @property
    def codec_version(self) -> str: ...
    @property
    def contract_ref(self) -> OperationContractRef: ...
    @property
    def payload_type_id(self) -> str: ...


@runtime_checkable
class _BoundHandler(RuntimeHandler, Protocol):
    contract: OperationContract
    binding: InterpreterBinding
    @property
    def input_codec(self) -> _CodecObservation: ...
    @property
    def output_codec(self) -> _CodecObservation: ...
    @property
    def input_payload_type_id(self) -> str: ...
    @property
    def output_payload_type_id(self) -> str: ...


def _project(view: InstalledOperationView[Source, Input, Output]) -> ProjectedContributionSpec:
    contract, owner = view.contract, view.contract.owner_capability_id
    prefix = f"mrw.installed-operation.native.v1:{contract.ref.kind}:{contract.ref.contract_digest}"
    input_id = f"{prefix}:input:{contract.input_type.type_id}:{view.input_codec.codec_id}"
    output_id = f"{prefix}:output:{contract.output_type.type_id}:{view.output_codec.codec_id}"
    return ProjectedContributionSpec(id=prefix, owner=owner, objects=(
        ContributionObject(input_id, "InstalledInput", owner), ContributionObject(output_id, "InstalledOutput", owner),
        ContributionObject(prefix, "InstalledOperation", owner, (input_id, output_id))))


def validate_installed_operation(
    view: InstalledOperationView[Source, Input, Output], candidate_handler: object,
) -> BindingAccepted[RuntimeHandler] | BindingRejected:
    if (isinstance(candidate_handler, _BoundHandler)
            and candidate_handler.contract == view.contract
            and candidate_handler.binding.operation_contract_digest == view.contract.ref.contract_digest
            and candidate_handler.binding.authority_requirement_digest == view.authority_requirement_digest
            and candidate_handler.interpreter_profile_digest == view.interpreter_profile_digest
            and candidate_handler.input_codec is view.input_codec and candidate_handler.output_codec is view.output_codec
            and candidate_handler.input_payload_type_id == view.contract.input_type.type_id
            and candidate_handler.output_payload_type_id == view.contract.output_type.type_id):
        return BindingAccepted(candidate_handler)
    return BindingRejected((NativeBindingIssue("$.binding", "installed handler differs from definition"),))


def _install(
    source: Source, contract: OperationContract, profiles: OperationProfiles,
    input_codec: PayloadCodec[Input], output_codec: PayloadCodec[Output],
    assemble: Callable[
        [InstalledOperationView[Source, Input, Output], InstalledOperationContext],
        RuntimeHandler | Failure,
    ],
    interpreter_digest: str | None = None, authority_digest: str | None = None,
) -> NativeContribution[InstalledOperationView[Source, Input, Output], InstalledOperationContext, RuntimeHandler]:
    view = InstalledOperationView(
        source, contract, profiles, input_codec, output_codec,
        interpreter_digest or contract.interpreter_compatibility_ref.profile_digest,
        authority_digest or contract.authority_profile_ref.profile_digest)
    native = define_native_contribution(NativeContributionSpec(
        definition=view, project=_project, assemble=assemble, validate_binding=validate_installed_operation))
    if isinstance(native, Failure):
        raise RuntimeError(f"invalid installed operation definition: {native.message}")
    return native


def _workflow(
    view: InstalledOperationView[
        workflow.WorkflowRuntimeOperationDefinition,
        workflow.WorkflowExecutionContext,
        workflow.WorkflowExecutionContext,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.projects.context import bind_resolved_project
    from app.services.workflow_graph.runtime import (
        WorkflowNodeSettledFailure,
        invoke_workflow_runtime_node,
    )
    from app.successor_runtime.assembly.workflow_assembly import (
        assemble_workflow_runtime_handler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, scope, entry = context[:3]
    return assemble_workflow_runtime_handler(
        operation=view.source,
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        project_key=scope.project_scope.project_key,
        resolved_schema=scope.project_scope.resolved_schema,
        bind_project_scope=bind_resolved_project,
        invoke_runtime_node=invoke_workflow_runtime_node,
        settled_failure_type=WorkflowNodeSettledFailure,
    )


def _candidate(
    view: InstalledOperationView[
        candidate.CandidateRuntimeDefinition,
        candidate.RetrievalCandidateInvocation,
        candidate.RetrievalCandidateAttemptOutcome,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.projects.context import bind_resolved_project
    from app.services.search.candidate_search import discover_candidates
    from app.successor_runtime.capabilities.retrieval_candidate_native import (
        complete_retrieval_candidate_attempt,
    )
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
        PersistentOperationHandler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, scope, entry = context[:3]
    operation = view.source

    def check_scope(
        invocation: candidate.RetrievalCandidateInvocation,
        project: ProjectScopeRef,
        _capability_id: str,
    ) -> None:
        if (
            invocation.request.project_ref is not None
            and invocation.request.project_ref != project.project_key
        ):
            raise ValueError("candidate request crosses the installed project scope")

    def discover(
        invocation: candidate.RetrievalCandidateInvocation,
    ) -> candidate.RetrievalCandidateAttemptOutcome:
        with bind_resolved_project(
            scope.project_scope.project_key,
            scope.project_scope.resolved_schema,
        ):
            return complete_retrieval_candidate_attempt(
                invocation,
                discover_candidates(invocation.request),
            )

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=operation.operation_contract,
        input_codec=operation.invocation_codec,
        output_codec=operation.output_codec,
        invoke=discover,
        validate_input=check_scope,
        validate_bound_inputs=operation.validate_bound_inputs,
    )


def _work_leaf(
    view: InstalledOperationView[
        leaf.RetrievalLeafDefinition[leaf.CandidateWork],
        leaf.CandidateWork,
        leaf.CandidateWork,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.project_retrieval.execution import (
        build_retrieval_leaf_invocations,
        build_retrieval_runtime_journal_reader,
        review_candidate_work,
        validate_retrieval_work_bound_inputs,
    )
    from app.services.project_retrieval.service import ProjectRetrievalService
    from app.services.project_retrieval.topology import build_topology_service
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
        PersistentOperationHandler,
    )
    from app.successor_runtime.substrate.postgres.runtime_activation import (
        read_ordered_prior_effect_outputs,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, scope, entry = context[:3]
    work_invocations, _ = build_retrieval_leaf_invocations(
        topology_service=build_topology_service(),
        plan_loader=ProjectRetrievalService().read_plan,
        journal_reader=build_retrieval_runtime_journal_reader(
            engine=engine,
            actor_id=scope.actor_id,
        ),
    )

    def check_retrieval_scope(
        payload: leaf.CandidateWork,
        project: ProjectScopeRef,
        capability_id: str,
    ) -> None:
        if (
            payload.project_key != project.project_key
            or capability_id != view.contract.owner_capability_id
        ):
            raise ValueError("retrieval payload crosses installed project or capability")

    def invoke_retrieval(payload: leaf.CandidateWork) -> leaf.CandidateWork:
        if view.contract.ref.kind == leaf.RETRIEVAL_CANDIDATE_REVIEW_KIND:
            raise ValueError("review requires its exact assignment prefix")
        with bind_resolved_project(
            scope.project_scope.project_key,
            scope.project_scope.resolved_schema,
        ):
            return work_invocations[view.contract.ref.kind](payload)

    def invoke_review(
        payload: leaf.CandidateWork,
        assignment: RuntimeAssignment,
    ) -> leaf.CandidateWork:
        with runtime_uow_factory(engine)() as uow:
            current_bytes, prior = read_ordered_prior_effect_outputs(
                uow.connection,
                scope,
                assignment,
            )
        codec = view.input_codec
        current = codec.decode_payload(json.loads(current_bytes))
        if current != payload or payload.candidate_ordinal != len(prior) + 1:
            raise ValueError("review current ordered invocation drift")
        approved = 0
        for position, (before_bytes, after_bytes) in enumerate(prior, 1):
            before = codec.decode_payload(json.loads(before_bytes))
            after = codec.decode_payload(json.loads(after_bytes))
            leaf.validate_candidate_work_transition(before, after)
            if (
                before.candidate_ordinal != position
                or before.stage != "candidate"
                or after.stage != "reviewed"
                or after.review is None
                or (
                    before.project_key,
                    before.root_run_id,
                    before.retrieval_budget_id,
                    before.plan_id,
                    before.mode_version,
                    before.route_id,
                    before.material_budget_remaining,
                )
                != (
                    payload.project_key,
                    payload.root_run_id,
                    payload.retrieval_budget_id,
                    payload.plan_id,
                    payload.mode_version,
                    payload.route_id,
                    payload.material_budget_remaining,
                )
            ):
                raise ValueError("review prior ordered output identity drift")
            approved += after.disposition == "approved"
        with bind_resolved_project(
            scope.project_scope.project_key,
            scope.project_scope.resolved_schema,
        ):
            return review_candidate_work(payload, approved_prefix_count=approved)

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=view.contract,
        input_codec=view.input_codec,
        output_codec=view.output_codec,
        invoke=invoke_retrieval,
        validate_input=check_retrieval_scope,
        invoke_with_assignment=(
            invoke_review
            if view.contract.ref.kind == leaf.RETRIEVAL_CANDIDATE_REVIEW_KIND
            else None
        ),
        validate_bound_inputs=validate_retrieval_work_bound_inputs,
        bound_payload_source="semantic",
    )


def _control_leaf(
    view: InstalledOperationView[
        leaf.RetrievalLeafDefinition[leaf.RetrievalControl],
        leaf.RetrievalControl,
        leaf.RetrievalControl,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.project_retrieval.execution import (
        build_retrieval_leaf_invocations,
        build_retrieval_runtime_journal_reader,
        validate_retrieval_work_bound_inputs,
    )
    from app.services.project_retrieval.service import ProjectRetrievalService
    from app.services.project_retrieval.topology import build_topology_service
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
        PersistentOperationHandler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, scope, entry = context[:3]
    _, control_invocations = build_retrieval_leaf_invocations(
        topology_service=build_topology_service(),
        plan_loader=ProjectRetrievalService().read_plan,
        journal_reader=build_retrieval_runtime_journal_reader(
            engine=engine,
            actor_id=scope.actor_id,
        ),
    )

    def invoke(payload: leaf.RetrievalControl) -> leaf.RetrievalControl:
        with bind_resolved_project(
            scope.project_scope.project_key,
            scope.project_scope.resolved_schema,
        ):
            return control_invocations[view.contract.ref.kind](payload)

    def check_scope(
        payload: leaf.RetrievalControl,
        project: ProjectScopeRef,
        capability_id: str,
    ) -> None:
        if (
            payload.project_key != project.project_key
            or capability_id != view.contract.owner_capability_id
        ):
            raise ValueError("retrieval payload crosses installed project or capability")

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=view.contract,
        input_codec=view.input_codec,
        output_codec=view.output_codec,
        invoke=invoke,
        validate_input=check_scope,
        validate_bound_inputs=validate_retrieval_work_bound_inputs,
        bound_payload_source="semantic",
    )


def _url(
    view: InstalledOperationView[
        OperationContract,
        url.UrlSingleUrlRequest,
        url.UrlSingleUrlOutcome,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.ingest.url_pool import (
        invoke_url_single_url,
        validate_url_single_url_input,
    )
    from app.services.projects.context import bind_resolved_project
    from app.successor_runtime.runtime.node import (
        DefiniteInterpreterFailure,
        OutcomeUncertain,
    )
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
        PersistentOperationHandler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, scope, entry = context[:3]

    def check_bindings(
        request: url.UrlSingleUrlRequest,
        bound_inputs: tuple[tuple[ValueRef, bytes], ...],
    ) -> None:
        if len(bound_inputs) != 1:
            from app.services.project_retrieval.execution import (
                validate_retrieval_url_bound_inputs,
            )

            validate_retrieval_url_bound_inputs(request, bound_inputs)

    def invoke(request: url.UrlSingleUrlRequest) -> url.UrlSingleUrlOutcome:
        with bind_resolved_project(
            scope.project_scope.project_key,
            scope.project_scope.resolved_schema,
        ):
            result = invoke_url_single_url(request)
        if result.status == "failed":
            raise DefiniteInterpreterFailure("URL_POOL_EXECUTION_FAILED")
        if result.status != "completed":
            raise OutcomeUncertain("URL_POOL_TERMINAL_READBACK_REQUIRED")
        return result

    return PersistentOperationHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=view.contract,
        input_codec=view.input_codec,
        output_codec=view.output_codec,
        invoke=invoke,
        validate_input=validate_url_single_url_input,
        validate_bound_inputs=check_bindings,
        bound_payload_source="semantic",
    )


def _historical_url_read_only(
    view: InstalledOperationView[
        OperationContract,
        url.LegacyUrlSingleUrlRequest,
        url.LegacyUrlSingleUrlOutcome,
    ],
    _context: InstalledOperationContext,
) -> Failure:
    """Keep frozen URL codecs available for readback without an effect path."""
    return Failure(
        "mrw.installed-operation",
        "HISTORICAL_OPERATION_READ_ONLY",
        "historical URL operation contracts are available for exact readback only",
        {
            "operation_kind": view.contract.ref.kind,
            "contract_version": view.contract.ref.contract_version,
            "contract_digest": view.contract.ref.contract_digest,
        },
    )


def _wait(
    view: InstalledOperationView[
        OperationContract,
        wait.BusinessWaitInput,
        wait.BatchBusinessResult,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.services.agent_batch.business_readback import build_batch_business_wait_invoke
    from app.successor_runtime.substrate.postgres.effect_reconciliation import (
        BatchBusinessWaitHandler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, _scope, entry, _dispatch, broker = context
    return BatchBusinessWaitHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=view.contract,
        input_codec=view.input_codec,
        output_codec=view.output_codec,
        invoke=build_batch_business_wait_invoke(broker),
    )


def _dispatch(
    view: InstalledOperationView[
        OperationContract,
        dispatch.BatchTaskSingleDispatchPayload,
        dispatch.BatchTaskSingleDispatchAck,
    ],
    context: InstalledOperationContext,
) -> RuntimeHandler:
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
        BatchTaskSingleDispatchHandler,
    )
    from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

    engine, _scope, entry, dispatch_call, _broker = context
    return BatchTaskSingleDispatchHandler(
        uow_factory=runtime_uow_factory(engine),
        binding=entry.interpreter_binding,
        contract=view.contract,
        input_codec=view.input_codec,
        output_codec=view.output_codec,
        dispatch=dispatch_call,
    )


WorkflowInstalledOperation = NativeContribution[
    InstalledOperationView[
        workflow.WorkflowRuntimeOperationDefinition,
        workflow.WorkflowExecutionContext,
        workflow.WorkflowExecutionContext,
    ],
    InstalledOperationContext,
    RuntimeHandler,
]


def workflow_installed_operation_catalog(
    definition: workflow.WorkflowRuntimeDefinition,
) -> tuple[WorkflowInstalledOperation, ...]:
    return tuple(_install(item, item.contract, item.profiles, item.context_codec, item.context_codec, _workflow)
                 for item in definition.operations)


workflow_installed_operations = workflow_installed_operation_catalog(workflow.build_workflow_runtime_definition())
if isinstance(retrieval_candidate_native, Failure):
    raise RuntimeError("registered retrieval candidate native is invalid")
candidate_installed_operation = _install(
    (candidate_runtime := retrieval_candidate_native.definition.runtime), candidate_runtime.operation_contract, candidate_runtime.profiles,
    candidate_runtime.invocation_codec, candidate_runtime.output_codec, _candidate)
WorkLeafInstalledOperation = NativeContribution[
    InstalledOperationView[
        leaf.RetrievalLeafDefinition[leaf.CandidateWork],
        leaf.CandidateWork,
        leaf.CandidateWork,
    ],
    InstalledOperationContext,
    RuntimeHandler,
]


def _work_leaf_install(kind: leaf.WorkLeafKind) -> WorkLeafInstalledOperation:
    item = leaf.build_retrieval_leaf_definition(kind)
    return _install(item, item.contract, item.profiles, item.input_codec, item.output_codec, _work_leaf)


ControlLeafInstalledOperation = NativeContribution[
    InstalledOperationView[
        leaf.RetrievalLeafDefinition[leaf.RetrievalControl],
        leaf.RetrievalControl,
        leaf.RetrievalControl,
    ],
    InstalledOperationContext,
    RuntimeHandler,
]


def _control_leaf_install(kind: leaf.ControlLeafKind) -> ControlLeafInstalledOperation:
    item = leaf.build_retrieval_leaf_definition(kind)
    return _install(item, item.contract, item.profiles, item.input_codec, item.output_codec, _control_leaf)


leaf_installed_operations = (*(_work_leaf_install(kind) for kind in leaf.WORK_LEAF_KINDS),
                             *(_control_leaf_install(kind) for kind in leaf.CONTROL_LEAF_KINDS))


url_legacy_contract, url_readback_legacy_contract, url_current_contract = (
    url.build_url_single_url_contracts()
)
url_historical_installed_operations = tuple(
    _install(
        contract,
        contract,
        (
            url.build_url_single_url_legacy_profiles()
            if contract.ref.contract_version
            == url.URL_SINGLE_URL_LEGACY_CONTRACT_VERSION
            else url.build_url_single_url_readback_legacy_profiles()
        ),
        url.build_url_single_url_legacy_request_codec(contract.ref),
        url.build_url_single_url_legacy_outcome_codec(contract.ref),
        _historical_url_read_only,
    )
    for contract in (url_legacy_contract, url_readback_legacy_contract)
)
url_current_installed_operation = _install(
    url_current_contract,
    url_current_contract,
    url.build_url_single_url_profiles(),
    url.build_url_single_url_request_codec(url_current_contract.ref),
    url.build_url_single_url_outcome_codec(url_current_contract.ref),
    _url,
)
url_installed_operations = (
    *url_historical_installed_operations,
    url_current_installed_operation,
)
wait_contract = wait.build_batch_business_wait_contract()
dispatch_contract = dispatch.build_batch_task_single_dispatch_contract()
nonworkflow_installed_operations: tuple[InstalledOperation, ...] = (
    candidate_installed_operation, *leaf_installed_operations,
    *url_installed_operations,
    _install(wait_contract, wait_contract, wait.build_batch_business_wait_profiles(),
             wait.build_batch_business_wait_input_codec(wait_contract.ref),
             wait.build_batch_business_wait_result_codec(wait_contract.ref), _wait),
    _install(dispatch_contract, dispatch_contract, dispatch.build_batch_task_single_dispatch_profiles(),
             dispatch.build_batch_task_single_dispatch_payload_codec(dispatch_contract.ref),
             dispatch.build_batch_task_single_dispatch_ack_codec(dispatch_contract.ref), _dispatch,
             dispatch_interpreters.successor_dispatch_single_interpreter_profile_digest(),
             dispatch_interpreters.dispatch_single_authority_requirement_digest()))
installed_operation_catalog: tuple[InstalledOperation, ...] = (*workflow_installed_operations,
                                                               *nonworkflow_installed_operations)
installed_operation_contribution_catalog = tuple(item.projection for item in installed_operation_catalog)


def installed_operation_for_ref(
    entries: Sequence[InstalledOperation], ref: OperationContractRef,
) -> InstalledOperation | None:
    same_kind = False
    for item in entries:
        installed_ref = item.definition.contract.ref
        if installed_ref == ref:
            return item
        same_kind = same_kind or installed_ref.kind == ref.kind
    if same_kind:
        raise ValueError("installed operation ref drift")
    return None
