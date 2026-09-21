"""Workflow fixed-length composition projection.

A Workflow is a fixed-length, ordered composition of ``operator:<id>`` and
``motif:<id>`` refs.  This module resolves those refs against the shared
:class:`~app.services.agent_core.functorial.registry.FunctorialCatalog` and
assembles a minimal, serializable linear Program.  It does not rewrite
operators/motifs and does not modify ``app/successor_runtime/language/*``.

The successor ``language/*`` compiler/validator expect a fully typed
``ProgramNode`` AST over ``ObjectType`` / ``OperationSpec``, whereas this
surface projects JSON-Schema ``input_schema`` / ``output_schema`` contracts.
Because those interfaces are not adapted to this projection, this module uses a
small ``_validate_workflow`` that checks reference completeness and ordered
schema compatibility without touching ``language/*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Annotated, Any, NoReturn, TypeAlias

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import (
    agent_functorial_projection_failures,
)

from .registry import catalog
from .catalog import ensure_operator_catalog

_DEFAULT_LAWS: tuple[str, ...] = ("identity", "associativity")
_REF_KINDS: tuple[str, ...] = ("operator", "motif")
_COLLECTION_BY_KIND: dict[str, str] = {"operator": "operators", "motif": "motifs"}
_PROGRAM_CODEC: str = "mrw.functorial-successor.workflow.program.v1"
_SCALAR_TYPES: frozenset[str] = frozenset(
    {"string", "number", "integer", "boolean", "null"}
)
_FAILURE_WITNESS = "test:test_w02_functorial_projection_failure_lifts"
ProjectionFailure: TypeAlias = Failure


class WorkflowValidationError(ValueError):
    """Raised when a workflow ref list is malformed, unresolved, or mis-ordered."""


def _projection_failure(code: str, message: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
        "owner": "agent_core.functorial.workflow",
        "operation": "functorial.workflow",
        "failure_family": agent_functorial_projection_failures.name,
        "witness": _FAILURE_WITNESS,
        **details,
    }
    return agent_functorial_projection_failures.fail(code, message, context)


def _raise_projection_failure(value: Failure) -> NoReturn:
    if not agent_functorial_projection_failures.matches(value):
        # kit:boundary owner=workflow.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_functorial_projection_failure_lifts
        raise TypeError("invalid functorial projection failure")  # noqa: TRY003
    # kit:boundary owner=workflow.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.functorial_projection.failure witness=test:test_w02_functorial_projection_failure_lifts
    raise WorkflowValidationError(value.message)


@dataclass(frozen=True)
class WorkflowSpec:
    """Fixed-length ordered composition of operator/motif refs."""

    workflow_id: str
    name: str
    steps: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    laws: tuple[str, ...]
    version: int
    program: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable workflow record (order preserved)."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "steps": list(self.steps),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "laws": list(self.laws),
            "version": self.version,
            "program": self.program,
        }


def _normalize_steps(steps: Any) -> tuple[str, ...] | ProjectionFailure:
    """Normalize a ref list (strings or ``{"ref": ...}`` dicts) to an ordered tuple."""
    if steps is None:
        return _projection_failure("workflow_steps_required", "steps are required")
    if isinstance(steps, str):
        return _projection_failure(
            "workflow_steps_invalid_type", "steps must be a list of refs, not a string"
        )
    try:
        iterator = iter(steps)
    except TypeError:
        return _projection_failure(
            "workflow_steps_invalid_type", "steps must be an iterable of refs"
        )

    refs: list[str] = []
    for index, step in enumerate(iterator):
        if isinstance(step, str):
            ref = step.strip()
        elif isinstance(step, dict) and "ref" in step:
            ref = str(step.get("ref") or "").strip()
        else:
            return _projection_failure(
                "workflow_step_invalid", f"invalid step: {step!r}", index=index
            )
        if not ref:
            return _projection_failure("ref_empty", "empty step ref", index=index)
        refs.append(ref)

    if not refs:
        return _projection_failure("workflow_steps_empty", "steps must not be empty")
    return tuple(refs)


def _split_ref(ref: str) -> tuple[str, str] | ProjectionFailure:
    """Split a ref into ``(kind, id)``; kind is ``operator`` or ``motif``."""
    if ":" not in ref:
        return _projection_failure("ref_invalid_format", f"ref missing kind prefix: {ref!r}", ref=ref)
    kind, _, ref_id = ref.partition(":")
    kind = kind.strip()
    ref_id = ref_id.strip()
    if kind not in _REF_KINDS:
        return _projection_failure(
            "ref_kind_unsupported",
            f"unsupported ref kind: {kind!r} (expected operator|motif)",
            ref=ref,
        )
    if not ref_id:
        return _projection_failure("ref_id_missing", f"ref missing id: {ref!r}", ref=ref)
    return kind, ref_id


def _get_schema(spec: dict[str, Any], key: str) -> dict[str, Any]:
    value = spec.get(key)
    return value if isinstance(value, dict) else {}


def _resolve_ref(ref: str) -> tuple[str, str, dict[str, Any]] | ProjectionFailure:
    """Resolve a ref to ``(kind, id, spec)`` against the shared catalog."""
    parsed = _split_ref(ref)
    if isinstance(parsed, Failure):
        return parsed
    kind, ref_id = parsed
    ensure_operator_catalog()
    collection = _COLLECTION_BY_KIND[kind]
    spec = catalog.get(collection, ref_id)
    if spec is None:
        # Tolerate a prefixed storage key ("operator:<id>").
        spec = catalog.get(collection, ref)
    if spec is None:
        return _projection_failure(
            "ref_unresolved",
            f"unresolved ref: {ref!r} (no {collection[:-1]} {ref_id!r})",
            ref=ref,
        )
    return kind, ref_id, spec


def _type_of(schema: dict[str, Any] | None) -> str | None:
    if not isinstance(schema, dict):
        return None
    t = schema.get("type")
    return t if isinstance(t, str) else None


def _schemas_compatible(
    out_schema: dict[str, Any] | None, in_schema: dict[str, Any] | None
) -> bool:
    """Lenient ordered-compatibility check; only a clear scalar mismatch fails."""
    out_t = _type_of(out_schema)
    in_t = _type_of(in_schema)
    if out_t is None or in_t is None:
        return True
    if out_t == in_t:
        return True
    # Object/array/any composites may still be routed into one another in this
    # projection; only a definite scalar-to-scalar mismatch is a hard violation.
    return not (out_t in _SCALAR_TYPES and in_t in _SCALAR_TYPES)


def _validate_workflow(steps: tuple[str, ...]) -> list[dict[str, Any]] | ProjectionFailure:
    """Check reference completeness and ordered compatibility.

    Returns the resolved step list (order preserved) or raises
    :class:`WorkflowValidationError`.
    """
    def resolve(ref: str, ancestors: frozenset[str]) -> dict[str, Any] | ProjectionFailure:
        resolved = _resolve_ref(ref)
        if isinstance(resolved, Failure):
            return resolved
        kind, ref_id, spec = resolved
        if ref in ancestors:
            return _projection_failure("ref_cycle", f"cycle in workflow refs: {ref!r}", ref=ref)
        return {
            "ref": ref,
            "kind": kind,
            "id": ref_id,
            "input_schema": _get_schema(spec, "input_schema"),
            "output_schema": _get_schema(spec, "output_schema"),
            "composition": spec.get("composition") if kind == "motif" else (),
            "ancestors": ancestors | {ref},
        }

    pending: list[dict[str, Any] | Failure] = [resolve(ref, frozenset()) for ref in steps]
    if any(isinstance(node, Failure) for node in pending):
        return next(node for node in pending if isinstance(node, Failure))
    flattened: list[dict[str, Any]] = []
    while pending:
        node = pending.pop(0)
        if isinstance(node, Failure):
            return node
        if node["kind"] == "motif":
            composition = node["composition"]
            if composition is None:
                composition = ()
            if not isinstance(composition, (list, tuple)):
                return _projection_failure(
                    "composition_step_invalid",
                    f"motif composition must be a list, got {type(composition).__name__}",
                    ref=node["ref"],
                )
            for ref in composition:
                if not isinstance(ref, str) or not ref.strip():
                    return _projection_failure(
                        "composition_step_invalid",
                        f"invalid motif composition ref: {ref!r}",
                        ref=node["ref"],
                    )
                child = resolve(str(ref), node["ancestors"])
                if isinstance(child, Failure):
                    return child
                pending.append(child)
        else:
            flattened.append(node)

    if not flattened:
        return _projection_failure(
            "workflow_no_operator", "workflow must resolve to at least one operator"
        )

    for left, right in pairwise(flattened):
        if not _schemas_compatible(left["output_schema"], right["input_schema"]):
            return _projection_failure(
                "workflow_order_incompatible",
                f"order violation: {left['ref']!r} output {left['output_schema']!r} "
                f"is incompatible with {right['ref']!r} input {right['input_schema']!r}",
                left=left["ref"],
                right=right["ref"],
            )
    return [
        {
            "ref": node["ref"],
            "kind": node["kind"],
            "id": node["id"],
            "input_schema": node["input_schema"],
            "output_schema": node["output_schema"],
        }
        for node in flattened
    ]


def _build_program(resolved: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a minimal fixed linear DAG program from resolved steps."""
    nodes = [
        {
            "ref": node["ref"],
            "kind": node["kind"],
            "id": node["id"],
            "input_schema": node["input_schema"],
            "output_schema": node["output_schema"],
        }
        for node in resolved
    ]
    edges = [[i, i + 1] for i in range(len(nodes) - 1)]
    return {"codec": _PROGRAM_CODEC, "kind": "linear", "nodes": nodes, "edges": edges}


