from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import MarketStat
from .adapters import MarketAdapter, MarketRecord
from ..job_logger import start_job, complete_job, fail_job
from ...subprojects.online_lottery.services.market import resolve_market_adapters


def get_market_adapters(
    state: str,
    source_hint: str | None = None,
    inject_params: Dict[str, Any] | None = None,
) -> List[MarketAdapter]:
    """Resolve adapters via subproject. inject_params is for project-specific overrides (e.g. game for lottery)."""
    return resolve_market_adapters(state=state, source_hint=source_hint, inject_params=inject_params or {})


def ingest_market_data(
    state: str,
    source_hint: str | None = None,
    limit: Optional[int] = None,
    inject_params: Dict[str, Any] | None = None,
) -> dict:
    adapters = get_market_adapters(state, source_hint, inject_params or {})
    records: List[MarketRecord] = []
    for adapter in adapters:
        recs = list(adapter.fetch_records())
        if limit is not None and limit > 0:
            recs = recs[:limit]
        records.extend(recs)

    inserted = 0
    skipped = 0
    updated = 0

    job_id = start_job("ingest_market", {"state": state})

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
                    game=_normalize_game(record.game),
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
    """
    查找现有记录，支持灵活的game字段匹配：
    1. 首先尝试精确匹配（game字段完全一致，忽略大小写）
    2. 如果精确匹配失败且新记录有game，尝试匹配同一天同一州但game为None的记录（用于补充game字段）
    3. 如果新记录的game为None，尝试匹配有game字段的记录（可能来自不同数据源）
    """
    game_normalized = game.strip().upper() if game else None
    
    # 获取同一天同一州的所有记录
    stmt = select(MarketStat).where(
        MarketStat.state == state,
        MarketStat.date == stat_date,
    )
    all_results = session.execute(stmt).scalars().all()
    
    if not all_results:
        return None
    
    # 首先尝试精确匹配（忽略大小写）
    if game_normalized:
        for result in all_results:
            if result.game:
                if result.game.strip().upper() == game_normalized:
                    return result
        
        # 精确匹配失败，尝试匹配game为None的记录（用于补充game字段）
        for result in all_results:
            if result.game is None:
                return result
    else:
        # 新记录的game为None，尝试匹配有game字段的记录（可能数据更完整）
        # 优先返回有更多数据的记录
        for result in all_results:
            if result.game is not None:
                if result.revenue is not None or result.sales_volume is not None:
                    return result
        
        # 如果没有找到有数据的记录，返回第一个有game字段的记录
        for result in all_results:
            if result.game is not None:
                return result
        
        # 如果都没有game字段，返回第一个（两者都是None）
        if all_results:
            return all_results[0]
    
    return None


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


def _normalize_game(game: Optional[str]) -> Optional[str]:
    """规范化game字段：去除空格并转换为标准格式"""
    if not game:
        return None
    # 保持原始格式，但去除首尾空格
    return game.strip() if game.strip() else None


def _update_existing(entry: MarketStat, record: MarketRecord) -> bool:
    """
    更新现有记录，补充缺失的字段
    优先使用新记录中非None的值来补充旧记录中None的字段
    """
    changed = False

    # 补充缺失的数值字段
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

    # 更新元数据字段
    if record.source_name and entry.source_name != record.source_name:
        entry.source_name = record.source_name
        changed = True
    if record.uri and entry.source_uri != record.uri:
        entry.source_uri = record.uri
        changed = True
    
    # 更新game字段：如果新记录有game而旧记录没有，或者game不一致，则更新
    record_game_normalized = _normalize_game(record.game)
    entry_game_normalized = _normalize_game(entry.game)
    
    if record_game_normalized:
        if not entry_game_normalized:
            # 新记录有game，旧记录没有，补充game字段
            entry.game = record_game_normalized
            changed = True
        elif entry_game_normalized.upper() != record_game_normalized.upper():
            # game字段不一致，使用新记录的game（可能更准确）
            entry.game = record_game_normalized
            changed = True
    
    if record.draw_number and entry.draw_number != record.draw_number:
        entry.draw_number = record.draw_number
        changed = True
    if record.extra and entry.extra != record.extra:
        entry.extra = record.extra
        changed = True

    return changed


