from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from pathlib import Path

import pytest

from app.services.collect_runtime.contracts import (
    CollectEffectGateway,
    CollectRequest,
    CollectResult,
    CollectFailure,
    source_library_compat_response,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit


def test_INVARIANT__runtime_module_does_not_import_concrete_adapters() -> None:
    from app.services.collect_runtime import runtime

    assert not any(
        "collect_runtime.adapters" in module
        for module in sys.modules
        if module == "app.services.collect_runtime.runtime"
    )
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "from .adapters." not in source


def test_INVARIANT__composition_owns_adapter_map_and_compat_projector() -> None:
    from app.composition import collect_runtime as composition
    from app.services.collect_runtime import runtime

    composition.configure_default_collect_adapters(force=True)
    channels = sorted(composition.default_collect_adapters())
    assert channels == [
        "crawler.scrapy",
        "search.market",
        "search.policy",
        "source_library",
        "url_pool",
    ]
    assert not hasattr(runtime, "list_collect_skills")
    assert not hasattr(runtime, "_SKILL_REGISTRY")
    assert callable(runtime._successor_effect_gateway)


def test_FAILURE_PRESERVED__successor_composition_does_not_fallback_for_unknown_channel() -> None:
    from app.composition import collect_runtime as composition
    from app.services.collect_runtime.contracts import CollectRequest
    from app.services.collect_runtime import runtime

    composition.configure_default_collect_adapters(force=True)
    result = runtime._successor_effect_gateway(CollectRequest(channel="not.registered"))
    assert result.status == "failed"
    assert result.errors[0].get("code") == "collect_effect_not_registered"


def test_TYPED_GATEWAY__search_and_url_pool_share_one_signature() -> None:
    from app.services.collect_runtime import runtime

    calls: list[str] = []

    def gateway(request: CollectRequest) -> CollectResult:
        calls.append(request.channel)
        return CollectResult(channel=request.channel, status="completed")

    gateway_contract: CollectEffectGateway = gateway
    runtime.register_successor_collect_effect_gateway(gateway_contract)
    assert runtime._successor_effect_gateway is not None
    for channel in ("search.market", "url_pool"):
        result = runtime._successor_effect_gateway(CollectRequest(channel=channel))
        assert result.status == "completed"
    assert calls == ["search.market", "url_pool"]


def test_TYPED_PROJECTOR__adapter_dict_is_validated_at_composition_seam() -> None:
    response = source_library_compat_response({
        "display_meta": {"summary": "来源"},
        "result": {"errors": []},
    })
    assert response["display_meta"] == {"summary": "来源"}

    with pytest.raises(TypeError, match="JSON object"):
        source_library_compat_response([])


def test_compat_response_rejects_non_json_and_non_object_payloads() -> None:
    with pytest.raises(TypeError, match="must be JSON"):
        source_library_compat_response({"bad": {1, 2}})

    with pytest.raises(TypeError, match="must be a JSON object"):
        source_library_compat_response([("display_meta", 1)])


@pytest.mark.skipif(
    TYPE_CHECKING,
    reason="checked by the Pyright selector; these objects would fail runtime registration",
)
def test_STATIC_NEGATIVE__handler_status_and_failure_shapes_are_rejected() -> None:
    from app.services.collect_runtime import runtime

    if not TYPE_CHECKING:
        pytest.skip("negative handler and result shapes are enforced by Pyright")

    def bad_gateway() -> int:
        return 1

    def bad_projector(result: CollectResult) -> int:
        return 1

    runtime.register_successor_collect_effect_gateway(bad_gateway)
    runtime.register_source_library_compat_projector(bad_projector)
    CollectResult(status="running")
    failure: CollectFailure = {
        "code": "auto_batch_execution_failed",
        "message": "bad",
        "not_a_contract_field": True,
    }
    assert failure


def test_FAILURE_PRESERVED__compat_projector_missing_fails_closed() -> None:
    from app.services.collect_runtime import runtime
    from app.composition.collect_runtime import configure_default_collect_adapters
    from app.services.collect_runtime.contracts import CollectResult

    configure_default_collect_adapters(force=True)
    original = runtime._source_library_compat_projector
    original_runner = runtime._run_collect_no_batch
    runtime._source_library_compat_projector = None
    try:
        runtime._run_collect_no_batch = lambda _request: CollectResult(channel="source_library")
        with pytest.raises(RuntimeError, match="compatibility projector is not configured"):
            runtime.run_source_library_item_compat(item_key="item")
    finally:
        runtime._source_library_compat_projector = original
        runtime._run_collect_no_batch = original_runner

        configure_default_collect_adapters(force=True)
