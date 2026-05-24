from __future__ import annotations

import unittest
from typing import Any

import pytest

from app.services.local_index import (
    LOCAL_INDEX_QUERY_MODES,
    LocalIndexChunk,
    LocalIndexQuery,
    LocalIndexSearchResult,
    LocalIndexService,
    RepoLocalHashingEmbeddingProvider,
    cosine_similarity,
    normalize_local_index_mode,
)
from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available

pytestmark = pytest.mark.unit


class FakeLocalIndexAdapter:
    def __init__(self) -> None:
        self.chunks: list[LocalIndexChunk] = []
        self.last_query: LocalIndexQuery | None = None

    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        self.chunks = list(chunks)
        return {"ok": True, "chunk_count": len(self.chunks), "adapter": "fake"}

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        self.last_query = query
        out: list[LocalIndexSearchResult] = []
        needle = query.query.lower()
        for chunk in self.chunks:
            if chunk.project_id != query.project_id:
                continue
            if query.source_id and chunk.source_id != query.source_id:
                continue
            if needle not in f"{chunk.title} {chunk.content}".lower():
                continue
            out.append(
                LocalIndexSearchResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    project_id=chunk.project_id,
                    source_id=chunk.source_id,
                    title=chunk.title,
                    content=chunk.content,
                    score=1.0,
                    url=chunk.url,
                    retrieval_mode=query.mode,
                    trace={"adapter": "fake", "requested_mode": query.mode},
                )
            )
        return out[: query.top_k]


class FakeLanceQuery:
    def __init__(self, rows: list[dict[str, Any]], call: dict[str, Any] | None = None) -> None:
        self.rows = rows
        self.call = call
        self.predicate: str | None = None
        self.limit_value: int | None = None

    def text(self, value: str) -> "FakeLanceQuery":
        if self.call is not None:
            self.call["builder_text"] = value
        return self

    def vector(self, value: list[float]) -> "FakeLanceQuery":
        if self.call is not None:
            self.call["builder_vector"] = value
        return self

    def where(self, predicate: str) -> "FakeLanceQuery":
        self.predicate = predicate
        return self

    def limit(self, limit_value: int) -> "FakeLanceQuery":
        self.limit_value = limit_value
        return self

    def to_list(self) -> list[dict[str, Any]]:
        return self.rows[: self.limit_value]


class FakeLanceTable:
    def __init__(self, *, fail_modes: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_modes = fail_modes or set()
        self.rows = [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "project_id": "demo_proj",
                "source_id": "source_a",
                "title": "Robotics policy",
                "content": "Embodied AI robotics policy material chunk.",
                "_score": 0.9,
            }
        ]

    def search(self, query: str | list[float] | None, **kwargs: Any) -> FakeLanceQuery:
        query_type = str(kwargs.get("query_type") or "vector")
        call = {"query": query, "kwargs": kwargs, "query_type": query_type}
        self.calls.append(call)
        if query_type in self.fail_modes:
            raise RuntimeError(f"{query_type} unavailable")
        return FakeLanceQuery(self.rows, call)


class FakeEmbeddingProvider:
    provider_id = "fake_live_provider"
    model = "fake-live-model"
    model_version = "2026-test"
    vector_version = "fake-vector-v1"
    embedding_dim = 2
    network_required = False

    def embed_text(self, _text: str) -> list[float]:
        return [0.25, 0.75]

    def embed_query(self, _text: str) -> list[float]:
        return [0.25, 0.75]

    def embed_documents(self, texts):
        return [self.embed_text(text) for text in texts]

    def metadata(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "model_version": self.model_version,
            "embedding_dim": self.embedding_dim,
            "vector_version": self.vector_version,
            "network_required": self.network_required,
        }

    def readback(self, texts) -> dict[str, object]:
        rows = list(texts)
        return {
            **self.metadata(),
            "status": "passed",
            "live_provider_verified": True,
            "vector_count": len(rows),
            "failures": [],
        }


