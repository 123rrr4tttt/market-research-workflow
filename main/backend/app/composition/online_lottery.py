"""Composition root for online-lottery market adapters."""

from __future__ import annotations

from typing import Any, Callable

from app.services.ingest.adapters.market_base import MarketAdapter
from app.services.ingest.adapters.market_ca_lottery import CaliforniaLotteryMarketAdapter
from app.services.ingest.adapters.market_ca_mega import CaliforniaMegaMillionsAdapter
from app.services.ingest.adapters.market_ca_powerball import CaliforniaPowerballAdapter
from app.services.ingest.adapters.market_ny_lottery import NewYorkLotteryMarketAdapter
from app.services.ingest.adapters.market_tx_lottery import TexasLotteryMarketAdapter
from app.services.ingest.adapters.lotterydata_api import LotteryDataCaliforniaAdapter
from app.services.ingest.adapters.magayo_api import MagayoCaliforniaAdapter
from app.services.ingest.provider_ports import MarketAdapterPort

MarketAdapterFactory = Callable[[str], MarketAdapter]


ADAPTERS: dict[str, MarketAdapterFactory] = {
    "CA": CaliforniaLotteryMarketAdapter,
    "NY": NewYorkLotteryMarketAdapter,
    "TX": TexasLotteryMarketAdapter,
}

CA_GAME_MAP: dict[str, MarketAdapterFactory] = {
    "SUPERLOTTO PLUS": CaliforniaLotteryMarketAdapter,
    "POWERBALL": CaliforniaPowerballAdapter,
    "MEGA MILLIONS": CaliforniaMegaMillionsAdapter,
}


def resolve_source_hint_adapter(hint: str, state_key: str) -> list[MarketAdapterPort] | None:
    if hint in {"magayo", "magayo_api"}:
        if state_key != "CA":
            raise ValueError("Magayo adapter supports CA only")
        return [MagayoCaliforniaAdapter(state_key)]
    if hint in {"lotterydata", "lotterydata_io"}:
        if state_key != "CA":
            raise ValueError("LotteryData adapter supports CA only")
        return [LotteryDataCaliforniaAdapter(state_key)]
    return None


def resolve_market_adapters(
    state: str,
    source_hint: str | None = None,
    inject_params: dict[str, Any] | None = None,
) -> list[MarketAdapterPort]:
    """Resolve market adapters. game (lottery-specific) comes from inject_params."""
    state_key = state.upper()
    hint = (source_hint or "").lower()
    params = inject_params or {}
    game = params.get("game")

    hinted = resolve_source_hint_adapter(hint, state_key)
    if hinted is not None:
        return hinted

    if state_key == "CA":
        if game:
            game_key = game.strip().upper()
            factory = CA_GAME_MAP.get(game_key)
            if not factory:
                raise ValueError(f"unsupported CA game: {game}")
            return [factory("CA")]
        return [
            CaliforniaLotteryMarketAdapter("CA"),
            CaliforniaPowerballAdapter("CA"),
            CaliforniaMegaMillionsAdapter("CA"),
        ]

    if hint == "ny_lottery":
        return [NewYorkLotteryMarketAdapter("NY")]
    if hint == "tx_lottery":
        return [TexasLotteryMarketAdapter("TX")]

    factory = ADAPTERS.get(state_key)
    if not factory:
        raise ValueError(f"market adapter not found for state: {state_key}")
    return [factory(state_key)]


__all__ = [
    "ADAPTERS",
    "CA_GAME_MAP",
    "resolve_market_adapters",
    "resolve_source_hint_adapter",
]
