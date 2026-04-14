"""Lottery stats ingest - fixed source collection for CA/NY/TX lottery data."""
from __future__ import annotations

from ....services.ingest.market import ingest_market_data


def ingest_lottery_stats(
    state: str,
    source_hint: str | None = None,
    limit: int | None = None,
    game: str | None = None,
) -> dict:
    """
    Ingest lottery draw/sales stats from state lottery sites.
    Lottery-specific fixed sources (CA, NY, TX).
    """
    inject = {"game": game} if game else None
    return ingest_market_data(
        state=state,
        source_hint=source_hint,
        limit=limit,
        inject_params=inject,
    )
