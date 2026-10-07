"""Typed business-result readback for one broker-dispatched batch item.

This module owns only the read-only mapping between a broker task identity and
the business terminal state of the item it carried.  It has no execution
callback and cannot re-dispatch the underlying business effect.

The broker observation preserves the real business output (or the real typed
failure error) as a validated ``CanonicalJsonValue``, never as a lossy
``str()`` or an untyped ``Any``.  ``PENDING``/``STARTED``/``RETRY`` are waiting
evidence and are never proof that the effect did not start.
"""

from __future__ import annotations

from typing import Annotated

import json
from collections.abc import Callable

from celery import Celery

from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonValue,
    canonical_json,
)
from app.successor_runtime.capabilities.batch_business import (
    BatchBusinessResult,
    BrokerBusinessReadback,
    BusinessCancelObservation,
    BusinessTaskObservation,
    BusinessTaskState,
    build_batch_business_result,
)
from app.successor_runtime.capabilities.batch_task import BatchTaskSingleDispatchAck
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    OutcomeUncertain,
)


_CELERY_WAITING_STATES = frozenset(
    {"pending", "received", "started", "retry", "running", "progress"}
)


def map_celery_state(raw_state: str | None) -> BusinessTaskState:
    """Map one Celery ``AsyncResult.status`` to the closed business state."""

    state = str(raw_state or "").strip().lower() or "unknown"
    if state == "success":
        return BusinessTaskState.SUCCESS
    if state == "failure":
        return BusinessTaskState.FAILURE
    if state == "revoked":
        return BusinessTaskState.REVOKED
    if state in _CELERY_WAITING_STATES:
        return BusinessTaskState.PENDING
    return BusinessTaskState.UNKNOWN


def _to_canonical_json_value(value: object) -> CanonicalJsonValue | None:
    """Validate one broker value as real canonical JSON without lossy coercion."""

    if value is None:
        return None
    decoded: CanonicalJsonValue = json.loads(canonical_json(value))
    return decoded


class CeleryBrokerBusinessReadback:
    """Map a real Celery ``AsyncResult`` to the typed business state."""

    def __init__(self, *, app: Celery | None = None) -> None:
        if app is None:
            from app.celery_app import celery_app

            app = celery_app
        self._app = app

    def read_task(self, task_id: str) -> BusinessTaskObservation:
        result = self._app.AsyncResult(task_id)
        state = map_celery_state(result.status)
        raw_result = result.result if result.ready() else None
        traceback = None
        if state is BusinessTaskState.SUCCESS:
            output = _to_canonical_json_value(raw_result)
        elif state is BusinessTaskState.FAILURE:
            candidate = getattr(result, "traceback", None)
            traceback = str(candidate) if candidate else None
            output = _to_canonical_json_value(
                {
                    "exception": type(raw_result).__name__ if raw_result is not None else None,
                    "traceback": traceback,
                }
            )
        elif state is BusinessTaskState.REVOKED:
            output = _to_canonical_json_value(
                {"exception": "Revoked", "traceback": None}
            )
        else:
            output = None
        return BusinessTaskObservation(
            task_id=task_id,
            state=state,
            result=output,
            traceback=traceback,
        )

    def cancel_task(self, task_id: str) -> BusinessCancelObservation:
        result = self._app.AsyncResult(task_id)
        try:
            # A soft revoke asks the worker to stop at the next boundary; it
            # never terminates a concurrent worker or fabricates a business
            # terminal.  The terminal state is settled by a later read back.
            result.revoke()
        except Exception as exc:  # noqa: BLE001 - broker revoke may be unavailable
            return BusinessCancelObservation(
                task_id=task_id,
                state="REVOKE_FAILED",
                reason=type(exc).__name__,
            )
        return BusinessCancelObservation(
            task_id=task_id,
            state="REVOKE_REQUESTED",
        )


def build_batch_business_wait_invoke(
    broker: BrokerBusinessReadback,
) -> Annotated[Callable[[BatchTaskSingleDispatchAck], BatchBusinessResult], 'kit:prepared-command effect_boundary=broker_business_readback witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift']:
    """Return the typed wait kernel the runtime wraps in a persistent handler."""

    def invoke(ack: BatchTaskSingleDispatchAck) -> BatchBusinessResult:
        observation = broker.read_task(ack.celery_task_id)
        if observation.task_id != ack.celery_task_id:
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift
            raise DefiniteInterpreterFailure("BUSINESS_WAIT_TASK_ID_DRIFT")
        if observation.state is BusinessTaskState.SUCCESS:
            return build_batch_business_result(ack, observation.result)
        if observation.state is BusinessTaskState.FAILURE:
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift
            raise DefiniteInterpreterFailure("BUSINESS_TASK_FAILURE")
        if observation.state is BusinessTaskState.REVOKED:
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift
            raise DefiniteInterpreterFailure("BUSINESS_TASK_REVOKED")
        if observation.state is BusinessTaskState.PENDING:
            # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift
            raise OutcomeUncertain("CELERY_PENDING")
        # kit:boundary owner=batch.business class=SHELL_BOUNDARY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_business_wait_kernel_preserves_terminal_waiting_and_drift
        raise OutcomeUncertain("CELERY_BROKER_STATE_UNKNOWN")

    return invoke


__all__ = [
    "BrokerBusinessReadback",
    "BusinessCancelObservation",
    "BusinessTaskObservation",
    "BusinessTaskState",
    "CeleryBrokerBusinessReadback",
    "build_batch_business_wait_invoke",
    "map_celery_state",
]
