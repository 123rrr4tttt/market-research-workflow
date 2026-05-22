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
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.predicate: str | None = None
        self.limit_value: int | None = None

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

    def search(self, query: str | list[float], **kwargs: Any) -> FakeLanceQuery:
        query_type = str(kwargs.get("query_type") or "vector")
        self.calls.append({"query": query, "kwargs": kwargs, "query_type": query_type})
        if query_type in self.fail_modes:
            raise RuntimeError(f"{query_type} unavailable")
        return FakeLanceQuery(self.rows)


class LocalIndexServiceTest(unittest.TestCase):
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
        self.assertEqual(table.calls[2]["kwargs"]["query_type"], "hybrid")
        self.assertEqual(keyword_results[0].retrieval_mode, "keyword")
        self.assertEqual(vector_results[0].retrieval_mode, "vector")
        self.assertEqual(hybrid_results[0].retrieval_mode, "hybrid")
        self.assertEqual(hybrid_results[0].trace["executed_mode"], "hybrid")

    def test_lancedb_adapter_falls_back_to_keyword_when_vector_runtime_is_unavailable(self) -> None:
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = FakeLanceTable(fail_modes={"vector"})
        adapter._table = table

        results = adapter.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="vector"))

        self.assertEqual([call["query_type"] for call in table.calls], ["vector", "fts"])
        self.assertEqual(results[0].retrieval_mode, "keyword")
        self.assertEqual(results[0].trace["fallback_from"], "vector")
        self.assertEqual(results[0].trace["fallback_reason"], "RuntimeError")

    def test_lancedb_adapter_has_clear_optional_dependency_boundary(self) -> None:
        if is_lancedb_available():
            self.assertIsNotNone(LanceDBLocalIndexAdapter)
            return
        with self.assertRaisesRegex(RuntimeError, "lancedb is not installed"):
            LanceDBLocalIndexAdapter()


if __name__ == "__main__":
    unittest.main()
