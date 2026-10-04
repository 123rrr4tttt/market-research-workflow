from __future__ import annotations

from collections.abc import Callable
from typing import get_args

import pytest

from app.successor_runtime.capabilities import (
    source_provider_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities import source_contracts as shared
from app.successor_runtime.capabilities.checksum import content_digest


def _effect_request() -> shared.ProviderEffectRequest:
    project_key = "demo_proj"
    resolved_schema = "mrw_p_demo_proj"
    incarnation = "scope-inc-5"
    scope = shared.AuthenticatedProjectScope(
        project_key=project_key,
        resolved_schema=resolved_schema,
        registry_revision=5,
        incarnation=incarnation,
        scope_digest=shared.project_scope_digest(
            project_key, resolved_schema, 5, incarnation
        ),
    )
    return shared.ProviderEffectRequest(
        schema_version=shared.SOURCE_PROVIDER_ACQUISITION_PAYLOAD_SCHEMA,
        operation_kind=shared.SOURCE_PROVIDER_ACQUISITION_KIND,
        request_id="request:c2-runtime-closure",
        idempotency_key="idem:c2-runtime-closure",
        project_scope=scope,
        item_key="item:demo",
        item_revision=1,
        item_incarnation="item-inc-1",
        item_content_digest=content_digest({"item": "demo"}),
        channel_key="channel:demo",
        provider="fixture",
        provider_config_ref="catalog:demo",
        effect_payload_codec_ref="codec:demo",
        effect_payload_digest=content_digest({"payload": "demo"}),
        effect_payload={"query": "demo"},
        credential_refs=(),
        policy=shared.SOURCE_PROVIDER_ACQUISITION_DEFAULT_RESOURCE_POLICY,
        catalog_revision=1,
        catalog_incarnation="catalog-inc-1",
        catalog_digest=content_digest({"catalog": "demo"}),
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


def test_fixture_missing_script_is_a_rejection_not_execution_failure() -> None:
    interpreter = c23_fixtures.FixtureProviderEffectPort()
    request = _effect_request()
    outcome = interpreter.execute(request, ())

    assert isinstance(outcome, shared.RejectedProviderEffect)
    assert outcome.kind == "rejected"
    assert outcome.code == "UNSUPPORTED_PROVIDER"
    assert interpreter.provider_calls == [request.request_id]
