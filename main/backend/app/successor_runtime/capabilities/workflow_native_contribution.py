"""Current workflow-definition contribution over the historical DSL authority.

The rule lowers one authored legacy DSL fact into the existing operation
contracts, catalog, registry, exact ProgramSpec/ExecutionPlan receipt and the
existing workflow family assembly.  :mod:`workflow_legacy_dsl` remains the
authority for parse/validate/compile semantics;
:mod:`workflow_slice_acceptance` and the workflow assembly remain the
authorities for acceptance and kernel wiring.  This rule
owns no domain kernel and creates no runtime, scheduler, cache or second DSL
consumer.
"""

from __future__ import annotations

# Structured architecture-boundary markers intentionally exceed the line limit.
# ruff: noqa: E501

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Final, Literal, NoReturn, cast

from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeContribution,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities import workflow_legacy_dsl as workflow_dsl
from app.successor_runtime.capabilities.workflow_common import (
    WORKFLOW_CONTRACT_KIND_UNSUPPORTED,
    WORKFLOW_DEFINITION_FAILURES,
    WORKFLOW_PROGRAM_PLAN_BINDING_INVALID,
    WorkflowDefinitionFailureCode,
    WorkflowJsonObject,
)
from app.successor_runtime.capabilities.catalog import build_operation_catalog
from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonObject,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.capabilities.profiles import (
    OperationProfiles,
    build_operation_profiles,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    OperationContract,
)
from app.successor_runtime.language.program import (
    ProgramNode,
    ProgramSpec,
    atom_node,
    then_node,
)
from app.successor_runtime.research.object_types import ObjectType

if TYPE_CHECKING:
    from app.successor_runtime.assembly.base import FamilyAssembly

__all__ = [
    "WORKFLOW_NATIVE_CONTRIBUTION_RULE",
    "WORKFLOW_NATIVE_RULE_ID",
    "WORKFLOW_NATIVE_VERIFICATION_INPUTS",
    "ASSEMBLY_CELL_IDS",
    "WORKFLOW_ASSEMBLY_CELL_IDS",
    "WORKFLOW_DEFINITION_COMPILE_CELL_ID",
    "WORKFLOW_DEFINITION_FAILURES",
    "WORKFLOW_FAMILY_ID",
    "WORKFLOW_RUNTIME_OBSERVE_CELL_ID",
    "WORKFLOW_STATE_RESTORE_CELL_ID",
    "WorkflowAssemblyContext",
    "WorkflowNativeBinding",
    "WorkflowNativeContribution",
    "WorkflowNativeDefinition",
    "WorkflowNativeSource",
    "WorkflowCellSource",
    "DEFAULT_WORKFLOW_NATIVE_SOURCE",
    "compile_workflow_native_contribution",
    "WORKFLOW_RUNTIME_CONTEXT_TYPE",
    "WORKFLOW_RUNTIME_NODE_KINDS",
    "WorkflowExecutionContext",
    "WorkflowRuntimeOperationDefinition",
    "WorkflowRuntimeDefinition",
    "WorkflowRuntimeProgram",
    "advance_workflow_execution_context",
    "build_workflow_runtime_definition",
    "build_workflow_runtime_program",
    "decode_workflow_runtime_output",
    "validate_workflow_context_bound_inputs",
    "validate_workflow_execution_context",
]

WORKFLOW_NATIVE_RULE_ID = "mrw.workflow.definition.native-rule.v2"
WORKFLOW_NATIVE_VERIFICATION_INPUTS = (
    "mrw.workflow.definition",
    "mrw.workflow.dsl-compile",
    "mrw.workflow.operation-catalog",
    "mrw.workflow.acceptance-boundary",
    "mrw.workflow.binding",
)

WORKFLOW_FAMILY_ID: Final = "mrw.workflow"
WORKFLOW_DEFINITION_COMPILE_CELL_ID: Final = "workflow.definition.compile.v2"
WORKFLOW_RUNTIME_OBSERVE_CELL_ID: Final = "workflow.runtime.observe.v2"
WORKFLOW_STATE_RESTORE_CELL_ID: Final = "workflow.state.restore.v2"

