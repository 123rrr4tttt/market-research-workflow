"""Collect runtime consumes the compiled C3 native definition, not a second bundle."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.services.collect_runtime import runtime
from app.services.collect_runtime.contracts import CollectEffectGateway, CollectRequest


def _request() -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4", "c1"],
        limit=90,
        project_key="project:native-runtime",
        source_context={"summary": "市场信息采集"},
    )


def test_missing_gateway_returns_unknown_outcome_without_business_effect() -> None:
    runtime.reset_successor_collect_effect_gateway()
    result = runtime._run_successor_collect(_request())
    assert result is not None
    assert result.status == "unknown"
    assert not result.inserted


def test_missing_gateway_status_is_closed_unknown() -> None:
    runtime.reset_successor_collect_effect_gateway()
    result = runtime._run_successor_collect(_request())
    assert result is not None
    assert result.status == "unknown"
    assert result.errors[0].get("code") == "successor_effect_gateway_unavailable"


def test_runtime_consumes_default_c3_native_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.successor_runtime.capabilities.acquisition_native_contribution import (
        default_acquisition_native_definition,
    )

    definition = default_acquisition_native_definition()
    calls: list[str] = []

    def _observed():
        calls.append(definition.bundle.bundle_id)
        return definition

    monkeypatch.setattr(
        "app.successor_runtime.capabilities.acquisition_native_contribution.default_acquisition_native_definition",
        _observed,
    )
    from app.services.collect_runtime.contracts import CollectResult

    def gateway(request: CollectRequest) -> CollectResult:
        return CollectResult(
            channel=request.channel,
            status="failed",
            errors=[{
                "code": "auto_batch_execution_failed",
                "message": "bad",
            }],
        )

    gateway_contract: CollectEffectGateway = gateway
    monkeypatch.setattr(
        runtime,
        "_SUCCESSOR_EFFECT_GATEWAY",
        gateway_contract,
    )
    result = runtime._run_successor_collect(_request())
    assert calls == [definition.bundle.bundle_id]
    assert result is not None
    assert result.status == "unknown"
    assert result.errors == []
    raw = result.meta.get("raw")
    assert isinstance(raw, dict)
    assert raw.get("reason") == "provider_readback_pending"


def test_STATIC_NEGATIVE__gateway_return_type_is_rejected() -> None:
    if not TYPE_CHECKING:
        return

    def bad_gateway(request: CollectRequest) -> int:
        return int(request.limit or 0)

    runtime.register_successor_collect_effect_gateway(bad_gateway)
