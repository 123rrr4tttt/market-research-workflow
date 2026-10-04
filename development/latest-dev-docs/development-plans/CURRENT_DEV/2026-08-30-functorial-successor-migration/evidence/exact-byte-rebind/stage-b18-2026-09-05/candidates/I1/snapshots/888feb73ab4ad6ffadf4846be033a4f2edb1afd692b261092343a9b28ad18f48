"""Canonical normalization for the Program AST.

Normalization preserves ordered composition and never assumes commutativity:
child order and branch order are unchanged.  Associative groupings of `Then`
and identity elimination collapse to one canonical left-leaning tree.
"""

from __future__ import annotations

from typing import Any

from .algebra import canonical_digest
from .program import (
    Decide,
    DecisionBranch,
    Identity,
    MapOutput,
    ProgramNode,
    ProgramSpec,
    Then,
    TraverseOrdered,
    ZipOrdered,
    then_node,
)


def normalize_node(node: ProgramNode) -> ProgramNode:
    if isinstance(node, Identity):
        return node
    if isinstance(node, Then):
        flat: "list[ProgramNode]" = []
        _flatten_then(node, flat)
        if not flat:
            from .program import identity_node

            return identity_node(node.input_type)
        rebuilt = flat[0]
        for child in flat[1:]:
            rebuilt = then_node(rebuilt, child)
        return rebuilt
    if isinstance(node, MapOutput):
        from .program import map_output_node

        return map_output_node(
            source=normalize_node(node.source),
            transform_ref=node.transform_ref,
            target_type=node.target_type,
        )
    if isinstance(node, ZipOrdered):
        from .program import zip_ordered_node

        return zip_ordered_node(
            left=normalize_node(node.left),
            right=normalize_node(node.right),
            merge_ref=node.merge_ref,
            output_type=node.output_type,
        )
    if isinstance(node, TraverseOrdered):
        from .program import traverse_ordered_node

        return traverse_ordered_node(
            element_program=normalize_node(node.element_program),
            traversal_policy=node.traversal_policy,
        )
    if isinstance(node, Decide):
        from .program import decide_node

        branches = tuple(
            DecisionBranch(
                branch_id=branch.branch_id,
                guard=branch.guard,
                program=normalize_node(branch.program),
            )
            for branch in node.branches
        )
        return decide_node(node.discriminator_ref, branches)
    return node


def _flatten_then(node: Then, out: "list[ProgramNode]") -> None:
    for child in (node.first, node.second):
        if isinstance(child, Identity):
            continue
        if isinstance(child, Then):
            _flatten_then(child, out)
        else:
            out.append(child)


def normalize_program(spec: ProgramSpec) -> ProgramSpec:
    root = normalize_node(spec.root)
    return ProgramSpec(
        program_id=spec.program_id,
        contract_version=spec.contract_version,
        project_key=spec.project_key,
        project_registry_revision=spec.project_registry_revision,
        project_scope_digest=spec.project_scope_digest,
        semantic_identity=spec.semantic_identity,
        input_type=spec.input_type,
        output_type=spec.output_type,
        root=root,
        algebra_refs=spec.algebra_refs,
        transform_refs=spec.transform_refs,
        observation_profile=spec.observation_profile,
        metadata=spec.metadata,
        program_digest="",
    ).with_digest()


def normalized_structure(node: ProgramNode) -> Any:
    """A stable, comparable projection of the normalized tree structure."""

    if isinstance(node, Identity):
        return ("identity", canonical_digest(node.object_type))
    if isinstance(node, Then):
        return ("then", normalized_structure(node.first), normalized_structure(node.second))
    if isinstance(node, MapOutput):
        return (
            "map_output",
            normalized_structure(node.source),
            node.transform_ref.label(),
            canonical_digest(node.target_type),
        )
    if isinstance(node, ZipOrdered):
        return (
            "zip_ordered",
            normalized_structure(node.left),
            normalized_structure(node.right),
            node.merge_ref.label(),
        )
    if isinstance(node, TraverseOrdered):
        return (
            "traverse_ordered",
            normalized_structure(node.element_program),
            node.traversal_policy,
        )
    if isinstance(node, Decide):
        return (
            "decide",
            node.discriminator_ref.label(),
            tuple(
                (branch.branch_id, normalized_structure(branch.program))
                for branch in node.branches
            ),
        )
    return (getattr(node, "node_kind", type(node).__name__), node.ast_digest())


def normalized_equivalent(left: ProgramNode, right: ProgramNode) -> bool:
    return normalize_node(left).ast_digest() == normalize_node(right).ast_digest()
