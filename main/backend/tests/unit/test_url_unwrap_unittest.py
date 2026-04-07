from __future__ import annotations

import base64
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest import url_unwrap as url_unwrap_module
    from app.services.ingest.url_unwrap import list_unwrap_adapters, unwrap_url

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class UrlUnwrapUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"url unwrap unit tests require backend dependencies: {_IMPORT_ERROR}")

    def setUp(self):
        url_unwrap_module._GOOGLE_NEWS_BATCH_CACHE.clear()
        url_unwrap_module._GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT.clear()
        url_unwrap_module._GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT.clear()
        url_unwrap_module._GOOGLE_NEWS_NETWORK_NEXT_AT = 0.0
        url_unwrap_module._GOOGLE_NEWS_BACKOFF_FAILURES = 0
        url_unwrap_module._GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL = 0.0

    def test_list_unwrap_adapters_exposes_pool(self):
        names = list_unwrap_adapters()
        self.assertIn("query_wrapped_url", names)
        self.assertIn("google_news_token", names)

    def test_unwrap_url_query_wrapper_strips_tracking_and_fragment(self):
        source = (
            "https://www.google.com/url?"
            "url=https%3A%2F%2Fexample.com%2Fstory%3Futm_source%3Dfeed%26id%3D1%23section"
        )
        result = unwrap_url(source, enable_network_redirect=False)
        self.assertEqual(result.url, "https://example.com/story?id=1")
        self.assertIn("query_wrapped_url", result.steps)
        self.assertIn("strip_tracking_query", result.steps)
        self.assertIn("strip_fragment", result.steps)

    def test_unwrap_url_supports_uddg_wrapper(self):
        source = (
            "https://duckduckgo.com/l/?uddg="
            "https%3A%2F%2Fexample.org%2Freport%3Futm_medium%3Dfeed%26k%3D2"
        )
        result = unwrap_url(source, enable_network_redirect=False)
        self.assertEqual(result.url, "https://example.org/report?k=2")
        self.assertIn("query_wrapped_url", result.steps)

    def test_unwrap_url_google_news_token_adapter_extracts_embedded_url(self):
        payload = "pref https://example.net/insight?ref=google suf"
        token = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8").rstrip("=")
        source = f"https://news.google.com/rss/articles/{token}?oc=5"
        result = unwrap_url(source, enable_network_redirect=False)
        self.assertEqual(result.url, "https://example.net/insight")
        self.assertIn("google_news_token", result.steps)
        self.assertIn("strip_tracking_query", result.steps)

    def test_unwrap_url_without_network_redirect_does_not_call_requests(self):
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.requests.post") as mock_post,
        ):
            unwrap_url("https://example.com/path?utm_source=test", enable_network_redirect=False)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

    def test_unwrap_url_google_news_batch_execute_decodes_source_url(self):
        source = "https://news.google.com/rss/articles/CBMiT0FVX3lxTE5mQXJ0aWNsZV90b2tlbg?oc=5"
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.requests.post") as mock_post,
            patch("app.services.ingest.url_unwrap._resolve_http_redirect", return_value=("https://example.com/story", False)),
            patch("app.services.ingest.url_unwrap._google_news_batch_acquire_network_slot", return_value=True),
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "<div data-n-a-sg='SIG_ABC' data-n-a-ts='1725891265'></div>"
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = (
                ')]}\'\\n\\n[["wrb.fr","Fbv4je","'
                '["garturlres","https://example.com/story",1,"https://example.com/amp"]'
                ',null,null,null,"generic"]]'
            )
            result = unwrap_url(source, enable_network_redirect=True)
        self.assertEqual(result.url, "https://example.com/story")
        self.assertIn("google_news_batch_execute", result.steps)

    def test_unwrap_url_google_news_batch_execute_is_disabled_without_network(self):
        source = "https://news.google.com/rss/articles/CBMiT0FVX3lxTE5mQXJ0aWNsZV90b2tlbg?oc=5"
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.requests.post") as mock_post,
        ):
            unwrap_url(source, enable_network_redirect=False)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)

    def test_unwrap_url_google_news_batch_execute_uses_cache_on_repeated_token(self):
        source = "https://news.google.com/rss/articles/CBMiT0FVX3lxTE5mQXJ0aWNsZV90b2tlbg?oc=5"
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.requests.post") as mock_post,
            patch("app.services.ingest.url_unwrap._resolve_http_redirect", return_value=("https://example.com/story", False)),
            patch("app.services.ingest.url_unwrap._google_news_batch_acquire_network_slot", return_value=True),
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "<div data-n-a-sg='SIG_ABC' data-n-a-ts='1725891265'></div>"
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = (
                ')]}\'\\n\\n[["wrb.fr","Fbv4je","'
                '["garturlres","https://example.com/story",1,"https://example.com/amp"]'
                ',null,null,null,"generic"]]'
            )
            first = unwrap_url(source, enable_network_redirect=True)
            second = unwrap_url(source, enable_network_redirect=True)
        self.assertEqual(first.url, "https://example.com/story")
        self.assertEqual(second.url, "https://example.com/story")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_post.call_count, 1)

    def test_unwrap_url_google_news_batch_execute_rate_limited_response_keeps_google_news_url(self):
        source = "https://news.google.com/rss/articles/CBMiT0FVX3lxTE5mQXJ0aWNsZV90b2tlbg?oc=5"
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.requests.post") as mock_post,
            patch("app.services.ingest.url_unwrap._resolve_http_redirect", return_value=(source, False)),
            patch("app.services.ingest.url_unwrap._google_news_batch_acquire_network_slot", return_value=True),
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "<div data-n-a-sg='SIG_ABC' data-n-a-ts='1725891265'></div>"
            mock_post.return_value.status_code = 429
            result = unwrap_url(source, enable_network_redirect=True)
        self.assertEqual(result.url, "https://news.google.com/rss/articles/CBMiT0FVX3lxTE5mQXJ0aWNsZV90b2tlbg")
        self.assertNotIn("google_news_batch_execute", result.steps)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_post.call_count, 1)

    def test_unwrap_url_network_redirect_accepts_public_target(self):
        with patch("app.services.ingest.url_unwrap.requests.get") as mock_get:
            mock_get.return_value.url = "https://public.example.net/report?id=7"
            result = unwrap_url("https://example.com/start", enable_network_redirect=True)
        self.assertEqual(result.url, "https://public.example.net/report?id=7")
        self.assertIn("http_redirect", result.steps)

    def test_unwrap_url_network_redirect_blocks_localhost_private_and_reserved_targets(self):
        blocked_targets = [
            "http://localhost/admin",
            "http://127.0.0.1/health",
            "http://10.1.2.3/internal",
            "http://192.168.1.100/metrics",
            "http://172.16.5.6/status",
            "http://[::1]/secret",
            "http://169.254.169.254/meta",
            "http://240.0.0.1/reserved",
        ]
        for target in blocked_targets:
            with self.subTest(target=target):
                with patch("app.services.ingest.url_unwrap.requests.get") as mock_get:
                    mock_get.return_value.url = target
                    result = unwrap_url("https://example.com/start", enable_network_redirect=True)
                self.assertEqual(result.url, "https://example.com/start")
                self.assertNotIn("http_redirect", result.steps)

    def test_unwrap_url_network_redirect_blocks_hostname_resolving_to_private_ip(self):
        with (
            patch("app.services.ingest.url_unwrap.requests.get") as mock_get,
            patch("app.services.ingest.url_unwrap.socket.getaddrinfo") as mock_getaddrinfo,
        ):
            mock_get.return_value.url = "http://internal.example.test/secret"
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 0)),
            ]
            result = unwrap_url("https://example.com/start", enable_network_redirect=True)
        self.assertEqual(result.url, "https://example.com/start")
        self.assertNotIn("http_redirect", result.steps)
