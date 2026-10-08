from __future__ import annotations
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
from app.successor_runtime.language.object_contracts import OperationContract, OperationContractRef
from app.successor_runtime.runtime.assignments import InterpreterBinding
from app.successor_runtime.runtime.node import RuntimeHandler
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.first_specimen_activation import ActivationCatalogEntry

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
class _BoundHandler(RuntimeHandler, Protocol):
    contract: OperationContract
    binding: InterpreterBinding
    @property
    def input_codec(self) -> object: ...
    @property
    def output_codec(self) -> object: ...
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
    assemble: Callable[[InstalledOperationView[Source, Input, Output], InstalledOperationContext], RuntimeHandler],
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


def _workflow(view: InstalledOperationView[workflow.WorkflowRuntimeOperationDefinition,
              workflow.WorkflowExecutionContext, workflow.WorkflowExecutionContext], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_workflow_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_workflow_operation(view.source, *context[:3])


def _candidate(view: InstalledOperationView[candidate.CandidateRuntimeDefinition,
               candidate.RetrievalCandidateInvocation, candidate.RetrievalCandidateAttemptOutcome], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_candidate_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_candidate_operation(view.source, *context[:3])


def _work_leaf(view: InstalledOperationView[leaf.RetrievalLeafDefinition[leaf.CandidateWork], leaf.CandidateWork,
               leaf.CandidateWork], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_retrieval_work_leaf_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_retrieval_work_leaf_operation(view, *context[:3])


def _control_leaf(view: InstalledOperationView[leaf.RetrievalLeafDefinition[leaf.RetrievalControl],
                  leaf.RetrievalControl, leaf.RetrievalControl], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_retrieval_control_leaf_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_retrieval_control_leaf_operation(view, *context[:3])


def _url(view: InstalledOperationView[OperationContract, url.UrlSingleUrlRequest, url.UrlSingleUrlOutcome], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_url_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_url_operation(view, *context[:3])


def _wait(view: InstalledOperationView[OperationContract, wait.BusinessWaitInput, wait.BatchBusinessResult], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_wait_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_wait_operation(view, *context[:3], context[4])


def _dispatch(view: InstalledOperationView[OperationContract, dispatch.BatchTaskSingleDispatchPayload, dispatch.BatchTaskSingleDispatchAck], context: InstalledOperationContext) -> RuntimeHandler:
    from app.composition.production import _assemble_dispatch_operation  # pyright: ignore[reportPrivateUsage]
    return _assemble_dispatch_operation(view, *context[:3], context[3])


def workflow_installed_operation_catalog(definition: workflow.WorkflowRuntimeDefinition):
    return tuple(_install(item, item.contract, item.profiles, item.context_codec, item.context_codec, _workflow)
                 for item in definition.operations)


workflow_installed_operations = workflow_installed_operation_catalog(workflow.build_workflow_runtime_definition())
if isinstance(retrieval_candidate_native, Failure):
    raise RuntimeError("registered retrieval candidate native is invalid")
candidate_installed_operation = _install(
    (candidate_runtime := retrieval_candidate_native.definition.runtime), candidate_runtime.operation_contract, candidate_runtime.profiles,
    candidate_runtime.invocation_codec, candidate_runtime.output_codec, _candidate)
def _work_leaf_install(kind: leaf.WorkLeafKind):
    item = leaf.build_retrieval_leaf_definition(kind)
    return _install(item, item.contract, item.profiles, item.input_codec, item.output_codec, _work_leaf)


def _control_leaf_install(kind: leaf.ControlLeafKind):
    item = leaf.build_retrieval_leaf_definition(kind)
    return _install(item, item.contract, item.profiles, item.input_codec, item.output_codec, _control_leaf)


leaf_installed_operations = (*(_work_leaf_install(kind) for kind in leaf.WORK_LEAF_KINDS),
                             *(_control_leaf_install(kind) for kind in leaf.CONTROL_LEAF_KINDS))


url_contract = url.build_url_single_url_contract()
wait_contract = wait.build_batch_business_wait_contract()
dispatch_contract = dispatch.build_batch_task_single_dispatch_contract()
nonworkflow_installed_operations: tuple[InstalledOperation, ...] = (
    candidate_installed_operation, *leaf_installed_operations,
    _install(url_contract, url_contract, url.build_url_single_url_profiles(),
             url.build_url_single_url_request_codec(url_contract.ref),
             url.build_url_single_url_outcome_codec(url_contract.ref), _url),
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
    for item in entries:
        if item.definition.contract.ref.kind == ref.kind:
            if item.definition.contract.ref != ref:
                raise ValueError("installed operation ref drift")
            return item
    return None
