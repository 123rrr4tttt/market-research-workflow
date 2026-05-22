from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.source_library_public_live_probes import _run_target
from scripts.source_library_public_live_probes import _status_counts


DEFAULT_REPLAY_QUERY_TERMS = [
    "openai api pricing",
    "anthropic claude code",
    "gpt 4.1 release",
    "langchain sqlitecache",
]

_HISTORICAL_DEMO_PROJ_SEARCH_TEMPLATE_ROWS: tuple[tuple[int, str, bool, str, str | None], ...] = (
    (33, "news.google.com", True, "https://news.google.com/search?q={{q}}", None),
    (34, "actiontoaction.ai", True, "https://actiontoaction.ai/search/search?query={{q}}", None),
    (35, "hai.stanford.edu", True, "https://hai.stanford.edu/search?q={{q}}", None),
    (37, "iyiou.com", True, "https://iyiou.com/search/?q={{q}}", None),
    (38, "news.cn", True, "http://news.cn/search?q={{q}}", None),
    (39, "x.com", False, "https://x.com/search?q={{q}}", "platform_api_required"),
    (40, "github.com", True, "https://github.com/search?q={{q}}", None),
    (41, "arxiv.org", True, "https://arxiv.org/search?q={{q}}", None),
    (43, "stcn.com", True, "https://stcn.com/search?q={{q}}", None),
    (49, "slashgear.com", True, "https://slashgear.com/search?q={{q}}", None),
    (59, "arstechnica.com", True, "https://arstechnica.com/search?q={{q}}", None),
    (62, "linkedin.com", False, "https://linkedin.com/search?q={{q}}", "platform_api_required"),
    (66, "laptopmag.com", True, "https://laptopmag.com/search?q={{q}}", None),
    (70, "theverge.com", True, "https://theverge.com/search?q={{q}}", None),
    (75, "howtogeek.com", True, "https://howtogeek.com/search/?q={{q}}", None),
    (79, "cosmopolitan.com", True, "https://cosmopolitan.com/search?q={{q}}", None),
    (83, "moorinsightsstrategy.com", True, "https://moorinsightsstrategy.com/find?q={{q}}", "parser_enhance"),
    (93, "androidpolice.com", True, "https://androidpolice.com/search/?q={{q}}", None),
    (99, "supernote.com", True, "https://supernote.com/search?q={{q}}", "parser_enhance"),
    (106, "gizmodo.com", True, "https://gizmodo.com/search?q={{q}}", "parser_enhance"),
    (110, "reddit.com", False, "https://reddit.com/search?q={{q}}", "platform_api_required"),
    (113, "youtube.com", False, "https://youtube.com/search?q={{q}}", "platform_api_required"),
    (116, "cybernews.com", True, "https://cybernews.com/search?q={{q}}", None),
    (119, "thequalityedit.com", True, "https://thequalityedit.com/search?q={{q}}", "parser_enhance"),
    (123, "dcrainmaker.com", True, "https://dcrainmaker.com/search?q={{q}}", None),
    (130, "serverman.co.uk", True, "https://www.serverman.co.uk/?s={{q}}", "parser_enhance"),
    (148, "news.google.com", True, "https://news.google.com/search?q={{q}}", "parser_enhance"),
    (150, "actiontoaction.ai", True, "https://actiontoaction.ai/search?q={{q}}", "parser_enhance"),
    (152, "github.com", True, "https://github.com/search?q={{q}}", None),
    (154, "x.com", False, "https://x.com/search?q={{q}}", "platform_api_required"),
    (156, "arxiv.org", True, "https://arxiv.org/search?q={{q}}", None),
    (159, "hai.stanford.edu", True, "https://hai.stanford.edu/search?q={{q}}", "parser_enhance"),
    (163, "stcn.com", True, "https://stcn.com/search?q={{q}}", None),
    (166, "iyiou.com", True, "https://iyiou.com/search?q={{q}}", "parser_enhance"),
    (168, "news.cn", True, "http://news.cn/search?q={{q}}", "parser_enhance"),
    (170, "docs.github.com", True, "https://docs.github.com/search?query={{q}}", None),
    (171, "developer.mozilla.org", True, "https://developer.mozilla.org/en-US/search?q={{q}}", None),
    (172, "docs.anthropic.com", True, "https://docs.anthropic.com/en/search?q={{q}}", None),
    (173, "cloud.google.com", True, "https://cloud.google.com/search?query={{q}}", None),
    (174, "help.openai.com", True, "https://help.openai.com/en/?q={{q}}", None),
    (175, "venturebeat.com", True, "https://venturebeat.com/?s={{q}}", None),
    (176, "www.pymnts.com", True, "https://www.pymnts.com/?s={{q}}", "parser_enhance"),
    (177, "www.finextra.com", True, "https://www.finextra.com/searcharticle.aspx?search={{q}}", None),
    (178, "commercialobserver.com", True, "https://commercialobserver.com/?s={{q}}", None),
    (179, "www.investopedia.com", True, "https://www.investopedia.com/search?q={{q}}", None),
)


