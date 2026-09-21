"""Functorial operator catalog facade.

A thin projection over the shared :data:`catalog` singleton (registry.py) using
``collection="operators"``. On import it idempotently upserts every operator
projected by :func:`operator.project_process_operators`.
"""

from __future__ import annotations

from typing import Any

from .operator import OperatorSpec, project_process_operators
from .registry import catalog

_COLLECTION = "operators"


def upsert_operator(spec: OperatorSpec) -> dict[str, Any]:
    if not isinstance(spec, OperatorSpec):
        # kit:boundary owner=catalog.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_programmer_defect_boundary
        raise TypeError("spec must be an OperatorSpec")
    return catalog.upsert_operator(spec.operator_id, spec.to_dict())


def get_operator(operator_id: str) -> dict[str, Any] | None:
    return catalog.get(_COLLECTION, operator_id)


def list_operators() -> list[dict[str, Any]]:
    return catalog.list(_COLLECTION)


def ensure_operator_catalog() -> None:
    """Project current AgentCore operators into the mutable catalog on demand."""

    for spec in project_process_operators():
        current = get_operator(spec.operator_id)
        # Re-seeding the same process-local projection must not advance revisions.
        if current is None or current.get("revision") in (None, 1):
            upsert_operator(spec)


__all__ = [
    "ensure_operator_catalog",
    "get_operator",
    "list_operators",
    "upsert_operator",
]
