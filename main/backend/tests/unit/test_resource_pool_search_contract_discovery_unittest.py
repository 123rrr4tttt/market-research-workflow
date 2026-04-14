from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.search_contract_discovery import discover_search_contract


class SearchContractDiscoveryUnitTestCase(unittest.TestCase):
    def test_discover_search_contract_persists_best_template_profile(self) -> None:
        entry = {
            "site_url": "https://example.com",
            "domain": "example.com",
            "entry_type": "search_template",
            "template": None,
            "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            "source": "manual",
            "source_ref": {},
            "tags": ["keep"],
            "enabled": True,
            "extra": {},
        }

        def _fake_execute_search_template(*, template, query_terms, params, probe_timeout, allow_term_fallback, entry_domain):  # noqa: ANN001
            if "search?q={{q}}" in template and query_terms == ["robotics pricing"]:
                selected = [SimpleNamespace(url="https://example.com/posts/robotics-pricing")]
                raw = [SimpleNamespace(url="https://example.com/posts/robotics-pricing")]
            else:
                selected = []
                raw = []
            return SimpleNamespace(
                raw_candidates=raw,
                selected_candidates=selected,
                diagnostics={"search_service": "basic"},
            )

        with patch(
            "app.services.resource_pool.search_contract_discovery.get_site_entry_by_url",
            return_value=entry,
        ), patch(
            "app.services.resource_pool.search_contract_discovery.execute_search_template",
            side_effect=_fake_execute_search_template,
        ), patch(
            "app.services.resource_pool.search_contract_discovery.upsert_site_entry",
            side_effect=lambda **kwargs: kwargs,
        ) as upsert:
            result = discover_search_contract(
                scope="project",
                project_key="demo",
                site_url="https://example.com",
                query_terms=["robotics"],
                suffixes=["", "pricing"],
                persist=True,
            )

        self.assertEqual(result.best_template, "https://example.com/search?q={{q}}")
        self.assertEqual(result.best_suffix, "pricing")
        self.assertGreater(result.best_score, 0)
        self.assertIsNotNone(result.persisted_entry)
        upsert.assert_called_once()
        persisted_extra = upsert.call_args.kwargs["extra"]
        self.assertEqual(persisted_extra["search_contract_profile"]["best_suffix"], "pricing")


if __name__ == "__main__":
    unittest.main()
