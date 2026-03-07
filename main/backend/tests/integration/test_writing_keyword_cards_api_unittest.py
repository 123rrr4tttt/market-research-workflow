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

    from app.contracts.schemas.writing import (
        KeywordCardDetailResponse,
        KeywordCardItem,
        KeywordCardListResponse,
        KeywordCardPreviewResponse,
        SuggestItem,
        SuggestResponse,
    )
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingKeywordCardsApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing keyword card tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "writing-keyword-cards"}

    def test_keyword_cards_success(self):
        response_model = KeywordCardListResponse(
            cards=[
                KeywordCardItem(
                    card_id="card-1",
                    source_type="document",
                    title="Doc",
                    snippet="Snippet",
                    score=0.8,
                )
            ],
            selection_hash="sel-1",
        )
        with patch("app.api.writing.aggregate_cards", return_value=response_model):
            response = self.client.post("/api/v1/writing/keyword-cards", json={"query": "market", "project_key": "demo_proj"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["cards"][0]["card_id"], "card-1")

    def test_keyword_card_preview_and_detail(self):
        with (
            patch(
                "app.api.writing.get_card_preview",
                return_value=KeywordCardPreviewResponse(
                    card_id="card-1",
                    title="Doc",
                    snippet="Preview",
                    score=0.8,
                    source_type="document",
                ),
            ),
            patch(
                "app.api.writing.get_card_detail",
                return_value=KeywordCardDetailResponse(
                    card_id="card-1",
                    title="Doc",
                    score=0.8,
                    source_type="document",
                ),
            ),
        ):
            preview = self.client.post(
                "/api/v1/writing/keyword-cards/preview",
                json={"project_key": "demo_proj", "card_id": "card-1"},
                headers=self.headers,
            )
            detail = self.client.get("/api/v1/writing/cards/card-1", headers=self.headers)

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(preview.json()["data"]["card_id"], "card-1")
        self.assertEqual(detail.json()["data"]["card_id"], "card-1")

    def test_suggest_success(self):
        with patch(
            "app.api.writing.suggest",
            return_value=SuggestResponse(
                items=[SuggestItem(kind="template", id="market_weekly", label="Market Weekly")],
                suggest_type="template",
                query="market",
            ),
        ):
            response = self.client.get("/api/v1/writing/suggest", params={"query": "market", "mode": "template"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"][0]["id"], "market_weekly")


if __name__ == "__main__":
    unittest.main()
