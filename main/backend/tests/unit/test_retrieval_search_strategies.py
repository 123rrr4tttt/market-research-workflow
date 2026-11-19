from datetime import datetime, timedelta

import numpy as np
import pytest
from app.models.entities import Embedding
from app.services.discovery import deep_search as deep_search_module
from app.services.projects import bind_project
from app.services.search import hybrid as hybrid_search_module
from app.services.search import smart
from app.services.search.candidate_contracts import Candidate, CandidateBundle, ProviderObservation
from elasticsearch import ConnectionError as ElasticsearchConnectionError
from sqlalchemy import Float, select
from sqlalchemy.dialects import postgresql


def _bundle(request, *, row=None, observations=()):
    candidates = () if row is None else (
        Candidate(
            resource_uri=row["link"], title=row.get("title"), snippet=None, source="test", keyword=request.topic,
            original_rank=1, result_rank=1, relevance_score=1.0, raw=dict(row),
        ),
    )
    return CandidateBundle(request, candidates, (), tuple(observations), "candidates_observed" if candidates else "no_candidates_observed")


def test_smart_search_bundle_uses_incremental_window_and_retains_typed_result(monkeypatch):
    monkeypatch.setattr(smart, "get_last_search_time", lambda _topic: datetime.now() - timedelta(days=4))
    seen = []

    def discover(request):
        seen.append(request)
        return _bundle(request, row={"link": "https://example.test/a"})

    monkeypatch.setattr(smart, "discover_candidates", discover)
    monkeypatch.setattr(smart, "update_search_time", lambda _topic: None)

    result = smart.smart_search_bundle("robotics", days_back=30, max_results=7, language="en", provider="serper")

    assert result.request.days_back == 4
    assert result.request.max_results == 7
    assert result.request.provider == "serper"
    assert result.legacy_list() == [{"link": "https://example.test/a"}]
    assert len(seen) == 1


def test_smart_same_day_skip_is_not_reported_as_an_attempted_empty_search(monkeypatch):
    monkeypatch.setattr(smart, "get_last_search_time", lambda _topic: datetime.now())
    monkeypatch.setattr(smart, "discover_candidates", lambda _request: (_ for _ in ()).throw(AssertionError("must skip")))

    result = smart.smart_search_bundle("robotics")

    assert result.stop_reason == "not_attempted"
    assert not result.observations
    assert not result.candidates


def test_deep_search_candidates_keeps_partial_branch_observations_and_stops_at_candidates(monkeypatch):
    monkeypatch.setattr(deep_search_module, "generate_keywords", lambda _topic, _language: ["robotics policy"])
    failed = ProviderObservation("ddg", "web", "robotics policy", "failed", failure_kind="timeout", error_type="TimeoutError")
    calls = []

    def discover(request):
        calls.append(request)
        return _bundle(request, row={"link": "https://example.test/policy", "title": "Policy"}, observations=(failed,))

    monkeypatch.setattr(deep_search_module, "discover_candidates", discover)
    result = deep_search_module.deep_search_candidates("robotics", iterations=1, breadth=1, max_results=5)

    assert len(calls) == 1
    assert result.candidates[0].resource_uri == "https://example.test/policy"
    assert result.observations == (failed,)
    assert result.partial
    assert deep_search_module.deep_search("robotics", iterations=1, breadth=1, max_results=5)["results"] == [
        {"link": "https://example.test/policy", "title": "Policy"}
    ]


def test_deep_search_bad_scores_keep_original_conversion_exception_types(monkeypatch):
    monkeypatch.setattr(deep_search_module, "generate_keywords", lambda _topic, _language: ["robotics policy"])

    def discover_bad_string(request):
        return _bundle(
            request,
            row={
                "link": "https://example.test/policy",
                "title": "Policy",
                "relevance_score": "not-a-number",
            },
        )

    monkeypatch.setattr(deep_search_module, "discover_candidates", discover_bad_string)
    with pytest.raises(ValueError, match="could not convert string to float"):
        deep_search_module.deep_search_candidates("robotics", iterations=1, breadth=1, max_results=5)

    def discover_bad_object(request):
        return _bundle(
            request,
            row={
                "link": "https://example.test/policy",
                "title": "Policy",
                "relevance_score": object(),
            },
        )

    monkeypatch.setattr(deep_search_module, "discover_candidates", discover_bad_object)
    with pytest.raises(TypeError, match="^relevance_score is not float-convertible$"):
        deep_search_module.deep_search_candidates("robotics", iterations=1, breadth=1, max_results=5)


