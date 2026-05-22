from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services import document_queries  # noqa: E402
from scripts.check_policy_state_document_query_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    REQUIRED_HELPER_CALLS,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class PolicyStateDocumentQueryBoundaryUnitTestCase(unittest.TestCase):
    def test_checker_passes_for_policy_state_endpoint_boundary(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(result["surface"]["path"], "main/backend/app/api/policies.py")
        self.assertEqual(result["surface"]["function"], "get_state_policies")
        self.assertFalse(result["surface"]["missing_imports"])
        self.assertFalse(result["surface"]["missing_calls"])
        self.assertFalse(result["surface"]["direct_document_extracted_data_reads"])
        self.assertFalse(result["helper"]["missing_definitions"])

    def test_policy_state_helpers_are_exported_and_compile(self) -> None:
        self.assertEqual(set(REQUIRED_HELPER_CALLS) - set(document_queries.__all__), set())

        compiled_state = str(document_queries.policy_state_condition("ca").compile(compile_kwargs={"literal_binds": True}))
        compiled_time = str(document_queries.policy_time_expr().compile(compile_kwargs={"literal_binds": True}))

        self.assertIn("policy", compiled_state)
        self.assertIn("state", compiled_state)
        self.assertIn("effective_time", compiled_time)
        self.assertIn("source_time", compiled_time)


if __name__ == "__main__":
    unittest.main()
