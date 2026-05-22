from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.search_template_adapters import apply_search_template_adapter_plan
from app.services.resource_pool.search_template_adapters import resolve_search_template_adapter_plan


class ResourcePoolSearchTemplateAdaptersUnitTestCase(unittest.TestCase):
    def test_known_parser_profile_is_allowed_for_parser_enhanced_domain(self) -> None:
        plan = resolve_search_template_adapter_plan(
            site_url="https://www.pymnts.com/?s={{q}}",
            entry_domain="www.pymnts.com",
            params={},
        )

        routed = apply_search_template_adapter_plan(plan=plan, params={})

        self.assertEqual(plan.adapter_key, "search_template.pymnts_card")
        self.assertEqual(routed["parser_profile"], "site_adaptive.pymnts_card")
        self.assertEqual(routed["parser_profile_resolved"], "site_adaptive.pymnts_card")
        self.assertEqual(routed["adapter_capability_status"], "allow")
        self.assertNotIn("candidate_relevance_review_required", routed)

    def test_unknown_parser_profile_downgrades_to_adapter_default(self) -> None:
        plan = resolve_search_template_adapter_plan(
            site_url="https://example.com/search?q={{q}}",
            entry_domain="example.com",
            params={},
        )

        routed = apply_search_template_adapter_plan(
            plan=plan,
            params={"parser_profile": "site_adaptive.missing_custom_profile"},
        )

        self.assertEqual(routed["parser_profile"], "site_adaptive")
        self.assertEqual(routed["parser_profile_requested"], "site_adaptive.missing_custom_profile")
        self.assertEqual(routed["parser_profile_resolved"], "site_adaptive")
        self.assertEqual(routed["adapter_capability_status"], "downgrade")
        self.assertEqual(routed["adapter_capability_reason"], "unknown_parser_profile_downgraded")

    def test_anchor_only_parser_profile_routes_to_relevance_review(self) -> None:
        plan = resolve_search_template_adapter_plan(
            site_url="https://example.com/search?q={{q}}",
            entry_domain="example.com",
            params={},
        )

        routed = apply_search_template_adapter_plan(
            plan=plan,
            params={"parser_profile": "fallback_anchor_only"},
        )

        self.assertEqual(routed["parser_profile"], "fallback_anchor_only")
        self.assertEqual(routed["parser_profile_resolved"], "fallback_anchor_only")
        self.assertEqual(routed["adapter_capability_status"], "review")
        self.assertTrue(routed["candidate_relevance_review_required"])


if __name__ == "__main__":
    unittest.main()