TargetRunner = Callable[[dict[str, Any]], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def _default_target(row: tuple[int, str, bool, str, str | None]) -> dict[str, Any]:
    site_entry_id, domain, enabled, template, remediation_status = row
    category = remediation_status or "historical_search_template"
    return {
        "target_id": f"demo_proj_{site_entry_id}_{_slug(domain)}",
        "site_entry_id": site_entry_id,
        "domain": domain,
        "template": template,
        "query_terms": list(DEFAULT_REPLAY_QUERY_TERMS),
        "enabled": enabled,
        "category": category,
        "historical_source": "project_demo_proj.resource_pool_site_entries",
        "source_library_item_key": "handler.cluster.search_template",
        "reason": (
            "Disabled in demo_proj as platform/API-required search; keep in the historical 45-site replay manifest "
            "but do not contact by default even when public replay is enabled."
            if not enabled
            else "Historical demo_proj handler.cluster.search_template site-entry replay target."
        ),
        "skip_public_execution": not enabled,
    }


DEFAULT_HISTORICAL_TARGETS: list[dict[str, Any]] = [
    _default_target(row) for row in _HISTORICAL_DEMO_PROJ_SEARCH_TEMPLATE_ROWS
]


def default_manifest() -> dict[str, Any]:
    return {
        "description": "Wave4 source_library replay scaleout manifest for the historical demo_proj 45-site search_template set.",
        "project_key": "demo_proj",
        "source_library_item_key": "handler.cluster.search_template",
        "query_terms": list(DEFAULT_REPLAY_QUERY_TERMS),
        "public_network_default": "disabled",
        "targets": [dict(row) for row in DEFAULT_HISTORICAL_TARGETS],
    }


def _load_manifest(path: Path | None) -> dict[str, Any]:
    if path is None:
        return default_manifest()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"targets": payload}
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object or a target list")
    return dict(payload)


def _targets_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_targets = manifest.get("targets")
    if not isinstance(raw_targets, list):
        raise ValueError("manifest.targets must be a list")
    default_terms = [str(x).strip() for x in manifest.get("query_terms") or DEFAULT_REPLAY_QUERY_TERMS if str(x).strip()]
    out: list[dict[str, Any]] = []
    for index, row in enumerate(raw_targets):
        if not isinstance(row, dict):
            raise ValueError(f"manifest target at index {index} must be an object")
        target = dict(row)
        target.setdefault("target_id", f"target_{index + 1}")
        target.setdefault("query_terms", default_terms)
        target.setdefault("enabled", True)
        target.setdefault("category", "historical_search_template")
        target.setdefault("skip_public_execution", not bool(target.get("enabled", True)))
        out.append(target)
    return out


