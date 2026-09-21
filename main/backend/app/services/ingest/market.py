from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal
import logging
from dataclasses import dataclass
from typing import Any, NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import MarketStat
from functorial_kit import Failure
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities.checksum import content_digest
from mrw_functorial_kit.core.provider_port_failures import ingest_market_failures
from .provider_ports import MarketRecord, get_market_adapters
from ..job_logger import start_job, complete_job, fail_job
from ..extraction.numeric import normalize_market_payload


logger = logging.getLogger(__name__)


_MARKET_MATERIALIZATION_SCHEMA = "mrw.successor.ingest.market.materialization.v1"
_MARKET_DEFAULT_RECORD_LIMIT = c3.COLLECT_FOLD_RESOURCE_CEILING.max_outcomes


@dataclass(frozen=True, slots=True)
class MarketNonAuthoritativeObservation:
    """C3 observation wrapper that cannot claim provider terminality."""

    schema_version: str
    observation: c3.CollectTraversalObservation
    kind: str = "outcome_unknown"

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "observation": self.observation.to_plain(),
        }


def _market_request_ref(state: str) -> c3.CollectRequestRef:
    normalized_state = str(state).strip().upper()
    return c3.build_collect_request_ref(
        request_id=f"market-materialize:{normalized_state}",
        project_key=f"market:{normalized_state}",
        channel="search.market",
    )


def _market_record_payload(record: MarketRecord, *, state: str) -> dict[str, Any]:
    raw_extra = getattr(record, "extra", None)
    if isinstance(raw_extra, dict):
        # Materialization metadata is a derived projection and must not alter
        # the content digest on replay.
        raw_extra = {
            key: value
            for key, value in raw_extra.items()
            if key not in {"replay_identity", "materialization"}
        }
        if not raw_extra:
            raw_extra = None
    return {
        "state": str(getattr(record, "state", None) or state),
        "game": getattr(record, "game", None),
        "date": (
            getattr(record, "date", None).isoformat()
            if getattr(record, "date", None) is not None
            else None
        ),
        "sales_volume": getattr(record, "sales_volume", None),
        "revenue": getattr(record, "revenue", None),
        "jackpot": getattr(record, "jackpot", None),
        "ticket_price": getattr(record, "ticket_price", None),
        "source_name": getattr(record, "source_name", None),
        "uri": getattr(record, "uri", None),
        "draw_number": getattr(record, "draw_number", None),
        "extra": raw_extra,
    }


def _market_record_replay_identity(
    record: MarketRecord, *, state: str, adapter_index: int
) -> tuple[str, str]:
    raw_digest = content_digest(_market_record_payload(record, state=state))
    existing_extra = getattr(record, "extra", None)
    explicit = existing_extra.get("replay_identity") if isinstance(existing_extra, dict) else None
    if isinstance(explicit, str) and explicit:
        replay_identity = (
            explicit
            if len(explicit) == 64 and all(ch in "0123456789abcdef" for ch in explicit)
            else content_digest({"schema": _MARKET_MATERIALIZATION_SCHEMA, "explicit": explicit})
        )
    else:
        replay_identity = content_digest(
            {
                "schema": _MARKET_MATERIALIZATION_SCHEMA,
                "state": str(state).strip().upper(),
                "adapter_index": adapter_index,
                "raw_digest": raw_digest,
            }
        )
    return replay_identity, raw_digest


def _market_receipt(
    *,
    state: str,
    adapter_index: int,
    input_index: int,
    replay_identity: str,
    raw_digest: str,
    status: str,
) -> c3.CollectAttemptReceipt:
    return c3.CollectAttemptReceipt(
        schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        # A synchronous iterable yield is only a local observation.  Without
        # an adapter-owned gateway/readback we must not claim provider
        # terminality or authoritative completion.
        receipt_kind="DISPATCH_ACKNOWLEDGEMENT",
        provider_type="market.adapter",
        provider_job_id=(
            f"market:{str(state).strip().upper()}:adapter:{adapter_index}:"
            f"record:{input_index}:{replay_identity}"
        ),
        provider_status=status,
        attempt_count=1,
        observed_at="1970-01-01T00:00:00Z",
        raw_digest=raw_digest,
        authoritative_readback=False,
        receipt_digest="",
    )


