"""Focused W07 node/reconciliation typed-outcome witnesses."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from functorial_kit import Failure
from pydantic import ValidationError

from app.successor_runtime.runtime.node import (
    ClockObservationError,
    NodeIdentity,
    RuntimeNode,
)
from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.observations import LegacyObservationSet
from app.successor_runtime.runtime.reconciliation import (
    EffectReconciler,
    ReconciliationError,
)
class _NaiveClock:
    def now(self) -> datetime:
        return datetime(2030, 1, 1)


def test_w07_node_result_lifts_clock_failure_and_preserves_old_abi() -> None:
    node = object.__new__(RuntimeNode)
    node.identity = NodeIdentity(
        node_id="node",
        incarnation="incarnation",
        started_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    node.clock = _NaiveClock()

    result = node.run_once_result()
    assert isinstance(result, Failure)
    assert result.family == "successor.runtime.failure"
    assert result.code == "CLOCK_OBSERVATION_INVALID"
    with pytest.raises(ClockObservationError):
        node.run_once()


def test_w07_reconciliation_binding_result_and_old_abi() -> None:
    assignment = SimpleNamespace(assignment_kind=AssignmentKind.INTERPRET)
    reconciler = EffectReconciler()

    result = reconciler.reconcile_result(
        assignment=assignment,
        attempt=object(),
        interpreter=object(),
    )
    assert isinstance(result, Failure)
    assert result.code == "RECONCILIATION_BINDING_REJECTED"
    with pytest.raises(ReconciliationError):
        reconciler.reconcile(
            assignment=assignment,
            attempt=object(),
            interpreter=object(),
        )


def test_w07_legacy_observation_readback_keeps_native_validation_error() -> None:
    result = LegacyObservationSet.readback_result({})
    assert isinstance(result, Failure)
    assert result.code == "LEGACY_OBSERVATION_INVALID"
    with pytest.raises(ValidationError):
        LegacyObservationSet.readback({})
