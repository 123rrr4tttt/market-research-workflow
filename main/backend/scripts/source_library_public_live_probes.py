from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resource_pool.search_template_adapters import apply_search_template_adapter_plan
from app.services.resource_pool.search_template_adapters import resolve_search_template_adapter_plan
from app.services.resource_pool.url_utils import domain_from_url
from app.services.source_library.adapters.generic_web import handle_generic_web_search_template


DEFAULT_TARGETS: list[dict[str, Any]] = [
    {
        "target_id": "commercialobserver_parser_weak",
        "template": "https://commercialobserver.com/?s={{q}}",
        "query_terms": ["openai"],
        "category": "parser_weak",
        "reason": "Wave2 parser-enhanced dirty-source candidate; verifies public card extraction or records anti-bot/source blocker.",
    },
    {
        "target_id": "pymnts_parser_weak",
        "template": "https://www.pymnts.com/?s={{q}}",
        "query_terms": ["openai"],
        "category": "parser_weak",
        "reason": "Wave2 parser-enhanced candidate; verifies public article-card extraction or records source semantics blocker.",
    },
    {
        "target_id": "investopedia_validated_query",
        "template": "https://www.investopedia.com/search?q={{q}}",
        "query_terms": ["inflation"],
        "category": "validated_query_capable",
        "reason": "Validated query-capable baseline used to separate environment/network failures from dirty-source failures.",
    },
    {
        "target_id": "hai_stanford_mixed_shell",
        "template": "https://hai.stanford.edu/search?keyword={{q}}",
        "query_terms": ["openai"],
        "category": "mixed_dynamic_shell",
        "reason": "Previously mixed dynamic-shell/parser target; records whether current public route is still source-side blocked.",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _redact_target(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(target.get("target_id") or "").strip(),
        "template": str(target.get("template") or "").strip(),
        "query_terms": [str(x).strip() for x in target.get("query_terms") or [] if str(x).strip()],
        "category": str(target.get("category") or "").strip(),
        "reason": str(target.get("reason") or "").strip(),
    }


def _summarize_adapter_result(result: dict[str, Any]) -> dict[str, Any]:
    diagnostics = dict(result.get("diagnostics") or {})
    return {
        "inserted": result.get("inserted"),
        "skipped": result.get("skipped"),
        "candidate_count": len(result.get("candidates") or []),
        "candidates": list(result.get("candidates") or [])[:10],
        "used_term_fallback": result.get("used_term_fallback"),
        "pages_scanned": result.get("pages_scanned"),
        "search_urls": list(result.get("search_urls") or []),
        "diagnostics": diagnostics,
        "errors": list(result.get("errors") or []),
        "source_mode": result.get("source_mode"),
        "capability_profile": dict(result.get("capability_profile") or {}),
        "adapter_taxonomy": dict(result.get("adapter_taxonomy") or {}),
    }


def _error_text(errors: list[dict[str, Any]]) -> str:
    return " ".join(str(row.get("error") or row) for row in errors).lower()


def classify_public_probe_result(result: dict[str, Any]) -> dict[str, Any]:
    candidates = list(result.get("candidates") or [])
    diagnostics = dict(result.get("diagnostics") or {})
    errors = list(result.get("errors") or [])
    raw_candidates = int(diagnostics.get("raw_candidates") or 0)
    selected_candidates = int(diagnostics.get("selected_candidates") or len(candidates))
    transport_errors = int(diagnostics.get("transport_errors") or 0)
    candidate_filter_state = str(diagnostics.get("candidate_filter_state") or "").strip()
    used_term_fallback = bool(result.get("used_term_fallback") or diagnostics.get("used_term_fallback"))
    text = _error_text(errors)

    if errors or transport_errors:
        if any(marker in text for marker in ("403", "429", "blocked", "rate limit", "failed to fetch")):
            return {
                "status": "anti_bot_or_transport_blocked",
                "blocker_type": "public_network_or_anti_bot",
                "reason": "Public fetch failed with anti-bot/rate-limit/transport signature.",
            }
        return {
            "status": "transport_blocked",
            "blocker_type": "public_network",
            "reason": "Public fetch failed before candidate extraction completed.",
        }
    if selected_candidates > 0 or candidates:
        if used_term_fallback or "fallback" in candidate_filter_state:
            return {
                "status": "candidate_ready_with_term_fallback",
                "blocker_type": "relevance_review",
                "reason": "Public execution returned candidates only after term fallback; keep as review evidence, not full dirty-source closure.",
            }
        return {
            "status": "candidate_ready",
            "blocker_type": None,
            "reason": "Public search-template execution returned selected candidates.",
        }
    if raw_candidates > 0:
        return {
            "status": "parser_or_source_semantics_blocked",
            "blocker_type": "parser_or_dirty_source",
            "reason": f"Public page returned raw candidates but selection ended as {candidate_filter_state or 'empty'}.",
        }
    return {
        "status": "empty_public_result",
        "blocker_type": "empty_or_dynamic_source",
        "reason": "Public page fetched without selected or raw candidates; dynamic shell or source mismatch likely.",
    }


def _load_targets(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(row) for row in DEFAULT_TARGETS]
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_targets = payload.get("targets") if isinstance(payload, dict) else payload
    if not isinstance(raw_targets, list):
        raise ValueError("target file must contain a list or an object with targets")
    targets: list[dict[str, Any]] = []
    for index, row in enumerate(raw_targets):
        if not isinstance(row, dict):
            raise ValueError(f"target at index {index} must be an object")
        targets.append(dict(row))
    return targets


def _target_params(target: dict[str, Any], *, probe_timeout: float) -> dict[str, Any]:
    template = str(target.get("template") or "").strip()
    query_terms = [str(x).strip() for x in target.get("query_terms") or [] if str(x).strip()]
    if not template or "{{q}}" not in template:
        raise ValueError(f"{target.get('target_id') or template or '<target>'} requires template containing {{q}}")
    if not query_terms:
        raise ValueError(f"{target.get('target_id') or template} requires non-empty query_terms")

    params = {
        "template": template,
        "query_terms": query_terms,
        "probe_timeout": float(target.get("probe_timeout") or probe_timeout),
        "allow_term_fallback": bool(target.get("allow_term_fallback", True)),
        "enable_search_service_fallback": bool(target.get("enable_search_service_fallback", True)),
        "max_pages": int(target.get("max_pages") or 1),
        "_source_library_item": {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "item_type": "service_aggregated",
            "managed_by": "system",
            "extra": {"expected_entry_type": "search_template"},
        },
    }
    for key in (
        "search_service",
        "parser_profile",
        "fallback_limit",
        "candidate_scoring_config",
        "external_search_provider",
        "external_search_language",
        "external_search_limit",
        "enable_external_search_fallback",
        "enable_external_search_slowlane",
    ):
        if key in target:
            params[key] = target[key]
    entry_domain = str(target.get("entry_domain") or domain_from_url(template) or "").strip().lower()
    plan = resolve_search_template_adapter_plan(site_url=template, entry_domain=entry_domain, params=params)
    return apply_search_template_adapter_plan(plan=plan, params=params)


def _run_target(target: dict[str, Any], *, project_key: str, probe_timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    target_id = str(target.get("target_id") or target.get("template") or "").strip()
    params = _target_params(target, probe_timeout=probe_timeout)
    template = str(params.get("template") or "")
    entry_domain = str(target.get("entry_domain") or domain_from_url(template) or "").strip().lower()
    plan = resolve_search_template_adapter_plan(site_url=template, entry_domain=entry_domain, params=params)
    try:
        adapter_result = handle_generic_web_search_template(params, project_key=project_key)
        summary = _summarize_adapter_result(adapter_result)
        classification = classify_public_probe_result(summary)
        return {
            "target": _redact_target(target),
            "entry_domain": entry_domain,
            "adapter_plan": {
                "adapter_key": plan.adapter_key,
                "parser_profile": plan.parser_profile,
                "param_overrides": dict(plan.param_overrides or {}),
                "reason": plan.reason,
            },
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "classification": classification,
            "adapter_result": summary,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "target": _redact_target(target),
            "entry_domain": entry_domain,
            "adapter_plan": {
                "adapter_key": plan.adapter_key,
                "parser_profile": plan.parser_profile,
                "param_overrides": dict(plan.param_overrides or {}),
                "reason": plan.reason,
            },
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "classification": {
                "status": "probe_exception",
                "blocker_type": "probe_runtime_exception",
                "reason": str(exc),
            },
            "adapter_result": {
                "inserted": 0,
                "skipped": 0,
                "candidate_count": 0,
                "candidates": [],
                "used_term_fallback": None,
                "pages_scanned": 0,
                "search_urls": [],
                "diagnostics": {},
                "errors": [{"error": str(exc), "error_class": "probe_exception"}],
            },
        }


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        status = str((row.get("classification") or {}).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _build_log_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        f"probe_id={result.get('probe_id')}",
        f"started_at={result.get('started_at')}",
        f"finished_at={result.get('finished_at')}",
        f"allow_public_network={result.get('mode', {}).get('allow_public_network')}",
        f"target_count={result.get('inputs', {}).get('target_count')}",
    ]
    for row in result.get("outputs", {}).get("target_results", []):
        target = row.get("target") or {}
        classification = row.get("classification") or {}
        adapter_result = row.get("adapter_result") or {}
        lines.append(
            "target={target_id} status={status} candidates={candidate_count} elapsed_ms={elapsed_ms} reason={reason}".format(
                target_id=target.get("target_id"),
                status=classification.get("status"),
                candidate_count=adapter_result.get("candidate_count"),
                elapsed_ms=row.get("elapsed_ms"),
                reason=classification.get("reason"),
            )
        )
    for blocker in result.get("outputs", {}).get("dirty_source_shortlist", []):
        lines.append(
            "blocker target={target_id} blocker_type={blocker_type} status={status}".format(
                target_id=blocker.get("target_id"),
                blocker_type=blocker.get("blocker_type"),
                status=blocker.get("status"),
            )
        )
    return lines


def run_probe(
    *,
    targets: list[dict[str, Any]] | None = None,
    allow_public_network: bool = False,
    project_key: str = "demo_proj",
    probe_timeout: float = 6.0,
    max_targets: int | None = None,
) -> dict[str, Any]:
    selected_targets = [dict(row) for row in (targets if targets is not None else DEFAULT_TARGETS)]
    if max_targets is not None:
        selected_targets = selected_targets[: max(0, int(max_targets))]
    started_at = _utc_now()
    if not allow_public_network:
        target_results = [
            {
                "target": _redact_target(target),
                "entry_domain": str(domain_from_url(str(target.get("template") or "")) or "").strip().lower(),
                "elapsed_ms": 0,
                "classification": {
                    "status": "skipped_public_network_disabled",
                    "blocker_type": "operator_gate",
                    "reason": "Set --allow-public-network or SOURCE_LIBRARY_ALLOW_PUBLIC_PROBES=1 to run public probes.",
                },
                "adapter_result": {
                    "inserted": 0,
                    "skipped": 1,
                    "candidate_count": 0,
                    "candidates": [],
                    "used_term_fallback": None,
                    "pages_scanned": 0,
                    "search_urls": [],
                    "diagnostics": {},
                    "errors": [],
                },
            }
            for target in selected_targets
        ]
        result = {
            "probe_id": "source_library_public_live_probes_2026_05_22",
            "started_at": started_at,
            "finished_at": _utc_now(),
            "mode": {
                "allow_public_network": False,
                "skip_safe": True,
                "public_network_env": os.environ.get("SOURCE_LIBRARY_ALLOW_PUBLIC_PROBES", ""),
            },
            "inputs": {
                "project_key": project_key,
                "probe_timeout": probe_timeout,
                "target_count": len(selected_targets),
                "targets": [_redact_target(target) for target in selected_targets],
            },
            "outputs": {
                "target_results": target_results,
                "status_counts": _status_counts(target_results),
                "candidate_ready_targets": [],
                "dirty_source_shortlist": [],
            },
            "closure_status": {
                "AT-AC-06": "public live probe skipped by explicit operator gate; deterministic local anti-bot evidence still stands",
                "AT-AC-10": "dirty-source public replay remains open until --allow-public-network is run in a suitable environment",
            },
            "validation": {
                "passed": True,
                "skipped": True,
                "live_evidence_sufficient": False,
                "errors": [],
                "warnings": ["public network probe skipped by operator gate"],
            },
        }
        return result

    target_results = [
        _run_target(target, project_key=project_key, probe_timeout=probe_timeout)
        for target in selected_targets
    ]
    candidate_ready = [
        str((row.get("target") or {}).get("target_id") or "")
        for row in target_results
        if str((row.get("classification") or {}).get("status") or "").startswith("candidate_ready")
    ]
    blockers = [
        {
            "target_id": str((row.get("target") or {}).get("target_id") or ""),
            "template": str((row.get("target") or {}).get("template") or ""),
            "status": str((row.get("classification") or {}).get("status") or ""),
            "blocker_type": (row.get("classification") or {}).get("blocker_type"),
            "reason": str((row.get("classification") or {}).get("reason") or ""),
        }
        for row in target_results
        if (row.get("classification") or {}).get("blocker_type")
    ]
    internal_errors = [
        blocker
        for blocker in blockers
        if blocker.get("blocker_type") == "probe_runtime_exception"
    ]
    return {
        "probe_id": "source_library_public_live_probes_2026_05_22",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "mode": {
            "allow_public_network": True,
            "skip_safe": True,
            "public_network_env": os.environ.get("SOURCE_LIBRARY_ALLOW_PUBLIC_PROBES", ""),
        },
        "inputs": {
            "project_key": project_key,
            "probe_timeout": probe_timeout,
            "target_count": len(selected_targets),
            "targets": [_redact_target(target) for target in selected_targets],
        },
        "outputs": {
            "target_results": target_results,
            "status_counts": _status_counts(target_results),
            "candidate_ready_targets": candidate_ready,
            "dirty_source_shortlist": blockers,
        },
        "closure_status": {
            "AT-AC-06": (
                "public live probe produced candidate-ready evidence"
                if candidate_ready
                else "public live probe ran but did not produce candidate-ready evidence"
            ),
            "AT-AC-10": (
                "public replay produced a dirty-source shortlist; unresolved blockers remain classified per target"
                if blockers
                else "public replay produced no dirty-source blockers for selected targets"
            ),
        },
        "validation": {
            "passed": not internal_errors,
            "skipped": False,
            "live_evidence_sufficient": bool(candidate_ready),
            "errors": internal_errors,
            "warnings": [
                "public live evidence is environment-dependent; rerun before using it as closure proof"
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run skip-safe public live probes for source_library search-template targets.")
    parser.add_argument("--target-file", type=Path, default=None, help="JSON target list. Defaults to curated Wave3 source-library targets.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--log-output", type=Path, default=None, help="Optional plain-text log output path.")
    parser.add_argument("--probe-timeout", type=float, default=6.0)
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--allow-public-network", action="store_true", help="Actually contact public websites.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when live evidence is skipped or has no candidate-ready target.")
    args = parser.parse_args(argv)

    env_allows_public = os.environ.get("SOURCE_LIBRARY_ALLOW_PUBLIC_PROBES", "").strip().lower() in {"1", "true", "yes"}
    targets = _load_targets(args.target_file)
    result = run_probe(
        targets=targets,
        allow_public_network=bool(args.allow_public_network or env_allows_public),
        project_key=args.project_key,
        probe_timeout=args.probe_timeout,
        max_targets=args.max_targets,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.log_output:
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text("\n".join(_build_log_lines(result)) + "\n", encoding="utf-8")
    print(payload)

    if not result.get("validation", {}).get("passed"):
        return 1
    if args.strict and not result.get("validation", {}).get("live_evidence_sufficient"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