def _market_failed_outcome(
    *,
    state: str,
    adapter_index: int,
    input_index: int,
    message: str,
    exception_type: str,
    raw_digest: str | None = None,
) -> c3.CollectElementFailed:
    error = c3.CollectElementError(
        code="auto_batch_execution_failed",
        message=message or exception_type,
        query_terms=(str(state).strip().upper(),),
        exception_type=exception_type,
        error_digest="",
    )
    digest = raw_digest or content_digest(
        {
            "schema": _MARKET_MATERIALIZATION_SCHEMA,
            "state": str(state).strip().upper(),
            "adapter_index": adapter_index,
            "input_index": input_index,
            "error_digest": error.error_digest,
        }
    )
    replay_identity = content_digest(
        {
            "schema": _MARKET_MATERIALIZATION_SCHEMA,
            "state": str(state).strip().upper(),
            "adapter_index": adapter_index,
            "raw_digest": digest,
        }
    )
    receipt = _market_receipt(
        state=state,
        adapter_index=adapter_index,
        input_index=input_index,
        replay_identity=replay_identity,
        raw_digest=digest,
        status="failed",
    )
    return c3.CollectElementFailed(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=(
            f"market:{str(state).strip().upper()}:adapter:{adapter_index}:"
            f"record:{input_index}"
        ),
        input_index=input_index,
        error=error,
        receipt=receipt,
        legacy_observation_ref="legacy:" + error.error_digest,
        outcome_digest="",
    )


def _market_materialization_result(
    *,
    state: str,
    outcomes: list[c3.CollectElementOutcome],
    cancellation: c3.CollectCancellationReceipt | None = None,
) -> c3.CollectTraversalResult | MarketNonAuthoritativeObservation:
    request_ref = _market_request_ref(state)
    if cancellation is not None:
        cause = c3.CollectElementError(
            code="auto_batch_execution_failed",
            message=cancellation.message,
            query_terms=(str(state).strip().upper(),),
            exception_type="CancellationRequested",
            error_digest="",
        )
        return c3.OrderedTraversalAborted(
            schema_version="mrw.successor.collect.c3.traversal-result.v1",
            partial_outcomes=tuple(outcomes),
            cause=cause,
            cancellation_receipt=cancellation,
            cancellation_observed=True,
            request_ref=request_ref,
        )
    observation = c3.CollectTraversalObservation(
        schema_version=c3.COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
        observation_profile=c3.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        request_ref=request_ref,
        traversal_policy="MATERIALIZED_SHAPE",
        failure_policy="ACCUMULATE",
        ordered_outcomes=tuple(outcomes),
        requested_parallelism=1,
        effective_parallelism=1,
        cancellation_observed=False,
        observation_digest="",
    )
    return MarketNonAuthoritativeObservation(
        schema_version="mrw.successor.collect.c3.traversal-result.v1",
        observation=observation,
    )


def _market_provider_iteration_failure(
    state: str, cause: BaseException
) -> Failure:
    return ingest_market_failures.fail(
        "market_provider_iteration_failed",
        str(cause) or "market provider iteration failed",
        {
            "state": str(state).strip().upper(),
            "cause_message": str(cause),
            "exception_type": type(cause).__name__,
        },
    )


def _raise_invalid_market_failure_lift() -> NoReturn:
    # kit:boundary owner=ingest.market.provider class=PROGRAMMER_DEFECT failure_family=none witness=test:test_latest_ingest_provider_iteration_failure_lifts
    raise TypeError("market provider iteration failure lift context is inconsistent")


def _raise_market_provider_iteration_failure(
    failure: Failure, cause: BaseException
) -> NoReturn:
    if not ingest_market_failures.matches(failure):
        _raise_invalid_market_failure_lift()
    # kit:boundary owner=ingest.market.provider class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.market.failure witness=test:test_latest_ingest_provider_iteration_failure_lifts
    raise cause