def _as_schema(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _build_workflow_program(
    workflow_id: str,
    name: str,
    steps: Any,
    laws: Any = None,
    *,
    input_schema: Any = None,
    output_schema: Any = None,
    version: int = 1,
) -> WorkflowSpec | ProjectionFailure:
    """Resolve an ordered ref list into a WorkflowSpec and idempotently register it.

    ``steps`` is a list of ``operator:<id>`` or ``motif:<id>`` refs (strings), or
    a list of ``{"ref": ...}`` dicts.  The resulting spec preserves step order and
    is upserted into ``catalog`` under the ``workflows`` collection.
    """
    workflow_id = str(workflow_id or "").strip()
    if not workflow_id:
        return _projection_failure("workflow_id_required", "workflow_id is required")
    name = str(name or "").strip() or workflow_id

    refs = _normalize_steps(steps)
    if isinstance(refs, Failure):
        return refs
    resolved = _validate_workflow(refs)
    if isinstance(resolved, Failure):
        return resolved

    if laws is None:
        laws_tuple = _DEFAULT_LAWS
    elif isinstance(laws, str):
        laws_tuple = (laws,)
    elif isinstance(laws, (list, tuple)):
        laws_tuple = tuple(str(item) for item in laws)
    else:
        return _projection_failure("workflow_step_invalid", "laws must be a list or string")

    try:
        version_value = int(version)
    except (TypeError, ValueError):
        return _projection_failure("workflow_step_invalid", "version must be an integer")

    spec = WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        steps=refs,
        input_schema=_as_schema(input_schema)
        if input_schema is not None
        else resolved[0]["input_schema"],
        output_schema=_as_schema(output_schema)
        if output_schema is not None
        else resolved[-1]["output_schema"],
        laws=laws_tuple,
        version=version_value,
        program=_build_program(resolved),
    )

    catalog.upsert_workflow(workflow_id, spec.to_dict())
    return spec


def build_workflow_program(
    workflow_id: str,
    name: str,
    steps: Any,
    laws: Any = None,
    *,
    input_schema: Any = None,
    output_schema: Any = None,
    version: int = 1,
) -> Annotated[
    WorkflowSpec,
    "kit:prepared-command effect_boundary=functorial_workflow "
    "witness=test:test_w02_agent_authority_metadata"
]:
    result = _build_workflow_program(
        workflow_id,
        name,
        steps,
        laws,
        input_schema=input_schema,
        output_schema=output_schema,
        version=version,
    )
    if isinstance(result, Failure):
        _raise_projection_failure(result)
    return result


__all__ = [
    "WorkflowSpec",
    "WorkflowValidationError",
    "build_workflow_program",
]
