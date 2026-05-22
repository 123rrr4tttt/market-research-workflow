from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_prompt_time_density_consumer_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    build_check,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class PromptTimeDensityConsumerBoundaryUnitTest(unittest.TestCase):
    def test_checker_passes_for_prompt_time_density_facade_slice(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["topic_id"], "2026-03-14-consumer-side-modularization")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["validation"]["passed"])
        self.assertFalse(result["surface"]["direct_extracted_data_reads"])
        self.assertFalse(result["surface"]["missing_document_view_imports"])
        self.assertFalse(result["facade"]["missing_definitions"])

        functions = {item["name"]: item for item in result["surface"]["functions"]}
        self.assertEqual(
            set(functions),
            {
                "resolve_document_effective_time_provenance",
                "_prompt_group_of",
                "_source_domain_of",
            },
        )
        for function in functions.values():
            self.assertTrue(function["passed"], function)
            self.assertFalse(function["missing_facade_calls"], function)


if __name__ == "__main__":
    unittest.main()
