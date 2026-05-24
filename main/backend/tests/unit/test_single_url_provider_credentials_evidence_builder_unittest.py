from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.build_single_url_provider_credentials_evidence import (  # noqa: E402
    build_provider_credentials_evidence,
)
from scripts.check_single_url_official_api_provider_maturity import (  # noqa: E402
    PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
)


class SingleUrlProviderCredentialsEvidenceBuilderTestCase(unittest.TestCase):
    def test_builds_configured_only_evidence_without_secret_values(self) -> None:
        evidence = build_provider_credentials_evidence(
            env={
                "TWITTER_BEARER_TOKEN": "secret-bearer-token",
                "SERPER_API_KEY": "secret-serper-key",
            }
        )

        self.assertEqual(evidence["contract_version"], PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION)
        self.assertFalse(evidence["credential_material_logged"])
        self.assertEqual(evidence["closure"]["configured_provider_count"], 2)
        self.assertEqual(evidence["closure"]["live_quota_validated_provider_count"], 0)
        self.assertFalse(evidence["closure"]["provider_credentials_beyond_crossref_satisfied"])
        rendered = str(evidence)
        self.assertNotIn("secret-bearer-token", rendered)
        self.assertNotIn("secret-serper-key", rendered)
        providers = {provider["provider_key"]: provider for provider in evidence["providers"]}
        self.assertEqual(providers["x_twitter"]["live_probe_status"], "configured_only")
        self.assertEqual(providers["x_twitter"]["quota_status"], "configured_only")
        self.assertFalse(providers["x_twitter"]["live_probe_authorized"])
        self.assertFalse(providers["x_twitter"]["provider_specific_quota_validated"])


if __name__ == "__main__":
    unittest.main()
