"""Ingest failure contracts."""

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
    ecom,
    frontdoor_ingress,
    market_web,
    policy,
)
from app.services.source_library import provider_ports as source_provider_ports  # noqa: E402

from mrw_functorial_kit.core.application_failure_semantics import (  # noqa: E402
    source_library_contract_failures,
)
from mrw_functorial_kit.core.provider_port_failures import (  # noqa: E402
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


class _InvalidCommodityRowResult:
    @staticmethod
    def scalar_one_or_none() -> object:
        return object()


class _InvalidCommodityRowSession(_NullSession):
    @staticmethod
    def execute(*_args: object, **_kwargs: object) -> _InvalidCommodityRowResult:
        return _InvalidCommodityRowResult()


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
    assert frontdoor_failure.family == source_library_contract_failures.name


def test_FAILURE_PRESERVED__commodity_failure_lift_preserves_original_exception() -> None:
    root_cause = ValueError("provider root cause")
    cause = RuntimeError("stooq unavailable")
    cause.__cause__ = root_cause
    failure = commodity._commodity_failure(
        str(cause),
        operation="ingest_commodity_metrics",
        site="app.services.ingest.commodity.ingest_commodity_metrics",
        public_exception=cause.__class__.__name__,
    )

    assert ingest_operation_failures.matches(failure)
    assert failure.code == "commodity_collection_failed"
    assert failure.context is not None
    assert failure.context["witness"] == (
        "test:test_FAILURE_PRESERVED__commodity_failure_lift_preserves_original_exception"
    )
    with pytest.raises(RuntimeError, match="^stooq unavailable$") as raised:
        commodity._raise_commodity_failure(failure, cause)
    assert raised.value is cause
    assert raised.value.__cause__ is root_cause

    with (
        patch.object(commodity, "start_job", return_value=21),
        patch.object(commodity, "fail_job") as fail_job,
        patch.object(commodity, "SessionLocal", return_value=_NullSession()),
        patch.object(commodity, "_fetch_stooq_rows", side_effect=cause),
        pytest.raises(RuntimeError, match="^stooq unavailable$") as public_raised,
    ):
        commodity.ingest_commodity_metrics(symbols={"commodity.test": "foo"}, limit=1)
    assert public_raised.value is cause
    assert public_raised.value.__cause__ is root_cause
    fail_job.assert_called_once_with(21, "stooq unavailable")

    with pytest.raises(TypeError, match="^commodity failure lift context is incomplete or inconsistent$"):
        commodity._raise_commodity_failure(
            Failure("other.family", "commodity_collection_failed", "bad"),
            cause,
        )


def test_FAILURE_PRESERVED__report_failure_lifts_preserve_original_exception() -> None:
    from app.services.ingest.reports import general

    for collector, code, job_id in (
        (
            general.collect_weekly_market_reports,
            "weekly_report_collection_failed",
            31,
        ),
        (
            general.collect_monthly_financial_reports,
            "monthly_report_collection_failed",
            32,
        ),
    ):
        root_cause = ValueError(f"{code} root cause")
        cause = RuntimeError(code)
        cause.__cause__ = root_cause
        failure = general._report_failure(
            code,
            str(cause),
            operation=collector.__name__,
            site=f"app.services.ingest.reports.general.{collector.__name__}",
            public_exception=cause.__class__.__name__,
        )
        assert ingest_operation_failures.matches(failure)
        assert failure.code == code
        with pytest.raises(RuntimeError, match=f"^{code}$") as lifted:
            general._raise_report_failure(failure, cause)
        assert lifted.value is cause
        assert lifted.value.__cause__ is root_cause

        with (
            patch.object(general, "start_job", return_value=job_id),
            patch.object(general, "fail_job") as fail_job,
            patch.object(general, "search_sources", side_effect=cause),
            pytest.raises(RuntimeError, match=f"^{code}$") as public_raised,
        ):
            collector()
        assert public_raised.value is cause
        assert public_raised.value.__cause__ is root_cause
        fail_job.assert_called_once_with(job_id, code)

    with pytest.raises(TypeError, match="^report failure lift context is incomplete or inconsistent$"):
        general._raise_report_failure(
            Failure("other.family", "weekly_report_collection_failed", "bad"),
            RuntimeError("bad"),
        )


def test_FAILURE_PRESERVED__report_and_commodity_contract_branches_are_observable() -> None:
    from app.services.ingest.reports import general

    with (
        patch.object(general, "start_job", return_value=41),
        patch.object(general, "fail_job") as report_fail_job,
        patch.object(general, "search_sources", return_value=[{"link": ["invalid"]}]),
        patch.object(general, "SessionLocal", return_value=_NullSession()),
        pytest.raises(
            TypeError,
            match="^report search result field link must be a string$",
        ) as report_raised,
    ):
        general.collect_weekly_market_reports(limit=1)
    assert isinstance(report_raised.value.__cause__, TypeError)
    assert str(report_raised.value.__cause__) == str(report_raised.value)
    report_fail_job.assert_called_once_with(41, str(report_raised.value))

    rows = [{"Date": "2026-10-06", "Close": "123.45"}]
    with (
        patch.object(commodity, "start_job", return_value=42),
        patch.object(commodity, "fail_job") as commodity_fail_job,
        patch.object(commodity, "SessionLocal", return_value=_InvalidCommodityRowSession()),
        patch.object(commodity, "_fetch_stooq_rows", return_value=rows),
        pytest.raises(
            TypeError,
            match="^MarketMetricPoint query returned an invalid row$",
        ) as commodity_raised,
    ):
        commodity.ingest_commodity_metrics(symbols={"commodity.test": "foo"}, limit=1)
    assert isinstance(commodity_raised.value.__cause__, TypeError)
    assert str(commodity_raised.value.__cause__) == str(commodity_raised.value)
    commodity_fail_job.assert_called_once_with(42, str(commodity_raised.value))
