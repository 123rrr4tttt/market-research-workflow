from datetime import date

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, DatabaseError
import logging

from ..models.base import SessionLocal
from ..models.entities import MarketStat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


def _decimal_to_float(value):
    if value is None:
        return None
    return float(value)


@router.get("")
def market_stats(
    state: str = Query(..., description="州，如 CA"),
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    game: str | None = Query(None, description="玩法过滤，如 SuperLotto Plus/Powerball/Mega Millions"),
):
    state = state.upper()

    try:
        with SessionLocal() as session:
            if period == "monthly":
                rows = (
                    session.query(
                        func.date_trunc("month", MarketStat.date).label("month"),
                        func.avg(MarketStat.revenue).label("revenue"),
                        func.avg(MarketStat.sales_volume).label("sales_volume"),
                        func.avg(MarketStat.jackpot).label("jackpot"),
                    )
                    .filter(MarketStat.state == state)
                    .group_by(func.date_trunc("month", MarketStat.date))
                    .order_by(func.date_trunc("month", MarketStat.date))
                    .all()
                )

                series = [
                    {
                        "date": row.month.date().isoformat(),
                        "revenue": _decimal_to_float(row.revenue),
                        "sales_volume": _decimal_to_float(row.sales_volume),
                        "jackpot": _decimal_to_float(row.jackpot),
                        "ticket_price": None,
                        "source_name": None,
                        "source_uri": None,
                    }
                    for row in rows
                ]
            else:
                q = session.query(MarketStat).filter(MarketStat.state == state)
                if game:
                    q = q.filter(MarketStat.game == game)
                rows = q.order_by(MarketStat.date.asc()).all()
                series = [
                    {
                        "date": stat.date.isoformat(),
                        "revenue": _decimal_to_float(stat.revenue),
                        "sales_volume": _decimal_to_float(stat.sales_volume),
                        "jackpot": _decimal_to_float(stat.jackpot),
                        "ticket_price": _decimal_to_float(stat.ticket_price),
                        "game": stat.game,
                        "source_name": stat.source_name,
                        "source_uri": stat.source_uri,
                    }
                    for stat in rows
                ]

            return {
                "state": state,
                "period": period,
                "series": series,
            }
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用，请检查数据库服务是否已启动。"
        )
    except Exception as e:
        logger.exception("获取市场数据失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "postgres" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="数据库服务不可用，请检查数据库服务是否已启动。"
            )
        raise HTTPException(status_code=500, detail=f"获取市场数据失败: {error_msg}")


@router.get("/games")
def market_games(state: str = Query(...)):
    state = state.upper()
    try:
        with SessionLocal() as session:
            rows = session.query(MarketStat.game).filter(MarketStat.state == state).distinct().all()
            games = [r[0] for r in rows if r[0]]
            return {"state": state, "games": games}
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用，请检查数据库服务是否已启动。"
        )
    except Exception as e:
        logger.exception("获取游戏列表失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="数据库服务不可用，请检查数据库服务是否已启动。"
            )
        raise HTTPException(status_code=500, detail=f"获取游戏列表失败: {error_msg}")


