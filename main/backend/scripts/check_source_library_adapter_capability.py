#!/usr/bin/env python3
"""Narrow source-library adapter capability gate for Wave8 parser profiles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.resource_pool.search_template_adapters import apply_search_template_adapter_plan
from app.services.resource_pool.search_template_adapters import resolve_search_template_adapter_plan


def _case(site_url: str, entry_domain: str, params: dict[str, object]) -> dict[str, object]:
    plan = resolve_search_template_adapter_plan(
        site_url=site_url,
        entry_domain=entry_domain,
        params=params,
    )
    routed = apply_search_template_adapter_plan(plan=plan, params=params)
    return {
        "site_url": site_url,
        "entry_domain": entry_domain,
        "adapter_key": plan.adapter_key,
        "parser_profile": routed.get("parser_profile"),
        "parser_profile_requested": routed.get("parser_profile_requested"),
        "parser_profile_resolved": routed.get("parser_profile_resolved"),
        "adapter_capability_status": routed.get("adapter_capability_status"),
        "adapter_capability_reason": routed.get("adapter_capability_reason"),
        "candidate_relevance_review_required": bool(routed.get("candidate_relevance_review_required")),
    }


def main() -> int:
    rows = [
        _case("https://www.pymnts.com/?s={{q}}", "www.pymnts.com", {}),
        _case(
            "https://example.com/search?q={{q}}",
            "example.com",
            {"parser_profile": "site_adaptive.missing_custom_profile"},
        ),
        _case(
            "https://example.com/search?q={{q}}",
            "example.com",
            {"parser_profile": "fallback_anchor_only"},
        ),
    ]
    expected = [
        ("allow", "site_adaptive.pymnts_card", False),
        ("downgrade", "site_adaptive", False),
        ("review", "fallback_anchor_only", True),
    ]
    failures = []
    for row, (status, resolved, review_required) in zip(rows, expected, strict=True):
        if row["adapter_capability_status"] != status:
            failures.append(f"{row['entry_domain']}: expected status={status}, got={row['adapter_capability_status']}")
        if row["parser_profile_resolved"] != resolved:
            failures.append(f"{row['entry_domain']}: expected resolved={resolved}, got={row['parser_profile_resolved']}")
        if row["candidate_relevance_review_required"] != review_required:
            failures.append(
                f"{row['entry_domain']}: expected review_required={review_required}, got={row['candidate_relevance_review_required']}"
            )

    payload = {"status": "fail" if failures else "pass", "cases": rows, "failures": failures}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
