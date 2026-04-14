from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.market import handle_market


class SourceLibraryMarketAdapterUnitTestCase(unittest.TestCase):
    def test_handle_market_passes_time_and_pagination_params(self) -> None:
        payload = {
            "query_terms": ["semiconductor"],
            "max_items": 15,
            "provider": "google",
            "language": "en",
            "start_offset": 11,
            "days_back": 7,
            "enable_extraction": False,
        }

        with patch("app.services.ingest.market_web.collect_market_info", return_value={"inserted": 1}) as mocked:
            result = handle_market(payload, None)

        self.assertEqual(result, {"inserted": 1})
        mocked.assert_called_once_with(
            keywords=["semiconductor"],
            limit=15,
            enable_extraction=False,
            provider="google",
            start_offset=11,
            days_back=7,
            language="en",
        )


if __name__ == "__main__":
    unittest.main()
