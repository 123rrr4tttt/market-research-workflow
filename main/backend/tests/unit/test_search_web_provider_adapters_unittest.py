from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import pytest

from app.services.ingest.retry_policy import RateGate, RequestScope
from app.composition.resource_pool import RequestHtmlSearchRequestPort
from app.services.search import web

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, payload: dict[str, object], *, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.headers = {"Retry-After": "1"} if status_code == 429 else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError

    def json(self) -> dict[str, object]:
        return self.payload


class _FakeJsonSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append((url, dict(kwargs)))
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def _deterministic_gate(sleeps: list[float]) -> RateGate:
    now = [0.0]

    def advance_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    return RateGate(
        rate_limit_interval_seconds=1.0,
        backoff_base_seconds=2.0,
        backoff_max_seconds=8.0,
        clock=lambda: now[0],
        sleeper=advance_sleep,
    )


class SearchWebProviderAdaptersTest(unittest.TestCase):
    def test_search_web_dynamic_boundaries_preserve_failure_paths(self) -> None:
        with patch.object(web, "_SEARCH_REQUEST_PORT", None):
            with self.assertRaisesRegex(RuntimeError, "request port is not configured"):
                web._request_search_json("https://example.test", scope=web._search_scope("test"))
        self.assertIsNone(web._json_dict({1: "value"}))
        with self.assertRaisesRegex(TypeError, "field 'title' must be text"):
            web._result_text({"title": 42}, "title")
        self.assertEqual(web._result_text({"title": 0}, "title"), "")
        with self.assertRaisesRegex(TypeError, "must be a JSON object"):
            web._json_object({1: "value"})
        with self.assertRaisesRegex(TypeError, "must be a JSON array"):
            web._json_rows({"row": "value"})
        with self.assertRaisesRegex(TypeError, "row must be a JSON object"):
            web._required_json_dict([])

    def test_searxng_adapter_normalizes_results_and_keeps_provider_source(self) -> None:
        payload = {
            "results": [
                {
                    "title": "Robotics policy",
                    "url": "https://example.com/page?utm_source=test&keep=1",
                    "content": "Policy snippet",
                    "engine": "bing",
                    "category": "general",
                }
            ]
        }
        session = _FakeJsonSession([_FakeResponse(payload)])
        sleeps: list[float] = []
        gate = _deterministic_gate(sleeps)
        with patch("app.services.search.web.generate_keywords", return_value=["robotics policy"]):
            with patch.object(web, "SEARCH_RATE_GATE", gate):
                port = RequestHtmlSearchRequestPort(
                    rate_gate=gate,
                    client_factory=lambda: session,
                )
                with patch.object(web, "_SEARCH_REQUEST_PORT", port):
                    results = web.search_sources(
                        "robotics policy",
                        language="en",
                        max_results=5,
                        provider="searxng",
                        exclude_existing=False,
                    )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "searxng")
        self.assertEqual(results[0]["title"], "Robotics policy")
        self.assertEqual(results[0]["snippet"], "Policy snippet")
        self.assertEqual(results[0]["link"], "https://example.com/page?keep=1")
        self.assertEqual(results[0]["provider_route"], "explicit:searxng")
        self.assertEqual(results[0]["provider_family"], "local_open_search")
        self.assertFalse(results[0]["provider_auto_included"])
        self.assertEqual(
            results[0]["backend_trace"],
            {
                "provider": "searxng",
                "provider_route": "explicit:searxng",
                "provider_family": "local_open_search",
                "auto_included": False,
                "pageno": 1,
            },
        )
        self.assertEqual(results[0]["raw"]["engine"], "bing")
        self.assertEqual(len(session.calls), 1)
        url, get_kwargs = session.calls[0]
        self.assertTrue(url.endswith("/search"))
        self.assertEqual(get_kwargs["params"]["format"], "json")
        self.assertEqual(session.headers["Accept"], "application/json")
        self.assertEqual(sleeps, [])

    def test_yacy_adapter_normalizes_channel_items_and_resource_mode(self) -> None:
        payload = {
            "channels": [
                {
                    "items": [
                        {
                            "title": "Local robotics note",
                            "link": "https://example.org/local?utm_medium=x",
                            "description": "Local corpus snippet",
                            "host": "example.org",
                        }
                    ]
                }
            ]
        }
        with patch.dict(os.environ, {"YACY_RESOURCE_MODE": "local"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                session = _FakeJsonSession([_FakeResponse(payload)])
                sleeps: list[float] = []
                gate = _deterministic_gate(sleeps)
                with patch.object(web, "SEARCH_RATE_GATE", gate):
                    port = RequestHtmlSearchRequestPort(
                        rate_gate=gate,
                        client_factory=lambda: session,
                    )
                    with patch.object(web, "_SEARCH_REQUEST_PORT", port):
                        results = web.search_sources(
                            "robotics",
                            language="en",
                            max_results=5,
                            provider="yacy",
                            exclude_existing=False,
                        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "yacy")
        self.assertEqual(results[0]["title"], "Local robotics note")
        self.assertEqual(results[0]["snippet"], "Local corpus snippet")
        self.assertEqual(results[0]["link"], "https://example.org/local")
        self.assertEqual(results[0]["provider_route"], "explicit:yacy")
        self.assertEqual(results[0]["provider_family"], "local_open_search")
        self.assertFalse(results[0]["provider_auto_included"])
        self.assertEqual(
            results[0]["backend_trace"],
            {
                "provider": "yacy",
                "provider_route": "explicit:yacy",
                "provider_family": "local_open_search",
                "auto_included": False,
                "resource": "local",
            },
        )
        self.assertEqual(results[0]["raw"]["resource"], "local")
        self.assertEqual(len(session.calls), 1)
        url, get_kwargs = session.calls[0]
        self.assertTrue(url.endswith("/yacysearch.json"))
        self.assertEqual(get_kwargs["params"]["resource"], "local")
        self.assertEqual(session.headers["Accept"], "application/json")
        self.assertEqual(sleeps, [])

    def test_auto_provider_does_not_call_experimental_local_providers(self) -> None:
        with patch.dict(os.environ, {"SERPER_API_KEY": "test-serper"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                with patch(
                    "app.services.search.web._serper_search",
                    return_value=[
                        {"title": "Serper", "link": "https://serper.example", "snippet": "ok", "source": "serper"}
                    ],
                ):
                    with patch("app.services.search.web._searxng_search") as searxng:
                        with patch("app.services.search.web._yacy_search") as yacy:
                            results = web.search_sources(
                                "robotics",
                                language="en",
                                max_results=5,
                                provider="auto",
                                exclude_existing=False,
                            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "serper")
        searxng.assert_not_called()
        yacy.assert_not_called()

    def test_searxng_adapter_paginates_for_larger_limits(self) -> None:
        first_page = {
            "results": [
                {"title": f"Result {idx}", "url": f"https://example.com/{idx}", "content": "First page"}
                for idx in range(1, 11)
            ]
        }
        second_page = {"results": [{"title": "Result 11", "url": "https://example.com/11", "content": "Second page"}]}
        session = _FakeJsonSession([_FakeResponse(first_page), _FakeResponse(second_page)])
        sleeps: list[float] = []
        gate = _deterministic_gate(sleeps)
        with patch.dict(os.environ, {"SEARXNG_MAX_PAGES": "2"}, clear=False):
            with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
                with patch.object(web, "SEARCH_RATE_GATE", gate):
                    port = RequestHtmlSearchRequestPort(
                        rate_gate=gate,
                        client_factory=lambda: session,
                    )
                    with patch.object(web, "_SEARCH_REQUEST_PORT", port):
                        results = web.search_sources(
                            "robotics",
                            language="en",
                            max_results=11,
                            provider="searxng",
                            exclude_existing=False,
                        )

        self.assertEqual(len(results), 11)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["params"]["pageno"], 1)
        self.assertEqual(session.calls[1][1]["params"]["pageno"], 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(results[-1]["raw"]["pageno"], 2)
        self.assertEqual(results[-1]["backend_trace"]["pageno"], 2)
        self.assertEqual(results[-1]["provider_route"], "explicit:searxng")

    def test_google_repeated_gets_use_frozen_rate_gate_without_sleep_call(self) -> None:
        first_page = {
            "items": [
                {"title": f"Result {idx}", "link": f"https://example.com/{idx}", "snippet": "ok"} for idx in range(10)
            ]
        }
        second_page = {"items": [{"title": "Result 11", "link": "https://example.com/11", "snippet": "ok"}]}
        session = _FakeJsonSession([_FakeResponse(first_page), _FakeResponse(second_page)])
        sleeps: list[float] = []
        gate = _deterministic_gate(sleeps)

        with patch.object(web, "SEARCH_RATE_GATE", gate):
            port = RequestHtmlSearchRequestPort(
                rate_gate=gate,
                client_factory=lambda: session,
            )
            with patch.object(web, "_SEARCH_REQUEST_PORT", port):
                results = web._google_search("robotics", "cse-id", 11, api_key="test-key")

        self.assertEqual(len(results), 11)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(session.headers["Accept"], "application/json")

    def test_serper_post_policy_boundary_is_not_faked_as_request_html(self) -> None:
        sleeps: list[float] = []
        gate = _deterministic_gate(sleeps)
        gate.record_throttle(RequestScope(provider="search:serper"), retry_after_seconds=2.0)

        with patch.object(web, "SEARCH_RATE_GATE", gate):
            with patch(
                "app.services.search.web.default_http_client.post_json",
                side_effect=AssertionError("denial must not reach provider HTTP"),
            ):
                results = web._serper_search("robotics", "test-key", 5)

        self.assertEqual(results, [])
        self.assertEqual(sleeps, [])

    def test_provider_429_failure_is_classified_and_never_returns_partial_data(self) -> None:
        session = _FakeJsonSession(
            [_FakeResponse({"organic_results": [{"title": "partial"}]}, status_code=429) for _ in range(3)]
        )
        sleeps: list[float] = []
        gate = _deterministic_gate(sleeps)

        with patch("time.sleep", sleeps.append):
            with patch.object(web, "SEARCH_RATE_GATE", gate):
                port = RequestHtmlSearchRequestPort(
                    rate_gate=gate,
                    client_factory=lambda: session,
                )
                with patch.object(web, "_SEARCH_REQUEST_PORT", port):
                    with self.assertRaises(Exception) as raised:
                        web._serpapi_search("robotics", "test-key", 5)

        self.assertIn("rate_limited", str(raised.exception))
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(sleeps, [1.0])
        self.assertNotIn("partial", str(raised.exception))

if __name__ == "__main__":
    unittest.main()
