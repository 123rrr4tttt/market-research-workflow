#!/usr/bin/env python3
"""Baseline gate checker for IP01/IP02 false-positive and false-negative CI gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingest.meaningful_gate import content_quality_check, normalize_reason_code, url_policy_check


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"No baseline cases found in {path}")
    return [c for c in cases if isinstance(c, dict)]


def _check_case(case: dict[str, Any]) -> tuple[bool, str]:
    cid = str(case.get("id") or "unknown")
    kind = str(case.get("kind") or "").strip()
    should_block = bool(case.get("should_block"))
    expected_reason = normalize_reason_code(case.get("expected_reason"), default="unknown_rejection_reason")
    config = dict(case.get("config") or {})
    config.setdefault("enable_strict_gate", True)

    if kind == "url_policy":
        decision = url_policy_check(str(case.get("url") or ""), config=config)
    elif kind == "content_quality":
        decision = content_quality_check(
            str(case.get("url") or ""),
            str(case.get("content") or ""),
            str(case.get("doc_type") or "url_fetch"),
            case.get("extraction_status"),
            config=config,
        )
    else:
        return False, f"{cid}: unsupported kind={kind!r}"

    got_reason = normalize_reason_code(decision.reason)
    ok = bool(decision.blocked) == should_block and got_reason == expected_reason
    if ok:
        return True, f"{cid}: pass"
    return (
        False,
        f"{cid}: fail should_block={should_block} got_blocked={decision.blocked} expected_reason={expected_reason} got_reason={got_reason}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ingest guardrail baseline for false-positive/false-negative CI gate")
    parser.add_argument(
        "--samples",
        default=str(ROOT / "tests/fixtures/ingest/guardrail_baseline_samples.json"),
        help="Path to baseline samples JSON",
    )
    parser.add_argument("--max-fp", type=int, default=0, help="Max allowed false positives")
    parser.add_argument("--max-fn", type=int, default=0, help="Max allowed false negatives")
    args = parser.parse_args()

    samples_path = Path(args.samples).resolve()
    cases = _load_cases(samples_path)

    passed = 0
    fp = 0
    fn = 0
    failed_msgs: list[str] = []

    for case in cases:
        ok, msg = _check_case(case)
        if ok:
            passed += 1
            continue
        failed_msgs.append(msg)
        should_block = bool(case.get("should_block"))
        kind = str(case.get("kind") or "")
        config = dict(case.get("config") or {})
        config.setdefault("enable_strict_gate", True)
        if kind == "url_policy":
            decision = url_policy_check(str(case.get("url") or ""), config=config)
        else:
            decision = content_quality_check(
                str(case.get("url") or ""),
                str(case.get("content") or ""),
                str(case.get("doc_type") or "url_fetch"),
                case.get("extraction_status"),
                config=config,
            )
        if decision.blocked and not should_block:
            fp += 1
        if (not decision.blocked) and should_block:
            fn += 1

    total = len(cases)
    print(
        json.dumps(
            {
                "samples": str(samples_path),
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "false_positive": fp,
                "false_negative": fn,
                "max_fp": args.max_fp,
                "max_fn": args.max_fn,
            },
            ensure_ascii=False,
        )
    )

    for line in failed_msgs:
        print(line)

    if fp > args.max_fp or fn > args.max_fn:
        return 2
    if failed_msgs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
