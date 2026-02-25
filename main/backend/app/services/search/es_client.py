from elasticsearch import Elasticsearch

from ...settings.config import settings


def get_es_client() -> Elasticsearch:
    """Create an Elasticsearch client using configured URL."""
    return Elasticsearch(settings.es_url)