WORKFLOW_RUNTIME_OWNER: Final = "workflow_graph.run"
WORKFLOW_RUNTIME_CONTEXT_CODEC_ID: Final = "mrw.workflow.runtime.context.v1"
WORKFLOW_RUNTIME_CONTEXT_TYPE = ObjectType(
    type_id="WorkflowRuntimeContext.v1",
    schema_version="1.0.0",
    codec_id=WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
    canonical_codec_version="1",
)
WORKFLOW_RUNTIME_NODE_KINDS: Final = {
    "vector_search": "workflow.runtime.vector-search.v1",
    "llm_call": "workflow.runtime.llm-call.v1",
    "join": "workflow.runtime.join.v1",
}
WORKFLOW_RUNTIME_CATALOG_ID: Final = "mrw.workflow.runtime.operations.v1"
WORKFLOW_RUNTIME_OBSERVATION_PROFILE: Final = "mrw.workflow.runtime.observation.v1"
_WORKFLOW_RUNTIME_FAILURE_WITNESS: Final = (
    "test:test_workflow_runtime_validation_uses_typed_failure_lift"
)
_WORKFLOW_RUNTIME_FAILURE_CONTEXT_KEYS: Final = frozenset(
    {
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _workflow_runtime_failure(
    code: WorkflowDefinitionFailureCode,
    message: str,
    *,
    site: str,
    public_exception: Literal["TypeError", "ValueError"] = "ValueError",
) -> Failure:
    return WORKFLOW_DEFINITION_FAILURES.fail(
        code,
        message,
        {
            "failure_family": WORKFLOW_DEFINITION_FAILURES.name,
            "operation": "validate_workflow_runtime",
            "owner": "workflow.runtime",
            "public_exception": public_exception,
            "public_message": message,
            "site": site,
            "witness": _WORKFLOW_RUNTIME_FAILURE_WITNESS,
        },
    )


def _raise_workflow_runtime_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not WORKFLOW_DEFINITION_FAILURES.matches(failure)
        or _WORKFLOW_RUNTIME_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") not in {"TypeError", "ValueError"}
    ):
        # kit:boundary owner=workflow.runtime.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_workflow_runtime_validation_uses_typed_failure_lift
        raise TypeError(  # noqa: TRY003
            "workflow runtime failure lift context is incomplete"
        )
    message = str(context["public_message"])
    if context["public_exception"] == "TypeError":
        # kit:boundary owner=workflow.runtime.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_workflow_runtime_validation_uses_typed_failure_lift
        raise TypeError(message)
    # kit:boundary owner=workflow.runtime.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_workflow_runtime_validation_uses_typed_failure_lift
    raise ValueError(message)


def _reject_workflow_runtime(
    message: str,
    *,
    site: str,
    code: WorkflowDefinitionFailureCode = WORKFLOW_PROGRAM_PLAN_BINDING_INVALID,
    public_exception: Literal["TypeError", "ValueError"] = "ValueError",
) -> NoReturn:
    _raise_workflow_runtime_failure(
        _workflow_runtime_failure(
            code,
            message,
            site=site,
            public_exception=public_exception,
        )
    )


@dataclass(frozen=True, slots=True)
class WorkflowExecutionContext:
    """Exact typed value transported between durable workflow node occurrences."""

    schema: str
    workflow_id: str
    project_key: str
    trace_id: str
    inputs: CanonicalJsonObject
    nodes: tuple[CanonicalJsonObject, ...]
    cursor: int
    results: CanonicalJsonObject


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeOperationDefinition:
    node_type: str
    contract: OperationContract
    profiles: OperationProfiles
    context_codec: PayloadCodec[WorkflowExecutionContext]


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeDefinition:
    """Installed facts for the three existing workflow node kernels."""

    operations: tuple[WorkflowRuntimeOperationDefinition, ...]
    catalog: OperationContractCatalogSnapshot
    registry: OperationContractRegistry

    def operation_for_node_type(
        self, node_type: str
    ) -> WorkflowRuntimeOperationDefinition:
        for operation in self.operations:
            if operation.node_type == node_type:
                return operation
        _reject_workflow_runtime(
            f"unsupported workflow runtime node type: {node_type}",
            code=WORKFLOW_CONTRACT_KIND_UNSUPPORTED,
            site="WorkflowRuntimeDefinition.operation_for_node_type",
        )

    def operation_for_kind(self, kind: str) -> WorkflowRuntimeOperationDefinition:
        for operation in self.operations:
            if operation.contract.ref.kind == kind:
                return operation
        _reject_workflow_runtime(
            f"unsupported workflow runtime operation kind: {kind}",
            code=WORKFLOW_CONTRACT_KIND_UNSUPPORTED,
            site="WorkflowRuntimeDefinition.operation_for_kind",
        )


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeProgram:
    """One durable workflow Program plus its exact static occurrence values."""

    program: ProgramSpec
    catalog: OperationContractCatalogSnapshot
    registry: OperationContractRegistry
    values: tuple[tuple[ValueRef, bytes], ...]
    canonical_bindings: Mapping[str, tuple[int, str]]
    operation_ids: tuple[str, ...]


def _build_workflow_runtime_profiles(node_type: str, kind: str) -> OperationProfiles:
    network_required = node_type in {"vector_search", "llm_call"}
    resource_class = "NETWORK_IO" if network_required else "CPU"
    dependency_digest = content_digest(
        {
            "interpreter": "app.services.workflow_graph.executors.kernel.execute_node",
            "node_type": node_type,
            "version": "1.0.0",
        }
    )
    return build_operation_profiles(
        identity=kind,
        semantic={
            "reads": (WORKFLOW_RUNTIME_CONTEXT_TYPE.type_id,),
            "creates": (WORKFLOW_RUNTIME_CONTEXT_TYPE.type_id,),
            "creates_relations": ("workflow.runtime.precedes",),
            "declared_loss": (),
            "observation_profile_ref": WORKFLOW_RUNTIME_OBSERVATION_PROFILE,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": network_required,
            "irreversible": False,
            "cancellation_points": ("step_boundary",),
            "internal_export_only": True,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": "logical_request_id",
        },
        resource={
            "resource_classes": (resource_class,),
            "concurrency_key": "project:workflow-graph",
            "budget_units": "node",
            "default_soft_limit_seconds": 120,
            "default_hard_limit_seconds": 300,
            "node_profile_selector": "any",
            "budget_ref": "workflow.runtime.node-budget.v1",
            "deadline_policy_ref": "workflow.runtime.node-deadline.v1",
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": (
                "WORKFLOW_NODE_INPUT_INVALID",
                "WORKFLOW_NODE_EFFECT_FAILED",
                "WORKFLOW_NODE_BINDING_DRIFT",
            ),
            "retryable": False,
            "degraded_acceptable": True,
            "unknown_outcome_supported": network_required,
            "readback_or_compensation": "readback" if network_required else "none",
            "failure_union_ref": f"{kind}.failures",
            "retryable_failure_kinds": (),
            "readback_profile_ref": (
                WORKFLOW_RUNTIME_OBSERVATION_PROFILE if network_required else None
            ),
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": (),
            "canonical_owner": WORKFLOW_RUNTIME_OWNER,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "supported_contract_kinds": (kind,),
            "supported_contract_refs": (),
            "dependency_digest": dependency_digest,
            "security_profile_ref": "mrw.workflow.runtime.security.v1",
            "resource_profile_ref": f"{kind}.resource",
            "credential_requirements_ref": None,
            "cancellation_profile_ref": "step_boundary",
            "idempotency_profile_ref": "logical_request_id",
            "authoritative_readback_profile_ref": None,
            "receipt_codec_ref": WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
        },
        observation={
            "dimensions": (
                "workflow_id",
                "node_id",
                "node_type",
                "status",
                "cursor",
            ),
            "compatible_with_legacy": True,
            "observation_schema_ref": WORKFLOW_RUNTIME_OBSERVATION_PROFILE,
        },
    )


