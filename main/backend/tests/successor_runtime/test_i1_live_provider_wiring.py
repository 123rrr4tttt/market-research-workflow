"""I1 assembly wiring for the bounded C2.3/C6.2 live provider ports."""

from __future__ import annotations

from typing import Any

import pytest

from app.successor_runtime.assembly.base import local_assembly_scope_digest
from app.successor_runtime.assembly.c2_assembly import build_c2_assembly
from app.successor_runtime.assembly.c6_assembly import (
    build_c6_assembly,
    build_openai_live_fixture_options,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2_live_model_port as c6_2_live,
)
from app.successor_runtime.capabilities import (
    source_library_c2_3_live_provider as c23_live,
)

pytestmark = pytest.mark.unit

_TEST_KEY = "test-key-not-a-real-credential"


def _uow_factory() -> Any:
    return lambda: None


def _scope_digest() -> str:
    return local_assembly_scope_digest()


def test_c2_assembly_wires_explicit_live_gateway_without_calling_it() -> None:
    calls: list[tuple[Any, ...]] = []

    def transport(*args: Any) -> tuple[int, dict[str, Any]]:
        calls.append(args)
        return 200, {"organic": []}

    gateway = c23_live.build_serper_live_gateway(
        api_key_provider=lambda: _TEST_KEY,
        transport=transport,
    )
    assert gateway is not None
    assembly = build_c2_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
        provider_gateway=gateway,
    )
    cell = assembly.cell("C2.3")
    assert cell.status == "INSTALLED"
    assert "LIVE_PROVIDER_DIMENSION_RESOLVED_SERPER" in cell.note
    assert assembly.handlers[2].gateway is gateway
    assert calls == []
    assert gateway.provider_calls == []


def test_c2_assembly_default_without_env_key_stays_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assembly = build_c2_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
    )
    cell = assembly.cell("C2.3")
    assert cell.status == "INSTALLED"
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in cell.note


def test_c6_assembly_wires_live_openai_port_without_calling_it() -> None:
    calls: list[tuple[Any, ...]] = []

    def transport(*args: Any) -> tuple[int, dict[str, Any]]:
        calls.append(args)
        return 200, {"choices": []}

    options = build_openai_live_fixture_options(
        api_key_provider=lambda: _TEST_KEY,
        transport=transport,
        model="fixture-model",
        base_url="https://fixture.example/v1",
    )
    assert options is not None
    assert isinstance(options.provider_port, c6_2_live.OpenAILiveProviderPort)
    assembly = build_c6_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
        options=options,
    )
    assert assembly.coverage() == {
        "C6.1": "INSTALLED",
        "C6.2": "INSTALLED",
        "C6.3": "INSTALLED",
    }
    cell = assembly.cell("C6.2")
    assert "LIVE_PROVIDER_DIMENSION_RESOLVED_OPENAI" in cell.note
    assert calls == []
    assert options.provider_port.provider_calls == 0


def test_c6_live_options_helper_returns_none_without_key() -> None:
    options = build_openai_live_fixture_options(api_key_provider=lambda: None)
    assert options is None


def test_c6_assembly_auto_env_closure_wires_live_without_calling_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _TEST_KEY)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assembly = build_c6_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
    )
    coverage = assembly.coverage()
    assert coverage["C6.2"] == "INSTALLED"
    assert coverage["C6.1"] == "FIXTURE_CLOSURE_REQUIRED"
    assert coverage["C6.3"] == "FIXTURE_CLOSURE_REQUIRED"
    assert "LIVE_PROVIDER_DIMENSION_RESOLVED_OPENAI" in assembly.cell("C6.2").note
    assert len(assembly.handlers) == 1
