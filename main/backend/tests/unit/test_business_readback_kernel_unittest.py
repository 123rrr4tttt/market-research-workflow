"""Typed business-result readback kernel: Celery state mapping and revoke."""

from __future__ import annotations

import pytest

from app.services.agent_batch.business_readback import (
    BusinessCancelObservation,
    BusinessTaskObservation,
    BusinessTaskState,
    CeleryBrokerBusinessReadback,
    build_batch_business_wait_invoke,
    map_celery_state,
)


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SUCCESS", BusinessTaskState.SUCCESS),
        ("success", BusinessTaskState.SUCCESS),
        ("FAILURE", BusinessTaskState.FAILURE),
        ("REVOKED", BusinessTaskState.REVOKED),
        ("PENDING", BusinessTaskState.PENDING),
        ("STARTED", BusinessTaskState.PENDING),
        ("RETRY", BusinessTaskState.PENDING),
        ("RECEIVED", BusinessTaskState.PENDING),
        ("running", BusinessTaskState.PENDING),
        ("PROGRESS", BusinessTaskState.PENDING),
        ("", BusinessTaskState.UNKNOWN),
        (None, BusinessTaskState.UNKNOWN),
        ("bogus", BusinessTaskState.UNKNOWN),
    ],
)
def test_map_celery_state_is_closed(raw: str | None, expected: BusinessTaskState) -> None:
    assert map_celery_state(raw) is expected


def test_map_celery_state_never_returns_not_started() -> None:
    # PENDING is the canonical ambiguous state and must not smuggle NOT_STARTED.
    assert map_celery_state("PENDING") is BusinessTaskState.PENDING
    assert map_celery_state("UNKNOWN") is BusinessTaskState.UNKNOWN
    assert BusinessTaskState.NOT_STARTED not in {
        map_celery_state(state)
        for state in (
            "PENDING",
            "STARTED",
            "RETRY",
            "RECEIVED",
            "SUCCESS",
            "FAILURE",
            "REVOKED",
            "UNKNOWN",
            "",
        )
    }


