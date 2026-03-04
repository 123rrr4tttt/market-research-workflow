from __future__ import annotations

import unittest

from app.models import base


class DbSessionReliabilityUnitTest(unittest.TestCase):
    def test_get_session_setup_sqls_contains_timeout_and_schema(self):
        original_timeout = base.settings.db_statement_timeout_ms
        original_url = base.settings.database_url
        try:
            base.settings.db_statement_timeout_ms = 15000
            base.settings.database_url = "postgresql+psycopg2://localhost/test"
            sqls = base._get_session_setup_sqls("project_demo")
        finally:
            base.settings.db_statement_timeout_ms = original_timeout
            base.settings.database_url = original_url

        self.assertIn("SET LOCAL statement_timeout = 15000", sqls)
        self.assertIn('SET search_path TO "project_demo"', sqls)

    def test_get_session_setup_sqls_disable_timeout_when_zero(self):
        original_timeout = base.settings.db_statement_timeout_ms
        original_url = base.settings.database_url
        try:
            base.settings.db_statement_timeout_ms = 0
            base.settings.database_url = "postgresql+psycopg2://localhost/test"
            sqls = base._get_session_setup_sqls(None)
        finally:
            base.settings.db_statement_timeout_ms = original_timeout
            base.settings.database_url = original_url

        self.assertEqual(sqls, [])


if __name__ == "__main__":
    unittest.main()
