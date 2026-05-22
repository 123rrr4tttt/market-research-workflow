from __future__ import annotations

import unittest

import pytest

from app.services.local_index import LocalIndexChunk, LocalIndexQuery, LocalIndexSearchResult, LocalIndexService
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
                    retrieval_family="local_index",
                    trace={"adapter": "fake", "mode": query.mode},
                )
            )
        return out[: query.top_k]


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
        result_dict = results[0].to_dict()
        self.assertIn("document_id", result_dict)
        self.assertNotIn("source_library_item", result_dict)
        self.assertEqual(result_dict["retrieval_mode"], "keyword")
        self.assertEqual(result_dict["retrieval_family"], "local_index")
        self.assertEqual(result_dict["trace"]["adapter"], "fake")

    def test_service_preserves_supported_query_modes(self) -> None:
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

        results = service.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="hybrid"))

        self.assertEqual(adapter.last_query.mode if adapter.last_query else None, "hybrid")
        self.assertEqual(results[0].retrieval_mode, "hybrid")

    def test_service_normalizes_unknown_query_mode_to_keyword(self) -> None:
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

        service.search(LocalIndexQuery(query="robotics", project_id="demo_proj", mode="semantic"))

        self.assertEqual(adapter.last_query.mode if adapter.last_query else None, "keyword")

    def test_empty_query_short_circuits(self) -> None:
        service = LocalIndexService(FakeLocalIndexAdapter())

        self.assertEqual(service.search(LocalIndexQuery(query=" ", project_id="demo_proj")), [])

    def test_lancedb_adapter_has_clear_optional_dependency_boundary(self) -> None:
        if is_lancedb_available():
            self.assertIsNotNone(LanceDBLocalIndexAdapter)
            return
        with self.assertRaisesRegex(RuntimeError, "lancedb is not installed"):
            LanceDBLocalIndexAdapter()


if __name__ == "__main__":
    unittest.main()