def validate_manifest_targets(targets: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, target in enumerate(targets):
        target_id = str(target.get("target_id") or "").strip()
        template = str(target.get("template") or "").strip()
        query_terms = [str(x).strip() for x in target.get("query_terms") or [] if str(x).strip()]
        if not target_id:
            errors.append(f"target[{index}] missing target_id")
        elif target_id in seen:
            errors.append(f"duplicate target_id: {target_id}")
        seen.add(target_id)
        if "{{q}}" not in template:
            errors.append(f"{target_id or f'target[{index}]'} template must contain {{q}}")
        if not query_terms:
            errors.append(f"{target_id or f'target[{index}]'} query_terms must be non-empty")
    return {
        "passed": not errors,
        "errors": errors,
        "target_count": len(targets),
        "enabled_target_count": sum(1 for target in targets if bool(target.get("enabled", True))),
        "policy_skipped_target_count": sum(1 for target in targets if bool(target.get("skip_public_execution"))),
    }


def _skipped_network_result(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": _target_summary(target),
        "entry_domain": str(target.get("domain") or "").strip().lower(),
        "elapsed_ms": 0,
        "classification": {
            "status": "skipped_public_network_disabled",
            "blocker_type": "operator_gate",
            "reason": "Set --allow-public-network or SOURCE_LIBRARY_ALLOW_PUBLIC_REPLAY=1 to run the public 45-site replay.",
        },
        "adapter_result": _empty_adapter_result(skipped=1),
    }


def _skipped_policy_result(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": _target_summary(target),
        "entry_domain": str(target.get("domain") or "").strip().lower(),
        "elapsed_ms": 0,
        "classification": {
            "status": "skipped_policy_disabled_platform_entry",
            "blocker_type": "policy_or_platform_required",
            "reason": "Historical target is disabled in demo_proj because it requires a platform/API-specific lane.",
        },
        "adapter_result": _empty_adapter_result(skipped=1),
    }


def _empty_adapter_result(*, skipped: int) -> dict[str, Any]:
    return {
        "inserted": 0,
        "skipped": skipped,
        "candidate_count": 0,
        "candidates": [],
        "used_term_fallback": None,
        "pages_scanned": 0,
        "search_urls": [],
        "diagnostics": {},
        "errors": [],
    }


def _target_summary(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(target.get("target_id") or "").strip(),
        "site_entry_id": target.get("site_entry_id"),
        "domain": str(target.get("domain") or "").strip(),
        "template": str(target.get("template") or "").strip(),
        "query_terms": [str(x).strip() for x in target.get("query_terms") or [] if str(x).strip()],
        "enabled": bool(target.get("enabled", True)),
        "category": str(target.get("category") or "").strip(),
        "reason": str(target.get("reason") or "").strip(),
    }


def _blockers_from_results(target_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for row in target_results:
        classification = row.get("classification") or {}
        blocker_type = classification.get("blocker_type")
        if not blocker_type:
            continue
        target = row.get("target") or {}
        blockers.append(
            {
                "target_id": str(target.get("target_id") or ""),
                "domain": str(target.get("domain") or row.get("entry_domain") or ""),
                "template": str(target.get("template") or ""),
                "status": str(classification.get("status") or ""),
                "blocker_type": blocker_type,
                "reason": str(classification.get("reason") or ""),
            }
        )
    return blockers


def _term_fallback_review(target_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for row in target_results:
        classification = row.get("classification") or {}
        if classification.get("status") != "candidate_ready_with_term_fallback":
            continue
        target = row.get("target") or {}
        adapter_result = row.get("adapter_result") or {}
        review.append(
            {
                "target_id": str(target.get("target_id") or ""),
                "domain": str(target.get("domain") or row.get("entry_domain") or ""),
                "query_terms": list(target.get("query_terms") or []),
                "candidate_count": int(adapter_result.get("candidate_count") or 0),
                "candidates": list(adapter_result.get("candidates") or [])[:10],
                "review_reason": "Candidates were selected only after term fallback; inspect relevance before counting as dirty-source closure.",
            }
        )
    return review


def _runner_for_target(*, project_key: str, probe_timeout: float) -> TargetRunner:
    def _runner(target: dict[str, Any]) -> dict[str, Any]:
        return _run_target(target, project_key=project_key, probe_timeout=probe_timeout)

    return _runner


def run_replay(
    *,
    manifest: dict[str, Any] | None = None,
    allow_public_network: bool = False,
    project_key: str = "demo_proj",
    probe_timeout: float = 6.0,
    max_targets: int | None = None,
    target_runner: TargetRunner | None = None,
) -> dict[str, Any]:
    resolved_manifest = dict(manifest or default_manifest())
    selected_targets = _targets_from_manifest(resolved_manifest)
    if max_targets is not None:
        selected_targets = selected_targets[: max(0, int(max_targets))]
    started_at = _utc_now()
    manifest_validation = validate_manifest_targets(selected_targets)

    if not manifest_validation["passed"]:
        target_results: list[dict[str, Any]] = []
    elif not allow_public_network:
        target_results = [_skipped_network_result(target) for target in selected_targets]
    else:
        runner = target_runner or _runner_for_target(project_key=project_key, probe_timeout=probe_timeout)
        target_results = []
        for target in selected_targets:
            if bool(target.get("skip_public_execution")):
                target_results.append(_skipped_policy_result(target))
                continue
            target_results.append(runner(target))

    blockers = _blockers_from_results(target_results)
    code_failures = [row for row in blockers if row.get("blocker_type") == "probe_runtime_exception"]
    candidate_ready = [
        str((row.get("target") or {}).get("target_id") or "")
        for row in target_results
        if str((row.get("classification") or {}).get("status") or "").startswith("candidate_ready")
    ]
    term_review = _term_fallback_review(target_results)
    public_attempted = sum(
        1
        for row in target_results
        if not str((row.get("classification") or {}).get("status") or "").startswith("skipped_")
    )
    validation_errors = list(manifest_validation["errors"]) + [
        f"{row['target_id']}: {row['reason']}" for row in code_failures
    ]
    result = {
        "probe_id": "source_library_replay_scaleout_2026_05_22",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "mode": {
            "allow_public_network": bool(allow_public_network),
            "skip_safe": True,
            "public_network_env": os.environ.get("SOURCE_LIBRARY_ALLOW_PUBLIC_REPLAY", ""),
        },
        "inputs": {
            "project_key": project_key,
            "source_library_item_key": str(resolved_manifest.get("source_library_item_key") or "handler.cluster.search_template"),
            "probe_timeout": probe_timeout,
            "target_count": len(selected_targets),
            "manifest_validation": manifest_validation,
            "targets": [_target_summary(target) for target in selected_targets],
        },
        "outputs": {
            "target_results": target_results,
            "status_counts": _status_counts(target_results),
            "candidate_ready_targets": candidate_ready,
            "public_targets_attempted": public_attempted,
            "blockers_by_target": blockers,
            "term_fallback_relevance_review": term_review,
            "blocker_type_counts": _blocker_type_counts(blockers),
        },
        "closure_status": {
            "AT-AC-06": (
                "public replay attempted and separated transport/anti-bot blockers from code failures"
                if allow_public_network
                else "full 45-site replay manifest is ready; public network execution skipped by operator gate"
            ),
            "AT-AC-10": (
                "full historical 45-site replay gate exists; unresolved targets remain classified per blocker_type"
                if allow_public_network
                else "full historical 45-site manifest is covered by a no-network gate; dirty-source closure still requires opt-in public replay"
            ),
        },
        "validation": {
            "passed": not validation_errors,
            "skipped": not bool(allow_public_network),
            "full_historical_manifest": len(selected_targets) == 45,
            "live_evidence_sufficient": bool(allow_public_network and public_attempted and not code_failures),
            "errors": validation_errors,
            "warnings": [
                "public replay is environment-dependent and must not be required by CI",
                "term-fallback targets require relevance review before closure",
            ],
        },
    }
    return result


def _blocker_type_counts(blockers: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for blocker in blockers:
        blocker_type = str(blocker.get("blocker_type") or "unknown")
        counts[blocker_type] = counts.get(blocker_type, 0) + 1
    return counts


def _build_log_lines(result: dict[str, Any]) -> list[str]:
    lines = [
        f"probe_id={result.get('probe_id')}",
        f"started_at={result.get('started_at')}",
        f"finished_at={result.get('finished_at')}",
        f"allow_public_network={result.get('mode', {}).get('allow_public_network')}",
        f"target_count={result.get('inputs', {}).get('target_count')}",
        f"public_targets_attempted={result.get('outputs', {}).get('public_targets_attempted')}",
    ]
    for row in result.get("outputs", {}).get("target_results", []):
        target = row.get("target") or {}
        classification = row.get("classification") or {}
        adapter_result = row.get("adapter_result") or {}
        lines.append(
            "target={target_id} domain={domain} status={status} blocker_type={blocker_type} candidates={candidate_count}".format(
                target_id=target.get("target_id"),
                domain=target.get("domain") or row.get("entry_domain"),
                status=classification.get("status"),
                blocker_type=classification.get("blocker_type"),
                candidate_count=adapter_result.get("candidate_count"),
            )
        )
    for blocker in result.get("outputs", {}).get("blockers_by_target", []):
        lines.append(
            "blocker target={target_id} domain={domain} blocker_type={blocker_type} status={status}".format(
                target_id=blocker.get("target_id"),
                domain=blocker.get("domain"),
                blocker_type=blocker.get("blocker_type"),
                status=blocker.get("status"),
            )
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run skip-safe source_library replay scaleout for the historical demo_proj 45-site manifest.")
    parser.add_argument("--manifest", type=Path, default=None, help="JSON manifest. Defaults to the embedded demo_proj 45-site snapshot.")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Write the resolved manifest JSON without changing replay behavior.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON replay output path.")
    parser.add_argument("--log-output", type=Path, default=None, help="Optional plain-text replay log path.")
    parser.add_argument("--probe-timeout", type=float, default=6.0)
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--max-targets", type=int, default=None)
    parser.add_argument("--allow-public-network", action="store_true", help="Actually contact public websites for enabled targets.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when live evidence is skipped or has code failures.")
    args = parser.parse_args(argv)

    env_allows_public = os.environ.get("SOURCE_LIBRARY_ALLOW_PUBLIC_REPLAY", "").strip().lower() in {"1", "true", "yes"}
    manifest = _load_manifest(args.manifest)
    if args.manifest_output:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    result = run_replay(
        manifest=manifest,
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

    validation = result.get("validation", {})
    if not validation.get("passed"):
        return 1
    if args.strict and not validation.get("live_evidence_sufficient"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
