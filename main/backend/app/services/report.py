from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Iterable, Sequence

from sqlalchemy import Date, case, cast, func, select, String

from ..models.base import SessionLocal
from ..models.entities import Document, MarketStat
from ..project_customization import get_project_customization
from .llm.service import summarize_policy_text


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value: str | None, *, field: str) -> date | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _DATE_RE.match(raw):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _policy_effective_date_expr():
    effective_raw = cast(Document.extracted_data["policy"]["effective_date"], String)
    effective_text = func.replace(effective_raw, '"', "")
    return case(
        (effective_text.op("~")(r"^\d{4}-\d{2}-\d{2}"), cast(func.substr(effective_text, 1, 10), Date)),
        else_=None,
    )


def _policy_time_expr():
    return func.coalesce(_policy_effective_date_expr(), Document.publish_date, func.date(Document.created_at))


def _load_policies(states: Sequence[str], start: date | None, end: date | None) -> list[Document]:
    with SessionLocal() as session:
        policy_time = _policy_time_expr()
        stmt = select(Document).filter(
            Document.doc_type.in_(["policy", "policy_regulation"]),
            Document.state.in_([s.upper() for s in states]),
        )
        if start:
            stmt = stmt.filter(policy_time >= start)
        if end:
            stmt = stmt.filter(policy_time <= end)
        stmt = stmt.order_by(policy_time.desc().nullslast(), Document.id.desc())
        return [row[0] for row in session.execute(stmt.limit(50)).all()]


def _load_market(states: Sequence[str], start: date | None, end: date | None) -> list[MarketStat]:
    with SessionLocal() as session:
        stmt = select(MarketStat).filter(MarketStat.state.in_([s.upper() for s in states]))
        if start:
            stmt = stmt.filter(MarketStat.date >= start)
        if end:
            stmt = stmt.filter(MarketStat.date <= end)
        stmt = stmt.order_by(MarketStat.date.desc())
        return [row[0] for row in session.execute(stmt.limit(200)).all()]


def generate_html_report(states: Sequence[str], start: str | None, end: str | None) -> str:
    start_date = _parse_date(start, field="start")
    end_date = _parse_date(end, field="end")

    policies = _load_policies(states, start_date, end_date)
    market = _load_market(states, start_date, end_date)

    policy_items = []
    for doc in policies:
        summary = doc.summary
        if not summary:
            try:
                summary = summarize_policy_text(doc.content or "")
            except Exception:  # noqa: BLE001
                summary = (doc.content or "")[:300]
        policy_items.append(
            {
                "state": doc.state,
                "title": doc.title,
                "publish_date": doc.publish_date.isoformat() if doc.publish_date else "",
                "summary": summary,
            }
        )

    market_rows = []
    for stat in market:
        market_rows.append(
            {
                "state": stat.state,
                "date": stat.date.isoformat(),
                "revenue": float(stat.revenue or 0),
                "sales_volume": float(stat.sales_volume or 0),
                "jackpot": float(stat.jackpot or 0),
            }
        )

    title = get_project_customization().get_report_title()
    html = [f"<section><h1>{title}</h1>"]
    html.append(f"<p>州：{', '.join(states)}；时间：{start or '全部'} - {end or '全部'}</p>")

    html.append("<h2>政策概览</h2><ul>")
    for item in policy_items:
        html.append(
            f"<li><strong>{item['state']}</strong> - {item['publish_date']} - {item['title']}<br/>"
            f"<em>{item['summary']}</em></li>"
        )
    html.append("</ul>")

    html.append("<h2>市场数据</h2><table border=1 cellpadding=4 cellspacing=0><thead><tr>"
                "<th>州</th><th>日期</th><th>销售额</th><th>销量</th><th>奖池</th></tr></thead><tbody>")
    for row in market_rows:
        html.append(
            f"<tr><td>{row['state']}</td><td>{row['date']}</td>"
            f"<td>{row['revenue']}</td><td>{row['sales_volume']}</td><td>{row['jackpot']}</td></tr>"
        )
    html.append("</tbody></table></section>")

    return "".join(html)


def generate_csv_report(states: Sequence[str], start: str | None, end: str | None) -> bytes:
    start_date = _parse_date(start, field="start")
    end_date = _parse_date(end, field="end")

    policies = _load_policies(states, start_date, end_date)
    market = _load_market(states, start_date, end_date)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["type", "state", "date", "title", "summary", "revenue", "sales_volume", "jackpot"])

    for doc in policies:
        writer.writerow([
            "policy",
            doc.state,
            doc.publish_date.isoformat() if doc.publish_date else "",
            doc.title or "",
            doc.summary or "",
            "",
            "",
            "",
        ])

    for stat in market:
        writer.writerow([
            "market",
            stat.state,
            stat.date.isoformat(),
            "",
            "",
            float(stat.revenue or 0),
            float(stat.sales_volume or 0),
            float(stat.jackpot or 0),
        ])

    return buffer.getvalue().encode("utf-8")
