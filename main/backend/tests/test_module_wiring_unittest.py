from __future__ import annotations

import unittest

from app.services.discovery.application import DiscoveryApplicationService
from app.services.extraction.application import ExtractionApplicationService
from app.services.indexer.application import IndexingApplicationService


class ModuleWiringTestCase(unittest.TestCase):
    def test_application_services_construct(self):
        discovery = DiscoveryApplicationService.build_default()
        self.assertIsNotNone(discovery)

        extraction = ExtractionApplicationService()
        self.assertIsNotNone(extraction)

        indexing = IndexingApplicationService()
        self.assertIsNotNone(indexing)

        # Social ingest imports adapter modules that require Python >=3.10
        # in this repository runtime (dataclass slots usage).
        try:
            from app.services.ingest.social_application import SocialIngestApplicationService
        except TypeError:
            self.skipTest("Current interpreter does not support required dataclass slots settings")
            return
        social_ingest = SocialIngestApplicationService()
        self.assertIsNotNone(social_ingest)


if __name__ == "__main__":
    unittest.main()
