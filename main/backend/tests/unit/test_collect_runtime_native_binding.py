"""Collect runtime binds the ordered sync kernel to the explicit effect gateway."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.services.collect_runtime import runtime
from app.services.collect_runtime.contracts import CollectEffectGateway, CollectRequest, CollectResult


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


def test_runtime_uses_ordered_sync_and_preserves_gateway_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traversals: list[tuple[int, ...]] = []
    gateway_calls: list[tuple[str, ...]] = []
    original = runtime.interpret_ordered_sync

    def observed(elements, **kwargs):
        traversals.append(tuple(element.input_index for element in elements))
        return original(elements, **kwargs)

    monkeypatch.setattr(runtime, "interpret_ordered_sync", observed)

    def gateway(request: CollectRequest) -> CollectResult:
        gateway_calls.append(tuple(request.query_terms))
        return CollectResult(
            channel=request.channel,
            status="failed",
            provider_job_id=f"job-{request.query_terms[0]}",
            errors=[{
                "code": "auto_batch_execution_failed",
                "message": "bad",
            }],
            meta={"terminal_readback": {
                "kind": "terminal",
                "provider_job_id": f"job-{request.query_terms[0]}",
                "status": "failed",
            }},
        )

    gateway_contract: CollectEffectGateway = gateway
    monkeypatch.setattr(
        runtime,
        "_successor_effect_gateway",
        gateway_contract,
    )
    result = runtime._run_successor_collect(_request())
    assert traversals == [(0, 1, 2)]
    assert gateway_calls == [
        ("a1", "a2", "a3", "a4"),
        ("b1", "b2", "b3", "b4"),
        ("c1",),
    ]
    assert result is not None
    assert result.status == "failed"
    assert [item["input_index"] for item in result.meta["raw"]["delivery_observations"]] == [0, 1, 2]
    raw = result.meta.get("raw")
    assert isinstance(raw, dict)
    assert "aggregate_kind" not in raw


def test_STATIC_NEGATIVE__gateway_return_type_is_rejected() -> None:
    if not TYPE_CHECKING:
        return

    def bad_gateway(request: CollectRequest) -> int:
        return int(request.limit or 0)

    runtime.register_successor_collect_effect_gateway(bad_gateway)
