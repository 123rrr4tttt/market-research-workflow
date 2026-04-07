from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WebUiRouteCompatMatrixTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"web ui route tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_legacy_html_routes_redirect_to_modern_frontend_hash_targets(self):
        cases = [
            ("/graph.html?type=market", "http://frontend.local/#graph.html%3Ftype%3Dmarket"),
            ("/market-graph.html?limit=20", "http://frontend.local/#graph.html%3Ftype%3Dmarket%26limit%3D20"),
            ("/policy-graph.html?limit=10", "http://frontend.local/#graph.html%3Ftype%3Dpolicy%26limit%3D10"),
            ("/social-media-graph.html?limit=5", "http://frontend.local/#graph.html%3Ftype%3Dsocial%26limit%3D5"),
            ("/topic-dashboard.html?topic=company", "http://frontend.local/#topic-dashboard.html%3Ftopic%3Dcompany"),
        ]

        with patch.dict("os.environ", {"MODERN_FRONTEND_URL": "http://frontend.local"}, clear=False):
            for path, expected_location in cases:
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 302, msg=f"path={path} body={response.text}")
                self.assertEqual(response.headers.get("location"), expected_location, msg=f"path={path}")


if __name__ == "__main__":
    unittest.main()