def build_workflow_runtime_definition() -> Annotated[
    WorkflowRuntimeDefinition,
    (
        "kit:non-authoritative derived_as=view "
        "fact_source=WORKFLOW_RUNTIME_NODE_KINDS+profile_constants "
        "witness=test:test_runtime_program_uses_real_profiles_exact_bytes_and_unique_occurrences"
    ),
]:
    """Build the current durable declarations without changing compile history."""

    operation_parts: list[
        tuple[str, OperationContract, OperationProfiles]
    ] = []
    for node_type, kind in WORKFLOW_RUNTIME_NODE_KINDS.items():
        profiles = _build_workflow_runtime_profiles(node_type, kind)
        contract = profiles.contract(
            kind=kind,
            contract_version="1",
            input_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
            output_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
            return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
            allowed_override_schema_ref="mrw.workflow.runtime.override.none.v1",
            owner_capability_id=WORKFLOW_RUNTIME_OWNER,
        )
        operation_parts.append((node_type, contract, profiles))
    contracts = tuple(contract for _, contract, _ in operation_parts)
    catalog = build_operation_catalog(
        contracts,
        catalog_id=WORKFLOW_RUNTIME_CATALOG_ID,
        catalog_version="1",
    )
    registry = OperationContractRegistry(catalog=catalog, contracts=contracts)
    operations = tuple(
        WorkflowRuntimeOperationDefinition(
            node_type=node_type,
            contract=contract,
            profiles=profiles,
            context_codec=_build_workflow_context_codec(contract),
        )
        for node_type, contract, profiles in operation_parts
    )
    return WorkflowRuntimeDefinition(
        operations=operations,
        catalog=catalog,
        registry=registry,
    )


def _build_workflow_context_codec(
    contract: OperationContract,
) -> PayloadCodec[WorkflowExecutionContext]:
    base = dataclass_codec(
        codec_id=WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
        codec_version="1",
        contract_ref=contract.ref,
        payload_type_id=WORKFLOW_RUNTIME_CONTEXT_TYPE.type_id,
        dto_cls=WorkflowExecutionContext,
    )

    def decode(value: CanonicalJsonObject) -> WorkflowExecutionContext:
        nodes_raw = value.get("nodes")
        inputs_raw = value.get("inputs")
        results_raw = value.get("results")
        if (
            not isinstance(nodes_raw, list)
            or not all(isinstance(node, dict) for node in nodes_raw)
            or not isinstance(inputs_raw, dict)
            or not isinstance(results_raw, dict)
            or not all(isinstance(result, dict) for result in results_raw.values())
        ):
            _reject_workflow_runtime(
                "workflow runtime context JSON shape is invalid",
                site="_build_workflow_context_codec.decode.shape",
                public_exception="TypeError",
            )
        schema = value.get("schema")
        workflow_id = value.get("workflow_id")
        project_key = value.get("project_key")
        trace_id = value.get("trace_id")
        cursor = value.get("cursor")
        if (
            not isinstance(schema, str)
            or not isinstance(workflow_id, str)
            or not isinstance(project_key, str)
            or not isinstance(trace_id, str)
            or not isinstance(cursor, int)
            or isinstance(cursor, bool)
        ):
            _reject_workflow_runtime(
                "workflow runtime context identity is invalid",
                site="_build_workflow_context_codec.decode.identity",
                public_exception="TypeError",
            )
        return WorkflowExecutionContext(
            schema=schema,
            workflow_id=workflow_id,
            project_key=project_key,
            trace_id=trace_id,
            inputs=inputs_raw,
            nodes=tuple(cast(CanonicalJsonObject, node) for node in nodes_raw),
            cursor=cursor,
            results=results_raw,
        )

    return PayloadCodec(
        codec_id=base.codec_id,
        codec_version=base.codec_version,
        contract_ref=base.contract_ref,
        payload_type_id=base.payload_type_id,
        encode=base.encode_payload,
        decode=decode,
        codec_digest=base.codec_digest,
    )


