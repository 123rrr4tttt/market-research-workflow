from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.persistence.graph_node_reader import GraphNodeReader


class _FakeScalarResult:
    def scalars(self):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.statements = []

    def execute(self, stmt):  # noqa: ANN001
        self.statements.append(stmt)
        return _FakeScalarResult()


class GraphPersistenceReaderUnitTestCase(unittest.TestCase):
    def test_reader_filters_by_project_key(self):
        session = _FakeSession()
        reader = GraphNodeReader(session, project_key="demo_proj")
        reader.load_graph(limit=10)

        rendered = "\n".join(str(stmt) for stmt in session.statements)
        self.assertIn("project_key", rendered)


if __name__ == "__main__":
    unittest.main()
