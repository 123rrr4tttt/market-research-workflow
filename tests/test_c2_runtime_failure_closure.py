from __future__ import annotations

from collections.abc import Callable
from typing import get_args

import pytest

from functorial_kit import Failure
from app.successor_runtime.capabilities import source_contracts as shared

def test_w06_c2_total_core_failure_lifts() -> None:
    failure = shared.source_contract_failure(
        "schema_contract_invalid",
        "typed source contract rejected",
        operation="test.source_contract",
        site="test.source_contracts",
        owner="source.resolve_and_acquire.shared.v2",
        public_exception="ValueError",
    )
    assert failure.family == "source.contract.failure"
    assert failure.code == "schema_contract_invalid"
    assert failure.context["witness"] == "test:test_w06_c2_total_core_failure_lifts"
    with pytest.raises(ValueError, match="^typed source contract rejected$"):
        shared.raise_source_contract_failure(failure)

    with pytest.raises(TypeError, match="^C2 contract lift context is invalid$"):
        shared.raise_source_contract_failure(
            Failure(
                "other.family",
                "bad",
                "bad",
                {"public_exception": "ValueError", "public_message": "bad"},
            )
        )


def test_literal_aliases_reuse_frozen_runtime_unions() -> None:
    assert set(get_args(shared.SourceWarningCode)) == shared.SOURCE_WARNING_CODES
    assert set(get_args(shared.SourceRejectionCode)) == shared.SOURCE_REJECTION_CODES
    assert (
        set(get_args(shared.PlanningRejectionCode))
        == shared.SOURCE_PLANNING_FAILURE_CODES
    )
    assert set(get_args(shared.ProviderRejectionCode)) == (
        shared.PROVIDER_REJECTION_CODES
    )
    assert set(get_args(shared.ProviderExecutionFailureCode)) == (
        shared.PROVIDER_EXECUTION_FAILURE_CODES
    )
    assert set(get_args(shared.CredentialRejectionCode)) == (
        shared.CREDENTIAL_REJECTION_CODES
    )
    assert set(get_args(shared.AggregateProviderFailureCode)) == (
        shared.SOURCE_PROVIDER_ACQUISITION_FAILURE_CODES
    )
    assert set(get_args(shared.SourcePlanningOperationKind)) == set(
        shared.SOURCE_PLANNING_KINDS
    )
    assert set(get_args(shared.SourceModeLiteral)) == set(shared.SOURCE_MODES)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: shared.OrderedProviderFailure(
                order_index=-1,
                code="TRANSPORT",
                message="failed",
                source="url-0",
            ),
            "OrderedProviderFailure.order_index must be a non-negative int",
        ),
        (
            lambda: shared.OrderedProviderFailure(
                order_index=0,
                code="NOT_REGISTERED",
                message="failed",
                source="url-0",
            ),
            "ordered provider failure code 'NOT_REGISTERED'",
        ),
        (
            lambda: shared.OrderedFailure(
                order_index=0,
                code="NOT_REGISTERED",
                message="failed",
                source="url-0",
            ),
            "ordered collection failure code 'NOT_REGISTERED'",
        ),
        (
            lambda: shared.CollectionRejected(code="NOT_REGISTERED"),
            "collection rejection code 'NOT_REGISTERED'",
        ),
        (
            lambda: shared.CollectionFailed(code="UNSUPPORTED_PROVIDER"),
            "collection failure code 'UNSUPPORTED_PROVIDER'",
        ),
        (
            lambda: shared.RedactedCredentialRejection(
                code="UNSUPPORTED_PROVIDER",
                credential_ref="credential:/demo",
                message="not a credential family",
            ),
            "credential rejection code 'UNSUPPORTED_PROVIDER'",
        ),
    ],
)
def test_runtime_failure_constructors_fail_closed(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_valid_failure_projections_keep_their_serialization() -> None:
    provider_failure = shared.OrderedProviderFailure(
        order_index=2,
        code="OUTCOME_UNKNOWN",
        message="provider outcome unknown",
        source="url-2",
    )
    collection_failure = shared.OrderedFailure(
        order_index=2,
        code="OUTCOME_UNKNOWN",
        message="collection outcome unknown",
        source="url-2",
    )
    rejected = shared.CollectionRejected(
        code="CHANNEL_DISABLED", message="channel disabled"
    )
    failed = shared.CollectionFailed(
        code="RATE_LIMIT", message="rate limited", retryable=True
    )
    credential = shared.RedactedCredentialRejection(
        code="MISSING_CREDENTIAL",
        credential_ref="credential:/demo/key",
        message="credential unavailable",
    )

    assert provider_failure.to_plain() == {
        "order_index": 2,
        "code": "OUTCOME_UNKNOWN",
        "message": "provider outcome unknown",
        "source": "url-2",
    }
    assert collection_failure.to_plain() == {
        "order_index": 2,
        "code": "OUTCOME_UNKNOWN",
        "message": "collection outcome unknown",
        "source": "url-2",
    }
    assert rejected.to_plain() == {
        "kind": "rejected",
        "code": "CHANNEL_DISABLED",
        "message": "channel disabled",
        "outcome_digest": rejected.outcome_digest,
    }
    assert failed.to_plain() == {
        "kind": "failed",
        "code": "RATE_LIMIT",
        "message": "rate limited",
        "retryable": True,
        "outcome_digest": failed.outcome_digest,
    }
    assert credential.to_plain() == {
        "code": "MISSING_CREDENTIAL",
        "credential_ref": "credential:/demo/key",
        "message": "credential unavailable",
        "credential_decision_receipt": None,
    }
