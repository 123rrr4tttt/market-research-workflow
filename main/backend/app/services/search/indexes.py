from elasticsearch import Elasticsearch


def ensure_indices(es: Elasticsearch) -> dict:
    """Create indices with minimal mappings if they do not exist."""
    results: dict[str, str] = {}

    policy_index = "policy_docs_es"
    market_index = "market_stats_es"
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
        results[policy_index] = "created"
    else:
        results[policy_index] = "exists"

    if not es.indices.exists(index=market_index):
        es.indices.create(
            index=market_index,
            mappings={
                "properties": {
                    "project_key": {"type": "keyword"},
                    "topic": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "state": {"type": "keyword"},
                    "date": {"type": "date"},
                    "sales_volume": {"type": "double"},
                    "revenue": {"type": "double"},
                    "jackpot": {"type": "double"},
                    "ticket_price": {"type": "double"},
                    "yoy": {"type": "double"},
                    "mom": {"type": "double"},
                }
            },
        )
        results[market_index] = "created"
    else:
        results[market_index] = "exists"

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
        results[metric_index] = "created"
    else:
        results[metric_index] = "exists"

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
        results[ecom_index] = "created"
    else:
        results[ecom_index] = "exists"

    return results


