from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.successor_runtime.runtime.facade import (
    FacadeInputError,
    FacadePortResultError,
    SuccessorRuntimeFacade,
)
from app.successor_runtime.runtime.facade_contracts import (
    C9TransactionFatal,
    CommandMetaV2,
    FacadeCommandV2,
    FacadeQueryV2,
    QueryMetaV2,
    derive_c9_request_digest_result,
    rollback_transition_id_result,
)
from app.successor_runtime.runtime.failure_policy import derive_failure_policy_result
from app.successor_runtime.runtime.ports import ProjectScopeRef


SCOPE = ProjectScopeRef(
    project_key="w07",
    resolved_schema="mrw_w07",
    project_registry_revision=1,
    incarnation="scope-w07",
    scope_digest="a" * 64,
)


def _command() -> FacadeCommandV2:
    meta = CommandMetaV2("w07", "trace", "command", SCOPE)
    return FacadeCommandV2(
        command_id="command",
        command_kind="noop",
        description="test",
        project_scope_ref=SCOPE,
        actor_ref="actor",
        idempotency_key="idempotency",
        expected_base_token=None,
        meta=meta,
    )


def _query() -> FacadeQueryV2:
    meta = QueryMetaV2("w07", "trace", "query", SCOPE)
    return FacadeQueryV2(
        query_id="query",
        query_kind="snapshot",
        project_scope_ref=SCOPE,
        actor_ref="actor",
        meta=meta,
    )


class _FatalSubmissionPort:
    def __init__(self, error: C9TransactionFatal) -> None:
        self.error = error

    def submit(self, command: FacadeCommandV2) -> object:
        raise self.error


class _FatalQueryPort:
    def __init__(self, error: C9TransactionFatal) -> None:
        self.error = error

    def read(self, query: FacadeQueryV2) -> object:
        raise self.error


class _BadQueryPort:
    def read(self, query: FacadeQueryV2) -> object:
        return object()


def test_facade_result_uses_typed_input_and_port_failures() -> None:
    facade = SuccessorRuntimeFacade(submission_port=object(), query_port=_BadQueryPort())
    input_failure = facade.submit_result(object())
    assert isinstance(input_failure, Failure)
    assert input_failure.code == "FACADE_INPUT_INVALID"

    port_failure = facade.query_result(_query())
    assert isinstance(port_failure, Failure)
    assert port_failure.code == "FACADE_PORT_RESULT_INVALID"
    with pytest.raises(FacadePortResultError):
        facade.query(_query())


def test_facade_transaction_fatal_submit_preserves_identity_and_cause() -> None:
    cause = ValueError("commit marker unavailable")
    fatal = C9TransactionFatal("submission transaction is partial")
    fatal.__cause__ = cause
    facade = SuccessorRuntimeFacade(
        submission_port=_FatalSubmissionPort(fatal),
        query_port=object(),
    )

    with pytest.raises(C9TransactionFatal) as raised:
        facade.submit_result(_command())

    assert raised.value is fatal
    assert raised.value.__cause__ is cause


def test_facade_transaction_fatal_query_preserves_identity_and_cause() -> None:
    cause = RuntimeError("readback transaction marker unavailable")
    fatal = C9TransactionFatal("query transaction is inconsistent")
    facade = SuccessorRuntimeFacade(
        submission_port=object(),
        query_port=_FatalQueryPort(fatal),
    )

    fatal.__cause__ = cause
    with pytest.raises(C9TransactionFatal) as raised:
        facade.query_result(_query())

    assert raised.value is fatal
    assert raised.value.__cause__ is cause


def test_facade_contract_helpers_are_total_with_legacy_lift() -> None:
    failure = rollback_transition_id_result(
        from_position={}, to_position={}, generation_completeness_digest="bad"
    )
    assert isinstance(failure, Failure)
    assert failure.code == "FACADE_CONTRACT_INVALID"

    request_failure = derive_c9_request_digest_result(
        scope_digest="bad",
        actor_ref="actor",
        command_id="command",
        command_kind="noop",
        payload={},
    )
    assert isinstance(request_failure, Failure)
    assert request_failure.code == "FACADE_CONTRACT_INVALID"


def test_failure_policy_result_has_closed_failure_code() -> None:
    result = derive_failure_policy_result(object(), object(), "missing")  # type: ignore[arg-type]
    assert isinstance(result, Failure)
    assert result.code == "FAILURE_POLICY_INVALID"