class _RecordingElasticsearch:
    def __init__(self, project_key="project_a"):
        self.search_bodies = []
        self.project_key = project_key

    def search(self, *, index, body):
        self.search_bodies.append({"index": index, "body": body})
        return {
            "hits": {
                "hits": [
                    {
                        "_score": 3.2,
                        "_source": {
                            "material_id": 71,
                            "project_key": self.project_key,
                            "object_type": "policy_chunk",
                            "object_id": 71,
                            "chunk_index": 0,
                            "title": "Project A policy",
                            "text": "shared policy phrase",
                        },
                    }
                ]
            }
        }


def test_bm25_search_filters_explicit_project_scope():
    es = _RecordingElasticsearch()

    hits = hybrid_search_module.bm25_search(
        es,
        "shared policy phrase",
        state=None,
        top_k=5,
        project_key="project_a",
    )

    body = es.search_bodies[0]["body"]
    assert es.search_bodies[0]["index"] == "policy_docs_es"
    assert {"term": {"project_key": "project_a"}} in body["query"]["bool"]["must"]
    assert hits[0]["material_id"] == 71
    assert hits[0]["project_key"] == "project_a"


def test_bm25_reads_the_elasticsearch_response_body():
    from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig, ObjectApiResponse

    class ElasticTransportResponse(_RecordingElasticsearch):
        def search(self, *, index, body):
            return ObjectApiResponse(
                meta=ApiResponseMeta(200, "1.1", HttpHeaders(), 0.0, NodeConfig("http", "localhost", 9200)),
                body=super().search(index=index, body=body),
            )

    hits = hybrid_search_module.bm25_search(ElasticTransportResponse(), "policy", None, 5, project_key="project_a")
    assert isinstance(hits, list)
    assert hits[0]["material_id"] == 71


def test_bm25_search_keeps_valid_hits_when_one_provider_row_is_not_json():
    class _PartialElasticsearch(_RecordingElasticsearch):
        def search(self, *, index, body):
            response = super().search(index=index, body=body)
            response["hits"]["hits"].append(
                {"_score": 1.0, "_source": {"material_id": object()}}
            )
            return response

    hits = hybrid_search_module.bm25_search(
        _PartialElasticsearch(),
        "shared policy phrase",
        state=None,
        top_k=5,
        project_key="project_a",
    )

    assert [hit["material_id"] for hit in hits] == [71]


def test_bm25_search_uses_bound_scope_for_existing_unparameterized_consumer():
    es = _RecordingElasticsearch("project_b")

    with bind_project("project_b"):
        hits = hybrid_search_module.bm25_search(
            es,
            "shared policy phrase",
            state=None,
            top_k=5,
        )

    body = es.search_bodies[0]["body"]
    assert {"term": {"project_key": "project_b"}} in body["query"]["bool"]["must"]
    assert hits[0]["project_key"] == "project_b"


def test_hybrid_search_passes_bound_scope_to_bm25(monkeypatch):
    calls = []

    def _bm25(es_client, query, state, top_k, *, project_key):
        calls.append(project_key)
        return [{"material_id": 71, "project_key": project_key, "backend": "opensearch"}]

    monkeypatch.setattr(hybrid_search_module, "bm25_search", _bm25)
    monkeypatch.setattr(
        hybrid_search_module,
        "observe_vector_search",
        lambda *_args, **_kwargs: hybrid_search_module.SearchInvocationObservation([], ("qdrant",), ()),
    )

    with bind_project("project_b"):
        hits = hybrid_search_module.hybrid_search(
            "shared policy phrase",
            state=None,
            top_k=5,
            mode="hybrid",
        )

    assert calls == ["project_b"]
    assert hits[0]["project_key"] == "project_b"


def test_pgvector_distance_operator_is_public_schema_qualified():
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    statement = select(Embedding.id).order_by(
        Embedding.vector.op('OPERATOR(public.<->)', return_type=Float)(vector)
    ).limit(1)
    distance = statement._order_by_clauses[0]
    compiled = statement.compile(dialect=postgresql.dialect())

    assert "ORDER BY embeddings.vector OPERATOR(public.<->) %(vector_1)s" in compiled.string
    assert distance.left.type == Embedding.vector.type
    assert distance.right.type == Embedding.vector.type
    assert distance.type.__class__ is Float
    assert compiled.params["vector_1"] is vector


def test_vector_successful_empty_stops_fallback_and_does_not_initialize_es(monkeypatch):
    monkeypatch.setattr(hybrid_search_module, "try_qdrant_vector_search", lambda *a, **kw: [])
    def forbidden(*args, **kwargs):
        raise AssertionError("successful empty query must not fall back")
    monkeypatch.setattr(hybrid_search_module, "_pgvector_search", forbidden)
    monkeypatch.setattr(hybrid_search_module, "get_es_client", forbidden)
    result = hybrid_search_module.observe_hybrid_search("empty", None, 5, "vector", project_key="a")
    assert result.hits == []
    assert result.used_backends == ("qdrant",)
    assert result.failures == ()


