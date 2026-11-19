from typing import TypedDict

from elasticsearch import Elasticsearch

from .es_client import SearchIndexEnsureStatus, ensure_policy_index



class SearchIndexEnsureResult(TypedDict):
    policy_docs_es: SearchIndexEnsureStatus
    market_metric_points_es: SearchIndexEnsureStatus
    price_observations_es: SearchIndexEnsureStatus


def ensure_indices(es: Elasticsearch) -> SearchIndexEnsureResult:
    """Create indices with minimal mappings if they do not exist."""
    metric_index = "market_metric_points_es"
    ecom_index = "price_observations_es"
    policy_status = ensure_policy_index(es)

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

