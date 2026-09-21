"""Motif: a named, reusable ordered composition of operators and other motifs.

This module projects the frozen functorial contract onto the shared
``functorial.registry.catalog``.  A Motif is only a *basic composition* (an
ordered chain); the heavier fixed-DAG workflow surface lives in ``workflow.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn, TypeAlias

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import (
    agent_functorial_projection_failures,
)

from .compose import ordered_compose
from .catalog import ensure_operator_catalog
from .registry import catalog

__all__ = ["MotifSpec", "compose_motif", "resolve_composition_ref"]
_FAILURE_WITNESS = "test:test_w02_functorial_projection_failure_lifts"
ProjectionFailure: TypeAlias = Failure


def _projection_failure(code: str, message: str, *, ref: str | None = None) -> Failure:
    context: dict[str, Any] = {
        "owner": "agent_core.functorial.motif",
        "operation": "functorial.motif",
        "failure_family": agent_functorial_projection_failures.name,
        "witness": _FAILURE_WITNESS,
    }
    if ref is not None:
        context["ref"] = ref
    return agent_functorial_projection_failures.fail(code, message, context)


def _raise_projection_failure(value: Failure, exception_type: type[Exception]) -> NoReturn:
    if not agent_functorial_projection_failures.matches(value):
        # kit:boundary owner=motif.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_functorial_projection_failure_lifts
        raise TypeError("invalid functorial projection failure")  # noqa: TRY003
    # kit:boundary owner=motif.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.functorial_projection.failure witness=test:test_w02_functorial_projection_failure_lifts
    raise exception_type(value.message)


@dataclass(frozen=True, slots=True)
class MotifSpec:
    motif_id: str
    name: str
    composition: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "motif_id": self.motif_id,
            "name": self.name,
            "composition": list(self.composition),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


def _parse_composition(composition: Any) -> list[str] | ProjectionFailure:
    if composition is None:
        return []
    if isinstance(composition, str):
        raw = composition.replace(",", " ")
        return [part for part in raw.split() if part.strip()]
    if isinstance(composition, dict):
        return _projection_failure(
            "composition_step_invalid",
            "composition must be a sequence of refs, not an object",
        )
    try:
        iterator = iter(composition)
    except TypeError:
        return _projection_failure(
            "composition_step_invalid",
            "composition must be iterable refs or a string",
        )
    refs: list[str] = []
    for index, item in enumerate(iterator):
        if not isinstance(item, (str, dict)):
            return _projection_failure(
                "composition_step_invalid",
                f"composition step must be a ref, got {type(item).__name__}",
                ref=f"index:{index}",
            )
        if isinstance(item, dict):
            item = item.get("ref")
            if item is None:
                return _projection_failure(
                    "composition_step_invalid",
                    "composition step object requires ref",
                    ref=f"index:{index}",
                )
        text = str(item).strip()
        if text:
            refs.append(text)
    return refs


def _resolve_composition_ref(ref: str) -> dict[str, Any] | ProjectionFailure:
    """Resolve ``operator:<id>`` or ``motif:<id>`` to its catalog spec."""
    if not isinstance(ref, str):
        return _projection_failure(
            "ref_invalid_format",
            f"composition ref must be a string, got {type(ref).__name__}",
        )
    ref = ref.strip()
    if not ref:
        return _projection_failure("ref_empty", "empty composition ref", ref=ref)
    if ":" not in ref:
        return _projection_failure(
            "ref_invalid_format",
            f"invalid ref {ref!r}: expected 'operator:<id>' or 'motif:<id>'",
            ref=ref,
        )
    kind, _, ref_id = ref.partition(":")
    kind = kind.strip()
    ref_id = ref_id.strip()
    if kind == "operator":
        collection = "operators"
    elif kind == "motif":
        collection = "motifs"
    else:
        return _projection_failure(
            "ref_kind_unsupported",
            f"unsupported ref kind {kind!r} in {ref!r}",
            ref=ref,
        )
    if not ref_id:
        return _projection_failure("ref_id_missing", f"missing id in ref {ref!r}", ref=ref)
    ensure_operator_catalog()
    spec = catalog.get(collection, ref_id)
    if spec is None:
        return _projection_failure(
            "ref_unresolved", f"unresolved {kind} ref: {ref_id}", ref=ref
        )
    return spec


def resolve_composition_ref(ref: str) -> dict[str, Any]:
    result = _resolve_composition_ref(ref)
    if isinstance(result, Failure):
        _raise_projection_failure(result, KeyError if result.code == "ref_unresolved" else ValueError)
    return result


def compose_motif(
    motif_id: str,
    name: str,
    composition: Any,
) -> MotifSpec:
    """Resolve, strictly compose, derive schema, and idempotently register a Motif."""
    motif_id = str(motif_id or "").strip()
    if not motif_id:
        _raise_projection_failure(
            _projection_failure("motif_id_required", "motif_id is required"), ValueError
        )

    refs = _parse_composition(composition)
    if isinstance(refs, Failure):
        _raise_projection_failure(refs, TypeError)
    resolved: list[dict[str, Any]] = []
    for ref in refs:
        result = _resolve_composition_ref(ref)
        if isinstance(result, Failure):
            _raise_projection_failure(
                result, KeyError if result.code == "ref_unresolved" else ValueError
            )
        resolved.append(result)

    composed = ordered_compose(resolved)
    input_schema = composed["input_schema"]
    output_schema = composed["output_schema"]

    spec = MotifSpec(
        motif_id=motif_id,
        name=str(name or "").strip() or motif_id,
        composition=tuple(refs),
        input_schema=input_schema,
        output_schema=output_schema,
    )
    catalog.upsert_motif(motif_id, spec.to_dict())
    return spec
