from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from app.api import ingest as ingest_api

pytestmark = pytest.mark.unit


class IngestSourceCollectAuthorityUnitTest(unittest.TestCase):
    def test_run_source_collect_batch_uses_authority_output_summary_for_sync_result(self):
        dashboard = ingest_api.GraphStructuredDashboardParams(project_key="demo_proj", async_mode=False)
        fake_run_result = {
            "authority_output": {
                "contract_version": "source_library.authority_output.v1",
                "summary": {
                    "record_stats": {"normalized": 3, "errors": 0},
                    "write_effects": {"inserted": 2, "updated": 1, "skipped": 0, "errors": []},
                    "bootstrap_required": False,
                },
            },
            "legacy_result": {
                "result": {
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "errors": [],
                }
            },
        }

        with patch("app.api.ingest.bind_project", return_value=nullcontext()), patch(
            "app.services.collect_runtime.run_source_library_item_compat",
            return_value=fake_run_result,
        ):
            result = ingest_api._run_source_collect_batch(
                project_key="demo_proj",
                entry_id="n-1",
                intent="general",
                query_terms=["ACME"],
                dashboard=dashboard,
                llm_assist=False,
                batch_id="source_collect:n-1:general:b1",
                source_item_key="existing.item",
            )

        self.assertEqual(result["type"], "source_collect")
        self.assertEqual(result["result"]["sources_inserted"], 2)
        self.assertEqual(result["result"]["sources_updated"], 1)
        self.assertEqual(result["result"]["skipped"], 0)
        self.assertEqual(result["result"]["errors"], [])
        self.assertFalse(result["result"]["bootstrap_required"])


if __name__ == "__main__":
    unittest.main()
