from typing import Literal, TypedDict

from elasticsearch import Elasticsearch


SearchIndexEnsureStatus = Literal["created", "exists"]


class SearchIndexEnsureResult(TypedDict):
    policy_docs_es: SearchIndexEnsureStatus
    market_metric_points_es: SearchIndexEnsureStatus
    price_observations_es: SearchIndexEnsureStatus


def ensure_indices(es: Elasticsearch) -> SearchIndexEnsureResult:
    """Create indices with minimal mappings if they do not exist."""
    policy_index = "policy_docs_es"
    metric_index = "market_metric_points_es"
    ecom_index = "price_observations_es"

    if not es.indices.exists(index=policy_index):
        es.indices.create(
            index=policy_index,
            mappings={
                "properties": {
                    "project_key": {"type": "keyword"},
                    "topic": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "state": {"type": "keyword"},
                    "title": {"type": "text"},
                    "status": {"type": "keyword"},
                    "publish_date": {"type": "date"},
                    "summary": {"type": "text"},
                    "content": {"type": "text"},
                    "keywords": {"type": "keyword"},
                }
            },
        )
        policy_status: SearchIndexEnsureStatus = "created"
    else:
        policy_status = "exists"

    if not es.indices.exists(index=metric_index):
        es.indices.create(
            index=metric_index,
            mappings={
                "properties": {
                    "project_key": {"type": "keyword"},
                    "metric_key": {"type": "keyword"},
                    "date": {"type": "date"},
                    "value": {"type": "double"},
                    "unit": {"type": "keyword"},
                    "currency": {"type": "keyword"},
                    "source_uri": {"type": "keyword"},
                }
            },
        )
        metric_status: SearchIndexEnsureStatus = "created"
    else:
        metric_status = "exists"

    if not es.indices.exists(index=ecom_index):
        es.indices.create(
            index=ecom_index,
            mappings={
                "properties": {
                    "project_key": {"type": "keyword"},
                    "product_id": {"type": "long"},
                    "captured_at": {"type": "date"},
                    "price": {"type": "double"},
                    "currency": {"type": "keyword"},
                    "availability": {"type": "keyword"},
                    "source_uri": {"type": "keyword"},
                }
            },
        )
        ecom_status: SearchIndexEnsureStatus = "created"
    else:
        ecom_status = "exists"

    return {
        "policy_docs_es": policy_status,
        "market_metric_points_es": metric_status,
        "price_observations_es": ecom_status,
    }

