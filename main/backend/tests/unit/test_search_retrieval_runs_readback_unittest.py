from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from app.services.search.retrieval_runs import (
    RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER,
    SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
    persist_search_retrieval_run_record,
    read_search_retrieval_run_record,
    run_search_retrieval_run_readback_gate,
)
from app.services.search.vector_contracts import build_retrieval_run_record, build_search_evidence_hits


pytestmark = pytest.mark.unit


class SearchRetrievalRunsReadbackUnitTestCase(unittest.TestCase):
    def _fixture_hits(self) -> tuple[str, list[dict]]:
        return build_search_evidence_hits(
            [
                {
                    "document_id": "doc-a",
                    "project_key": "demo_proj",
                    "object_type": "policy_chunk",
                    "object_id": "doc-a",
                    "chunk_id": "doc-a:chunk:0",
                    "source_id": "source-a",
                    "score": 1.7,
                    "mode": "bm25",
                    "backend": "opensearch",
                },
                {
                    "document_id": "doc-b",
                    "project_key": "demo_proj",
                    "object_type": "policy_chunk",
                    "object_id": "doc-b",
                    "chunk_id": "doc-b:chunk:0",
                    "source_id": "source-b",
                    "score": 0.92,
                    "mode": "vector",
                    "backend": "qdrant",
                },
            ],
            query="robotics policy",
            project_key="demo_proj",
            rank_mode="hybrid",
            state="CA",
            modality="text",
            top_k=2,
        )

    def test_run_readback_gate_persists_branches_and_hit_details(self) -> None:
        query_group_id, hits = self._fixture_hits()
        with tempfile.TemporaryDirectory(prefix="search-retrieval-runs-") as tmp_dir:
            path = Path(tmp_dir) / "retrieval_runs.jsonl"
            result = run_search_retrieval_run_readback_gate(
                query="robotics policy",
                query_group_id=query_group_id,
                evidence_hits=hits,
                path=path,
                project_key="demo_proj",
                rank_mode="hybrid",
                state="CA",
                modality="text",
                top_k=2,
            )

            self.assertEqual(result["contract_version"], SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION)
            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["write_performed"])
            self.assertTrue(result["readback_performed"])
            self.assertEqual(result["closed_repo_local_blockers"], [RETRIEVAL_RUNS_BRANCHES_HITS_BLOCKER])
            self.assertEqual(result["remaining_repo_local_blockers"], [])

            record = result["readback_record"]
            self.assertEqual(record, read_search_retrieval_run_record(path, result["run_id"]))
            self.assertEqual(record["query_group_id"], query_group_id)
            self.assertEqual(record["branch_count"], 2)
            self.assertEqual(record["hit_count"], 2)
            self.assertEqual(len(record["retrieval_branches"]), 2)
            self.assertEqual(len(record["retrieval_hits"]), 2)
            self.assertEqual(
                sorted(hit["matrix_branch_id"] for hit in record["retrieval_hits"]),
                sorted(branch["matrix_branch_id"] for branch in record["retrieval_branches"]),
            )

    def test_persist_reads_back_latest_matching_run(self) -> None:
        query_group_id, hits = self._fixture_hits()
        record = build_retrieval_run_record(
            query="robotics policy",
            query_group_id=query_group_id,
            evidence_hits=hits,
            project_key="demo_proj",
            rank_mode="hybrid",
            state="CA",
            modality="text",
            top_k=2,
        )

        with tempfile.TemporaryDirectory(prefix="search-retrieval-runs-") as tmp_dir:
            path = Path(tmp_dir) / "retrieval_runs.jsonl"
            result = persist_search_retrieval_run_record(record, path=path)
            readback = read_search_retrieval_run_record(path, record["run_id"])

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["branch_count"], 2)
        self.assertEqual(result["hit_count"], 2)
        self.assertEqual(readback["run_id"], record["run_id"])


if __name__ == "__main__":
    unittest.main()
