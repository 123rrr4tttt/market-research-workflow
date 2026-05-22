from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resource_pool.site_entry_discovery import _discover_domain_candidates
from app.services.source_library.adapters.generic_web import handle_generic_web_rss
from app.services.source_library.adapters.generic_web import handle_generic_web_search_template
from app.services.source_library.adapters.generic_web import handle_generic_web_sitemap


@dataclass
class _ProbeState:
    blocked_search_attempts: int = 0
    requests: list[dict[str, Any]] = field(default_factory=list)

    def record(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        self.requests.append(
            {
                "method": handler.command,
                "path": parsed.path,
                "query": dict(parse_qs(parsed.query)),
                "user_agent": handler.headers.get("User-Agent", ""),
                "accept": handler.headers.get("Accept", ""),
            }
        )

    def request_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.requests:
            path = str(row.get("path") or "")
            counts[path] = counts.get(path, 0) + 1
        return counts


class _ProbeServer:
    def __init__(self) -> None:
        self.state = _ProbeState()
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                state.record(self)
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/sitemap.xml":
                    self._send_xml(
                        """
                        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                          <url><loc>{base}/articles/robotics-sitemap</loc></url>
                        </urlset>
                        """
                    )
                    return
                if path == "/feed.xml":
                    self._send_xml(
                        """
                        <rss version="2.0">
                          <channel>
                            <item>
                              <title>Robotics market weekly</title>
                              <description>Robotics market evidence from the local fixture.</description>
                              <link>{base}/articles/robotics-feed</link>
                            </item>
                          </channel>
                        </rss>
                        """
                    )
                    return
                if path == "/search":
                    self._send_html(_search_html("{base}/articles/robotics-entry"))
                    return
                if path == "/blocked-search":
                    state.blocked_search_attempts += 1
                    if state.blocked_search_attempts == 1:
                        self._send_html("rate limited by local fixture", status=429, headers={"Retry-After": "0"})
                        return
                    self._send_html(_search_html("{base}/articles/robotics-market?utm_source=fixture"))
                    return
                if path.startswith("/articles/"):
                    self._send_html(f"<html><title>{path}</title><body>Robotics market fixture article.</body></html>")
                    return
                self._send_html("not found", status=404)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_xml(self, template: str, *, status: int = 200) -> None:
                self._send_text(
                    template.format(base=f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"),
                    status=status,
                    content_type="application/xml; charset=utf-8",
                )

            def _send_html(self, template: str, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
                self._send_text(
                    template.format(base=f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"),
                    status=status,
                    content_type="text/html; charset=utf-8",
                    headers=headers,
                )

            def _send_text(
                self,
                body: str,
                *,
                status: int,
                content_type: str,
                headers: dict[str, str] | None = None,
            ) -> None:
                data = body.strip().encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="source-library-real-probe-fixture", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def domain(self) -> str:
        host, port = self.server.server_address
        return f"{host}:{port}"

    def __enter__(self) -> "_ProbeServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


def _search_html(article_url_template: str) -> str:
    return f"""
    <html>
      <body>
        <nav>
          <a href="/about">About</a>
          <a href="/pricing">Pricing</a>
        </nav>
        <main class="search-results">
          <article class="search-result">
            <h2><a href="{article_url_template}">Robotics market adoption report</a></h2>
            <p>Robotics market evidence, adoption rates, and pricing signals.</p>
          </article>
        </main>
      </body>
    </html>
    """


def _summarize_adapter_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "inserted": result.get("inserted"),
        "skipped": result.get("skipped"),
        "candidates": list(result.get("candidates") or []),
        "used_term_fallback": result.get("used_term_fallback"),
        "pages_scanned": result.get("pages_scanned"),
        "search_urls": list(result.get("search_urls") or []),
        "diagnostics": dict(result.get("diagnostics") or {}),
        "errors": list(result.get("errors") or []),
        "source_mode": result.get("source_mode"),
        "capability_profile": dict(result.get("capability_profile") or {}),
        "adapter_taxonomy": dict(result.get("adapter_taxonomy") or {}),
    }


def _discover_site_entries(*, domain: str, probe_timeout: float) -> dict[str, Any]:
    candidates, stats, errors = _discover_domain_candidates(
        d=domain,
        target_scope="project",
        probe_timeout=probe_timeout,
        include_link_alternate=False,
        sitemap_paths=["/sitemap.xml"],
        rss_paths=["/feed.xml"],
    )
    return {
        "entry_types": sorted({str(row.get("entry_type") or "") for row in candidates if row.get("entry_type")}),
        "candidate_count": len(candidates),
        "candidates": [
            {
                "site_url": row.get("site_url"),
                "entry_type": row.get("entry_type"),
                "template": row.get("template"),
                "source_ref": row.get("source_ref"),
            }
            for row in candidates
        ],
        "probe_stats": dict(stats or {}),
        "errors": list(errors or []),
    }


def _validate(result: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    discovery = result["outputs"]["site_entry_discovery"]
    entry_types = set(discovery["entry_types"])
    for expected in ("sitemap", "rss", "search_template"):
        if expected not in entry_types:
            errors.append(f"missing discovered entry type: {expected}")
    adapters = result["outputs"]["adapter_results"]
    for key in ("rss", "sitemap", "search_template"):
        if not adapters[key]["candidates"]:
            errors.append(f"{key} adapter returned no candidates")
    search = adapters["search_template"]
    diagnostics = search["diagnostics"]
    if diagnostics.get("search_service") != "resilient":
        errors.append("search_template did not switch to resilient service after 429")
    if diagnostics.get("search_service_fallbacks") != 1:
        errors.append("search_template did not record exactly one search_service_fallback")
    if result["outputs"]["transport_resilience"]["blocked_search_attempts"] != 2:
        errors.append("blocked-search fixture was not retried exactly once")
    if search["errors"]:
        errors.append("search_template returned transport errors after resilient fallback")
    return {"passed": not errors, "errors": errors}


def run_probe(*, probe_timeout: float = 1.0) -> dict[str, Any]:
    with _ProbeServer() as fixture:
        base_url = fixture.base_url
        query_terms = ["robotics", "market"]
        search_template = f"{base_url}/blocked-search?q={{{{q}}}}"
        result = {
            "probe_id": "source_library_real_probes_2026_05_22_local_http_fixture",
            "fixture": {
                "kind": "local_http_server",
                "base_url": base_url,
                "public_network_required": False,
                "simulated_conditions": [
                    "site_entry_sitemap",
                    "site_entry_rss",
                    "site_entry_search_path",
                    "anti_bot_429_then_success",
                ],
            },
            "inputs": {
                "project_key": "demo_proj",
                "query_terms": query_terms,
                "site_entry_domain": fixture.domain,
                "search_template": search_template,
                "rss_url": f"{base_url}/feed.xml",
                "sitemap_url": f"{base_url}/sitemap.xml",
                "probe_timeout": probe_timeout,
            },
            "outputs": {
                "site_entry_discovery": _discover_site_entries(domain=fixture.domain, probe_timeout=probe_timeout),
                "adapter_results": {
                    "search_template": _summarize_adapter_result(
                        handle_generic_web_search_template(
                            {
                                "template": search_template,
                                "query_terms": query_terms,
                                "probe_timeout": probe_timeout,
                                "allow_term_fallback": False,
                                "enable_search_service_fallback": True,
                                "_source_library_item": {
                                    "item_key": "handler.cluster.search_template.fixture",
                                    "channel_key": "handler.cluster",
                                    "item_type": "service_aggregated",
                                    "managed_by": "system",
                                    "extra": {"expected_entry_type": "search_template"},
                                },
                            },
                            project_key="demo_proj",
                        )
                    ),
                    "rss": _summarize_adapter_result(
                        handle_generic_web_rss(
                            {
                                "feed_url": f"{base_url}/feed.xml",
                                "query_terms": ["robotics"],
                                "probe_timeout": probe_timeout,
                                "allow_term_fallback": False,
                            },
                            project_key="demo_proj",
                        )
                    ),
                    "sitemap": _summarize_adapter_result(
                        handle_generic_web_sitemap(
                            {
                                "sitemap_url": f"{base_url}/sitemap.xml",
                                "query_terms": ["robotics"],
                                "probe_timeout": probe_timeout,
                                "allow_term_fallback": False,
                                "max_depth": 1,
                                "max_sitemaps": 5,
                            },
                            project_key="demo_proj",
                        )
                    ),
                },
                "transport_resilience": {
                    "blocked_search_attempts": fixture.state.blocked_search_attempts,
                    "request_counts": fixture.state.request_counts(),
                    "requests": fixture.state.requests,
                },
            },
            "closure_status": {
                "AT-AC-06": "deterministic local anti-bot/transport fallback evidence added; live public anti-bot runtime remains environment-dependent",
                "AT-AC-10": "local site-entry probe evidence added; dirty-source shortlist still requires live demo_proj public-site replay",
            },
        }
        result["validation"] = _validate(result)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic source_library real-probe local HTTP fixture.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--probe-timeout", type=float, default=1.0)
    args = parser.parse_args(argv)

    result = run_probe(probe_timeout=args.probe_timeout)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.get("validation", {}).get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
