from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.source_library_replay_scaleout import DEFAULT_HISTORICAL_TARGETS
from scripts.source_library_replay_scaleout import run_replay
from scripts.source_library_replay_scaleout import validate_manifest_targets


CONTRACT_VERSION = "source_library.public_replay_a5_gate.v1"
REPLAY_RUN_DIR = Path("development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22")
LIVE_PROBE_RUN_DIR = Path("development/latest-dev-docs/automation-runs/source-library-live-probes/2026-05-22")
WAVE7_A5_DOC = Path(
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-07-crawler-source-expansion/2026-05-22-wave7-a5-public-replay-evidence.md"
)
WAVE47_CLOSURE_DOC = Path(
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-07-crawler-source-expansion/10_wave47-manual-public-replay-closure-2026-05-23.md"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(root: Path, relative_path: Path, errors: list[str]) -> dict[str, Any]:
    path = root / relative_path
    if not path.is_file():
        errors.append(f"missing json artifact: {relative_path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid json artifact {relative_path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"json artifact must be an object: {relative_path}")
        return {}
    return payload


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _status_counts(payload: dict[str, Any]) -> dict[str, int]:
    raw_counts = ((payload.get("outputs") or {}).get("status_counts") or {})
    if not isinstance(raw_counts, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw_counts.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            counts[str(key)] = 0
    return counts


def _load_text(root: Path, relative_path: Path, errors: list[str]) -> str:
    path = root / relative_path
    if not path.is_file():
        errors.append(f"missing review artifact: {relative_path}")
        return ""
    return path.read_text(encoding="utf-8")


def _target_ids(payload: dict[str, Any]) -> set[str]:
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list):
        return set()
    return {
        str(target.get("target_id") or "").strip()
        for target in raw_targets
        if isinstance(target, dict) and str(target.get("target_id") or "").strip()
    }


def _artifact_input_summary(input_payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    expected_ids = {str(target.get("target_id") or "").strip() for target in DEFAULT_HISTORICAL_TARGETS}
    artifact_ids = _target_ids(input_payload)
    raw_targets = input_payload.get("targets") if isinstance(input_payload.get("targets"), list) else []
    enabled_count = sum(1 for target in raw_targets if isinstance(target, dict) and bool(target.get("enabled", True)))
    policy_skipped_count = sum(
        1 for target in raw_targets if isinstance(target, dict) and bool(target.get("skip_public_execution"))
    )

    _require(len(raw_targets) == 45, errors, "replay input artifact must contain 45 historical targets")
    _require(artifact_ids == expected_ids, errors, "replay input target_id set differs from embedded manifest")
    _require(enabled_count == 40, errors, "replay input artifact must contain 40 enabled public targets")
    _require(policy_skipped_count == 5, errors, "replay input artifact must contain 5 policy-disabled targets")

    return {
        "target_count": len(raw_targets),
        "enabled_target_count": enabled_count,
        "policy_skipped_target_count": policy_skipped_count,
        "target_ids_match_embedded_manifest": artifact_ids == expected_ids,
    }


def _deterministic_replay_summary(result: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    validation = result.get("validation") or {}
    outputs = result.get("outputs") or {}
    counts = _status_counts(result)

    _require(bool(validation.get("passed")), errors, "deterministic no-network replay validation must pass")
    _require(bool(validation.get("skipped")), errors, "deterministic no-network replay must stay skipped")
    _require(bool(validation.get("full_historical_manifest")), errors, "deterministic replay must cover full 45-site manifest")
    _require(counts == {"skipped_public_network_disabled": 45}, errors, "deterministic replay status_counts must skip 45 targets")
    _require(int(outputs.get("public_targets_attempted") or 0) == 0, errors, "deterministic replay must not attempt public targets")

    return {
        "validation_passed": bool(validation.get("passed")),
        "skipped": bool(validation.get("skipped")),
        "full_historical_manifest": bool(validation.get("full_historical_manifest")),
        "status_counts": counts,
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0),
    }


def _public_live_fixture_summary(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    validation = payload.get("validation") or {}
    outputs = payload.get("outputs") or {}
    counts = _status_counts(payload)
    blockers = outputs.get("dirty_source_shortlist") if isinstance(outputs.get("dirty_source_shortlist"), list) else []
    relevance_review = [
        blocker
        for blocker in blockers
        if isinstance(blocker, dict) and blocker.get("blocker_type") == "relevance_review"
    ]

    _require(bool(payload.get("mode", {}).get("allow_public_network")), errors, "public live fixture must record allow_public_network=true")
    _require(bool(validation.get("passed")), errors, "public live fixture validation must pass")
    _require(bool(validation.get("live_evidence_sufficient")), errors, "public live fixture must contain candidate-ready evidence")
    _require(int(payload.get("inputs", {}).get("target_count") or 0) == 4, errors, "public live fixture must cover the curated four-target probe")
    _require(counts.get("candidate_ready", 0) >= 1, errors, "public live fixture must contain candidate_ready targets")
    _require(
        counts.get("candidate_ready_with_term_fallback", 0) == len(relevance_review) and relevance_review,
        errors,
        "term-fallback targets must be preserved as relevance_review blockers",
    )

    return {
        "validation_passed": bool(validation.get("passed")),
        "live_evidence_sufficient": bool(validation.get("live_evidence_sufficient")),
        "target_count": int(payload.get("inputs", {}).get("target_count") or 0),
        "status_counts": counts,
        "candidate_ready_targets": list(outputs.get("candidate_ready_targets") or []),
        "relevance_review_targets": [
            {
                "target_id": str(blocker.get("target_id") or ""),
                "status": str(blocker.get("status") or ""),
                "reason": str(blocker.get("reason") or ""),
            }
            for blocker in relevance_review
        ],
    }


def _full_public_replay_summary(root: Path, errors: list[str]) -> dict[str, Any]:
    relative_path = REPLAY_RUN_DIR / "output.public.json"
    if not (root / relative_path).is_file():
        return {
            "status": "missing",
            "path": str(relative_path),
        }
    payload = _load_json(root, relative_path, errors)
    if not payload:
        return {
            "status": "missing",
            "path": str(relative_path),
        }

    mode = payload.get("mode") if isinstance(payload.get("mode"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    manifest_validation = (
        inputs.get("manifest_validation") if isinstance(inputs.get("manifest_validation"), dict) else {}
    )
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    target_results = outputs.get("target_results") if isinstance(outputs.get("target_results"), list) else []
    counts = _status_counts(payload)
    blocker_type_counts = outputs.get("blocker_type_counts") if isinstance(outputs.get("blocker_type_counts"), dict) else {}

    _require(bool(mode.get("allow_public_network")), errors, "full public replay must record allow_public_network=true")
    _require(bool(validation.get("passed")), errors, "full public replay validation must pass")
    _require(not bool(validation.get("skipped")), errors, "full public replay must not be skipped")
    _require(bool(validation.get("full_historical_manifest")), errors, "full public replay must cover full 45-site manifest")
    _require(bool(validation.get("live_evidence_sufficient")), errors, "full public replay must be sufficient live evidence")
    _require(int(inputs.get("target_count") or 0) == 45, errors, "full public replay must record 45 targets")
    _require(
        int(manifest_validation.get("enabled_target_count") or 0) == 40,
        errors,
        "full public replay must record 40 enabled public targets",
    )
    _require(
        int(manifest_validation.get("policy_skipped_target_count") or 0) == 5,
        errors,
        "full public replay must record 5 policy-disabled targets",
    )
    _require(len(target_results) == 45, errors, "full public replay must contain 45 target results")
    _require(int(outputs.get("public_targets_attempted") or 0) == 40, errors, "full public replay must attempt 40 targets")
    _require(
        int(counts.get("skipped_policy_disabled_platform_entry") or 0) == 5,
        errors,
        "full public replay must keep 5 platform/API entries policy-skipped",
    )
    _require(
        int(counts.get("skipped_public_network_disabled") or 0) == 0,
        errors,
        "full public replay must not contain operator-gate skips",
    )

    return {
        "status": "real_evidence_present_review_required",
        "path": str(relative_path),
        "allow_public_network": bool(mode.get("allow_public_network")),
        "target_count": int(inputs.get("target_count") or 0),
        "public_targets_attempted": int(outputs.get("public_targets_attempted") or 0),
        "status_counts": counts,
        "blocker_type_counts": blocker_type_counts,
        "live_evidence_sufficient": bool(validation.get("live_evidence_sufficient")),
    }


def _closure_review_summary(root: Path, errors: list[str]) -> dict[str, Any]:
    before_error_count = len(errors)
    text = _load_text(root, WAVE47_CLOSURE_DOC, errors)
    if not text:
        return {
            "status": "missing",
            "path": str(WAVE47_CLOSURE_DOC),
        }
    required_tokens = (
        "Wave47 Manual Public Replay Closure",
        "A5 status: `closed`",
        "real_evidence_present_review_required",
        "candidate_ready_with_term_fallback",
        "closure decision: `closed`",
    )
    missing = [token for token in required_tokens if token not in text]
    for token in missing:
        errors.append(f"closure review missing token {token!r}: {WAVE47_CLOSURE_DOC}")
    return {
        "status": "reviewed_for_topic_closure" if len(errors) == before_error_count else "needs_update",
        "path": str(WAVE47_CLOSURE_DOC),
        "missing_tokens": missing,
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    errors: list[str] = []

    manifest_validation = validate_manifest_targets([dict(target) for target in DEFAULT_HISTORICAL_TARGETS])
    _require(bool(manifest_validation.get("passed")), errors, "embedded 45-site manifest validation must pass")
    _require(int(manifest_validation.get("target_count") or 0) == 45, errors, "embedded manifest must contain 45 targets")
    _require(int(manifest_validation.get("enabled_target_count") or 0) == 40, errors, "embedded manifest must contain 40 enabled targets")
    _require(
        int(manifest_validation.get("policy_skipped_target_count") or 0) == 5,
        errors,
        "embedded manifest must contain 5 policy-disabled targets",
    )

    replay_input = _load_json(root, REPLAY_RUN_DIR / "input.json", errors)
    replay_output = _load_json(root, REPLAY_RUN_DIR / "output.json", errors)
    live_output = _load_json(root, LIVE_PROBE_RUN_DIR / "output.json", errors)

    artifact_input = _artifact_input_summary(replay_input, errors) if replay_input else {}
    replay_artifact = _deterministic_replay_summary(replay_output, errors) if replay_output else {}
    replay_dry_run = _deterministic_replay_summary(run_replay(allow_public_network=False), errors)
    live_fixture = _public_live_fixture_summary(live_output, errors) if live_output else {}
    full_public_replay = _full_public_replay_summary(root, errors)
    closure_review = _closure_review_summary(root, errors) if full_public_replay.get("status") != "missing" else {}

    full_public_output_path = root / REPLAY_RUN_DIR / "output.public.json"
    full_public_reviewed = (
        full_public_replay.get("status") == "real_evidence_present_review_required"
        and closure_review.get("status") == "reviewed_for_topic_closure"
    )
    external_blocker = {
        "status": (
            "resolved" if full_public_reviewed else "recorded" if not full_public_output_path.is_file() else "public_output_present"
        ),
        "blocker_type": (
            None
            if full_public_reviewed
            else "external_public_network_or_site_stability"
            if not full_public_output_path.is_file()
            else "human_review_required"
        ),
        "path": str(REPLAY_RUN_DIR / "output.public.json"),
        "reason": (
            "Full 45-site public replay output is absent from this worktree; public site availability, anti-bot, "
            "rate-limit, and parser volatility remain outside the deterministic CI gate."
            if not full_public_output_path.is_file()
            else "A full public replay output artifact is present and reviewed for topic closure."
            if full_public_reviewed
            else "A full public replay output artifact is present and should be reviewed separately before upgrading A5."
        ),
    }

    result = {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "a5_status": (
            "deterministic_replay_gate_closed_external_public_replay_blocked"
            if not full_public_output_path.is_file()
            else "full_public_replay_reviewed_closed"
            if full_public_reviewed
            else "full_public_replay_artifact_present_review_required"
        ),
        "evidence_doc": str(WAVE7_A5_DOC),
        "closure_review_doc": str(WAVE47_CLOSURE_DOC),
        "a5_gate": {
            "embedded_manifest": manifest_validation,
            "artifact_input": artifact_input,
            "replay_artifact": replay_artifact,
            "fresh_no_network_dry_run": replay_dry_run,
        },
        "public_live_fixture": live_fixture,
        "full_public_replay": full_public_replay,
        "closure_review": closure_review,
        "term_fallback_relevance_review": {
            "status": "review_required_not_full_closure",
            "review_target_count": len(live_fixture.get("relevance_review_targets") or []),
            "targets": list(live_fixture.get("relevance_review_targets") or []),
            "rule": "candidate_ready_with_term_fallback is evidence for parser reachability, but remains a relevance-review blocker.",
        },
        "external_blocker": external_blocker,
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
            "shared_indexes_edited": False,
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the deterministic A5 public replay gate without public network access.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