def materialize_market_records(
    adapters: Iterable[Any],
    *,
    state: str,
    max_records_per_adapter: int | None = None,
    cancel_check: Callable[[int], bool] | None = None,
    limit: int | None = None,
    iteration_error_sink: list[BaseException] | None = None,
) -> tuple[list[MarketRecord], c3.CollectTraversalResult | MarketNonAuthoritativeObservation]:
    """Materialize market adapter iterables into ordered C3 outcomes.

    Each adapter is consumed serially and bounded independently.  Every record
    (including an iteration failure) receives a deterministic attempt/readback
    receipt and replay identity.  Legacy callers receive only the materialized
    records; the typed traversal remains the canonical observation.
    """
    # Legacy ``limit`` treats non-positive values as unbounded; retain that
    # public behavior while enforcing the C3 resource ceiling.
    if limit is not None:
        max_records_per_adapter = limit
    bound = (
        _MARKET_DEFAULT_RECORD_LIMIT
        if max_records_per_adapter is None or int(max_records_per_adapter) <= 0
        else int(max_records_per_adapter)
    )
    normalized_state = str(state).strip().upper()
    records: list[MarketRecord] = []
    outcomes: list[c3.CollectElementOutcome] = []
    input_index = 0

    for adapter_index, adapter in enumerate(adapters):
        if cancel_check is not None and bool(cancel_check(input_index)):
            cancellation = c3.CollectCancellationReceipt(
                schema_version=c3.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
                code="FAIL_FAST_CANCELLED",
                message="market materialization cancelled",
                trigger_input_index=input_index,
                observed="SERIAL_EXECUTION",
                receipt_digest="",
            )
            return records, _market_materialization_result(
                state=normalized_state,
                outcomes=outcomes,
                cancellation=cancellation,
            )
        try:
            iterator = iter(adapter.fetch_records())
        except Exception as exc:  # noqa: BLE001 - provider boundary
            if iteration_error_sink is not None:
                iteration_error_sink.append(exc)
            outcomes.append(
                _market_failed_outcome(
                    state=normalized_state,
                    adapter_index=adapter_index,
                    input_index=input_index,
                    message=str(exc),
                    exception_type=exc.__class__.__name__,
                )
            )
            input_index += 1
            continue

        record_count = 0
        while record_count < bound:
            if cancel_check is not None and bool(cancel_check(input_index)):
                cancellation = c3.CollectCancellationReceipt(
                    schema_version=c3.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
                    code="FAIL_FAST_CANCELLED",
                    message="market materialization cancelled",
                    trigger_input_index=input_index,
                    observed="SERIAL_EXECUTION",
                    receipt_digest="",
                )
                close = getattr(iterator, "close", None)
                if callable(close):
                    close()
                return records, _market_materialization_result(
                    state=normalized_state,
                    outcomes=outcomes,
                    cancellation=cancellation,
                )
            try:
                record = next(iterator)
            except StopIteration:
                break
            except Exception as exc:  # noqa: BLE001 - provider boundary
                if iteration_error_sink is not None:
                    iteration_error_sink.append(exc)
                outcomes.append(
                    _market_failed_outcome(
                        state=normalized_state,
                        adapter_index=adapter_index,
                        input_index=input_index,
                        message=str(exc),
                        exception_type=exc.__class__.__name__,
                    )
                )
                input_index += 1
                break

            if not isinstance(record, MarketRecord):
                outcomes.append(
                    _market_failed_outcome(
                        state=normalized_state,
                        adapter_index=adapter_index,
                        input_index=input_index,
                        message="market provider yielded an invalid record",
                        exception_type="TypeError",
                    )
                )
                input_index += 1
                record_count += 1
                continue

            replay_identity, raw_digest = _market_record_replay_identity(
                record, state=normalized_state, adapter_index=adapter_index
            )
            extra = dict(record.extra) if isinstance(record.extra, dict) else {}
            extra.setdefault("replay_identity", replay_identity)
            extra.setdefault(
                "materialization",
                {
                    "schema": _MARKET_MATERIALIZATION_SCHEMA,
                    "adapter_index": adapter_index,
                    "input_index": input_index,
                    "raw_digest": raw_digest,
                    "readback_status": "NON_AUTHORITATIVE_LOCAL_ITERATION",
                },
            )
            record.extra = extra
            receipt = _market_receipt(
                state=normalized_state,
                adapter_index=adapter_index,
                input_index=input_index,
                replay_identity=replay_identity,
                raw_digest=raw_digest,
                status="materialized",
            )
            outcomes.append(
                c3.CollectElementSucceeded(
                    schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                    element_id=(
                        f"market:{normalized_state}:adapter:{adapter_index}:"
                        f"record:{input_index}"
                    ),
                    input_index=input_index,
                    counts=c3.CollectCounts(),
                    links=((str(record.uri).strip(),) if record.uri else ()),
                    receipt=receipt,
                    legacy_observation_ref="legacy:" + replay_identity,
                    outcome_digest="",
                )
            )
            records.append(record)
            input_index += 1
            record_count += 1

        close = getattr(iterator, "close", None)
        if callable(close):
            close()

    return records, _market_materialization_result(
        state=normalized_state, outcomes=outcomes
    )


