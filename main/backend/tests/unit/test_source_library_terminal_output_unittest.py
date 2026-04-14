from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.terminal_output import CONTRACT_VERSION, to_terminal_output_dto


class SourceLibraryTerminalOutputUnitTestCase(unittest.TestCase):
    def test_protocol_search_ok_and_request_normalization(self) -> None:
        legacy = {
            "item_key": "report.market",
            "channel_key": "market.stats",
            "item_type": "user_defined",
            "managed_by": "user",
            "params": {
                "query_terms": ["semiconductor", "ai"],
                "days_back": 7,
                "page": 2,
                "start_offset": 20,
                "cursor": "abc",
                "limit": 10,
                "per_keyword_limit": 3,
                "max_candidates": 100,
                "ingest_limit": 25,
            },
            "result": {
                "records": [
                    {
                        "record_id": "rec-1",
                        "url": "https://example.com/a",
                        "title": "Semiconductor update",
                        "content_text": "AI demand remains strong.",
                    }
                ],
                "errors": [],
                "execution_request": {"source_mode": "protocol_search"},
            },
        }

        dto = to_terminal_output_dto(legacy)

        self.assertEqual(dto["contract_version"], CONTRACT_VERSION)
        self.assertEqual(dto["status"], "ok")
        self.assertEqual(dto["source_mode"], "protocol_search")
        self.assertNotIn("channel_key", dto["item"])
        self.assertEqual(dto["item"]["item_type"], "user_defined")
        self.assertEqual(dto["item"]["managed_by"], "user")
        self.assertIsNone(dto["request"]["project_key"])
        self.assertEqual(dto["request"]["query_terms"], ["semiconductor", "ai"])
        self.assertEqual(dto["request"]["time_window"]["days_back"], 7)
        self.assertNotIn("source_params", dto["request"])
        self.assertEqual(dto["request"]["paging"]["page"], 2)
        self.assertEqual(dto["request"]["paging"]["start_offset"], 20)
        self.assertEqual(dto["request"]["paging"]["cursor"], "abc")
        self.assertEqual(dto["request"]["limits"]["limit"], 10)
        self.assertEqual(dto["request"]["limits"]["per_keyword_limit"], 3)
        self.assertEqual(dto["request"]["limits"]["max_candidates"], 100)
        self.assertEqual(dto["request"]["limits"]["ingest_limit"], 25)
        self.assertEqual(len(dto["results"]["records"]), 1)
        self.assertEqual(dto["results"]["stats"]["normalized"], 1)
        self.assertEqual(dto["meta"]["reason_code"], "ok")

    def test_provider_harvest_partial_status(self) -> None:
        legacy = {
            "item_key": "crawler.company",
            "channel_key": "crawler.demo",
            "params": {"query": "chip stocks"},
            "result": {
                "records": [
                    {
                        "record_id": "crawler-1",
                        "url": "https://example.com/crawl",
                        "title": "Crawler result",
                        "content_text": "harvested text",
                    }
                ],
                "errors": ["upstream timeout"],
                "execution_request": {"source_mode": "provider_harvest"},
            },
        }

        dto = to_terminal_output_dto(legacy)

        self.assertEqual(dto["source_mode"], "provider_harvest")
        self.assertEqual(dto["status"], "partial")
        self.assertEqual(dto["request"]["query_terms"], ["chip stocks"])
        self.assertEqual(dto["results"]["stats"]["normalized"], 1)
        self.assertGreaterEqual(dto["results"]["stats"]["errors"], 1)
        self.assertEqual(dto["meta"]["reason_code"], "fetch_errors")

    def test_site_search_partial_and_stats(self) -> None:
        legacy = {
            "item_key": "report.root_site_search",
            "channel_key": "handler.cluster",
            "params": {"query_terms": ["earnings"]},
            "result": {
                "candidates": ["https://a", "https://b", "https://c"],
                "by_url": [
                    {
                        "url": "https://a",
                        "channel_key": "url_pool",
                        "error": None,
                        "result": {"status": "fetched", "title": "A", "content_text": "text a"},
                    }
                ],
                "error_details": [{"url": "https://b", "error": "parse failed"}],
                "execution_request": {"source_mode": "site_search"},
            },
        }

        dto = to_terminal_output_dto(legacy)

        self.assertEqual(dto["source_mode"], "site_search")
        self.assertEqual(dto["status"], "partial")
        self.assertEqual(dto["results"]["stats"]["fetched"], 3)
        self.assertEqual(dto["results"]["stats"]["normalized"], 3)
        self.assertEqual(dto["results"]["stats"]["dropped"], 0)
        self.assertEqual(dto["results"]["stats"]["errors"], 1)
        self.assertEqual(len(dto["results"]["records"]), 3)
        self.assertEqual(dto["results"]["records"][1]["url"], "https://b")

    def test_url_execution_error_status(self) -> None:
        legacy = {
            "item_key": "url_pool.default",
            "channel_key": None,
            "params": {"urls": ["https://a", "https://b"]},
            "result": {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": ["channel not found"],
                "by_url": [
                    {"url": "https://a", "channel_key": "url_pool", "error": "invalid url", "result": None},
                    {"url": "https://b", "channel_key": "url_pool", "error": "runtime failure", "result": None},
                ],
                "execution_request": {"source_mode": "url_execution"},
            },
        }

        dto = to_terminal_output_dto(legacy)

        self.assertEqual(dto["source_mode"], "url_execution")
        self.assertEqual(dto["status"], "error")
        self.assertEqual(dto["results"]["stats"]["fetched"], 2)
        self.assertEqual(dto["results"]["stats"]["normalized"], 0)
        self.assertGreaterEqual(dto["results"]["stats"]["errors"], 3)

    def test_empty_payload_is_compatible(self) -> None:
        dto = to_terminal_output_dto(None)

        self.assertEqual(dto["contract_version"], CONTRACT_VERSION)
        self.assertEqual(dto["status"], "error")
        self.assertEqual(dto["source_mode"], "protocol_search")
        self.assertNotIn("channel_key", dto["item"])
        self.assertGreaterEqual(dto["results"]["stats"]["errors"], 1)
        self.assertEqual(dto["meta"]["reason_code"], "fetch_errors")

    def test_protocol_search_retryable_queue_is_normalized(self) -> None:
        legacy = {
            "item_key": "news.general.regulation",
            "channel_key": "news.google.general",
            "params": {"keywords": ["OpenAI"], "limit": 30},
            "result": {
                "queued": 30,
                "retryable": True,
                "retryable_queued": 30,
                "decode_breakdown": {"rate_limited": 30},
                "errors": [],
                "execution_request": {"source_mode": "protocol_search"},
            },
        }

        dto = to_terminal_output_dto(legacy)

        self.assertEqual(dto["status"], "ok")
        self.assertEqual(dto["results"]["records"], [])
        self.assertEqual(dto["meta"]["retryable"], True)
        self.assertEqual(dto["meta"]["reason_code"], "empty")


if __name__ == "__main__":
    unittest.main()
