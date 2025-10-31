from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import MarketStat
from .adapters import (
    CaliforniaLotteryMarketAdapter,
    MarketAdapter,
    MarketRecord,
    NewYorkLotteryMarketAdapter,
    TexasLotteryMarketAdapter,
    CaliforniaPowerballAdapter,
    CaliforniaMegaMillionsAdapter,
    USPowerballAdapter,
    MagayoCaliforniaAdapter,
    LotteryDataCaliforniaAdapter,
)
from ..job_logger import start_job, complete_job, fail_job

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
    "POWERBALL US": USPowerballAdapter,
}

def get_market_adapters(state: str, game: Optional[str] = None, source_hint: str | None = None) -> List[MarketAdapter]:
    state_key = state.upper()
    adapters: List[MarketAdapter] = []
    hint = (source_hint or "").lower()
    if hint in {"magayo", "magayo_api"}:
        if state_key != "CA":
            raise ValueError("Magayo 适配器目前仅支持 CA 州")
        return [MagayoCaliforniaAdapter(state_key)]
    if hint in {"lotterydata", "lotterydata_io"}:
        if state_key != "CA":
            raise ValueError("LotteryData.io 适配器目前仅支持 CA 州")
        return [LotteryDataCaliforniaAdapter(state_key)]

    if state_key == "CA":
        if game:
            gkey = game.strip().upper()
            factory = CA_GAME_MAP.get(gkey)
            if not factory:
                raise ValueError(f"暂不支持的 CA 游戏: {game}")
            adapters.append(factory("CA"))
        else:
            adapters.extend([
                CaliforniaLotteryMarketAdapter("CA"),
                CaliforniaPowerballAdapter("CA"),
                CaliforniaMegaMillionsAdapter("CA"),
                USPowerballAdapter("CA"),
            ])
        return adapters
    if source_hint and source_hint.lower() == "ny_lottery":
        return [NewYorkLotteryMarketAdapter("NY")]
    if source_hint and source_hint.lower() == "tx_lottery":
        return [TexasLotteryMarketAdapter("TX")]
    factory = ADAPTERS.get(state_key)
    if not factory:
        raise ValueError(f"暂无州 {state_key} 的市场适配器")
    return [factory(state_key)]


def ingest_market_data(state: str, source_hint: str | None = None, game: Optional[str] = None, limit: Optional[int] = None) -> dict:
    adapters = get_market_adapters(state, game, source_hint)
    records: List[MarketRecord] = []
    for adapter in adapters:
        recs = list(adapter.fetch_records())
        if limit is not None and limit > 0:
            recs = recs[:limit]
        records.extend(recs)

    inserted = 0
    skipped = 0
    updated = 0

    job_id = start_job("ingest_market", {"state": state, "game": game})

    with SessionLocal() as session:
        try:
            for record in records:
                if record.date is None:
                    skipped += 1
                    continue

                existing = _get_existing(session, record.state, record.game, record.date)
                if existing:
                    if _update_existing(existing, record):
                        updated += 1
                    else:
                        skipped += 1
                    continue

                mom, yoy = _calculate_growth(session, record)

                db_entry = MarketStat(
                    state=record.state,
                    game=(record.game or None),
                    date=record.date,
                    sales_volume=_decimal_or_none(record.sales_volume),
                    revenue=_decimal_or_none(record.revenue),
                    jackpot=_decimal_or_none(record.jackpot),
                    ticket_price=_decimal_or_none(record.ticket_price),
                    draw_number=record.draw_number,
                    yoy=_decimal_or_none(yoy),
                    mom=_decimal_or_none(mom),
                    source_name=record.source_name,
                    source_uri=record.uri,
                    extra=record.extra,
                )
                session.add(db_entry)
                inserted += 1

            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            fail_job(job_id, str(exc))
            raise

    result = {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "state": state.upper(),
    }
    complete_job(job_id, result=result)
    return result


def _get_existing(session: Session, state: str, game: Optional[str], stat_date) -> MarketStat | None:
    stmt = select(MarketStat).where(
        MarketStat.state == state,
        MarketStat.game == (game or None),
        MarketStat.date == stat_date,
    )
    return session.execute(stmt).scalars().one_or_none()


def _calculate_growth(session: Session, record: MarketRecord) -> tuple[float | None, float | None]:
    # Query previous record (by date desc) for same state
    prev = (
        session.query(MarketStat)
        .filter(
            MarketStat.state == record.state,
            MarketStat.game == (record.game or None),
            MarketStat.date < record.date,
        )
        .order_by(MarketStat.date.desc())
        .first()
    )
    mom = None
    yoy = None

    if prev and prev.revenue and record.revenue:
        try:
            mom = float((record.revenue - float(prev.revenue)) / float(prev.revenue))
        except ZeroDivisionError:
            mom = None

    # Year-over-year vs same date previous year
    prev_year = (
        session.query(MarketStat)
        .filter(
            MarketStat.state == record.state,
            MarketStat.game == (record.game or None),
            MarketStat.date == record.date.replace(year=record.date.year - 1),
        )
        .one_or_none()
    )
    if prev_year and prev_year.revenue and record.revenue:
        try:
            yoy = float((record.revenue - float(prev_year.revenue)) / float(prev_year.revenue))
        except ZeroDivisionError:
            yoy = None

    return mom, yoy


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _update_existing(entry: MarketStat, record: MarketRecord) -> bool:
    changed = False

    if record.sales_volume is not None and entry.sales_volume is None:
        entry.sales_volume = _decimal_or_none(record.sales_volume)
        changed = True
    if record.revenue is not None and entry.revenue is None:
        entry.revenue = _decimal_or_none(record.revenue)
        changed = True
    if record.jackpot is not None and entry.jackpot is None:
        entry.jackpot = _decimal_or_none(record.jackpot)
        changed = True
    if record.ticket_price is not None and entry.ticket_price is None:
        entry.ticket_price = _decimal_or_none(record.ticket_price)
        changed = True

    if record.source_name and entry.source_name != record.source_name:
        entry.source_name = record.source_name
        changed = True
    if record.uri and entry.source_uri != record.uri:
        entry.source_uri = record.uri
        changed = True
    if record.game and entry.game != record.game:
        entry.game = record.game
        changed = True
    if record.draw_number and entry.draw_number != record.draw_number:
        entry.draw_number = record.draw_number
        changed = True
    if record.extra and entry.extra != record.extra:
        entry.extra = record.extra
        changed = True

    return changed