def validate_workflow_execution_context(
    context: WorkflowExecutionContext,
    *,
    expected_node_type: str | None = None,
    require_prior_results: bool = True,
) -> CanonicalJsonObject:
    """Return the current node after checking the exact transported context."""

    if context.schema != "mrw.workflow.runtime.context.v1":
        _reject_workflow_runtime(
            "workflow runtime context schema drift",
            site="validate_workflow_execution_context.schema",
        )
    if not context.workflow_id or not context.project_key or not context.trace_id:
        _reject_workflow_runtime(
            "workflow runtime context identity is incomplete",
            site="validate_workflow_execution_context.identity",
        )
    if context.cursor < 0 or context.cursor >= len(context.nodes):
        _reject_workflow_runtime(
            "workflow runtime cursor is outside the declared nodes",
            site="validate_workflow_execution_context.cursor",
        )
    node = context.nodes[context.cursor]
    node_id = node.get("node_id")
    node_type = node.get("node_type")
    if not isinstance(node_id, str) or not node_id:
        _reject_workflow_runtime(
            "workflow runtime node_id is invalid",
            site="validate_workflow_execution_context.node_id",
        )
    if node_type not in WORKFLOW_RUNTIME_NODE_KINDS:
        _reject_workflow_runtime(
            "workflow runtime node_type is invalid",
            site="validate_workflow_execution_context.node_type",
        )
    if expected_node_type is not None and node_type != expected_node_type:
        _reject_workflow_runtime(
            "workflow runtime operation/node type drift",
            site="validate_workflow_execution_context.operation",
        )
    if require_prior_results and set(context.results) != {
        str(item.get("node_id")) for item in context.nodes[: context.cursor]
    }:
        _reject_workflow_runtime(
            "workflow runtime prior results do not match the cursor",
            site="validate_workflow_execution_context.results",
        )
    return node


def validate_workflow_context_bound_inputs(
    context: WorkflowExecutionContext,
    bound_inputs: tuple[tuple[ValueRef, bytes], ...],
    *,
    operation: WorkflowRuntimeOperationDefinition,
) -> None:
    """Bind the dynamic context to this Atom's exact static occurrence fact."""

    validate_workflow_execution_context(
        context,
        expected_node_type=operation.node_type,
    )
    if len(bound_inputs) != 1:
        _reject_workflow_runtime(
            "workflow runtime Atom requires one static occurrence input",
            site="validate_workflow_context_bound_inputs.arity",
        )
    ref, exact = bound_inputs[0]
    if (
        ref.object_type != WORKFLOW_RUNTIME_CONTEXT_TYPE
        or ref.codec_id != WORKFLOW_RUNTIME_CONTEXT_CODEC_ID
        or ref.byte_size != len(exact)
        or ref.content_digest != sha256_hex(exact)
    ):
        _reject_workflow_runtime(
            "workflow runtime static occurrence binding drift",
            site="validate_workflow_context_bound_inputs.binding",
        )
    decoded = json.loads(exact)
    if not isinstance(decoded, dict):
        _reject_workflow_runtime(
            "workflow runtime static occurrence bytes are noncanonical",
            site="validate_workflow_context_bound_inputs.shape",
        )
    decoded_object = cast(CanonicalJsonObject, decoded)
    if canonical_json(decoded_object).encode() != exact:
        _reject_workflow_runtime(
            "workflow runtime static occurrence bytes are noncanonical",
            site="validate_workflow_context_bound_inputs.canonical_bytes",
        )
    static_context = operation.context_codec.decode_payload(decoded_object)
    validate_workflow_execution_context(
        static_context,
        expected_node_type=operation.node_type,
        require_prior_results=False,
    )
    if (
        static_context.workflow_id != context.workflow_id
        or static_context.project_key != context.project_key
        or static_context.trace_id != context.trace_id
        or static_context.inputs != context.inputs
        or static_context.nodes != context.nodes
        or static_context.cursor != context.cursor
    ):
        _reject_workflow_runtime(
            "workflow runtime dynamic/static occurrence identity drift",
            site="validate_workflow_context_bound_inputs.identity",
        )


