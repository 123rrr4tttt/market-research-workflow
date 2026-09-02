"""C1.1 legacy graph DSL -> typed successor Program facade.

movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity
movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples

This module is the pure, effect-free compile facade for the legacy
``WorkflowGraphDSL`` mapping shape.  It parses and validates the DSL, maps the
three allowed node types onto capability-owned typed operation contracts, and
constructs an exact ``ProgramSpec``/``ExecutionPlan`` with the shared successor
Program AST.  It never imports the legacy workflow-graph service, a provider,
or a store, and it records zero provider/store/effect counters.

The DAG is projected onto a Program tree using ordered composition only:
single upstream edges become ``then_node`` and multiple upstream edges become
``zip_ordered_node`` in topological order.  No commutativity is claimed.  Node
config is bound into Program metadata and into each atom's deterministic
``ValueRef``, so node-kind/config changes alter the exact program and plan
digests.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
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
from app.successor_runtime.language.compile import CompileFailure, compile_program
from app.successor_runtime.language.object_contracts import (
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
    ReturnContract,
    make_operation_contract,
)
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import (
    ProgramNode,
    ProgramSpec,
    atom_node,
    identity_node,
    then_node,
    zip_ordered_node,
)
from app.successor_runtime.language.transforms import MergeRef
from app.successor_runtime.language.validate import validate_program
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "C1_DSL_COMPILE_FAILURE",
    "C1_DSL_CYCLE",
    "C1_DSL_DUPLICATE_NODE_ID",
    "C1_DSL_MALFORMED_PAYLOAD",
    "C1_DSL_MISSING_ENDPOINT",
    "C1_DSL_UNSUPPORTED_NODE_TYPE",
    "C1_LEGACY_ALLOWED_NODE_TYPES",
    "C1_LEGACY_DSL_RECEIPT_SCHEMA",
    "C1_LEGACY_DSL_VERSION",
    "C1_OPERATION_CATALOG_ID",
    "C1_OPERATION_CATALOG_VERSION",
    "C1_PROJECT_KEY",
    "C1_WORKFLOW_CONTEXT_TYPE",
    "C1LegacyDSLFailure",
    "C1LegacyDSLReceipt",
    "build_c1_catalog",
    "build_c1_contract",
    "build_c1_operation_contracts",
    "build_c1_registry",
    "parse_and_validate_legacy_dsl",
]

C1_LEGACY_DSL_VERSION = "1.0"
C1_LEGACY_DSL_RECEIPT_SCHEMA = "mrw.functorial-successor.c1.legacy-dsl-receipt.v1"
C1_LEGACY_ALLOWED_NODE_TYPES = frozenset({"vector_search", "llm_call", "join"})

C1_DSL_MALFORMED_PAYLOAD = "C1_DSL_MALFORMED_PAYLOAD"
C1_DSL_DUPLICATE_NODE_ID = "C1_DSL_DUPLICATE_NODE_ID"
C1_DSL_UNSUPPORTED_NODE_TYPE = "C1_DSL_UNSUPPORTED_NODE_TYPE"
C1_DSL_MISSING_ENDPOINT = "C1_DSL_MISSING_ENDPOINT"
C1_DSL_CYCLE = "C1_DSL_CYCLE"
C1_DSL_COMPILE_FAILURE = "C1_DSL_COMPILE_FAILURE"

NODE_TYPE_TO_CONTRACT_KIND = {
    "vector_search": "workflow.vector_search.v1",
    "llm_call": "workflow.llm_call.v1",
    "join": "workflow.join.v1",
}
C1_CONTRACT_KINDS = tuple(NODE_TYPE_TO_CONTRACT_KIND.values())

C1_OPERATION_CATALOG_ID = "mrw.functorial-successor.c1.operations"
C1_OPERATION_CATALOG_VERSION = "1.0.0"
C1_OPERATION_CONTRACT_VERSION = "1"
C1_OPERATION_OWNER = "workflow_graph.c1.1"
C1_PROGRAM_CONTRACT_VERSION = "mrw.functorial-successor.program-spec.v1"
C1_PROJECT_KEY = "legacy-workflow-graph.c1.1"
C1_SEMANTIC_IDENTITY = "c1.legacy-graph.parse-validate-compile"
C1_OBSERVATION_PROFILE = "mrw.successor.c1.legacy-dsl.observation.v1"
C1_ORDERED_MERGE_NAME = "mrw.successor.c1.ordered-merge.v1"
C1_ORDERED_MERGE_VERSION = "1"

C1_WORKFLOW_CONTEXT_TYPE = ObjectType(
    type_id="WorkflowContext.v1",
    schema_version="1.0.0",
    codec_id="mrw.successor.c1.context-codec.v1",
    canonical_codec_version="1",
)


@dataclass(frozen=True, slots=True)
class C1LegacyDSLFailure:
    """One typed C1 DSL parse/validate/compile failure."""

    code: str
    message: str
    path: str = ""
    nested_code: str | None = None
    nested_path: str = ""


@dataclass(frozen=True, slots=True)
class C1LegacyDSLReceipt:
    """Effect-free receipt for one legacy DSL parse/validate/compile attempt."""

    schema: str
    ok: bool
    failure: C1LegacyDSLFailure | None = None
    program: ProgramSpec | None = None
    plan: ExecutionPlan | None = None
    program_digest: str = ""
    plan_digest: str = ""
    catalog_digest: str = ""
    node_count: int = 0
    edge_count: int = 0
    topo_order: tuple[str, ...] = ()
    provider_calls: int = 0
    store_writes: int = 0
    canonical_effect_calls: int = 0

    def __post_init__(self) -> None:
        if self.ok:
            if self.failure is not None or self.program is None or self.plan is None:
                raise ValueError("success receipt requires program/plan and no failure")
            for name in ("program_digest", "plan_digest", "catalog_digest"):
                if not getattr(self, name):
                    raise ValueError(f"{name} must be bound on success")
        elif self.failure is None:
            raise ValueError("failure receipt requires a typed failure")


@dataclass(frozen=True, slots=True)
class _ParsedNode:
    node_id: str
    node_type: str
    config: dict[str, Any]
    contract_kind: str


@dataclass(frozen=True, slots=True)
class _ParsedGraph:
    version: str
    options: dict[str, Any]
    nodes: tuple[_ParsedNode, ...]
    edges: tuple[tuple[str, str], ...]
    topo_order: tuple[str, ...]


class _C1ParseFailure(Exception):
    def __init__(self, code: str, message: str, path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


def _failure_receipt(
    code: str,
    message: str,
    path: str = "",
    *,
    nested_code: str | None = None,
    nested_path: str = "",
) -> C1LegacyDSLReceipt:
    return C1LegacyDSLReceipt(
        schema=C1_LEGACY_DSL_RECEIPT_SCHEMA,
        ok=False,
        failure=C1LegacyDSLFailure(
            code=code,
            message=message,
            path=path,
            nested_code=nested_code,
            nested_path=nested_path,
        ),
    )


def _parse_payload(payload: Any) -> _ParsedGraph:
    if not isinstance(payload, Mapping):
        raise _C1ParseFailure(
            C1_DSL_MALFORMED_PAYLOAD,
            "legacy graph DSL payload must be a mapping",
            "payload",
        )
    version = payload.get("version", C1_LEGACY_DSL_VERSION)
    if not isinstance(version, str) or not version.strip():
        raise _C1ParseFailure(
            C1_DSL_MALFORMED_PAYLOAD,
            "version must be a non-empty string",
            "version",
        )
    options_raw = payload.get("options", {})
    if not isinstance(options_raw, Mapping):
        raise _C1ParseFailure(
            C1_DSL_MALFORMED_PAYLOAD,
            "options must be a mapping",
            "options",
        )
    nodes_raw = payload.get("nodes", [])
    if not isinstance(nodes_raw, list):
        raise _C1ParseFailure(
            C1_DSL_MALFORMED_PAYLOAD,
            "nodes must be a list",
            "nodes",
        )
    edges_raw = payload.get("edges", [])
    if not isinstance(edges_raw, list):
        raise _C1ParseFailure(
            C1_DSL_MALFORMED_PAYLOAD,
            "edges must be a list",
            "edges",
        )

    nodes: list[_ParsedNode] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(nodes_raw):
        path = f"nodes[{index}]"
        if not isinstance(item, Mapping):
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"node at index {index} must be a mapping",
                path,
            )
        node_id = item.get("node_id") or item.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"node_id at index {index} must be a non-empty string",
                path,
            )
        node_type = item.get("node_type")
        if not isinstance(node_type, str) or not node_type.strip():
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"node_type at index {index} must be a non-empty string",
                path,
            )
        config_raw = item.get("config")
        if config_raw is None:
            config_raw = item.get("params", {})
        if not isinstance(config_raw, Mapping):
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"config for node {node_id!r} must be a mapping",
                path,
            )
        if node_id in seen_ids:
            raise _C1ParseFailure(
                C1_DSL_DUPLICATE_NODE_ID,
                f"duplicate node_id: {node_id}",
                path,
            )
        seen_ids.add(node_id)
        if node_type not in C1_LEGACY_ALLOWED_NODE_TYPES:
            raise _C1ParseFailure(
                C1_DSL_UNSUPPORTED_NODE_TYPE,
                f"invalid node_type {node_type!r} for node {node_id!r}",
                path,
            )
        nodes.append(
            _ParsedNode(
                node_id=node_id,
                node_type=node_type,
                config=dict(config_raw),
                contract_kind=NODE_TYPE_TO_CONTRACT_KIND[node_type],
            )
        )

    edges: list[tuple[str, str]] = []
    for index, item in enumerate(edges_raw):
        path = f"edges[{index}]"
        if not isinstance(item, Mapping):
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"edge at index {index} must be a mapping",
                path,
            )
        from_node = item.get("from") or item.get("from_node") or item.get("source")
        to_node = item.get("to") or item.get("to_node") or item.get("target")
        if not isinstance(from_node, str) or not from_node.strip():
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"edge.from at index {index} must be a non-empty string",
                path,
            )
        if not isinstance(to_node, str) or not to_node.strip():
            raise _C1ParseFailure(
                C1_DSL_MALFORMED_PAYLOAD,
                f"edge.to at index {index} must be a non-empty string",
                path,
            )
        edges.append((from_node, to_node))

    node_ids = tuple(node.node_id for node in nodes)
    node_id_set = set(node_ids)
    for index, (from_node, to_node) in enumerate(edges):
        path = f"edges[{index}]"
        if from_node not in node_id_set:
            raise _C1ParseFailure(
                C1_DSL_MISSING_ENDPOINT,
                f"edge references missing node: {from_node}",
                path,
            )
        if to_node not in node_id_set:
            raise _C1ParseFailure(
                C1_DSL_MISSING_ENDPOINT,
                f"edge references missing node: {to_node}",
                path,
            )

    topo_order = _topological_order(node_ids, tuple(edges))
    if topo_order is None:
        raise _C1ParseFailure(
            C1_DSL_CYCLE,
            "workflow graph contains a cycle",
            "edges",
        )
    return _ParsedGraph(
        version=version,
        options=dict(options_raw),
        nodes=tuple(nodes),
        edges=tuple(edges),
        topo_order=topo_order,
    )


def _topological_order(
    node_ids: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
) -> tuple[str, ...] | None:
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for from_node, to_node in edges:
        outgoing[from_node].append(to_node)
        indegree[to_node] += 1
    queue = deque(node_id for node_id in node_ids if indegree[node_id] == 0)
    topo_order: list[str] = []
    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for child in outgoing[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(topo_order) != len(node_ids):
        return None
    return tuple(topo_order)


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _return_contract() -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=False,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


def _make_contract(kind: str) -> OperationContract:
    if kind not in C1_CONTRACT_KINDS:
        raise ValueError(f"unsupported C1 operation contract kind: {kind!r}")
    suffix = kind.removeprefix("workflow.").removesuffix(".v1")
    profile = f"mrw.successor.c1.{suffix}"
    return make_operation_contract(
        kind=kind,
        contract_version=C1_OPERATION_CONTRACT_VERSION,
        input_type=C1_WORKFLOW_CONTEXT_TYPE,
        output_type=C1_WORKFLOW_CONTEXT_TYPE,
        return_contract_ref=SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
        semantic_profile_ref=f"{profile}.semantic.v1",
        effect_profile_ref=f"{profile}.effect.v1",
        resource_profile_ref=f"{profile}.resource.v1",
        failure_profile_ref=f"{profile}.failure.v1",
        authority_profile_ref=f"{profile}.authority.v1",
        interpreter_compatibility_ref=f"{profile}.interpreter.v1",
        observation_profile_ref=f"{profile}.observation.v1",
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=C1_OPERATION_OWNER,
    )


def build_c1_operation_contracts() -> tuple[OperationContract, ...]:
    return tuple(_make_contract(kind) for kind in C1_CONTRACT_KINDS)


def build_c1_contract(kind: str) -> OperationContract:
    return _make_contract(kind)


def build_c1_catalog(
    contracts: tuple[OperationContract, ...] | None = None,
) -> OperationContractCatalogSnapshot:
    operations = (
        tuple(contracts) if contracts is not None else build_c1_operation_contracts()
    )
    return OperationContractCatalogSnapshot(
        catalog_id=C1_OPERATION_CATALOG_ID,
        catalog_version=C1_OPERATION_CATALOG_VERSION,
        entries=tuple(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            )
            for operation in operations
        ),
        catalog_digest=None,
    )


def build_c1_registry(
    contracts: tuple[OperationContract, ...] | None = None,
) -> OperationContractRegistry:
    operations = (
        tuple(contracts) if contracts is not None else build_c1_operation_contracts()
    )
    return OperationContractRegistry(build_c1_catalog(operations), operations)


def _atom_for_node(
    node: _ParsedNode,
    *,
    program_id: str,
    project_key: str,
    catalog: OperationContractCatalogSnapshot,
) -> ProgramNode:
    ref = catalog.lookup(node.contract_kind)
    if ref is None:
        # Keep the typed compile path: a missing catalog entry surfaces as an
        # UNKNOWN_OPERATION_CONTRACT validation failure below.
        ref = OperationContractRef(
            kind=node.contract_kind,
            contract_version=C1_OPERATION_CONTRACT_VERSION,
            contract_digest="0" * 64,
        )
    value_id = f"{program_id}:node:{node.node_id}:payload"
    storage_ref = f"project-value:{value_id}"
    value = ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=C1_WORKFLOW_CONTEXT_TYPE,
        codec_id=C1_WORKFLOW_CONTEXT_TYPE.codec_id,
        content_digest=content_digest(
            {
                "program_id": program_id,
                "node_id": node.node_id,
                "node_type": node.node_type,
                "contract_kind": node.contract_kind,
                "config": node.config,
            }
        ),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=storage_ref,
        byte_size=len(canonical_json(node.config).encode("utf-8")),
        provenance_digest=content_digest({"provenance": value_id}),
    )
    operation = OperationSpec(
        operation_id=node.contract_kind,
        contract_ref=ref,
        input_refs=(value,),
        payload_ref=value,
        allowed_overrides=freeze_json_object({}),
    )
    return atom_node(
        operation,
        input_type=C1_WORKFLOW_CONTEXT_TYPE,
        output_type=C1_WORKFLOW_CONTEXT_TYPE,
        return_contract=_return_contract(),
    )


def _merge_ref(
    left_source_ids: tuple[str, ...],
    right_source_ids: tuple[str, ...],
) -> MergeRef:
    left_ids = _ordered_unique(left_source_ids)
    right_ids = _ordered_unique(right_source_ids)
    binding = {
        "name": C1_ORDERED_MERGE_NAME,
        "version": C1_ORDERED_MERGE_VERSION,
        "left_sources": left_ids,
        "right_sources": right_ids,
        "order": "left,right",
        "commutativity": "NOT_CLAIMED",
    }
    return MergeRef(
        name=C1_ORDERED_MERGE_NAME,
        version=C1_ORDERED_MERGE_VERSION,
        digest=content_digest(binding),
        transform_kind="merge",
    )


def _program_root(
    graph: _ParsedGraph,
    *,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
) -> tuple[ProgramNode, tuple[str, ...]]:
    if not graph.topo_order:
        return identity_node(C1_WORKFLOW_CONTEXT_TYPE), ()
    nodes_by_id = {node.node_id: node for node in graph.nodes}
    incoming: dict[str, list[str]] = {node_id: [] for node_id in graph.topo_order}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in graph.topo_order}
    for from_node, to_node in graph.edges:
        incoming[to_node].append(from_node)
        outgoing[from_node].append(to_node)

    memo: dict[str, tuple[ProgramNode, tuple[str, ...]]] = {}

    def build(node_id: str) -> tuple[ProgramNode, tuple[str, ...]]:
        cached = memo.get(node_id)
        if cached is not None:
            return cached
        node = nodes_by_id[node_id]
        atom = _atom_for_node(
            node,
            program_id=program_id,
            project_key=project_key,
            catalog=catalog,
        )
        predecessors = tuple(incoming[node_id])
        if not predecessors:
            result = (atom, (node_id,))
        elif len(predecessors) == 1:
            pred_program, pred_ids = build(predecessors[0])
            result = (then_node(pred_program, atom), pred_ids + (node_id,))
        else:
            merged_program, merged_ids = build(predecessors[0])
            for pred in predecessors[1:]:
                pred_program, pred_ids = build(pred)
                merged_program = zip_ordered_node(
                    merged_program,
                    pred_program,
                    _merge_ref(merged_ids, pred_ids),
                    output_type=C1_WORKFLOW_CONTEXT_TYPE,
                )
                merged_ids = merged_ids + pred_ids
            result = (then_node(merged_program, atom), merged_ids + (node_id,))
        memo[node_id] = result
        return result

    sinks = [node_id for node_id in graph.topo_order if not outgoing[node_id]]
    root_program, root_ids = build(sinks[0])
    for sink in sinks[1:]:
        sink_program, sink_ids = build(sink)
        root_program = zip_ordered_node(
            root_program,
            sink_program,
            _merge_ref(root_ids, sink_ids),
            output_type=C1_WORKFLOW_CONTEXT_TYPE,
        )
        root_ids = root_ids + sink_ids
    return root_program, _ordered_unique(root_ids)


def _program_identities(graph: _ParsedGraph) -> tuple[str, str]:
    canonical_input = {
        "version": graph.version,
        "options": graph.options,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "config": node.config,
            }
            for node in graph.nodes
        ],
        "edges": [{"from": frm, "to": to} for frm, to in graph.edges],
    }
    program_id = (
        "program:c1:"
        + content_digest(
            {
                "schema": "mrw.successor.c1.legacy-dsl.v1",
                "input": canonical_input,
            }
        )[:24]
    )
    project_scope_digest = content_digest(
        {
            "schema": "mrw.successor.c1.legacy-dsl.project-scope.v1",
            "project_key": C1_PROJECT_KEY,
            "version": graph.version,
        }
    )
    return program_id, project_scope_digest


def _build_program(
    graph: _ParsedGraph,
    *,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
) -> ProgramSpec:
    root, ordered_source_ids = _program_root(
        graph,
        catalog=catalog,
        program_id=program_id,
        project_key=project_key,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.c1.legacy-dsl.program-metadata.v1",
            "version": graph.version,
            "options": graph.options,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "contract_kind": node.contract_kind,
                    "config": node.config,
                }
                for node in graph.nodes
            ],
            "edges": [{"from": frm, "to": to} for frm, to in graph.edges],
            "topo_order": list(graph.topo_order),
            "ordered_source_ids": list(ordered_source_ids),
            "ordered_composition": "THEN_AND_ZIP_ORDERED_NONCOMMUTATIVE",
            "program_id": program_id,
            "project_key": project_key,
            "project_registry_revision": 1,
            "project_scope_digest": project_scope_digest,
            "semantic_identity": C1_SEMANTIC_IDENTITY,
            "lifecycle_state": "C1_PURE_PARSE_VALIDATE_COMPILE",
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version=C1_PROGRAM_CONTRACT_VERSION,
        project_key=project_key,
        project_registry_revision=1,
        project_scope_digest=project_scope_digest,
        semantic_identity=C1_SEMANTIC_IDENTITY,
        input_type=C1_WORKFLOW_CONTEXT_TYPE,
        output_type=C1_WORKFLOW_CONTEXT_TYPE,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=C1_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def parse_and_validate_legacy_dsl(
    payload: Any,
    *,
    catalog: OperationContractCatalogSnapshot | None = None,
    operation_contracts: OperationContractRegistry | None = None,
) -> C1LegacyDSLReceipt:
    if catalog is None or operation_contracts is None:
        contracts = build_c1_operation_contracts()
        catalog = build_c1_catalog(contracts)
        operation_contracts = build_c1_registry(contracts)
    try:
        graph = _parse_payload(payload)
    except _C1ParseFailure as exc:
        return _failure_receipt(exc.code, exc.message, exc.path)

    try:
        program_id, project_scope_digest = _program_identities(graph)
        program = _build_program(
            graph,
            catalog=catalog,
            program_id=program_id,
            project_key=C1_PROJECT_KEY,
            project_scope_digest=project_scope_digest,
        )
    except (TypeError, ValueError) as exc:
        return _failure_receipt(
            C1_DSL_COMPILE_FAILURE,
            f"program construction failed: {exc}",
            "program",
            nested_code=type(exc).__name__,
        )

    validation = validate_program(
        program,
        catalog,
        operation_contract_resolver=operation_contracts,
    )
    if not validation.valid:
        first = validation.failures[0]
        return _failure_receipt(
            C1_DSL_COMPILE_FAILURE,
            f"program validation failed: {first.message}",
            first.path,
            nested_code=first.code,
            nested_path=first.path,
        )

    try:
        plan = compile_program(
            program,
            catalog,
            operation_contracts=operation_contracts,
        )
    except CompileFailure as exc:
        return _failure_receipt(
            C1_DSL_COMPILE_FAILURE,
            f"program compile failed: {exc.message}",
            exc.path,
            nested_code=exc.code,
            nested_path=exc.path,
        )
    except (TypeError, ValueError) as exc:
        return _failure_receipt(
            C1_DSL_COMPILE_FAILURE,
            f"program compile failed: {exc}",
            "compile",
            nested_code=type(exc).__name__,
        )

    return C1LegacyDSLReceipt(
        schema=C1_LEGACY_DSL_RECEIPT_SCHEMA,
        ok=True,
        program=program,
        plan=plan,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        catalog_digest=catalog.catalog_digest,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        topo_order=graph.topo_order,
    )