class _FakeAsyncResult:
    def __init__(
        self,
        status: str,
        *,
        result: object = None,
        traceback: str | None = None,
        ready: bool = True,
        revoke_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._result = result
        self.traceback = traceback
        self._ready = ready
        self.revoke_calls: list[bool] = []
        self._revoke_error = revoke_error

    def ready(self) -> bool:
        return self._ready

    @property
    def result(self) -> object:
        return self._result

    def revoke(self, terminate: bool = False) -> None:
        self.revoke_calls.append(terminate)
        if self._revoke_error is not None:
            raise self._revoke_error


class _FakeApp:
    def __init__(self, results: dict[str, _FakeAsyncResult]) -> None:
        self._results = results

    def AsyncResult(self, task_id: str) -> _FakeAsyncResult:
        return self._results[task_id]


def test_celery_broker_reads_success_and_failure() -> None:
    ok = _FakeAsyncResult("SUCCESS", result={"items": 3})
    failed = _FakeAsyncResult("FAILURE", traceback="Traceback: boom")
    broker = CeleryBrokerBusinessReadback(
        app=_FakeApp({"t-ok": ok, "t-fail": failed})
    )

    ok_obs = broker.read_task("t-ok")
    assert isinstance(ok_obs, BusinessTaskObservation)
    assert ok_obs.state is BusinessTaskState.SUCCESS
    assert ok_obs.result == {"items": 3}
    assert ok_obs.traceback is None

    fail_obs = broker.read_task("t-fail")
    assert fail_obs.state is BusinessTaskState.FAILURE
    assert fail_obs.result is not None
    assert "exception" in fail_obs.result
    assert fail_obs.traceback == "Traceback: boom"


def test_celery_broker_reads_pending_without_result() -> None:
    pending = _FakeAsyncResult("PENDING", ready=False)
    broker = CeleryBrokerBusinessReadback(app=_FakeApp({"t": pending}))

    obs = broker.read_task("t")
    assert obs.state is BusinessTaskState.PENDING
    assert obs.result is None


def test_celery_broker_validates_result_as_json_not_str() -> None:
    ok = _FakeAsyncResult("SUCCESS", result={"payload": {"n": 1, "ok": True}})
    broker = CeleryBrokerBusinessReadback(app=_FakeApp({"t": ok}))
    obs = broker.read_task("t")
    assert isinstance(obs.result, dict)
    assert obs.result == {"payload": {"n": 1, "ok": True}}


def test_celery_broker_rejects_non_json_success_instead_of_empty_success() -> None:
    broker = CeleryBrokerBusinessReadback(app=_FakeApp({
        "t": _FakeAsyncResult("SUCCESS", result={"payload": object()}),
    }))
    with pytest.raises((TypeError, ValueError)):
        broker.read_task("t")


def test_celery_broker_cancel_is_idempotent_and_typed() -> None:
    result = _FakeAsyncResult("PENDING", ready=False)
    broker = CeleryBrokerBusinessReadback(app=_FakeApp({"t": result}))

    first = broker.cancel_task("t")
    second = broker.cancel_task("t")

    assert first.state == "REVOKE_REQUESTED"
    assert second.state == "REVOKE_REQUESTED"
    # Soft revoke never passes terminate=True; it only asks for a boundary stop.
    assert result.revoke_calls == [False, False]
    assert isinstance(first, BusinessCancelObservation)


def test_celery_broker_cancel_reports_revoke_failure() -> None:
    result = _FakeAsyncResult("PENDING", ready=False, revoke_error=RuntimeError("down"))
    broker = CeleryBrokerBusinessReadback(app=_FakeApp({"t": result}))

    cancelled = broker.cancel_task("t")
    assert cancelled.state == "REVOKE_FAILED"
    assert cancelled.reason == "RuntimeError"


class _WaitBroker:
    def __init__(
        self,
        state: BusinessTaskState,
        result: object | None = None,
    ) -> None:
        self.state = state
        self.result = result

    def read_task(self, task_id: str) -> BusinessTaskObservation:
        return BusinessTaskObservation(
            task_id=task_id, state=self.state, result=self.result
        )

    def cancel_task(self, task_id: str) -> BusinessCancelObservation:
        return BusinessCancelObservation(task_id=task_id, state="REVOKE_REQUESTED")


def _ack() -> object:
    from app.successor_runtime.capabilities import batch_task

    return batch_task.BatchTaskSingleDispatchAck(
        schema_version=batch_task.DISPATCH_SINGLE_ACK_SCHEMA,
        operation_kind=batch_task.DISPATCH_SINGLE_KIND,
        dispatch_id="dispatch:1",
        channel="search.market",
        celery_task_id="b" * 64,
        lane="main",
        queue="celery",
    )


def test_wait_invoke_success_returns_precise_typed_result() -> None:
    from app.successor_runtime.capabilities.batch_business import BatchBusinessResult

    ack = _ack()
    output = {"collected": 3}
    invoke = build_batch_business_wait_invoke(
        _WaitBroker(BusinessTaskState.SUCCESS, result=output)
    )
    result = invoke(ack)
    assert isinstance(result, BatchBusinessResult)
    assert result.task_id == "b" * 64
    assert result.provider_locator == "celery-task:" + "b" * 64
    assert result.output == output


def test_wait_invoke_pending_raises_outcome_uncertain() -> None:
    from app.successor_runtime.runtime.node import OutcomeUncertain

    invoke = build_batch_business_wait_invoke(_WaitBroker(BusinessTaskState.PENDING))
    try:
        invoke(_ack())
    except OutcomeUncertain as exc:
        assert exc.reconciliation_hint == "CELERY_PENDING"
    else:
        raise AssertionError("expected OutcomeUncertain")


def test_wait_invoke_failure_raises_definite_failure() -> None:
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure

    for state, code in (
        (BusinessTaskState.FAILURE, "BUSINESS_TASK_FAILURE"),
        (BusinessTaskState.REVOKED, "BUSINESS_TASK_REVOKED"),
    ):
        invoke = build_batch_business_wait_invoke(_WaitBroker(state))
        try:
            invoke(_ack())
        except DefiniteInterpreterFailure as exc:
            assert exc.failure_code == code
        else:
            raise AssertionError(f"expected DefiniteInterpreterFailure for {state}")
