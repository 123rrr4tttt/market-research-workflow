from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.composition.ingest import configure_ingest_adapters
from app.composition.online_lottery import (
    ADAPTERS,
    CA_GAME_MAP,
    resolve_market_adapters,
    resolve_source_hint_adapter,
)
from app.services.ingest import provider_ports
from app.services.ingest.adapters.lotterydata_api import LotteryDataCaliforniaAdapter
from app.services.ingest.adapters.magayo_api import MagayoCaliforniaAdapter
from app.services.ingest.adapters.market_ca_lottery import CaliforniaLotteryMarketAdapter
from app.services.ingest.adapters.market_ca_mega import CaliforniaMegaMillionsAdapter
from app.services.ingest.adapters.market_ca_powerball import CaliforniaPowerballAdapter
from app.services.ingest.adapters.market_ny_lottery import NewYorkLotteryMarketAdapter
from app.services.ingest.adapters.market_tx_lottery import TexasLotteryMarketAdapter


@pytest.fixture
def configured_market_provider():
    original = provider_ports._MARKET_ADAPTER_RESOLVER
    configure_ingest_adapters()
    try:
        yield
    finally:
        provider_ports._MARKET_ADAPTER_RESOLVER = original


def test_INVARIANT__ca_default_order_is_stable() -> None:
    adapters = resolve_market_adapters("ca")

    assert [type(adapter) for adapter in adapters] == [
        CaliforniaLotteryMarketAdapter,
        CaliforniaPowerballAdapter,
        CaliforniaMegaMillionsAdapter,
    ]
    assert [adapter.state for adapter in adapters] == ["CA", "CA", "CA"]


def test_INVARIANT__ca_game_map_owns_exact_and_normalized_lookup() -> None:
    assert CA_GAME_MAP.keys() == {"SUPERLOTTO PLUS", "POWERBALL", "MEGA MILLIONS"}
    assert isinstance(CA_GAME_MAP["SUPERLOTTO PLUS"]("CA"), CaliforniaLotteryMarketAdapter)

    adapters = resolve_market_adapters("CA", inject_params={"game": " powerball "})
    assert type(adapters[0]) is CaliforniaPowerballAdapter


def test_INVARIANT__provider_hints_select_ca_only_factories() -> None:
    for alias in ("magayo", "magayo_api"):
        adapters = resolve_source_hint_adapter(alias, "CA")
        assert adapters is not None
        assert type(adapters[0]) is MagayoCaliforniaAdapter

    for alias in ("lotterydata", "lotterydata_io"):
        adapters = resolve_source_hint_adapter(alias, "CA")
        assert adapters is not None
        assert type(adapters[0]) is LotteryDataCaliforniaAdapter

    with pytest.raises(ValueError, match="Magayo adapter supports CA only"):
        resolve_source_hint_adapter("magayo", "NY")
    with pytest.raises(ValueError, match="LotteryData adapter supports CA only"):
        resolve_source_hint_adapter("lotterydata", "NY")


def test_INVARIANT__ny_and_tx_state_routes_are_preserved() -> None:
    assert type(resolve_market_adapters("NY")[0]) is NewYorkLotteryMarketAdapter
    assert type(resolve_market_adapters("ny", "ny_lottery")[0]) is NewYorkLotteryMarketAdapter
    assert type(resolve_market_adapters("TX")[0]) is TexasLotteryMarketAdapter
    assert type(resolve_market_adapters("tx", "tx_lottery")[0]) is TexasLotteryMarketAdapter


def test_FAILURE_PRESERVED__unsupported_state_and_game_fail_with_exact_messages() -> None:
    with pytest.raises(ValueError, match="unsupported CA game: KENO"):
        resolve_market_adapters("CA", inject_params={"game": "KENO"})
    with pytest.raises(ValueError, match="market adapter not found for state: ZZ"):
        resolve_market_adapters("zz")


def test_INVARIANT__service_uses_installed_market_port(
    configured_market_provider: None,
) -> None:
    service = importlib.import_module("app.subprojects.online_lottery.services.market")

    adapters = service.resolve_market_adapters("CA", inject_params={"game": "Mega Millions"})

    assert type(adapters[0]) is CaliforniaMegaMillionsAdapter


def test_INVARIANT__shell_does_not_reexport_concrete_market_composition() -> None:
    shell = importlib.import_module("app.subprojects.online_lottery")

    assert not hasattr(shell, "ADAPTERS")
    assert not hasattr(shell, "CA_GAME_MAP")
    assert not hasattr(shell, "resolve_market_adapters")


def test_INVARIANT__domain_and_service_do_not_import_concrete_adapters() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    domain_source = (
        app_root / "subprojects/online_lottery/domain/market.py"
    ).read_text(encoding="utf-8")
    service_source = (
        app_root / "subprojects/online_lottery/services/market.py"
    ).read_text(encoding="utf-8")

    assert "services.ingest.adapters" not in domain_source
    assert "services.ingest.adapters" not in service_source
    assert "provider_ports" in domain_source
    assert "provider_ports" in service_source