def ingest_market_data(
    state: str,
    source_hint: str | None = None,
    limit: int | None = None,
    inject_params: dict[str, Any] | None = None,
    *,
    cancel_check: Callable[[int], bool] | None = None,
) -> dict:
    adapters = get_market_adapters(state, source_hint, inject_params or {})
    iteration_errors: list[BaseException] = []
    records, materialization = materialize_market_records(
        adapters,
        state=state,
        max_records_per_adapter=limit,
        cancel_check=cancel_check,
        iteration_error_sink=iteration_errors,
    )
    # Preserve the legacy provider ABI: adapter iteration failures happen
    # before job creation and are re-raised unchanged.  The materializer still
    # exposes the typed partial failure to callers that use it directly.
    if iteration_errors:
        _raise_market_provider_iteration_failure(
            _market_provider_iteration_failure(state, iteration_errors[0]),
            iteration_errors[0],
        )

    inserted = 0
    skipped = 0
    updated = 0
    seen_replay_ids: set[str] = set()

    job_id = start_job("ingest_market", {"state": state})

    with SessionLocal() as session:
        try:
            for record in records:
                replay_identity = (
                    record.extra.get("replay_identity")
                    if isinstance(record.extra, dict)
                    else None
                )
                if isinstance(replay_identity, str) and replay_identity:
                    if replay_identity in seen_replay_ids:
                        skipped += 1
                        continue
                    seen_replay_ids.add(replay_identity)
                    persisted_replay = _get_existing_by_replay_identity(
                        session, replay_identity
                    )
                    if persisted_replay is not None:
                        skipped += 1
                        continue
                if record.date is None:
                    skipped += 1
                    continue

                record, _ = _normalize_market_record(record)
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
            # kit:boundary owner=ingest.market.persistence class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.market.failure witness=test:test_ingest_service_a_failure_lifts
            raise

    result = {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "state": state.upper(),
        # Compatibility projection: typed C3 materialization remains the
        # canonical observation and is exposed only as a readback summary.
        "materialization": {
            "status": (
                "CANCELLED"
                if isinstance(materialization, c3.OrderedTraversalAborted)
                else "OBSERVED_NON_AUTHORITATIVE"
            ),
            "readback_status": "NON_AUTHORITATIVE_LOCAL_ITERATION",
            "outcome_count": len(
                getattr(getattr(materialization, "observation", None), "ordered_outcomes", ())
                or getattr(materialization, "partial_outcomes", ())
                or ()
            ),
            "sequence_digest": content_digest(
                {
                    "schema": "mrw.successor.collect.c3.outcome-sequence.v1",
                    "request_ref": _market_request_ref(state).to_plain(),
                    "outcomes": [
                        outcome.to_plain()
                        for outcome in (
                            getattr(getattr(materialization, "observation", None), "ordered_outcomes", ())
                            or getattr(materialization, "partial_outcomes", ())
                            or ()
                        )
                    ],
                }
            ),
            "replay_identity": _market_request_ref(state).request_digest,
            "cancellation": (
                materialization.cancellation_receipt.to_plain()
                if isinstance(materialization, c3.OrderedTraversalAborted)
                and materialization.cancellation_receipt is not None
                else None
            ),
        },
    }
    complete_job(job_id, result=result)
    return result


def _get_existing(session: Session, state: str, game: str | None, stat_date) -> MarketStat | None:
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


def _get_existing_by_replay_identity(
    session: Session, replay_identity: str
) -> MarketStat | None:
    """Best-effort idempotence lookup over the compatibility JSON projection."""
    if not replay_identity:
        return None
    try:
        return (
            session.query(MarketStat)
            .filter(MarketStat.extra.contains({"replay_identity": replay_identity}))
            .first()
        )
    except Exception:  # noqa: BLE001 - legacy stores may not support JSON lookup
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

    # Return growth as percentage value, e.g. 10.5 = 10.5%
    # to keep consistency with extraction schema and dashboard display conventions.
    if prev and prev.revenue and record.revenue:
        try:
            mom = float((record.revenue - float(prev.revenue)) / float(prev.revenue) * 100)
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
            yoy = float((record.revenue - float(prev_year.revenue)) / float(prev_year.revenue) * 100)
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


def _normalize_market_record(record: MarketRecord) -> tuple[MarketRecord, dict]:
    """Normalize market numeric fields in each record before persistence."""
    raw_market = {
        "sales_volume": record.sales_volume,
        "revenue": record.revenue,
        "jackpot": record.jackpot,
        "ticket_price": record.ticket_price,
        "yoy_change": None,
        "mom_change": None,
    }
    try:
        normalized_market, quality = normalize_market_payload(raw_market, scope="lottery.market")
    except Exception as e:
        logger.warning("ingest_market_data: market normalization failed, fallback raw: %s", e)
        normalized_market = raw_market
        quality = {
            "scope": "project.lottery.market",
            "data_class": "project_extension",
            "parsed_fields": {},
            "issues": ["normalize_failed"],
            "quality_score": 0.0,
        }

    record.sales_volume = normalized_market.get("sales_volume")
    record.revenue = normalized_market.get("revenue")
    record.jackpot = normalized_market.get("jackpot")
    record.ticket_price = normalized_market.get("ticket_price")

    quality["source"] = "ingest_market_normalize"
    merged_quality = dict(quality)
    if isinstance(record.extra, dict):
        existing_extra = dict(record.extra)
    else:
        existing_extra = {}
    if isinstance(existing_extra.get("numeric_quality"), dict):
        existing_extra["numeric_quality"] = {
            "source": existing_extra["numeric_quality"],
            "ingest": merged_quality,
        }
    else:
        existing_extra["numeric_quality"] = merged_quality
    record.extra = existing_extra
    return record, merged_quality


def _normalize_game(game: str | None) -> str | None:
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