def decode_workflow_runtime_output(
    value_ref: ValueRef,
    exact: bytes,
) -> WorkflowExecutionContext:
    """Decode one digest-verified durable output with its matching operation codec."""

    if (
        value_ref.object_type != WORKFLOW_RUNTIME_CONTEXT_TYPE
        or value_ref.codec_id != WORKFLOW_RUNTIME_CONTEXT_CODEC_ID
        or value_ref.byte_size != len(exact)
        or value_ref.content_digest != sha256_hex(exact)
    ):
        _reject_workflow_runtime(
            "workflow runtime output value binding drift",
            site="decode_workflow_runtime_output.binding",
        )
    decoded = json.loads(exact)
    if not isinstance(decoded, dict):
        _reject_workflow_runtime(
            "workflow runtime output bytes are noncanonical",
            site="decode_workflow_runtime_output.shape",
        )
    decoded_object = cast(CanonicalJsonObject, decoded)
    if canonical_json(decoded_object).encode() != exact:
        _reject_workflow_runtime(
            "workflow runtime output bytes are noncanonical",
            site="decode_workflow_runtime_output.canonical_bytes",
        )

    nodes = decoded_object.get("nodes")
    cursor = decoded_object.get("cursor")
    if (
        not isinstance(nodes, list)
        or not isinstance(cursor, int)
        or isinstance(cursor, bool)
        or cursor <= 0
        or cursor > len(nodes)
    ):
        _reject_workflow_runtime(
            "workflow runtime output cursor is invalid",
            site="decode_workflow_runtime_output.cursor",
        )
    completed_node = nodes[cursor - 1]
    if not isinstance(completed_node, dict):
        _reject_workflow_runtime(
            "workflow runtime output node is invalid",
            site="decode_workflow_runtime_output.node",
        )
    node_type = completed_node.get("node_type")
    if not isinstance(node_type, str):
        _reject_workflow_runtime(
            "workflow runtime output node type is invalid",
            site="decode_workflow_runtime_output.node_type",
        )
    operation = build_workflow_runtime_definition().operation_for_node_type(node_type)
    context = operation.context_codec.decode_payload(decoded_object)

    if context.schema != "mrw.workflow.runtime.context.v1":
        _reject_workflow_runtime(
            "workflow runtime output schema drift",
            site="decode_workflow_runtime_output.schema",
        )
    if not context.workflow_id or not context.project_key or not context.trace_id:
        _reject_workflow_runtime(
            "workflow runtime output identity is incomplete",
            site="decode_workflow_runtime_output.identity",
        )
    expected_result_ids = {
        str(item.get("node_id")) for item in context.nodes[: context.cursor]
    }
    if set(context.results) != expected_result_ids:
        _reject_workflow_runtime(
            "workflow runtime output results do not match the cursor",
            site="decode_workflow_runtime_output.results",
        )
    return context


def advance_workflow_execution_context(
    context: WorkflowExecutionContext,
    *,
    node_id: str,
    result: CanonicalJsonObject,
) -> WorkflowExecutionContext:
    """Transport one typed kernel result to the next occurrence."""

    current = validate_workflow_execution_context(context)
    if current["node_id"] != node_id:
        _reject_workflow_runtime(
            "workflow runtime result node_id drift",
            site="advance_workflow_execution_context.node_id",
        )
    next_results = dict(context.results)
    next_results[node_id] = result
    return WorkflowExecutionContext(
        schema=context.schema,
        workflow_id=context.workflow_id,
        project_key=context.project_key,
        trace_id=context.trace_id,
        inputs=dict(context.inputs),
        nodes=context.nodes,
        cursor=context.cursor + 1,
        results=next_results,
    )


def _workflow_runtime_value_ref(
    *,
    context: WorkflowExecutionContext,
    codec: PayloadCodec[WorkflowExecutionContext],
    program_id: str,
    project_key: str,
    ordinal: int,
    node_id: str,
) -> tuple[ValueRef, bytes]:
    exact = canonical_json(codec.encode_payload(context)).encode()
    value_id = f"{program_id}:node:{ordinal}:{node_id}:context"
    digest = sha256_hex(exact)
    return (
        ValueRef(
            value_id=value_id,
            project_key=project_key,
            object_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
            codec_id=WORKFLOW_RUNTIME_CONTEXT_CODEC_ID,
            content_digest=digest,
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref=f"project-value:{value_id}",
            byte_size=len(exact),
            provenance_digest=content_digest(
                {
                    "schema": "mrw.workflow.runtime.occurrence-provenance.v1",
                    "program_id": program_id,
                    "project_key": project_key,
                    "ordinal": ordinal,
                    "node_id": node_id,
                    "content_digest": digest,
                }
            ),
        ),
        exact,
    )


