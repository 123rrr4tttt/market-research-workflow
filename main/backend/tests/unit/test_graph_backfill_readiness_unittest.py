from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.backfill_graph_nodes import run_graph_node_backfill
from app.services.graph.models import Graph, GraphNode


class _FakeResult:
    def __init__(self, docs):
        self._docs = docs

    def scalars(self):
        return self

    def all(self):
        return self._docs


class _FakeSession:
    def __init__(self, docs):
        self._docs = docs
        self.commits = 0
        self.rollbacks = 0

    def execute(self, _query):  # noqa: ANN001
        return _FakeResult(self._docs)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _doc(doc_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=doc_id, extracted_data={"entities": [{"text": "Acme"}]})


def _graph() -> Graph:
    return Graph(
        nodes={"Entity:acme": GraphNode(type="Entity", id="Acme", properties={"name": "Acme"})},
        edges=[],
        schema_version="v1",
    )


class GraphBackfillReadinessUnitTestCase(unittest.TestCase):
    def test_backfill_dry_run_does_not_instantiate_writer_or_commit(self):
        session = _FakeSession([_doc(1)])

        with patch(
            "app.services.graph.backfill_graph_nodes.normalize_document",
            return_value=SimpleNamespace(doc_id=1),
        ), patch(
            "app.services.graph.backfill_graph_nodes.build_graph",
            return_value=_graph(),
        ), patch("app.services.graph.backfill_graph_nodes.GraphNodeWriter") as writer_cls:
            result = run_graph_node_backfill(session, limit=1, dry_run=True)

        self.assertEqual(result.scanned_docs, 1)
        self.assertEqual(result.written_nodes, 1)
        self.assertEqual(result.next_resume_token, 1)
        self.assertEqual(session.commits, 0)
        self.assertEqual(session.rollbacks, 0)
        writer_cls.assert_not_called()

    def test_backfill_apply_rolls_back_and_reraises_writer_failure(self):
        session = _FakeSession([_doc(1)])

        with patch(
            "app.services.graph.backfill_graph_nodes.normalize_document",
            return_value=SimpleNamespace(doc_id=1),
        ), patch(
            "app.services.graph.backfill_graph_nodes.build_graph",
            return_value=_graph(),
        ), patch("app.services.graph.backfill_graph_nodes.GraphNodeWriter") as writer_cls:
            writer = writer_cls.return_value
            writer.persist_graph_nodes.side_effect = RuntimeError("write failed")

            with self.assertRaisesRegex(RuntimeError, "write failed"):
                run_graph_node_backfill(session, limit=1, dry_run=False)

        self.assertEqual(session.commits, 0)
        self.assertEqual(session.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
