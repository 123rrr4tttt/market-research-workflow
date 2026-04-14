from __future__ import annotations

from typing import Callable, Dict

from ....services.ingest.adapters import (
    CaliforniaLotteryMarketAdapter,
    CaliforniaMegaMillionsAdapter,
    CaliforniaPowerballAdapter,
    LotteryDataCaliforniaAdapter,
    MagayoCaliforniaAdapter,
    MarketAdapter,
    NewYorkLotteryMarketAdapter,
    TexasLotteryMarketAdapter,
)

AdapterFactory = Callable[[str], MarketAdapter]

ADAPTERS: Dict[str, AdapterFactory] = {
    "CA": CaliforniaLotteryMarketAdapter,
    "NY": NewYorkLotteryMarketAdapter,
    "TX": TexasLotteryMarketAdapter,
}

CA_GAME_MAP: Dict[str, AdapterFactory] = {
    "SUPERLOTTO PLUS": CaliforniaLotteryMarketAdapter,
    "POWERBALL": CaliforniaPowerballAdapter,
    "MEGA MILLIONS": CaliforniaMegaMillionsAdapter,
}


def resolve_source_hint_adapter(hint: str, state_key: str) -> list[MarketAdapter] | None:
    if hint in {"magayo", "magayo_api"}:
        if state_key != "CA":
            raise ValueError("Magayo adapter supports CA only")
        return [MagayoCaliforniaAdapter(state_key)]
    if hint in {"lotterydata", "lotterydata_io"}:
        if state_key != "CA":
            raise ValueError("LotteryData adapter supports CA only")
        return [LotteryDataCaliforniaAdapter(state_key)]
    return None
