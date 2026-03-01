from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeExecuteResult(self._rows)


@contextmanager
def _fake_session_local(rows):
    yield _FakeSession(rows)


class MigratedProductsTopicsEnvelopeContractTestCase(unittest.TestCase):
    def _build_app(self):
        try:
            from fastapi import FastAPI
            from app.api.products import router as products_router
            from app.api.topics import router as topics_router
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import routers for contract test: {exc}")
        app = FastAPI()
        app.include_router(products_router, prefix="/api/v1")
        app.include_router(topics_router, prefix="/api/v1")
        return app

    def test_products_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        rows = [
            SimpleNamespace(
                id=1,
                name="Product A",
                category="lottery",
                source_name="demo-source",
                source_uri="https://example.com/a",
                selector_hint=".price",
                currency="USD",
                enabled=True,
            )
        ]

        client = TestClient(self._build_app())
        with patch("app.api.products.SessionLocal", side_effect=lambda: _fake_session_local(rows)):
            response = client.get("/api/v1/products")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["data"]["items"][0]["name"], "Product A")

    def test_topics_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        rows = [
            SimpleNamespace(
                id=7,
                topic_name="California Lotto",
                domains=["example.com"],
                languages=["en"],
                keywords_seed=["lottery"],
                subreddits=["lottery"],
                enabled=True,
                description="topic description",
            )
        ]

        client = TestClient(self._build_app())
        with patch("app.api.topics.SessionLocal", side_effect=lambda: _fake_session_local(rows)):
            response = client.get("/api/v1/topics")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["data"]["items"][0]["topic_name"], "California Lotto")


if __name__ == "__main__":
    unittest.main()
