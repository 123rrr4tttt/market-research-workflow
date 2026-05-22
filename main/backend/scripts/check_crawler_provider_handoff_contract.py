from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.collect_runtime.adapters.source_library import to_source_library_response
from app.services.collect_runtime.contracts import CollectResult


CONTRACT_VERSION = "crawler_provider_handoff.check.v1"
PROVIDER_HANDOFF_CONTRACT_VERSION = "source_library.provider_handoff.v1"


def build_fixture_payload() -> dict[str, Any]:
    route_profile = {
        "contract_version": "ingest.frontdoor_route_profile.v1",
        "route_hint": "crawler_browse",
        "fetch_strategy": "browser_render",
        "domain": "x.com",
        "search_like": True,
        "high_js": True,
        "prefer_crawler": True,
        "prefer_search_shell": True,
        "render_required": True,
        "fallback_fetch_strategy": "http_fetch",
    }
    provider_handoff = {
        "contract_version": PROVIDER_HANDOFF_CONTRACT_VERSION,
        "handoff_kind": "crawler_provider",
        "channel_key": "crawler.demo_proj",
        "provider": "crawler",
        "provider_type": "scrapy",
        "provider_dispatch": "crawlers/providers",
        "downstream_handoff": "ingest",
        "execution_layer": "terminal_output_only",
        "route_hint": "crawler_browse",
        "fetch_strategy": "browser_render",
        "render_required": True,
        "prefer_crawler_first": True,
        "force_url_routing_flow": False,
        "provider_job_id": "job-high-js-1",
        "provider_status": "queued",
        "attempt_count": 1,
        "frontdoor_route_profile": route_profile,
    }
    return {
        "item_key": "handler.cluster.high_js",
        "channel_key": "handler.cluster",
        "params": {
            "urls": ["https://x.com/search?q=robotics"],
            "query_terms": ["robotics"],
            "frontdoor_route_profile": route_profile,
        },
        "result": {
            "by_url": [
                {
                    "url": "https://x.com/search?q=robotics",
                    "channel_key": "crawler.demo_proj",
                    "error": None,
                    "result": {
                        "status": "accepted",
                        "provider_type": "scrapy",
                        "provider_status": "queued",
                        "provider_job_id": "job-high-js-1",
                        "attempt_count": 1,
                    },
                    "provider_handoff": provider_handoff,
                    "frontdoor_route_profile": route_profile,
                }
            ],
            "execution_request": {
                "source_mode": "url_execution",
                "project_key": "demo_proj",
                "params": {
                    "urls": ["https://x.com/search?q=robotics"],
                    "query_terms": ["robotics"],
                    "frontdoor_route_profile": route_profile,
                },
            },
        },
    }


def build_check() -> dict[str, Any]:
    raw = build_fixture_payload()
    response = to_source_library_response(CollectResult(channel="source_library", meta={"raw": raw}))
    terminal_meta = response.get("terminal_output", {}).get("meta", {})
    provider_handoff = terminal_meta.get("provider_handoff") if isinstance(terminal_meta, dict) else {}
    source_ref = response.get("frontdoor_ingress", {}).get("source_ref", {})
    authority_summary = response.get("authority_output", {}).get("summary", {})
    authority_handoff = authority_summary.get("provider_handoff", {}) if isinstance(authority_summary, dict) else {}

    assertions = {
        "terminal_handoff_contract": provider_handoff.get("contract_version") == PROVIDER_HANDOFF_CONTRACT_VERSION,
        "terminal_provider_job_id": provider_handoff.get("provider_job_id") == "job-high-js-1",
        "frontdoor_provider_dispatch": source_ref.get("provider_dispatch") == "crawlers/providers",
        "frontdoor_browser_route": source_ref.get("fetch_strategy") == "browser_render",
        "authority_provider_summary": bool(authority_handoff.get("present"))
        and authority_handoff.get("provider_type") == "scrapy",
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if all(assertions.values()) else "failed",
        "assertions": assertions,
        "handoff": {
            "terminal": provider_handoff,
            "frontdoor_source_ref": source_ref,
            "authority_summary": authority_handoff,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check crawler provider handoff contract projection.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
