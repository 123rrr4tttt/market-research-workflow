from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.models.entities import KeywordHistory
from app.services import keyword_memory


class _FakeExecResult:
    def __init__(self, *, scalar_one_or_none=None, scalar=None, scalars=None):
        self._scalar_one_or_none = scalar_one_or_none
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self):
        return self._scalar_one_or_none

    def scalar(self):
        return self._scalar

    def scalars(self):
        return self._scalars


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []
        self.added = []
        self.commits = 0
        self.refreshed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, stmt):
        self.executed.append(stmt)
        if not self._results:
            raise AssertionError("Unexpected session.execute call")
        return self._results.pop(0)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        self.refreshed.append(row)


class _SessionFactory:
    def __init__(self, sessions):
        self._sessions = list(sessions)

    def __call__(self):
        if not self._sessions:
            raise AssertionError("Unexpected SessionLocal() call")
        return self._sessions.pop(0)


class KeywordMemoryUnitTestCase(unittest.TestCase):
    def test_normalize_keyword_compacts_and_lowercases(self):
        self.assertEqual(keyword_memory.normalize_keyword("  Foo   BAR\tbaz  "), "foo bar baz")
        self.assertEqual(keyword_memory.normalize_keyword(""), "")

    def test_record_keyword_history_updates_existing_and_inserts_new(self):
        now = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
        existing = KeywordHistory(
            keyword="foo",
            normalized_keyword="foo",
            search_count=2,
            hit_count=1,
            inserted_count=5,
            rejected_count=0,
            extra={"old": 1},
        )
        session = _FakeSession(
            [
                _FakeExecResult(scalar_one_or_none=existing),
                _FakeExecResult(scalar_one_or_none=None),
            ]
        )

        with (
            patch("app.services.keyword_memory.SessionLocal", new=_SessionFactory([session])),
            patch("app.services.keyword_memory._now_utc", return_value=now),
        ):
            touched = keyword_memory.record_keyword_history(
                keywords=[" Foo ", "bar", "foo"],
                source="crawler",
                source_domain="example.com",
                status="ok",
                inserted=3,
                inserted_valid=1,
                rejected_count=2,
                filter_decision="allow",
                extra={"new": 2},
            )

        self.assertEqual(touched, 2)
        self.assertEqual(session.commits, 1)

        self.assertEqual(existing.search_count, 3)
        self.assertEqual(existing.hit_count, 2)
        self.assertEqual(existing.inserted_count, 8)
        self.assertEqual(existing.rejected_count, 2)
        self.assertEqual(existing.last_status, "ok")
        self.assertEqual(existing.last_source, "crawler")
        self.assertEqual(existing.last_source_domain, "example.com")
        self.assertEqual(existing.last_filter_decision, "allow")
        self.assertEqual(existing.last_seen_at, now)
        self.assertEqual(existing.extra, {"new": 2})

        self.assertEqual(len(session.added), 1)
        inserted_row = session.added[0]
        self.assertEqual(inserted_row.keyword, "bar")
        self.assertEqual(inserted_row.normalized_keyword, "bar")
        self.assertEqual(inserted_row.search_count, 1)
        self.assertEqual(inserted_row.hit_count, 1)
        self.assertEqual(inserted_row.inserted_count, 3)
        self.assertEqual(inserted_row.rejected_count, 2)
        self.assertEqual(inserted_row.first_seen_at, now)
        self.assertEqual(inserted_row.last_seen_at, now)

    def test_upsert_keyword_prior_clamps_values_and_normalizes_fields(self):
        session = _FakeSession([_FakeExecResult(scalar_one_or_none=None)])

        with patch("app.services.keyword_memory.SessionLocal", new=_SessionFactory([session])):
            row = keyword_memory.upsert_keyword_prior(
                keyword="  AI  ",
                prior_score=1.3,
                confidence=-0.2,
                source="   ",
                enabled=False,
                tags=[" a ", "", "b"],
                notes="  memo  ",
                extra={"x": 1},
            )

        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, [row])
        self.assertEqual(row.keyword, "ai")
        self.assertEqual(row.prior_score, Decimal("1.0"))
        self.assertEqual(row.confidence, Decimal("0.0"))
        self.assertEqual(row.source, "manual")
        self.assertFalse(row.enabled)
        self.assertEqual(row.tags, ["a", "b"])
        self.assertEqual(row.notes, "memo")
        self.assertEqual(row.extra, {"x": 1})

    def test_list_keyword_history_and_stats_core_paths(self):
        session_list = _FakeSession(
            [
                _FakeExecResult(
                    scalars=[
                        KeywordHistory(
                            keyword="alpha",
                            normalized_keyword="alpha",
                            search_count=1,
                            hit_count=0,
                            inserted_count=0,
                            rejected_count=0,
                        )
                    ]
                )
            ]
        )
        session_stats = _FakeSession(
            [
                _FakeExecResult(scalar=5),
                _FakeExecResult(scalar=3),
                _FakeExecResult(scalar=2),
            ]
        )
        session_factory = _SessionFactory([session_list, session_stats])

        with patch("app.services.keyword_memory.SessionLocal", new=session_factory):
            rows = keyword_memory.list_keyword_history(limit=0, q="  Foo   Bar ")
            stats = keyword_memory.keyword_memory_stats()

        self.assertEqual(len(rows), 1)
        stmt_params = session_list.executed[0].compile().params
        self.assertIn("%foo bar%", stmt_params.values())
        self.assertIn(1, stmt_params.values())

        self.assertEqual(
            stats,
            {
                "history_total": 5,
                "prior_total": 3,
                "prior_enabled": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
