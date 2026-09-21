from __future__ import annotations

import unittest
from typing import Annotated, get_args, get_origin, get_type_hints

from scripts.check_crawler_provider_handoff_contract import build_check, build_fixture_payload


class CrawlerProviderHandoffContractAuthorityTest(unittest.TestCase):
    def test_crawler_provider_handoff_contract_authority_metadata(self) -> None:
        expected = {
            build_fixture_payload: (
                "kit:non-authoritative derived_as=generated_evidence fact_source=repo_local.frontdoor_route_profile.fixture "
                "witness=test:test_crawler_provider_handoff_contract_authority_metadata"
            ),
            build_check: (
                "kit:non-authoritative derived_as=preflight fact_source=repo_local.frontdoor_route_profile.contract "
                "witness=test:test_crawler_provider_handoff_contract_authority_metadata"
            ),
        }
        for function, metadata in expected.items():
            with self.subTest(function=function.__name__):
                return_hint = get_type_hints(function, include_extras=True)["return"]
                self.assertIs(get_origin(return_hint), Annotated)
                self.assertEqual(get_args(return_hint)[1], metadata)


if __name__ == "__main__":
    unittest.main()
