from __future__ import annotations

from datetime import date
from typing import Literal, Sequence

from sqlalchemy import Date, and_, case, cast, func, or_
from sqlalchemy.sql.elements import Cast, ColumnElement

from ...models.entities import Material
from .policy_filters import policy_has_data_condition


TopicScope = Literal["company", "product", "operation"]


def material_has_extracted_data_condition() -> ColumnElement[bool]:
    return Material.extracted_data.isnot(None)


def material_missing_extracted_data_condition() -> ColumnElement[bool]:
    return Material.extracted_data.is_(None)


def material_extracted_data_present_case() -> ColumnElement[int | None]:
    return case((material_has_extracted_data_condition(), 1), else_=0)


def material_publish_or_created_on_or_after_condition(value: date) -> ColumnElement[bool]:
    return or_(
        Material.publish_date >= value,
        and_(Material.publish_date.is_(None), func.date(Material.created_at) >= value),
    )


def material_publish_or_created_on_or_before_condition(value: date) -> ColumnElement[bool]:
    return or_(
        Material.publish_date <= value,
        and_(Material.publish_date.is_(None), func.date(Material.created_at) <= value),
    )


def social_material_base_conditions(material_types: Sequence[str]) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    return (
        Material.material_type.in_(tuple(material_types)),
        material_has_extracted_data_condition(),
    )


def social_platform_condition(platform: str) -> ColumnElement[bool]:
    return Material.extracted_data["platform"].astext == platform


def social_sentiment_orientation_condition(sentiment_orientation: str) -> ColumnElement[bool]:
    return Material.extracted_data["sentiment"]["sentiment_orientation"].astext == sentiment_orientation


def content_graph_structured_condition() -> ColumnElement[bool]:
    return and_(
        material_has_extracted_data_condition(),
        or_(
            Material.extracted_data["sentiment"].isnot(None),
            Material.extracted_data["entities_relations"].isnot(None),
        ),
    )


def market_graph_structured_condition(
    *,
    deep_view: bool,
    topic_scope: TopicScope | None = None,
) -> ColumnElement[bool]:
    if not deep_view:
        structured_condition = Material.extracted_data["market"].isnot(None)
    elif topic_scope == "company":
        structured_condition = Material.extracted_data["company_structured"].isnot(None)
    elif topic_scope == "product":
        structured_condition = Material.extracted_data["product_structured"].isnot(None)
    elif topic_scope == "operation":
        structured_condition = Material.extracted_data["operation_structured"].isnot(None)
    else:
        structured_condition = or_(
            Material.extracted_data["market"].isnot(None),
            Material.extracted_data["company_structured"].isnot(None),
            Material.extracted_data["product_structured"].isnot(None),
            Material.extracted_data["operation_structured"].isnot(None),
            Material.extracted_data["entities_relations"].isnot(None),
        )
    return and_(material_has_extracted_data_condition(), structured_condition)


def market_state_condition(state: str) -> ColumnElement[bool]:
    state_upper = state.upper()
    return or_(
        Material.state == state_upper,
        Material.extracted_data["market"]["state"].astext == state_upper,
    )


def market_game_condition(game: str) -> ColumnElement[bool]:
    return Material.extracted_data["market"]["game"].astext.ilike(f"%{game}%")


def market_report_date_expr() -> Cast[date]:
    return cast(Material.extracted_data["market"]["report_date"].astext, Date)


def market_publish_created_or_report_on_or_after_condition(value: date) -> ColumnElement[bool]:
    return or_(
        material_publish_or_created_on_or_after_condition(value),
        market_report_date_expr() >= value,
    )


def market_publish_created_or_report_on_or_before_condition(value: date) -> ColumnElement[bool]:
    return or_(
        material_publish_or_created_on_or_before_condition(value),
        market_report_date_expr() <= value,
    )


def policy_graph_has_data_condition() -> ColumnElement[bool]:
    return policy_has_data_condition()


def policy_graph_state_condition(state: str) -> ColumnElement[bool]:
    state_upper = state.upper()
    return or_(
        Material.state == state_upper,
        Material.extracted_data["policy"]["state"].astext == state_upper,
    )


def policy_graph_type_ilike_condition(policy_type: str) -> ColumnElement[bool]:
    return Material.extracted_data["policy"]["policy_type"].astext.ilike(f"%{policy_type}%")
