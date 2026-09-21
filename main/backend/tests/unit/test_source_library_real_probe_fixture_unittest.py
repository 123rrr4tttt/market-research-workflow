from __future__ import annotations

import sys
import socket
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

import scripts.source_library_real_probes as real_probe  # noqa: E402
from app.services.resource_pool.http_port import HttpFetchError  # noqa: E402
from app.services.resource_pool.http_port import HttpFetchFailureReason  # noqa: E402
from app.services.resource_pool.http_port import HttpFetchResponse  # noqa: E402

from scripts.source_library_real_probes import run_probe  # noqa: E402


class SourceLibraryRealProbeFixtureUnitTestCase(unittest.TestCase):
    def test_local_http_fixture_covers_site_entries_and_transport_fallback(self) -> None:
        class InMemoryFixture:
            base_url = "http://source-library-fixture.invalid"
            domain = "source-library-fixture.invalid"

            def __init__(self) -> None:
                self.state = real_probe._ProbeState()

            def __enter__(self) -> InMemoryFixture:
                return self

            def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
                return None

        fixture = InMemoryFixture()

        class InMemoryHttpFetchPort:
            def fetch_html(
                self,
                url: str,
                *,
                headers: Any = None,
                params: Any = None,
                cookies: Any = None,
                timeout: float = 30.0,
                retries: int = 3,
                backoff: float = 1.5,
            ) -> tuple[str, HttpFetchResponse]:
                del headers, params, cookies, timeout, retries, backoff
                parsed = urlparse(url)
                path = parsed.path or "/"
                fixture.state.requests.append(
                    {
                        "method": "GET",
                        "path": path,
                        "query": dict(parse_qs(parsed.query)),
                        "user_agent": "",
                        "accept": "",
                    }
                )

                if path == "/blocked-search":
                    fixture.state.blocked_search_attempts += 1
                    if fixture.state.blocked_search_attempts == 1:
                        raise HttpFetchError(  # noqa: TRY003
                            "HTTP 429 from deterministic in-memory fixture",
                            reason=HttpFetchFailureReason.HTTP_STATUS,
                            url=url,
                            status_code=429,
                            retryable=True,
                        )
                    body = real_probe._search_html(
                        f"{fixture.base_url}/articles/robotics-market?utm_source=fixture"
                    )
                    content_type = "text/html; charset=utf-8"
                elif path == "/sitemap.xml":
                    body = f"""
                    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                      <url><loc>{fixture.base_url}/articles/robotics-sitemap</loc></url>
                    </urlset>
                    """
                    content_type = "application/xml; charset=utf-8"
                elif path == "/feed.xml":
                    body = f"""
                    <rss version="2.0">
                      <channel>
                        <item>
                          <title>Robotics market weekly</title>
                          <description>Robotics market evidence from the in-memory fixture.</description>
                          <link>{fixture.base_url}/articles/robotics-feed</link>
                        </item>
                      </channel>
                    </rss>
                    """
                    content_type = "application/xml; charset=utf-8"
                elif path == "/search":
                    body = real_probe._search_html(f"{fixture.base_url}/articles/robotics-entry")
                    content_type = "text/html; charset=utf-8"
                elif path.startswith("/articles/"):
                    body = f"<html><title>{path}</title><body>Robotics market fixture article.</body></html>"
                    content_type = "text/html; charset=utf-8"
                else:
                    raise HttpFetchError(  # noqa: TRY003
                        f"unexpected in-memory fixture path: {path}",
                        reason=HttpFetchFailureReason.HTTP_STATUS,
                        url=url,
                        status_code=404,
                        retryable=False,
                    )

                response = HttpFetchResponse(
                    text=body,
                    content=body.encode("utf-8"),
                    headers={"content-type": content_type},
                    status_code=200,
                    final_url=url,
                )
                return body, response

        transport = InMemoryHttpFetchPort()
        with (
            patch.object(real_probe, "_ProbeServer", return_value=fixture),
            patch.object(
                socket,
                "socket",
                side_effect=AssertionError("socket access is forbidden in this unit fixture"),
            ) as socket_ctor,
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access is forbidden in this unit fixture"),
            ) as create_connection,
            patch.object(
                socket,
                "getaddrinfo",
                side_effect=AssertionError("DNS access is forbidden in this unit fixture"),
            ) as getaddrinfo,
            patch("app.services.resource_pool.http_port._HTTP_FETCH_PORT", transport),
        ):
            result = run_probe(probe_timeout=0.5)

        self.assertFalse(socket_ctor.called, "in-memory transport must not construct a socket")
        self.assertFalse(create_connection.called, "in-memory transport must not open a network connection")
        self.assertFalse(getaddrinfo.called, "in-memory transport must not perform DNS resolution")

        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertIn("sitemap", result["outputs"]["site_entry_discovery"]["entry_types"])
        self.assertIn("rss", result["outputs"]["site_entry_discovery"]["entry_types"])
        self.assertIn("search_template", result["outputs"]["site_entry_discovery"]["entry_types"])

        search = result["outputs"]["adapter_results"]["search_template"]
        self.assertEqual(search["diagnostics"]["search_service"], "resilient")
        self.assertEqual(search["diagnostics"]["search_service_fallbacks"], 1)
        self.assertEqual(result["outputs"]["transport_resilience"]["blocked_search_attempts"], 2)
        self.assertEqual(search["diagnostics"]["transport_errors"], 0)
        self.assertEqual(search["diagnostics"]["candidate_filter_state"], "selected")
        self.assertEqual(len(search["candidates"]), 1)

        request_counts = result["outputs"]["transport_resilience"]["request_counts"]
        self.assertGreaterEqual(request_counts.get("/sitemap.xml", 0), 1)
        self.assertGreaterEqual(request_counts.get("/feed.xml", 0), 1)
        self.assertGreaterEqual(request_counts.get("/search", 0), 1)
        self.assertEqual(request_counts.get("/blocked-search", 0), 2)


if __name__ == "__main__":
    unittest.main()
