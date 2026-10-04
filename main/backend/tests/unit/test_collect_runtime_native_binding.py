"""Collect runtime consumes the compiled C3 native definition, not a second bundle."""

from __future__ import annotations

from app.services.collect_runtime import runtime
from app.services.collect_runtime.contracts import CollectRequest


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


def test_runtime_consumes_default_c3_native_definition(monkeypatch) -> None:
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

    monkeypatch.setattr(
        runtime,
        "_SUCCESSOR_EFFECT_GATEWAY",
        lambda req: CollectResult(channel=req.channel, status="failed", errors=[{"code": "x", "message": "bad"}]),
    )
    result = runtime._run_successor_collect(_request())
    assert calls == [definition.bundle.bundle_id]
    assert result is not None
