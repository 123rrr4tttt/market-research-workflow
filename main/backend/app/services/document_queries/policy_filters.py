from __future__ import annotations

from sqlalchemy import Date, String, and_, case, cast, func, or_

from ...models.entities import Document


def policy_effective_date_expr():
    effective_raw = cast(Document.extracted_data["policy"]["effective_date"], String)
    effective_text = func.replace(effective_raw, '"', "")
    return case(
        (effective_text.op("~")(r"^\d{4}-\d{2}-\d{2}"), cast(func.substr(effective_text, 1, 10), Date)),
        else_=None,
    )


def policy_time_expr():
    return func.coalesce(policy_effective_date_expr(), Document.publish_date, func.date(Document.created_at))


def policy_has_data_condition():
    return and_(Document.extracted_data.isnot(None), Document.extracted_data["policy"].isnot(None))


def policy_state_condition(state: str):
    state_upper = str(state or "").strip().upper()
    return or_(
        Document.state == state_upper,
        cast(Document.extracted_data["policy"]["state"], String) == state_upper,
    )


def policy_type_condition(policy_type: str):
    return cast(Document.extracted_data["policy"]["policy_type"], String) == str(policy_type or "").strip()


def policy_type_order_expr():
    return cast(Document.extracted_data["policy"]["policy_type"], String)