def build_workflow_runtime_program(
    *,
    workflow_id: str,
    nodes: tuple[CanonicalJsonObject, ...],
    topo_order: tuple[str, ...],
    inputs: CanonicalJsonObject,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    incarnation: str,
    trace_id: str,
) -> Annotated[
    WorkflowRuntimeProgram,
    (
        "kit:non-authoritative derived_as=view "
        "fact_source=workflow_compiled_graph+runtime_definition "
        "witness=test:test_runtime_program_uses_real_profiles_exact_bytes_and_unique_occurrences"
    ),
]:
    """Lower one compiled graph to exact installed node occurrences."""

    if not workflow_id or not program_id or not project_key or not trace_id:
        _reject_workflow_runtime(
            "workflow runtime Program identity is incomplete",
            site="build_workflow_runtime_program.identity",
        )
    if not incarnation:
        _reject_workflow_runtime(
            "workflow runtime Program requires an incarnation",
            site="build_workflow_runtime_program.incarnation",
        )
    nodes_by_id: dict[str, CanonicalJsonObject] = {}
    for raw_node in nodes:
        node_id = raw_node.get("node_id")
        node_type = raw_node.get("node_type")
        params = raw_node.get("params")
        depends_on = raw_node.get("depends_on")
        if (
            not isinstance(node_id, str)
            or not node_id
            or node_id in nodes_by_id
            or node_type not in WORKFLOW_RUNTIME_NODE_KINDS
            or not isinstance(params, dict)
            or not isinstance(depends_on, list)
            or not all(isinstance(item, str) for item in depends_on)
        ):
            _reject_workflow_runtime(
                "workflow runtime node declaration is invalid",
                site="build_workflow_runtime_program.node_declaration",
            )
        nodes_by_id[node_id] = {
            "node_id": node_id,
            "node_type": node_type,
            "params": dict(params),
            "depends_on": list(depends_on),
        }
    if not topo_order or len(topo_order) != len(nodes_by_id):
        _reject_workflow_runtime(
            "workflow runtime Program requires a complete nonempty topo order",
            site="build_workflow_runtime_program.topo_order_arity",
        )
    if len(set(topo_order)) != len(topo_order) or set(topo_order) != set(nodes_by_id):
        _reject_workflow_runtime(
            "workflow runtime topo order differs from declared nodes",
            site="build_workflow_runtime_program.topo_order_identity",
        )
    ordered_nodes = tuple(nodes_by_id[node_id] for node_id in topo_order)
    for ordinal, node in enumerate(ordered_nodes):
        depends_value = node.get("depends_on")
        if not isinstance(depends_value, list):
            _reject_workflow_runtime(
                "workflow runtime node dependencies are invalid",
                site="build_workflow_runtime_program.dependencies",
            )
        declared_dependencies = {
            value for value in depends_value if isinstance(value, str)
        }
        if not declared_dependencies <= set(topo_order[:ordinal]):
            _reject_workflow_runtime(
                "workflow runtime node dependency is not earlier in topo order",
                site="build_workflow_runtime_program.dependency_order",
            )

    definition = build_workflow_runtime_definition()
    atoms: list[ProgramNode] = []
    values: list[tuple[ValueRef, bytes]] = []
    operation_ids: list[str] = []
    for ordinal, node in enumerate(ordered_nodes):
        node_id = str(node["node_id"])
        node_type = str(node["node_type"])
        operation = definition.operation_for_node_type(node_type)
        context = WorkflowExecutionContext(
            schema="mrw.workflow.runtime.context.v1",
            workflow_id=workflow_id,
            project_key=project_key,
            trace_id=trace_id,
            inputs=dict(inputs),
            nodes=ordered_nodes,
            cursor=ordinal,
            results={},
        )
        value_ref, exact = _workflow_runtime_value_ref(
            context=context,
            codec=operation.context_codec,
            program_id=program_id,
            project_key=project_key,
            ordinal=ordinal,
            node_id=node_id,
        )
        operation_id = f"workflow-node:{ordinal}:{node_id}"
        operation_ids.append(operation_id)
        values.append((value_ref, exact))
        atoms.append(
            atom_node(
                OperationSpec(
                    operation_id=operation_id,
                    contract_ref=operation.contract.ref,
                    input_refs=(value_ref,),
                    payload_ref=value_ref,
                    allowed_overrides=freeze_json_object({}),
                ),
                input_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
                output_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
            )
        )
    root = atoms[0]
    for atom in atoms[1:]:
        root = then_node(root, atom)
    program = ProgramSpec(
        program_id=program_id,
        contract_version="mrw.workflow.runtime.program.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="workflow.runtime.ordered-topology.v1",
        input_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
        output_type=WORKFLOW_RUNTIME_CONTEXT_TYPE,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=WORKFLOW_RUNTIME_OBSERVATION_PROFILE,
        metadata=freeze_json_object(
            {
                "schema": "mrw.workflow.runtime.program-metadata.v1",
                "workflow_id": workflow_id,
                "topo_order": list(topo_order),
                "operation_ids": operation_ids,
                "project_scope_digest": project_scope_digest,
                "canonical_owner": WORKFLOW_RUNTIME_OWNER,
            }
        ),
        program_digest="",
    ).with_digest()
    plan = compile_program(
        program,
        definition.catalog,
        operation_contracts=definition.registry,
    )
    effects = tuple(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    if len(effects) != len(atoms):
        _reject_workflow_runtime(
            "workflow runtime Program effect count drift",
            site="build_workflow_runtime_program.effect_count",
        )
    return WorkflowRuntimeProgram(
        program=program,
        catalog=definition.catalog,
        registry=definition.registry,
        values=tuple(values),
        canonical_bindings={step.step_id: (0, incarnation) for step in effects},
        operation_ids=tuple(operation_ids),
    )

WorkflowCellRole = Literal[
    "definition_compile",
    "runtime_observe",
    "state_restore",
]


@dataclass(frozen=True, slots=True)
class WorkflowCellSource:
    """One ordered workflow cell and its runtime-kernel identity."""

    cell_id: str
    role: WorkflowCellRole
    owner: str
    kernel_id: str | None
    kernel_version: str
    digest_preimage: str
    recovery_binding_ref: str

@dataclass(frozen=True, slots=True)
class WorkflowNativeSource:
    """One authored workflow definition fact: exact DSL payload plus its rollback authority."""

    contribution_id: str
    owner: str
    family_id: str
    cells: tuple[WorkflowCellSource, ...]
    dsl_payload: WorkflowJsonObject
    rollback_refs: tuple[str, ...]
    interpreter_profile_id: str
    deployment_catalog_preimage: str
    authority_requirement_preimage: str


DEFAULT_WORKFLOW_NATIVE_SOURCE = WorkflowNativeSource(
    contribution_id="mrw.workflow.definition.native.v2",
    owner="workflow.definition.v2",
    family_id=WORKFLOW_FAMILY_ID,
    cells=(
        WorkflowCellSource(
            cell_id=WORKFLOW_DEFINITION_COMPILE_CELL_ID,
            role="definition_compile",
            owner="workflow.definition.v2",
            kernel_id=None,
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.definition.compile.handler.v2",
            recovery_binding_ref="mrw.workflow.definition.compile.recovery.v2",
        ),
        WorkflowCellSource(
            cell_id=WORKFLOW_RUNTIME_OBSERVE_CELL_ID,
            role="runtime_observe",
            owner="workflow.runtime.v2",
            kernel_id="mrw.workflow.runtime-observe.kernel.v2",
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.runtime-observe.kernel-wiring.v2",
            recovery_binding_ref="mrw.workflow.runtime.observe.recovery.v2",
        ),
        WorkflowCellSource(
            cell_id=WORKFLOW_STATE_RESTORE_CELL_ID,
            role="state_restore",
            owner="workflow.state.v2",
            kernel_id="mrw.workflow.state-restore.replay.v2",
            kernel_version="2.0.0",
            digest_preimage="mrw.workflow.state-restore.kernel-wiring.v2",
            recovery_binding_ref="mrw.workflow.state.restore.recovery.v2",
        ),
    ),
    dsl_payload={
        "version": "1.0",
        "options": {},
        "nodes": [
            {"node_id": "retrieve", "node_type": "vector_search", "config": {"top_k": 5}},
            {"node_id": "draft", "node_type": "llm_call", "config": {"model": "mrw-local"}},
            {"node_id": "combine", "node_type": "join", "config": {"field": "values"}},
        ],
        "edges": [
            {"from": "retrieve", "to": "combine"},
            {"from": "draft", "to": "combine"},
        ],
    },
    rollback_refs=(
        "main/backend/app/successor_runtime/capabilities/workflow_legacy_dsl.py",
        "main/backend/app/successor_runtime/capabilities/workflow_slice_acceptance.py",
        "main/backend/app/services/workflow_graph/runtime.py",
    ),
    interpreter_profile_id="workflow.definition.compile.interpreter.v2",
    deployment_catalog_preimage="mrw.workflow.deployment-catalog.v2",
    authority_requirement_preimage="mrw.workflow.definition.compile.authority.v2",
)

ASSEMBLY_CELL_IDS: Final = tuple(
    cell.cell_id for cell in DEFAULT_WORKFLOW_NATIVE_SOURCE.cells
)
WORKFLOW_ASSEMBLY_CELL_IDS = ASSEMBLY_CELL_IDS


@dataclass(frozen=True, slots=True)
class WorkflowNativeDefinition:
    """Lowered view of one authored workflow source over existing authorities."""

    source: WorkflowNativeSource
    receipt: workflow_dsl.WorkflowLegacyDSLReceipt
    operation_contracts: tuple[workflow_dsl.OperationContract, ...]
    catalog: workflow_dsl.OperationContractCatalogSnapshot
    registry: workflow_dsl.OperationContractRegistry

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
        context_type = workflow_dsl.WORKFLOW_CONTEXT_TYPE.type_id
        for operation in self.operation_contracts:
            declared = (
                (context_type, "ObjectType", ()),
                (
                    operation.ref.kind,
                    "Capability",
                    (context_type, context_type),
                ),
            )
            for object_id, kind, references in declared:
                key = (object_id, kind, self.source.owner)
                prior_references = merged.setdefault(key, ())
                merged[key] = prior_references + tuple(
                    reference
                    for reference in references
                    if reference not in prior_references
                )
        return tuple(
            ContributionObject(object_id, kind, owner, references)
            for (object_id, kind, owner), references in merged.items()
        )


def _definition_issues(
    source: WorkflowNativeSource,
    definition: WorkflowNativeDefinition,
) -> tuple[NativeBindingIssue, ...]:
    issues: tuple[NativeBindingIssue, ...] = ()
    checks: tuple[tuple[bool, str, str], ...] = (
        (bool(source.owner), "$.source.owner", "owner is empty"),
        (
            source.family_id == WORKFLOW_FAMILY_ID,
            "$.source.family_id",
            "workflow family identity drift",
        ),
        (
            len(source.cells) == 3
            and tuple(cell.cell_id for cell in source.cells) == ASSEMBLY_CELL_IDS,
            "$.source.cells",
            "workflow cell order drift",
        ),
        (
            tuple(cell.role for cell in source.cells)
            == ("definition_compile", "runtime_observe", "state_restore"),
            "$.source.cells",
            "workflow cell roles drift",
        ),
        (
            len(source.cells) == 3
            and source.cells[0].kernel_id is None
            and all(cell.kernel_id for cell in source.cells[1:]),
            "$.source.cells.kernel_id",
            "compile cell must be a handler and observe/restore must be kernels",
        ),
        (
            all(
                value and ".c1" not in value and "successor" not in value
                for value in (
                    source.interpreter_profile_id,
                    source.deployment_catalog_preimage,
                    source.authority_requirement_preimage,
                    *(cell.digest_preimage for cell in source.cells),
                    *(cell.recovery_binding_ref for cell in source.cells),
                    *(cell.kernel_id or "workflow.definition.compile.handler.v2" for cell in source.cells),
                )
            ),
            "$.source.runtime_identity",
            "current workflow runtime identity contains historical C1/successor naming",
        ),
        (bool(source.rollback_refs), "$.source.rollback_refs", "rollback binding is empty"),
        (definition.receipt.ok, "$.source.dsl_payload", "DSL did not compile successfully"),
        (
            definition.receipt.node_count > 0,
            "$.source.dsl_payload.nodes",
            "compiled DSL has no nodes",
        ),
        (
            definition.receipt.provider_calls == 0
            and definition.receipt.store_writes == 0
            and definition.receipt.canonical_effect_calls == 0,
            "$.source.dsl_payload.effects",
            "Workflow compile must remain pure",
        ),
        (
            definition.catalog.catalog_digest == definition.receipt.catalog_digest,
            "$.catalog_digest",
            "operation catalog digest drifts from compiled receipt",
        ),
        (
            tuple(operation.ref.kind for operation in definition.operation_contracts)
            == tuple(entry[0] for entry in definition.catalog.entries),
            "$.operation_contracts",
            "contract/catalog operation order drift",
        ),
    )
    issues += tuple(
        NativeBindingIssue(path, message)
        for valid, path, message in checks
        if not valid
    )
    return issues


def lower_workflow_native_source(source: WorkflowNativeSource) -> WorkflowNativeDefinition | Failure:
    operation_contracts = workflow_dsl.build_workflow_operation_contracts()
    catalog = workflow_dsl.build_workflow_catalog(operation_contracts)
    registry = workflow_dsl.build_workflow_registry(operation_contracts)
    receipt = workflow_dsl.parse_and_validate_workflow_dsl(
        source.dsl_payload,
        catalog=catalog,
        operation_contracts=registry,
    )
    definition = WorkflowNativeDefinition(
        source=source,
        receipt=receipt,
        operation_contracts=operation_contracts,
        catalog=catalog,
        registry=registry,
    )
    issues = _definition_issues(source, definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native workflow definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return definition


def project_workflow_native_definition(
    definition: WorkflowNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        failures=(WORKFLOW_DEFINITION_FAILURES, contribution_failures),
    )


@dataclass(frozen=True, slots=True)
class WorkflowAssemblyContext:
    """Explicit inert assembly boundary; the C1.1 handler remains pure."""

    project_scope_digest: str


@dataclass(frozen=True, slots=True)
class WorkflowNativeBinding:
    """Derived workflow binding over the existing family assembly and compiler."""

    definition: WorkflowNativeDefinition
    family_assembly: FamilyAssembly

    @property
    def rollback_binding_refs_by_cell(self) -> tuple[tuple[str, ...], ...]:
        """Read the actual installed rollback declarations, not the source."""
        return tuple(
            rollback.binding_refs
            for rollback in self.family_assembly.rollback_bindings
        )

    @property
    def receipt(self) -> workflow_dsl.WorkflowLegacyDSLReceipt:
        return self.definition.receipt


def assemble_workflow_native_definition(
    definition: WorkflowNativeDefinition,
    context: WorkflowAssemblyContext,
) -> WorkflowNativeBinding | Failure:
    from app.successor_runtime.assembly.workflow_assembly import build_workflow_assembly

    family_assembly = build_workflow_assembly(
        project_scope_digest=context.project_scope_digest,
        native=definition,
    )
    return WorkflowNativeBinding(
        definition=definition,
        family_assembly=family_assembly,
    )


def _issue_tuple(checks: tuple[tuple[bool, str, str], ...]) -> tuple[NativeBindingIssue, ...]:
    return tuple(
        NativeBindingIssue(path, message) for valid, path, message in checks if not valid
    )


def validate_workflow_native_binding(
    definition: WorkflowNativeDefinition,
    candidate: object,
) -> BindingAccepted[WorkflowNativeBinding] | BindingRejected:
    if not isinstance(candidate, WorkflowNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected WorkflowNativeBinding"),))
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.family_assembly.family_id == definition.source.family_id,
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (
                tuple(cell.cell_id for cell in candidate.family_assembly.cells)
                == ASSEMBLY_CELL_IDS,
                "$.binding.family_assembly.cells",
                "workflow cell order drift",
            ),
            (
                tuple(rollback.cell_id for rollback in candidate.family_assembly.rollback_bindings)
                == ASSEMBLY_CELL_IDS,
                "$.binding.rollback_bindings",
                "rollback binding cell order drift",
            ),
            (
                tuple(rollback.status for rollback in candidate.family_assembly.rollback_bindings)
                == ("PRESENT", "PRESENT", "PRESENT"),
                "$.binding.rollback_bindings",
                "rollback binding status drift",
            ),
            (
                candidate.family_assembly.rollback_bindings[0].binding_refs
                == definition.source.rollback_refs,
                f"$.binding.rollback_bindings.{ASSEMBLY_CELL_IDS[0]}",
                "workflow compile rollback binding drift from authored source",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_workflow_native_definition(
    definition: WorkflowNativeDefinition,
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
        f"test_workflow_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=WORKFLOW_NATIVE_RULE_ID,
        inputs=WORKFLOW_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=WORKFLOW_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


WORKFLOW_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    WorkflowNativeSource,
    WorkflowNativeDefinition,
    WorkflowAssemblyContext,
    WorkflowNativeBinding,
](
    lower=lower_workflow_native_source,
    project=project_workflow_native_definition,
    assemble=assemble_workflow_native_definition,
    validate_binding=validate_workflow_native_binding,
    verification=verify_workflow_native_definition,
)

WorkflowNativeContribution = NativeContribution[
    WorkflowNativeDefinition,
    WorkflowAssemblyContext,
    WorkflowNativeBinding,
]


def compile_workflow_native_contribution(
    source: WorkflowNativeSource,
) -> WorkflowNativeContribution | Failure:
    return compile_native_contribution(source, WORKFLOW_NATIVE_CONTRIBUTION_RULE)
