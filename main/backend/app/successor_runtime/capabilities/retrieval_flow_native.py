"""Typed retrieval method contribution rule.

The typed flow-expression language and its lowering/assembly substrate live in
``retrieval_common`` and are re-exported here for the existing consumers. This
module adds only the native contribution rule: projection and explicit, typed
operation binding. It never imports a concrete provider callable or another
capability's implementation.
"""

from __future__ import annotations

from functorial_kit.contribution_compiler import NativeContributionRule, compile_native_contribution
from functorial_kit.contributions import ContributionObject
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities.retrieval_common import (
    CANDIDATE_BUNDLE_TYPE,
    CANDIDATE_REQUEST_TYPE,
    FlowEdge,
    FlowEnd,
    FlowIdentity,
    FlowInterface,
    FlowOccurrence,
    FlowOperation,
    FlowOperationBinding,
    FlowPort,
    FlowThen,
    PortWire,
    RetrievalFlowAssemblyContext,
    RetrievalFlowBinding,
    RetrievalFlowDefinition,
    RetrievalFlowSource,
    RetrievalMethodIndexEntry,
    assemble_retrieval_flow_definition,
    lower_retrieval_flow_source,
    project_retrieval_method_index,
)


def project_retrieval_flow_definition(definition: RetrievalFlowDefinition) -> ProjectedContributionSpec:
    owner = definition.source.owner
    operation_ids = tuple(dict.fromkeys(item.operation.operation_id for item in definition.occurrences))
    objects = (ContributionObject(definition.contribution_id, "Method", owner, operation_ids),)
    if definition.source.indexed:
        objects += (ContributionObject(f"{definition.contribution_id}.index", "MethodIndex", owner, (definition.contribution_id,)),)
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=owner,
        objects=objects,
    )


def validate_retrieval_flow_binding(
    definition: RetrievalFlowDefinition, candidate: object,
) -> BindingAccepted[RetrievalFlowBinding] | BindingRejected:
    if isinstance(candidate, RetrievalFlowBinding) and candidate.definition == definition:
        assembled = assemble_retrieval_flow_definition(definition, RetrievalFlowAssemblyContext(candidate.bindings))
        if not isinstance(assembled, Failure):
            return BindingAccepted(candidate)
    return BindingRejected((NativeBindingIssue("$.binding", "retrieval flow binding definition or typed operations mismatch"),))


RETRIEVAL_FLOW_NATIVE_RULE = NativeContributionRule[
    RetrievalFlowSource, RetrievalFlowDefinition, RetrievalFlowAssemblyContext, RetrievalFlowBinding
](
    lower=lower_retrieval_flow_source,
    project=project_retrieval_flow_definition,
    assemble=assemble_retrieval_flow_definition,
    validate_binding=validate_retrieval_flow_binding,
)


def compile_retrieval_flow_native(source: RetrievalFlowSource):
    return compile_native_contribution(source, RETRIEVAL_FLOW_NATIVE_RULE)


FIXED_CANDIDATE_OPERATION = FlowOperation(
    operation_id="retrieval.candidate.discover.v1", version="1",
    inputs=FlowInterface((FlowPort("query", CANDIDATE_REQUEST_TYPE),)),
    outputs=FlowInterface((FlowPort("candidates", CANDIDATE_BUNDLE_TYPE),)),
    effect_refs=("provider.search",), failure_refs=("candidate.provider_observation",),
    entrypoint_ref="services.search.candidate_search.discover_candidates",
)
DEFAULT_RETRIEVAL_FLOW_SOURCE = RetrievalFlowSource(
    "mrw.retrieval.fixed-candidate", "1", "services.search.candidate_search",
    FlowOccurrence("discover:0", FIXED_CANDIDATE_OPERATION),
)
