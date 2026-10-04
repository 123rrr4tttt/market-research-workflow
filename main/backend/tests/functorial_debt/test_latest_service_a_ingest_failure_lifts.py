"""Focused witnesses for Service-A ingest shell and compatibility boundaries."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from functorial_kit import Failure

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.ingest import (  # noqa: E402
    canary_metrics_readback,
    commodity,
    digestion_scaffold,
    ecom,
    frontdoor_ingress,
    policy,
    market_web,
)
from app.services.source_library import provider_ports as source_provider_ports  # noqa: E402
from mrw_functorial_kit.core.application_failure_semantics import (  # noqa: E402
    source_library_contract_failures,
)
from mrw_functorial_kit.core.provider_port_failures import (  # noqa: E402
    ingest_long_cycle_failures,
    ingest_operation_failures,
    ingest_policy_failures,
)

_DATABASE_SESSION_FAILURE = "database session failed"


class _ExplodingSession:
    def __enter__(self) -> _ExplodingSession:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def execute(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError(_DATABASE_SESSION_FAILURE)

    def rollback(self) -> None:
        return None


class _ExplodingIterable:
    def __iter__(self):
        raise ValueError("provider iteration failed")


class _NullSession:
    def __enter__(self) -> "_NullSession":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def test_crawler_resolution_programmer_defect() -> None:
    with pytest.raises(
        ValueError,
        match="^unknown crawler provider resolution code: unknown$",
    ):
        source_provider_ports.CrawlerProviderResolutionError(
            "unknown",  # type: ignore[arg-type]
            "scrapyd",
            "invalid code",
        )


def test_unconfigured_crawler_resolver_fails_closed() -> None:
    source_provider_ports.set_crawler_provider_resolver(None)
    with pytest.raises(
        source_provider_ports.CrawlerProviderResolutionError,
        match="^crawler provider resolver is not configured$",
    ) as raised:
        source_provider_ports.resolve_crawler_provider(
            "scrapyd",
            channel={},
            params={},
        )
    assert raised.value.code == "resolver_not_configured"
    assert raised.value.provider_type == "scrapyd"


def test_latest_ingest_provider_iteration_failure_lifts() -> None:
    policy_cause = ValueError("policy provider iteration failed")
    policy_failure = policy._policy_provider_iteration_failure("ca", policy_cause)
    assert policy_failure.family == ingest_policy_failures.name
    assert policy_failure.code == "policy_provider_iteration_failed"
    assert policy_failure.context == {
        "state": "CA",
        "cause_message": "policy provider iteration failed",
        "exception_type": "ValueError",
    }
    with pytest.raises(ValueError, match="^policy provider iteration failed$") as raised:
        policy._raise_policy_provider_iteration_failure(policy_failure, policy_cause)
    assert raised.value is policy_cause
    with pytest.raises(TypeError, match="^policy provider iteration failure lift context is inconsistent$"):
        policy._raise_policy_provider_iteration_failure(
            Failure("other.family", "bad", "bad", {}), policy_cause
        )


def test_latest_ingest_provider_iteration_preserves_legacy_abi() -> None:
    class _PolicyAdapter:
        @staticmethod
        def fetch_documents() -> _ExplodingIterable:
            return _ExplodingIterable()

    def _unexpected_job_start(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("job started before provider iteration completed")

    with (
        patch.object(policy, "get_policy_adapter", return_value=_PolicyAdapter()),
        patch.object(policy, "start_job", _unexpected_job_start),
        pytest.raises(ValueError, match="^provider iteration failed$"),
    ):
        policy.ingest_policy_documents("CA")


def test_ingest_service_a_failure_lifts() -> None:
    canary_failure = canary_metrics_readback._failure(
        "canary_readback_not_object",
        "canary record is invalid",
        operation="test",
        site="test.canary",
    )
    with pytest.raises(ValueError, match="^canary record is invalid$"):
        canary_metrics_readback._raise_failure(canary_failure)
    cause = RuntimeError("readback cause")
    with pytest.raises(ValueError, match="^canary record is invalid$") as raised:
        canary_metrics_readback._raise_failure(canary_failure, cause=cause)
    assert raised.value.__cause__ is cause
    with pytest.raises(TypeError, match="^canary metrics readback failure lift context is incomplete or inconsistent$"):
        canary_metrics_readback._raise_failure(Failure("other.family", "bad", "bad", {}))

    long_cycle_failure = digestion_scaffold._failure(
        "required_ref_missing",
        "long-cycle reference is required",
        operation="test",
        site="test.long_cycle",
    )
    with pytest.raises(ValueError, match="^long-cycle reference is required$"):
        digestion_scaffold._raise_failure(long_cycle_failure)
    long_cycle_cause = RuntimeError("long-cycle cause")
    with pytest.raises(ValueError, match="^long-cycle reference is required$") as raised:
        digestion_scaffold._raise_failure(long_cycle_failure, cause=long_cycle_cause)
    assert raised.value.__cause__ is long_cycle_cause
    with pytest.raises(TypeError, match="^long-cycle failure lift context is incomplete or inconsistent$"):
        digestion_scaffold._raise_failure(Failure("other.family", "bad", "bad", {}))

    frontdoor_failure = frontdoor_ingress._frontdoor_contract_failure(
        "entrypoint is required",
        ingress_type="discovery",
        entrypoint="",
        project_key="demo_proj",
        site="test.frontdoor",
    )
    with pytest.raises(ValueError, match="^entrypoint is required$"):
        frontdoor_ingress._raise_frontdoor_contract_failure(frontdoor_failure)
    with pytest.raises(TypeError, match="^frontdoor contract lift context is incomplete or inconsistent$"):
        frontdoor_ingress._raise_frontdoor_contract_failure(Failure("other.family", "bad", "bad", {}))

    with (
        patch.object(commodity, "start_job", return_value=1),
        patch.object(commodity, "fail_job") as commodity_fail,
        patch.object(commodity, "_fetch_stooq_rows", side_effect=RuntimeError("stooq unavailable")),
        patch.object(commodity, "SessionLocal", return_value=_ExplodingSession()),
        pytest.raises(RuntimeError, match="^stooq unavailable$"),
    ):
        commodity.ingest_commodity_metrics(symbols={"commodity.test": "foo"}, limit=1)
    commodity_fail.assert_called_once_with(1, "stooq unavailable")

    with (
        patch.object(ecom, "start_job", return_value=2),
        patch.object(ecom, "fail_job") as ecom_fail,
        patch.object(ecom, "SessionLocal", return_value=_ExplodingSession()),
        pytest.raises(RuntimeError, match="^database session failed$"),
    ):
        ecom.collect_ecom_price_observations(limit=1)
    ecom_fail.assert_called_once_with(2, "database session failed")

    with (
        patch.object(market_web, "start_job", return_value=4),
        patch.object(market_web, "fail_job") as market_web_fail,
        patch.object(market_web, "SessionLocal", return_value=_NullSession()),
        patch.object(market_web, "_get_or_create_source", return_value=object()),
        patch(
            "app.services.search.candidate_search.search_sources",
            side_effect=RuntimeError("search provider failed"),
        ),
        pytest.raises(RuntimeError, match="^search provider failed$"),
    ):
        market_web.collect_market_info(["robotics"], limit=1)
    market_web_fail.assert_called_once_with(4, "search provider failed")

    assert canary_failure.family == ingest_operation_failures.name
    assert long_cycle_failure.family == ingest_long_cycle_failures.name
    assert frontdoor_failure.family == source_library_contract_failures.name