@pytest.mark.parametrize("outcome", ["empty", "embedding", "operator", "sql"])
def test_vector_fallback_preserves_ordered_failures(monkeypatch, outcome):
    from unittest.mock import MagicMock
    h = hybrid_search_module
    qfailure = h._qdrant_failure("backend_unavailable", "qdrant unavailable", RuntimeError())
    monkeypatch.setattr(h, "try_qdrant_vector_search", lambda *a, **kw: qfailure)
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1, 0.2]
    if outcome == "embedding":
        embeddings.embed_query.side_effect = RuntimeError("embedding unavailable")
    monkeypatch.setattr(h, "get_embeddings", lambda: embeddings)
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(h, "SessionLocal", lambda: session)
    if outcome == "operator":
        monkeypatch.setattr(h, "_pgvector_distance", lambda _: None)
    elif outcome == "sql":
        session.execute.side_effect = RuntimeError("sql unavailable")
    result = h.observe_vector_search("empty", None, 5, project_key="a")
    assert result.hits == []
    assert result.failures[0] is qfailure
    if outcome == "empty":
        assert result.used_backends == ("pgvector",)
        assert len(result.failures) == 1
    else:
        assert result.used_backends == ()
        assert [f.context["provider"] for f in result.failures] == ["qdrant", "pgvector"]
        assert result.failures[1].code == {"embedding": "embedding_failed", "operator": "backend_unavailable", "sql": "vector_search_failed"}[outcome]


def test_hybrid_degradation_keeps_bm25_and_both_failure_observations(monkeypatch):
    h = hybrid_search_module
    failures = (h._qdrant_failure("backend_unavailable", "q", RuntimeError()), h._pgvector_failure("embedding_failed", "p"))
    monkeypatch.setattr(h, "get_es_client", object)
    monkeypatch.setattr(h, "bm25_search", lambda *a, **kw: [{"material_id": 7}])
    monkeypatch.setattr(h, "observe_vector_search", lambda *a, **kw: h.SearchInvocationObservation([], (), failures))
    result = h.observe_hybrid_search("market", None, 5, "hybrid", project_key="a")
    assert result.hits == [{"material_id": 7}]
    assert result.used_backends == ("opensearch",)
    assert result.failures == failures


def test_interleaved_calls_keep_their_own_backend_and_failure(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    h = hybrid_search_module
    barrier = Barrier(2)
    failure = h._qdrant_failure("backend_unavailable", "q unavailable", RuntimeError())
    def qdrant(query, *args, **kwargs):
        barrier.wait(timeout=5)
        return [] if query == "q" else failure
    monkeypatch.setattr(h, "try_qdrant_vector_search", qdrant)
    monkeypatch.setattr(h, "_pgvector_search", lambda *a, **kw: [])
    with ThreadPoolExecutor(max_workers=2) as pool:
        q, p = list(pool.map(lambda query: h.observe_vector_search(query, None, 5, project_key="a"), ["q", "p"]))
    assert (q.used_backends, q.failures) == (("qdrant",), ())
    assert (p.used_backends, p.failures) == (("pgvector",), (failure,))


@pytest.mark.parametrize("response", [{"hits": {}}, {"hits": {"hits": [None]}}, {"hits": {"hits": []}}])
def test_bm25_distinguishes_missing_or_invalid_hits_from_successful_empty(monkeypatch, response):
    class SearchClient:
        def search(self, **kwargs):
            return response

    h = hybrid_search_module
    monkeypatch.setattr(h, "get_es_client", SearchClient)
    result = h.observe_hybrid_search("empty", None, 5, "bm25", project_key="a")
    assert result.hits == []
    if response == {"hits": {"hits": []}}:
        assert result.used_backends == ("opensearch",)
        assert result.failures == ()
    else:
        assert result.used_backends == ()
        assert result.failures[0].context["provider"] == "opensearch"
        assert result.failures[0].code == "backend_unavailable"
        assert result.failures[0].message.startswith("OpenSearch response")


def test_hybrid_degradation_keeps_vector_after_lexical_query_fails(monkeypatch):
    client = _RecordingElasticsearch()
    failure = ElasticsearchConnectionError("Connection refused")

    def search(**kwargs):
        raise failure

    monkeypatch.setattr(client, "search", search)

    h = hybrid_search_module
    monkeypatch.setattr(h, "get_es_client", lambda: client)
    vector_hits = [{"material_id": 7, "backend": "qdrant"}]
    monkeypatch.setattr(h, "try_qdrant_vector_search", lambda *a, **kw: vector_hits)
    result = h.observe_hybrid_search("market", None, 5, "hybrid", project_key="a")
    assert result.hits == vector_hits
    assert result.used_backends == ("qdrant",)
    assert [(f.code, f.context["provider"]) for f in result.failures] == [("backend_unavailable", "opensearch")]
