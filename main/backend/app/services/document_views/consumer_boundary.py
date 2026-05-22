from __future__ import annotations

from typing import Any

from .common_view import get_extracted_data


CONSUMER_FACADE_CONTRACT_VERSION = "consumer.facade_boundary.wave9.v1"
CONSUMER_FACADE_BOUNDARY_RULE = (
    "Python consumer surfaces read structured document fields through document_views; "
    "SQL JSON predicates and sort expressions stay in document_queries or documented query-only bridges."
)


def has_structured_data(doc: Any) -> bool:
    return bool(get_extracted_data(doc))


def get_structured_field(doc: Any, key: str, *, default: Any = None) -> Any:
    extracted = get_extracted_data(doc)
    value = extracted.get(key)
    return default if value is None else value


def get_document_source_label(doc: Any) -> str | None:
    for key in ("platform", "source", "source_name", "publisher"):
        value = str(get_structured_field(doc, key, default="") or "").strip()
        if value:
            return value
    return None


def get_social_identity(doc: Any) -> dict[str, str | None]:
    return {
        "username": _string_or_none(get_structured_field(doc, "username")),
        "subreddit": _string_or_none(get_structured_field(doc, "subreddit")),
    }


def get_consumer_boundary_snapshot() -> dict[str, Any]:
    return {
        "contract_version": CONSUMER_FACADE_CONTRACT_VERSION,
        "boundary_rule": CONSUMER_FACADE_BOUNDARY_RULE,
        "python_read_facade": "main/backend/app/services/document_views",
        "sql_json_query_boundary": "main/backend/app/services/document_queries",
        "worker5_scope": [
            "graph.adapters_python_read_boundary",
            "writing.suggest_material_query_boundary",
            "search.api_no_document_json_read",
        ],
        "worker4_boundary": "does_not_modify_document_queries_core",
    }


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
