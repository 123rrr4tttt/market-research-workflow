from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


CONTRACT_VERSION = "meaningful_ingest_guardrails.wave9_1.check.v1"
TOPIC_DOC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-02-meaningful-ingest-guardrails-plan/"
    "02_wave9-1-meaningful-ingest-guardrails-contract-evidence-2026-05-22.md"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _token_check(root: Path, path: str, tokens: tuple[str, ...]) -> dict[str, Any]:
    full_path = root / path
    exists = full_path.is_file()
    text = _read_text(full_path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": path,
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def _runtime_checks(root: Path) -> list[dict[str, Any]]:
    backend_root = root / "main" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.services.ingest.postprocess_frontdoor import _evaluate_quality_frontdoor

    low_value_candidate = {
        "uri": "https://example.com/search?q=robotics",
        "title": "Search page",
        "summary": "summary",
        "content": "Robotics market update with enough meaningful context. " * 8,
        "source_base_url": "example.com",
        "doc_type": "market",
    }
    base_context = {
        "capability_profile": {"entry_type": "search_template"},
        "content_extraction": {"page_family": "article"},
        "http_status": 200,
        "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
        "meaningful_gate_config": {"min_semantic_len": 20},
    }

    with patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False):
        disabled_result = _evaluate_quality_frontdoor(
            document_candidate=low_value_candidate,
            terminal_context=dict(base_context),
        )
        strict_result = _evaluate_quality_frontdoor(
            document_candidate=low_value_candidate,
            terminal_context={**base_context, "strict_mode": True},
        )

    disabled_gate = (disabled_result.get("quality_gates") or {}).get("gate_config") or {}
    strict_gate = (strict_result.get("quality_gates") or {}).get("gate_config") or {}
    return [
        {
            "name": "disabled_default_does_not_force_low_value_reject",
            "passed": disabled_result.get("admission") == "accept"
            and disabled_gate.get("enable_strict_gate") is False
            and disabled_gate.get("strict_gate_source") == "disabled",
            "evidence": {
                "admission": disabled_result.get("admission"),
                "gate_config": disabled_gate,
            },
        },
        {
            "name": "strict_mode_forces_meaningful_gate",
            "passed": strict_result.get("admission") == "reject"
            and strict_result.get("reason_code") == "domain_blocked"
            and strict_gate.get("enable_strict_gate") is True
            and strict_gate.get("strict_gate_source") == "terminal_context.strict_mode"
            and ((strict_result.get("quality_gates") or {}).get("url_gate") or {}).get("reason")
            == "url_policy_low_value_endpoint",
            "evidence": {
                "admission": strict_result.get("admission"),
                "reason_code": strict_result.get("reason_code"),
                "gate_config": strict_gate,
                "url_gate": (strict_result.get("quality_gates") or {}).get("url_gate"),
            },
        },
    ]


def run_check() -> dict[str, Any]:
    root = _repo_root()
    token_results = [
        _token_check(
            root,
            "main/backend/app/services/ingest/postprocess_frontdoor.py",
            (
                "terminal_context.strict_mode",
                "meaningful_gate_config",
                "strict_gate_source",
                '"gate_config"',
                '"strict_gate_enabled"',
            ),
        ),
        _token_check(
            root,
            "main/backend/app/services/ingest/url_pool.py",
            (
                '"strict_mode": bool(strict_mode)',
                '"source_library_frontdoor"',
                "run_postprocess_frontdoor",
            ),
        ),
        _token_check(
            root,
            "main/backend/tests/unit/test_postprocess_frontdoor_unittest.py",
            (
                "test_frontdoor_quality_gate_strict_mode_forces_request_level_gate",
                "terminal_context.strict_mode",
            ),
        ),
        _token_check(
            root,
            "main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py",
            (
                'captured["params"]["strict_mode"]',
                'terminal_context"]["strict_mode"]',
            ),
        ),
        _token_check(
            root,
            str(TOPIC_DOC),
            (
                "Wave9-1 Meaningful Ingest Guardrails Contract",
                "strict_mode",
                "gate_config",
                "remaining_gap",
            ),
        ),
    ]
    runtime_results = _runtime_checks(root)
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_doc": str(TOPIC_DOC),
        "token_results": token_results,
        "runtime_results": runtime_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)

    result = run_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"token_checks={len(result['token_results'])} runtime_checks={len(result['runtime_results'])}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