class LocalIndexServiceTest(unittest.TestCase):
    def test_repo_local_embedding_provider_is_executable_and_query_sensitive(self) -> None:
        provider = RepoLocalHashingEmbeddingProvider()
        readback = provider.readback(
            [
                "robotics commercialization policy grant",
                "unrelated festival ticket sales",
            ]
        )

        self.assertEqual(readback["status"], "passed")
        self.assertTrue(readback["live_provider_verified"])
        self.assertFalse(readback["network_required"])
        self.assertEqual(readback["embedding_dim"], 512)

        query_vector = provider.embed_query("robotics policy")
        robotics_vector = provider.embed_text("robotics automation policy procurement")
        festival_vector = provider.embed_text("music festival ticket sales venue")
        self.assertGreater(cosine_similarity(query_vector, robotics_vector), cosine_similarity(query_vector, festival_vector))

    def test_service_indexes_material_chunks_without_source_library_schema(self) -> None:
        adapter = FakeLocalIndexAdapter()
        service = LocalIndexService(adapter)
        status = service.upsert_chunks(
            [
                LocalIndexChunk(
                    chunk_id="c1",
                    document_id="d1",
                    project_id="demo_proj",
                    source_id="source_a",
                    title="Robotics policy",
                    content="Embodied AI robotics policy material chunk.",
                    url="https://example.gov/robotics",
                ),
                LocalIndexChunk(
                    chunk_id="c2",
                    document_id="d2",
                    project_id="other_proj",
                    source_id="source_b",
                    title="Other",
                    content="Embodied AI but outside project.",
                ),
            ]
        )
        self.assertEqual(status["chunk_count"], 2)

        results = service.search(LocalIndexQuery(query="robotics", project_id="demo_proj", source_id="source_a", top_k=5))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, "c1")
        self.assertEqual(results[0].source_id, "source_a")
        self.assertIn("document_id", results[0].to_dict())
        self.assertNotIn("source_library_item", results[0].to_dict())
        self.assertEqual(results[0].to_dict()["retrieval_mode"], "keyword")
        self.assertEqual(results[0].to_dict()["retrieval_family"], "local_index")

    def test_empty_query_short_circuits(self) -> None:
        service = LocalIndexService(FakeLocalIndexAdapter())

        self.assertEqual(service.search(LocalIndexQuery(query=" ", project_id="demo_proj")), [])

    def test_query_mode_contract_is_exported_and_normalized(self) -> None:
        self.assertEqual(LOCAL_INDEX_QUERY_MODES, {"keyword", "vector", "hybrid"})
        self.assertEqual(normalize_local_index_mode("VECTOR"), "vector")
        self.assertEqual(normalize_local_index_mode(" hybrid "), "hybrid")
        self.assertEqual(normalize_local_index_mode("unknown"), "keyword")

    def test_service_preserves_supported_modes_and_normalizes_unknown_mode(self) -> None:
        adapter = FakeLocalIndexAdapter()
        service = LocalIndexService(adapter)
        service.upsert_chunks(
            [
                LocalIndexChunk(
                    chunk_id="c1",
                    document_id="d1",
                    project_id="demo_proj",
                    source_id="source_a",
                    title="Robotics policy",
                    content="Embodied AI robotics policy material chunk.",
                )
            ]
        )

        vector_results = service.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="VECTOR"))
        self.assertEqual(adapter.last_query.mode, "vector")
        self.assertEqual(vector_results[0].retrieval_mode, "vector")

        service.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="semantic"))
        self.assertEqual(adapter.last_query.mode, "keyword")

    def test_lancedb_adapter_dispatches_keyword_vector_and_hybrid_modes(self) -> None:
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = FakeLanceTable()
        adapter._table = table

        keyword_results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="keyword"))
        vector_results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="vector"))
        hybrid_results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="hybrid"))

        self.assertEqual(table.calls[0]["kwargs"]["query_type"], "fts")
        self.assertIsInstance(table.calls[1]["query"], list)
        self.assertEqual(table.calls[1]["query_type"], "vector")
        self.assertIsNone(table.calls[2]["query"])
        self.assertEqual(table.calls[2]["kwargs"]["query_type"], "hybrid")
        self.assertEqual(table.calls[2]["builder_text"], "robotics")
        self.assertIsInstance(table.calls[2]["builder_vector"], list)
        self.assertEqual(keyword_results[0].retrieval_mode, "keyword")
        self.assertEqual(vector_results[0].retrieval_mode, "vector")
        self.assertEqual(hybrid_results[0].retrieval_mode, "hybrid")
        self.assertEqual(hybrid_results[0].trace["executed_mode"], "hybrid")
        self.assertEqual(hybrid_results[0].trace["project_id"], "demo_proj")
        self.assertIsNone(hybrid_results[0].trace["source_id"])
        self.assertEqual(hybrid_results[0].trace["top_k"], 10)
        self.assertTrue(hybrid_results[0].trace["provider_live_verified"])
        self.assertEqual(
            hybrid_results[0].trace["embedding_provider"]["provider_id"],
            "repo_local_token_hashing",
        )

    def test_lancedb_adapter_uses_injected_live_embedding_provider_for_vector_queries(self) -> None:
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = FakeLanceTable()
        adapter._table = table
        adapter._embedding_provider = FakeEmbeddingProvider()

        results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="vector"))

        self.assertEqual(table.calls[0]["query"], [0.25, 0.75])
        self.assertEqual(results[0].retrieval_mode, "vector")
        self.assertEqual(results[0].trace["embedding_provider"]["provider_id"], "fake_live_provider")
        self.assertTrue(results[0].trace["provider_live_verified"])

    def test_lancedb_adapter_falls_back_to_keyword_when_vector_runtime_is_unavailable(self) -> None:
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = FakeLanceTable(fail_modes={"vector"})
        adapter._table = table

        results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="vector"))

        self.assertEqual([call["query_type"] for call in table.calls], ["vector", "fts"])
        self.assertEqual(results[0].retrieval_mode, "keyword")
        self.assertEqual(results[0].trace["fallback_from"], "vector")
        self.assertEqual(results[0].trace["fallback_reason"], "RuntimeError")

    def test_lancedb_adapter_falls_back_to_keyword_when_hybrid_runtime_is_unavailable(self) -> None:
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = FakeLanceTable(fail_modes={"hybrid"})
        adapter._table = table

        results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="hybrid"))

        self.assertEqual([call["query_type"] for call in table.calls], ["hybrid", "fts"])
        self.assertEqual(results[0].retrieval_mode, "keyword")
        self.assertEqual(results[0].trace["requested_mode"], "hybrid")
        self.assertEqual(results[0].trace["executed_mode"], "keyword")
        self.assertEqual(results[0].trace["fallback_from"], "hybrid")
        self.assertEqual(results[0].trace["fallback_reason"], "RuntimeError")

    def test_lancedb_adapter_has_clear_optional_dependency_boundary(self) -> None:
        if is_lancedb_available():
            self.assertIsNotNone(LanceDBLocalIndexAdapter)
            return
        with self.assertRaisesRegex(RuntimeError, "lancedb is not installed"):
            LanceDBLocalIndexAdapter()


if __name__ == "__main__":
    unittest.main()
