from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from sqlalchemy.exc import OperationalError

from app.models import base


class _FakeSession:
    def __init__(self) -> None:
        self.commit = Mock()
        self.rollback = Mock()


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self):
        self.calls += 1
        session = _FakeSession()
        manager = Mock()
        manager.__enter__ = Mock(return_value=session)
        manager.__exit__ = Mock(return_value=None)
        return manager


class DbSessionReliabilityUnitTest(unittest.TestCase):
    def test_get_session_setup_sqls_contains_timeout_and_schema(self):
        original_timeout = base.settings.db_statement_timeout_ms
        original_lock_timeout = base.settings.db_lock_timeout_ms
        original_idle_timeout = base.settings.db_idle_in_transaction_timeout_ms
        original_isolation = base.settings.db_transaction_isolation_level
        original_url = base.settings.database_url
        try:
            base.settings.db_statement_timeout_ms = 15000
            base.settings.db_lock_timeout_ms = 2500
            base.settings.db_idle_in_transaction_timeout_ms = 100000
            base.settings.db_transaction_isolation_level = "repeatable read"
            base.settings.database_url = "postgresql+psycopg2://localhost/test"
            sqls = base._get_session_setup_sqls("project_demo")
        finally:
            base.settings.db_statement_timeout_ms = original_timeout
            base.settings.db_lock_timeout_ms = original_lock_timeout
            base.settings.db_idle_in_transaction_timeout_ms = original_idle_timeout
            base.settings.db_transaction_isolation_level = original_isolation
            base.settings.database_url = original_url

        self.assertIn("SET LOCAL statement_timeout = 15000", sqls)
        self.assertIn("SET LOCAL lock_timeout = 2500", sqls)
        self.assertIn("SET LOCAL idle_in_transaction_session_timeout = 100000", sqls)
        self.assertIn("SET LOCAL TRANSACTION ISOLATION LEVEL REPEATABLE READ", sqls)
        self.assertIn('SET search_path TO "project_demo"', sqls)

    def test_get_session_setup_sqls_disable_timeout_when_zero(self):
        original_timeout = base.settings.db_statement_timeout_ms
        original_lock_timeout = base.settings.db_lock_timeout_ms
        original_idle_timeout = base.settings.db_idle_in_transaction_timeout_ms
        original_isolation = base.settings.db_transaction_isolation_level
        original_url = base.settings.database_url
        try:
            base.settings.db_statement_timeout_ms = 0
            base.settings.db_lock_timeout_ms = 0
            base.settings.db_idle_in_transaction_timeout_ms = 0
            base.settings.db_transaction_isolation_level = "unknown"
            base.settings.database_url = "postgresql+psycopg2://localhost/test"
            sqls = base._get_session_setup_sqls(None)
        finally:
            base.settings.db_statement_timeout_ms = original_timeout
            base.settings.db_lock_timeout_ms = original_lock_timeout
            base.settings.db_idle_in_transaction_timeout_ms = original_idle_timeout
            base.settings.db_transaction_isolation_level = original_isolation
            base.settings.database_url = original_url

        self.assertEqual(sqls, [])

    def test_get_session_setup_sqls_non_postgres_keeps_only_schema(self):
        original_timeout = base.settings.db_statement_timeout_ms
        original_lock_timeout = base.settings.db_lock_timeout_ms
        original_idle_timeout = base.settings.db_idle_in_transaction_timeout_ms
        original_isolation = base.settings.db_transaction_isolation_level
        original_url = base.settings.database_url
        try:
            base.settings.db_statement_timeout_ms = 15000
            base.settings.db_lock_timeout_ms = 3000
            base.settings.db_idle_in_transaction_timeout_ms = 120000
            base.settings.db_transaction_isolation_level = "serializable"
            base.settings.database_url = "sqlite+pysqlite:///:memory:"
            sqls = base._get_session_setup_sqls("project_demo")
        finally:
            base.settings.db_statement_timeout_ms = original_timeout
            base.settings.db_lock_timeout_ms = original_lock_timeout
            base.settings.db_idle_in_transaction_timeout_ms = original_idle_timeout
            base.settings.db_transaction_isolation_level = original_isolation
            base.settings.database_url = original_url

        self.assertEqual(sqls, ['SET search_path TO "project_demo"'])

    def test_run_with_session_retry_retries_on_transient_operational_error(self):
        session_factory = _FakeSessionFactory()
        attempts = {"value": 0}

        def _operation(_session):
            attempts["value"] += 1
            if attempts["value"] == 1:
                raise OperationalError("SELECT 1", {}, Exception("deadlock detected"))
            return "ok"

        result = base.run_with_session_retry(
            _operation,
            session_factory=session_factory,
            max_attempts=3,
            base_backoff_ms=1,
            max_backoff_ms=1,
            log_context={"test_case": "transient"},
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["value"], 2)
        self.assertEqual(session_factory.calls, 2)

    def test_run_with_session_retry_does_not_retry_non_retriable_error(self):
        session_factory = _FakeSessionFactory()
        attempts = {"value": 0}

        def _operation(_session):
            attempts["value"] += 1
            raise ValueError("bad payload")

        with self.assertRaises(ValueError):
            base.run_with_session_retry(
                _operation,
                session_factory=session_factory,
                max_attempts=3,
                base_backoff_ms=1,
                max_backoff_ms=1,
                log_context={"test_case": "non_retriable"},
            )

        self.assertEqual(attempts["value"], 1)
        self.assertEqual(session_factory.calls, 1)

    def test_run_with_session_retry_concurrent_threads_isolated(self):
        lock = threading.Lock()
        first_seen_by_key: dict[str, bool] = {}

        def _worker(key: str) -> str:
            session_factory = _FakeSessionFactory()

            def _operation(_session):
                with lock:
                    if not first_seen_by_key.get(key):
                        first_seen_by_key[key] = True
                        raise OperationalError("SELECT 1", {}, Exception("could not serialize access due to concurrent update"))
                return key

            return base.run_with_session_retry(
                _operation,
                session_factory=session_factory,
                max_attempts=2,
                base_backoff_ms=1,
                max_backoff_ms=1,
                log_context={"worker": key},
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = sorted(executor.map(_worker, ["a", "b", "c", "d"]))

        self.assertEqual(results, ["a", "b", "c", "d"])


if __name__ == "__main__":
    unittest.main()
