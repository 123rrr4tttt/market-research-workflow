from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import Float, select
from sqlalchemy.dialects import postgresql

from app.services.search.candidate_contracts import Candidate, CandidateBundle, CandidateSearchRequest, ProviderObservation
from app.models.entities import Embedding
from app.services.search import smart
from app.services.discovery import deep_search as deep_search_module
from app.services.projects import bind_project
from app.services.search import hybrid as hybrid_search_module


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
                            "document_id": 71,
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
    assert hits[0]["document_id"] == 71
    assert hits[0]["project_key"] == "project_a"


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
        return [{"document_id": 71, "project_key": project_key, "backend": "opensearch"}]

    monkeypatch.setattr(hybrid_search_module, "bm25_search", _bm25)
    monkeypatch.setattr(
        hybrid_search_module,
        "vector_search",
        lambda *_args, **_kwargs: [],
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
