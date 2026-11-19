from typing import Literal

from elasticsearch import BadRequestError, Elasticsearch

from ...settings.config import settings


POLICY_INDEX = "policy_docs_es"
SearchIndexEnsureStatus = Literal["created", "exists"]


def get_es_client() -> Elasticsearch:
    """Create an Elasticsearch client using configured URL."""
    return Elasticsearch(settings.es_url)


def ensure_policy_index(es: Elasticsearch) -> SearchIndexEnsureStatus:
    if es.indices.exists(index=POLICY_INDEX):
        return "exists"
    try:
        es.indices.create(
            index=POLICY_INDEX,
            mappings={
                "properties": {
                    "project_key": {"type": "keyword"},
                    "material_id": {"type": "long"},
                    "topic": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "state": {"type": "keyword"},
                    "title": {"type": "text"},
                    "status": {"type": "keyword"},
                    "publish_date": {"type": "date"},
                    "summary": {"type": "text"},
                    "content": {"type": "text"},
                    "text": {"type": "text"},
                    "keywords": {"type": "keyword"},
                }
            },
        )
    except BadRequestError as exc:
        # A concurrent writer may have created the shared index after our check.
        if exc.error != "resource_already_exists_exception":
            # kit:boundary
            raise
        return "exists"
    return "created"
