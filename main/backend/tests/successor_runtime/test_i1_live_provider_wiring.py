"""I1 assembly wiring for the bounded C2.3 live provider port."""

from __future__ import annotations

from typing import Any

import pytest
from app.successor_runtime.assembly.base import local_assembly_scope_digest
from app.successor_runtime.assembly.source_assembly import (
    SOURCE_PROVIDER_ACQUISITION_CELL_ID,
    build_source_assembly,
)
from app.successor_runtime.capabilities import (
    source_provider_worker as c23_live,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    C2_3StoreRehydratedHandler,
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
    assembly = build_source_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
        provider_gateway=gateway,
    )
    cell = assembly.cell(SOURCE_PROVIDER_ACQUISITION_CELL_ID)
    assert cell.status == "INSTALLED"
    assert "LIVE_PROVIDER_DIMENSION_RESOLVED_SERPER" in cell.note
    handler = next(
        item
        for item in assembly.handlers
        if isinstance(item, C2_3StoreRehydratedHandler)
    )
    assert handler.gateway is gateway
    assert calls == []
    assert gateway.provider_calls == []


def test_c2_assembly_default_without_env_key_stays_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assembly = build_source_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=_scope_digest(),
    )
    cell = assembly.cell(SOURCE_PROVIDER_ACQUISITION_CELL_ID)
    assert cell.status == "INSTALLED"
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in cell.note
