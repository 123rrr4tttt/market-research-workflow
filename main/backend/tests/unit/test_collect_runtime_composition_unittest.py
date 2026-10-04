from __future__ import annotations

import sys
from pathlib import Path

import pytest

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


def test_INVARIANT__composition_registers_adapters_and_compat_projector() -> None:
    from app.composition import collect_runtime as composition
    from app.services.collect_runtime import runtime

    composition.configure_default_collect_adapters(force=True)
    assert "search.market" in runtime.list_collect_skills()
    assert "collect.source_library" in runtime.list_collect_skills()
    assert "crawler.scrapy" in runtime.list_collect_skills()
    assert callable(runtime._SUCCESSOR_EFFECT_GATEWAY)


def test_FAILURE_PRESERVED__successor_composition_does_not_fallback_for_unknown_channel() -> None:
    from app.composition import collect_runtime as composition
    from app.services.collect_runtime.contracts import CollectRequest
    from app.services.collect_runtime import runtime

    composition.configure_default_collect_adapters(force=True)
    result = runtime._SUCCESSOR_EFFECT_GATEWAY(CollectRequest(channel="not.registered"))
    assert result.status == "failed"
    assert result.errors[0]["code"] == "collect_effect_not_registered"


def test_FAILURE_PRESERVED__compat_projector_missing_fails_closed() -> None:
    from app.services.collect_runtime import runtime
    from app.composition.collect_runtime import configure_default_collect_adapters
    from app.services.collect_runtime.contracts import CollectResult

    configure_default_collect_adapters(force=True)
    original = runtime._SOURCE_LIBRARY_COMPAT_PROJECTOR
    original_runner = runtime._run_collect_no_batch
    runtime._SOURCE_LIBRARY_COMPAT_PROJECTOR = None
    try:
        runtime._run_collect_no_batch = lambda _request: CollectResult(channel="source_library")
        with pytest.raises(RuntimeError, match="compatibility projector is not configured"):
            runtime.run_source_library_item_compat(item_key="item")
    finally:
        runtime._SOURCE_LIBRARY_COMPAT_PROJECTOR = original
        runtime._run_collect_no_batch = original_runner

        configure_default_collect_adapters(force=True)
