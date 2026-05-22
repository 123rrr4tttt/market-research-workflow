from __future__ import annotations

from typing import Literal, Sequence

from sqlalchemy import Date, and_, case, cast, func, or_

from ...models.entities import Document
from .policy_filters import policy_has_data_condition


TopicScope = Literal["company", "product", "operation"]


def document_has_extracted_data_condition():
    return Document.extracted_data.isnot(None)


def document_missing_extracted_data_condition():
    return Document.extracted_data.is_(None)


def document_extracted_data_present_case():
    return case((document_has_extracted_data_condition(), 1), else_=0)


def document_publish_or_created_on_or_after_condition(value):
    return or_(
        Document.publish_date >= value,
        and_(Document.publish_date.is_(None), func.date(Document.created_at) >= value),
    )


def document_publish_or_created_on_or_before_condition(value):
    return or_(
        Document.publish_date <= value,
        and_(Document.publish_date.is_(None), func.date(Document.created_at) <= value),
    )


def social_document_base_conditions(doc_types: Sequence[str]):
    return (
        Document.doc_type.in_(tuple(doc_types)),
        document_has_extracted_data_condition(),
    )


def social_platform_condition(platform: str):
    return Document.extracted_data["platform"].astext == platform


def social_sentiment_orientation_condition(sentiment_orientation: str):
    return Document.extracted_data["sentiment"]["sentiment_orientation"].astext == sentiment_orientation


def content_graph_structured_condition():
    return and_(
        document_has_extracted_data_condition(),
        or_(
            Document.extracted_data["sentiment"].isnot(None),
            Document.extracted_data["entities_relations"].isnot(None),
        ),
    )


def market_graph_structured_condition(
    *,
    deep_view: bool,
    topic_scope: TopicScope | None = None,
):
    if not deep_view:
        structured_condition = Document.extracted_data["market"].isnot(None)
    elif topic_scope == "company":
        structured_condition = Document.extracted_data["company_structured"].isnot(None)
    elif topic_scope == "product":
        structured_condition = Document.extracted_data["product_structured"].isnot(None)
    elif topic_scope == "operation":
        structured_condition = Document.extracted_data["operation_structured"].isnot(None)
    else:
        structured_condition = or_(
            Document.extracted_data["market"].isnot(None),
            Document.extracted_data["company_structured"].isnot(None),
            Document.extracted_data["product_structured"].isnot(None),
            Document.extracted_data["operation_structured"].isnot(None),
            Document.extracted_data["entities_relations"].isnot(None),
        )
    return and_(document_has_extracted_data_condition(), structured_condition)


def market_state_condition(state: str):
    state_upper = state.upper()
    return or_(
        Document.state == state_upper,
        Document.extracted_data["market"]["state"].astext == state_upper,
    )


def market_game_condition(game: str):
    return Document.extracted_data["market"]["game"].astext.ilike(f"%{game}%")


def market_report_date_expr():
    return cast(Document.extracted_data["market"]["report_date"].astext, Date)


def market_publish_created_or_report_on_or_after_condition(value):
    return or_(
        document_publish_or_created_on_or_after_condition(value),
        market_report_date_expr() >= value,
    )


def market_publish_created_or_report_on_or_before_condition(value):
    return or_(
        document_publish_or_created_on_or_before_condition(value),
        market_report_date_expr() <= value,
    )


def policy_graph_has_data_condition():
    return policy_has_data_condition()


def policy_graph_state_condition(state: str):
    state_upper = state.upper()
    return or_(
        Document.state == state_upper,
        Document.extracted_data["policy"]["state"].astext == state_upper,
    )


def policy_graph_type_ilike_condition(policy_type: str):
    return Document.extracted_data["policy"]["policy_type"].astext.ilike(f"%{policy_type}%")
