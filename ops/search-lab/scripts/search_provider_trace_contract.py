#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.search import web  # noqa: E402


DEFAULT_OUT = (
    REPO_ROOT
    / "development"
    / "latest-dev-docs"
    / "automation-runs"
    / "search-provider-trace-artifacts"
    / "2026-05-22"
    / "search_provider_trace_contract.json"
)

REQUIRED_TRACE_FIELDS = [
    "provider_route",
    "provider_family",
    "provider_auto_included",
    "backend_trace",
]
LOCAL_OPEN_SEARCH_FAMILY = "local_open_search"


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": result.get("source"),
        "title": result.get("title"),
        "link": result.get("link"),
        "canonical_link": result.get("canonical_link"),
        "provider_route": result.get("provider_route"),
        "provider_family": result.get("provider_family"),
        "provider_auto_included": result.get("provider_auto_included"),
        "backend_trace": result.get("backend_trace"),
        "raw": result.get("raw"),
    }


def _assert_explicit_trace(provider: str, result: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_TRACE_FIELDS if field not in result]
    if missing:
        raise AssertionError(f"{provider} result missing trace field(s): {', '.join(missing)}")
    expected_route = f"explicit:{provider}"
    if result["provider_route"] != expected_route:
        raise AssertionError(f"{provider} provider_route={result['provider_route']!r}, expected {expected_route!r}")
    if result["provider_family"] != LOCAL_OPEN_SEARCH_FAMILY:
        raise AssertionError(f"{provider} provider_family={result['provider_family']!r}")
    if result["provider_auto_included"] is not False:
        raise AssertionError(f"{provider} provider_auto_included must be false")
    trace = result.get("backend_trace")
    if not isinstance(trace, dict):
        raise AssertionError(f"{provider} backend_trace must be an object")
    expected_trace = {
        "provider": provider,
        "provider_route": expected_route,
        "provider_family": LOCAL_OPEN_SEARCH_FAMILY,
        "auto_included": False,
    }
    for key, value in expected_trace.items():
        if trace.get(key) != value:
            raise AssertionError(f"{provider} backend_trace.{key}={trace.get(key)!r}, expected {value!r}")


def build_contract() -> dict[str, Any]:
    searxng_payload = {
        "results": [
            {
                "title": "Robotics policy",
                "url": "https://example.com/robotics?utm_source=fixture&keep=1",
                "content": "Policy snippet",
                "engine": "bing",
                "category": "general",
            }
        ]
    }
    yacy_payload = {
        "channels": [
            {
                "items": [
                    {
                        "title": "Local robotics note",
                        "link": "https://example.org/local?utm_medium=fixture",
                        "description": "Local corpus snippet",
                        "host": "example.org",
                    }
                ]
            }
        ]
    }

    with patch("app.services.search.web.generate_keywords", return_value=["robotics policy"]):
        with patch("app.services.search.web.default_http_client.get_json", return_value=searxng_payload):
            searxng_results = web.search_sources(
                "robotics policy",
                language="en",
                max_results=5,
                provider="searxng",
                exclude_existing=False,
            )

    with patch.dict(os.environ, {"YACY_RESOURCE_MODE": "local"}, clear=False):
        with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
            with patch("app.services.search.web.default_http_client.get_json", return_value=yacy_payload):
                yacy_results = web.search_sources(
                    "robotics",
                    language="en",
                    max_results=5,
                    provider="yacy",
                    exclude_existing=False,
                )

    if not searxng_results:
        raise AssertionError("searxng fixture produced no result")
    if not yacy_results:
        raise AssertionError("yacy fixture produced no result")
    _assert_explicit_trace("searxng", searxng_results[0])
    _assert_explicit_trace("yacy", yacy_results[0])

    with patch.dict(os.environ, {"SERPER_API_KEY": "offline-serper"}, clear=False):
        with patch("app.services.search.web.generate_keywords", return_value=["robotics"]):
            with patch(
                "app.services.search.web._serper_search",
                return_value=[
                    {
                        "title": "Serper result",
                        "link": "https://serper.example/robotics",
                        "snippet": "ok",
                        "source": "serper",
                    }
                ],
            ):
                with patch("app.services.search.web._searxng_search") as searxng_search:
                    with patch("app.services.search.web._yacy_search") as yacy_search:
                        auto_results = web.search_sources(
                            "robotics",
                            language="en",
                            max_results=5,
                            provider="auto",
                            exclude_existing=False,
                        )
                        auto_trace = {
                            "result_sources": sorted({str(item.get("source")) for item in auto_results}),
                            "searxng_called": searxng_search.called,
                            "yacy_called": yacy_search.called,
                            "local_open_search_called": searxng_search.called or yacy_search.called,
                        }

    if auto_trace["local_open_search_called"]:
        raise AssertionError("provider=auto called local open-search providers")
    if "searxng" in auto_trace["result_sources"] or "yacy" in auto_trace["result_sources"]:
        raise AssertionError(f"provider=auto returned local open-search source(s): {auto_trace['result_sources']}")

    return {
        "contract_version": "search-provider-trace-artifacts.v1",
        "scope": "offline_unit_contract_no_containers",
        "generated_by": "ops/search-lab/scripts/search_provider_trace_contract.py",
        "required_result_fields": REQUIRED_TRACE_FIELDS,
        "provider_auto_policy": {
            "excluded_local_open_search_providers": ["searxng", "yacy"],
            "reason": "local open-search providers remain explicit-only until replay, quality, timeout, and approval-gate evidence is separately accepted",
        },
        "explicit_results": {
            "searxng": _normalize_result(searxng_results[0]),
            "yacy": _normalize_result(yacy_results[0]),
        },
        "auto_route": auto_trace,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    contract = build_contract()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out_path), "contract_version": contract["contract_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
