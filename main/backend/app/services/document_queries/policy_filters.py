from __future__ import annotations

from sqlalchemy import Date, String, and_, case, cast, func, or_
from sqlalchemy.sql.elements import ColumnElement

from ...models.entities import Document


def document_json_iso_date_expr(key: str) -> ColumnElement[object | None]:
    raw = cast(Document.extracted_data[key], String)
    text = func.replace(raw, '"', "")
    return case(
        (text.op("~")(r"^\d{4}-\d{2}-\d{2}"), cast(func.substr(text, 1, 10), Date)),
        else_=None,
    )


def policy_effective_date_expr() -> ColumnElement[object | None]:
    effective_raw = cast(Document.extracted_data["policy"]["effective_date"], String)
    effective_text = func.replace(effective_raw, '"', "")
    return case(
        (effective_text.op("~")(r"^\d{4}-\d{2}-\d{2}"), cast(func.substr(effective_text, 1, 10), Date)),
        else_=None,
    )


def policy_time_expr() -> ColumnElement[object | None]:
    return func.coalesce(
        document_json_iso_date_expr("effective_time"),
        document_json_iso_date_expr("source_time"),
        policy_effective_date_expr(),
        Document.publish_date,
        func.date(Document.created_at),
    )


def prompt_time_density_time_expr() -> ColumnElement[object | None]:
    return policy_time_expr()


def policy_has_data_condition() -> ColumnElement[bool]:
    return and_(Document.extracted_data.isnot(None), Document.extracted_data["policy"].isnot(None))


def policy_state_condition(state: str) -> ColumnElement[bool]:
    state_upper = str(state or "").strip().upper()
    return or_(
        Document.state == state_upper,
        cast(Document.extracted_data["policy"]["state"], String) == state_upper,
    )


def policy_type_condition(policy_type: str) -> ColumnElement[bool]:
    return cast(Document.extracted_data["policy"]["policy_type"], String) == str(policy_type or "").strip()


def policy_type_order_expr() -> ColumnElement[str]:
    return cast(Document.extracted_data["policy"]["policy_type"], String)
