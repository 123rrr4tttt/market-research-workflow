from elasticsearch import Elasticsearch


def ensure_indices(es: Elasticsearch) -> dict:
    """Create indices with minimal mappings if they do not exist."""
    results: dict[str, str] = {}

    policy_index = "policy_docs_es"
    market_index = "market_stats_es"

    if not es.indices.exists(index=policy_index):
        es.indices.create(
            index=policy_index,
            mappings={
                "properties": {
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

    return results


