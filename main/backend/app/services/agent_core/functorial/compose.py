"""Strictly ordered composition for Motif steps.

A Motif is an ordered chain of typed steps (operators or other motifs).  This
module provides the minimal composition primitive for that flat, schema-only
surface: ordered composition, composed-schema derivation, and the two frozen
composition laws (identity and associativity).

We deliberately do not import ``app.successor_runtime.language.laws`` or
``app.successor_runtime.language.normalize`` here.  Those modules operate on the
heavier ``ExecutionPlan`` / ``Program`` AST, while Motif composition is a flat
ordered list of ``input_schema`` -> ``output_schema`` steps.  The semantics stay
aligned (no commutativity is assumed, grouping is flattened), but no
``language/*`` file is modified or re-used for this lighter surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn, TypeAlias

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import (
    agent_functorial_projection_failures,
)

__all__ = [
    "LawResult",
    "check_composition_laws",
    "composition_laws_hold",
    "derive_composed_schema",
    "ordered_compose",
]

_IDENTITY_REF = "identity"
_FAILURE_WITNESS = "test:test_w02_functorial_projection_failure_lifts"
ProjectionFailure: TypeAlias = Failure


def _projection_failure(code: str, message: str, *, index: int | None = None) -> Failure:
    context: dict[str, Any] = {
        "owner": "agent_core.functorial.compose",
        "operation": "functorial.compose",
        "failure_family": agent_functorial_projection_failures.name,
        "witness": _FAILURE_WITNESS,
    }
    if index is not None:
        context["index"] = index
    return agent_functorial_projection_failures.fail(code, message, context)


def _raise_projection_failure(value: Failure, exception_type: type[Exception]) -> NoReturn:
    if not agent_functorial_projection_failures.matches(value):
        # kit:boundary owner=compose.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_functorial_projection_failure_lifts
        raise TypeError("invalid functorial projection failure")  # noqa: TRY003
    # kit:boundary owner=compose.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.functorial_projection.failure witness=test:test_w02_functorial_projection_failure_lifts
    raise exception_type(value.message)


def _as_schema(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _schemas(step: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _as_schema(step.get("input_schema")), _as_schema(step.get("output_schema"))


def _step_ref(step: dict[str, Any], index: int) -> str:
    for key in ("ref", "operator_id", "motif_id", "id"):
        value = step.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"step:{index}"


def _flatten_steps(steps: Any) -> list[dict[str, Any]] | ProjectionFailure:
    """Flatten nested composed steps into one strictly ordered list."""
    if steps is None:
        return []
    if isinstance(steps, dict):
        steps = [steps]
    try:
        iterator = iter(steps)
    except TypeError:
        return _projection_failure(
            "composition_step_invalid",
            f"composition steps must be iterable, got {type(steps).__name__}",
        )
    flat: list[dict[str, Any]] = []
    for index, step in enumerate(iterator):
        if not isinstance(step, dict):
            return _projection_failure(
                "composition_step_invalid",
                f"composition step must be a dict, got {type(step).__name__}",
                index=index,
            )
        nested = step.get("_composed_steps")
        if step.get("_composed") is True and isinstance(nested, list):
            nested_flat = _flatten_steps(nested)
            if isinstance(nested_flat, Failure):
                return nested_flat
            flat.extend(nested_flat)
        else:
            flat.append(step)
    return flat


def derive_composed_schema(steps: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """First step input -> last step output; the empty chain is identity ({}, {})."""
    flat = _flatten_steps(steps)
    if isinstance(flat, Failure):
        _raise_projection_failure(flat, TypeError)
    if not flat:
        return {}, {}
    first_input, _ = _schemas(flat[0])
    _, last_output = _schemas(flat[-1])
    return first_input, last_output


def ordered_compose(steps: Any) -> dict[str, Any]:
    """Compose steps in strict order, preserving identity and ordered composition.

    The result carries the first-step input schema, the last-step output schema,
    and the flattened ordered step list, so associativity holds structurally
    rather than by assertion.  Nested composed steps are flattened; order is
    never reordered and commutativity is never assumed.
    """
    flat = _flatten_steps(steps)
    if isinstance(flat, Failure):
        _raise_projection_failure(flat, TypeError)
    if not flat:
        return {
            "ref": _IDENTITY_REF,
            "name": _IDENTITY_REF,
            "input_schema": {},
            "output_schema": {},
            "_composed": True,
            "_composed_steps": [],
        }
    input_schema, output_schema = derive_composed_schema(flat)
    refs = [_step_ref(step, i) for i, step in enumerate(flat)]
    joined = " >> ".join(refs)
    return {
        "ref": joined,
        "name": joined,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "_composed": True,
        "_composed_steps": flat,
    }


def _identity() -> dict[str, Any]:
    return ordered_compose([])


def _structure(steps: Any) -> tuple[str, ...]:
    flat = _flatten_steps(steps)
    if isinstance(flat, Failure):
        _raise_projection_failure(flat, TypeError)
    return tuple(_step_ref(step, i) for i, step in enumerate(flat))


@dataclass(frozen=True, slots=True)
class LawResult:
    law: str
    holds: bool
    left: Any
    right: Any
    counterexample: str | None = None


def check_composition_laws(steps: Any) -> list[LawResult]:
    """Check identity (empty = identity, identity is neutral) and associativity.

    ``steps`` is a flat ordered list of step dicts.  Pass means every returned
    ``LawResult.holds`` is True.
    """
    flat = _flatten_steps(steps)
    if isinstance(flat, Failure):
        _raise_projection_failure(flat, TypeError)
    results: list[LawResult] = []

    empty = _identity()
    identity_ok = (
        empty["input_schema"] == empty["output_schema"]
        and empty["_composed_steps"] == []
    )
    results.append(
        LawResult(
            "identity",
            identity_ok,
            {},
            {},
            None if identity_ok else "empty composition is not identity",
        )
    )

    struct = _structure(flat)
    left_composed = ordered_compose([_identity(), *flat])
    right_composed = ordered_compose([*flat, _identity()])
    left_struct = _structure(left_composed)
    right_struct = _structure(right_composed)
    results.append(
        LawResult(
            "left_identity",
            left_struct == struct,
            left_struct,
            struct,
            None
            if left_struct == struct
            else f"left_identity mismatch: {left_struct} != {struct}",
        )
    )
    results.append(
        LawResult(
            "right_identity",
            right_struct == struct,
            right_struct,
            struct,
            None
            if right_struct == struct
            else f"right_identity mismatch: {right_struct} != {struct}",
        )
    )

    if len(flat) >= 3:
        a, b, c = flat[0], flat[1], flat[2]
        left_group = ordered_compose([ordered_compose([a, b]), c])
        right_group = ordered_compose([a, ordered_compose([b, c])])
        left_struct = _structure(left_group)
        right_struct = _structure(right_group)
        expected = (_step_ref(a, 0), _step_ref(b, 1), _step_ref(c, 2))
        holds = left_struct == right_struct == expected
        results.append(
            LawResult(
                "associativity",
                holds,
                left_struct,
                right_struct,
                None
                if holds
                else f"left={left_struct} right={right_struct} expected={expected}",
            )
        )
    else:
        results.append(LawResult("associativity", True, struct, struct, None))

    return results


def composition_laws_hold(steps: Any) -> bool:
    return all(result.holds for result in check_composition_laws(steps))
