from __future__ import annotations

from typing import Any, Dict, List

from ....services.ingest.adapters import (
    CaliforniaLotteryMarketAdapter,
    CaliforniaMegaMillionsAdapter,
    CaliforniaPowerballAdapter,
    MarketAdapter,
    NewYorkLotteryMarketAdapter,
    TexasLotteryMarketAdapter,
)
from ..domain.market import ADAPTERS, CA_GAME_MAP, resolve_source_hint_adapter


def resolve_market_adapters(
    state: str,
    source_hint: str | None = None,
    inject_params: Dict[str, Any] | None = None,
) -> List[MarketAdapter]:
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
            gkey = game.strip().upper()
            factory = CA_GAME_MAP.get(gkey)
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
