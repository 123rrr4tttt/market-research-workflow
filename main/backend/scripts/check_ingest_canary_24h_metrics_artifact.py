#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.canary_handoff import CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION  # noqa: E402
from app.services.ingest.canary_metrics import CONTRACT_VERSION as READINESS_CONTRACT_VERSION  # noqa: E402
from app.services.ingest.canary_metrics_readback import CONTRACT_VERSION as READBACK_CONTRACT_VERSION  # noqa: E402


CONTRACT_VERSION = "ingest.canary_24h_metrics_artifact.v1"
ARTIFACT_KIND = "deterministic_ingest_canary_24h_metrics_fixture"

TOPIC_DOCS = [
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-ingest-platformization-assessment/"
        "06_wave19-ingest-canary-24h-metrics-artifact-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-single-url-first-ingest-allocation-plan/"
        "07_wave19-single-url-canary-24h-metrics-artifact-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-meaningful-ingest-guardrails-plan/"
        "07_wave19-meaningful-ingest-canary-24h-metrics-artifact-2026-05-22.md"
    ),
]

REQUIRED_DOC_TOKENS = (
    "Wave19 Ingest Canary 24h Metrics Artifact",
    "contract_version: ingest.canary_24h_metrics_artifact.v1",
    "deterministic_fixture: true",
    "window_hours: 24",
    "live_production_canary_claim: false",
    "metric_24h_live_readback_claim: false",
    "closure_claim: false",
)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _counter_rows(counter: Counter[str], *, total: int, key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: key, "count": count, "rate": _rate(count, total)}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _fixture_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "canary-24h-fixture-001",
            "occurred_at": "2026-05-21T00:10:00Z",
            "source_url": "https://example.com/search?q=robotics",
            "source_mode": "url_execution",
            "entrypoint": "ingest.url_pool",
            "adapter": "source_library_frontdoor",
            "guardrail_channel": "canary",
            "decision": "inserted_valid",
            "reason_code": "accepted",
            "inserted_valid": True,
        },
        {
            "event_id": "canary-24h-fixture-002",
            "occurred_at": "2026-05-21T08:35:00Z",
            "source_url": "https://example.com/reports/robotics-market",
            "source_mode": "url_execution",
            "entrypoint": "ingest.url_pool",
            "adapter": "source_library_frontdoor",
            "guardrail_channel": "canary",
            "decision": "inserted_valid",
            "reason_code": "accepted",
            "inserted_valid": True,
        },
        {
            "event_id": "canary-24h-fixture-003",
            "occurred_at": "2026-05-21T16:45:00Z",
            "source_url": "https://example.com/search?q=empty",
            "source_mode": "url_execution",
            "entrypoint": "ingest.url_pool",
            "adapter": "source_library_frontdoor",
            "guardrail_channel": "canary",
            "decision": "rejected",
            "reason_code": "empty_body",
            "inserted_valid": False,
        },
        {
            "event_id": "canary-24h-fixture-004",
            "occurred_at": "2026-05-21T23:50:00Z",
            "source_url": "https://example.com/reports/automation-market",
            "source_mode": "url_execution",
            "entrypoint": "ingest.url_pool",
            "adapter": "source_library_frontdoor",
            "guardrail_channel": "canary",
            "decision": "inserted_valid",
            "reason_code": "accepted",
            "inserted_valid": True,
        },
    ]


def build_24h_metrics_artifact(*, project_key: str = "demo_proj") -> dict[str, Any]:
    normalized_project = str(project_key or "demo_proj").strip() or "demo_proj"
    events = _fixture_events()
    total_attempts = len(events)
    rejected_count = sum(1 for event in events if event["decision"] == "rejected")
    inserted_total_count = sum(1 for event in events if str(event["decision"]).startswith("inserted"))
    inserted_valid_count = sum(1 for event in events if event["inserted_valid"] is True)
    inserted_invalid_count = inserted_total_count - inserted_valid_count
    reason_counts = Counter(str(event["reason_code"]) for event in events)
    adapter_counts = Counter(str(event["adapter"]) for event in events)
    source_mode_counts = Counter(str(event["source_mode"]) for event in events)

    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "status": "passed",
        "project_key": normalized_project,
        "deterministic_fixture": True,
        "generated_by": "check_ingest_canary_24h_metrics_artifact.py",
        "input_contracts": {
            "canary_metrics_snapshot": CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
            "canary_metrics_readiness": READINESS_CONTRACT_VERSION,
            "canary_metrics_readback": READBACK_CONTRACT_VERSION,
        },
        "window": {
            "window_label": "fixture_24h",
            "window_hours": 24,
            "started_at": "2026-05-21T00:00:00Z",
            "ended_at": "2026-05-22T00:00:00Z",
            "timezone": "UTC",
            "live_window_observed": False,
        },
        "single_url_first_allocation": {
            "project_key": normalized_project,
            "entrypoint": "ingest.url_pool",
            "source_mode": "url_execution",
            "allocation_policy": "single_url_first",
            "canary_scope": "demo_proj",
            "frontdoor_required": True,
            "source_urls": [event["source_url"] for event in events],
        },
        "metrics_24h": {
            "total_attempts": total_attempts,
            "rejected_count": rejected_count,
            "inserted_total_count": inserted_total_count,
            "inserted_valid_count": inserted_valid_count,
            "inserted_invalid_count": inserted_invalid_count,
            "rejection_rate": _rate(rejected_count, total_attempts),
            "inserted_valid_ratio": _rate(inserted_valid_count, inserted_total_count),
            "reason_code_top_n": _counter_rows(reason_counts, total=total_attempts, key_name="reason_code"),
            "adapter_hit_rate": _counter_rows(adapter_counts, total=total_attempts, key_name="adapter"),
            "source_mode_counts": _counter_rows(source_mode_counts, total=total_attempts, key_name="source_mode"),
        },
        "guardrail_rollout": {
            "channel": "canary",
            "rollout_mode": "canary",
            "strict_enabled_samples": total_attempts,
            "canary_matched_samples": total_attempts,
            "strict_enabled_rate": 1.0,
            "canary_matched_rate": 1.0,
            "reason_code_review_present": True,
            "guardrail_rollout_counts_review_present": True,
        },
        "fixture_events": events,
        "readback_expectations": {
            "artifact_shape_readback_required": True,
            "window_hours_at_least_24": True,
            "rejection_rate_field_required": True,
            "inserted_valid_ratio_field_required": True,
            "guardrail_rollout_counts_required": True,
        },
        "live_boundaries": {
            "live_production_canary_claim": False,
            "metric_24h_live_readback_claim": False,
            "production_data_claim": False,
            "closure_claim": False,
            "remaining_live_gaps": [
                "demo_proj live canary execution against configured services remains open",
                "production 24h rejection-rate readback remains open",
                "production 24h inserted-valid ratio readback remains open",
            ],
        },
    }
    artifact["snapshot_digest"] = _digest({key: value for key, value in artifact.items() if key != "snapshot_digest"})
    return artifact


def _metrics_failures(artifact: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    metrics = artifact.get("metrics_24h") if isinstance(artifact.get("metrics_24h"), Mapping) else {}
    events = artifact.get("fixture_events") if isinstance(artifact.get("fixture_events"), list) else []
    total_attempts = int(metrics.get("total_attempts") or 0)
    rejected_count = int(metrics.get("rejected_count") or 0)
    inserted_total_count = int(metrics.get("inserted_total_count") or 0)
    inserted_valid_count = int(metrics.get("inserted_valid_count") or 0)
    inserted_invalid_count = int(metrics.get("inserted_invalid_count") or 0)

    if total_attempts != len(events):
        errors.append("metrics_24h.total_attempts must match fixture_events length")
    if total_attempts <= 0:
        errors.append("metrics_24h.total_attempts must be positive")
    if rejected_count + inserted_total_count != total_attempts:
        errors.append("rejected_count + inserted_total_count must equal total_attempts")
    if inserted_valid_count + inserted_invalid_count != inserted_total_count:
        errors.append("inserted_valid_count + inserted_invalid_count must equal inserted_total_count")
    if metrics.get("rejection_rate") != _rate(rejected_count, total_attempts):
        errors.append("metrics_24h.rejection_rate does not match counts")
    if metrics.get("inserted_valid_ratio") != _rate(inserted_valid_count, inserted_total_count):
        errors.append("metrics_24h.inserted_valid_ratio does not match counts")
    for key in ("reason_code_top_n", "adapter_hit_rate", "source_mode_counts"):
        if not isinstance(metrics.get(key), list) or not metrics.get(key):
            errors.append(f"metrics_24h.{key} must be a non-empty list")
    return errors


def validate_24h_metrics_artifact(artifact: Mapping[str, Any], *, project_key: str = "demo_proj") -> list[str]:
    normalized_project = str(project_key or "demo_proj").strip() or "demo_proj"
    errors: list[str] = []
    window = artifact.get("window") if isinstance(artifact.get("window"), Mapping) else {}
    allocation = (
        artifact.get("single_url_first_allocation")
        if isinstance(artifact.get("single_url_first_allocation"), Mapping)
        else {}
    )
    guardrail = artifact.get("guardrail_rollout") if isinstance(artifact.get("guardrail_rollout"), Mapping) else {}
    live_boundaries = artifact.get("live_boundaries") if isinstance(artifact.get("live_boundaries"), Mapping) else {}
    input_contracts = artifact.get("input_contracts") if isinstance(artifact.get("input_contracts"), Mapping) else {}
    readback_expectations = (
        artifact.get("readback_expectations") if isinstance(artifact.get("readback_expectations"), Mapping) else {}
    )

    if artifact.get("contract_version") != CONTRACT_VERSION:
        errors.append(f"contract_version must be {CONTRACT_VERSION}")
    if artifact.get("artifact_kind") != ARTIFACT_KIND:
        errors.append(f"artifact_kind must be {ARTIFACT_KIND}")
    if artifact.get("status") != "passed":
        errors.append("status must be passed")
    if artifact.get("project_key") != normalized_project:
        errors.append(f"project_key must be {normalized_project}")
    if artifact.get("deterministic_fixture") is not True:
        errors.append("deterministic_fixture must be true")

    expected_contracts = {
        "canary_metrics_snapshot": CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        "canary_metrics_readiness": READINESS_CONTRACT_VERSION,
        "canary_metrics_readback": READBACK_CONTRACT_VERSION,
    }
    for key, expected in expected_contracts.items():
        if input_contracts.get(key) != expected:
            errors.append(f"input_contracts.{key} must be {expected}")

    if int(window.get("window_hours") or 0) < 24:
        errors.append("window.window_hours must be at least 24")
    if window.get("live_window_observed") is not False:
        errors.append("window.live_window_observed must be false")
    if allocation.get("entrypoint") != "ingest.url_pool":
        errors.append("single_url_first_allocation.entrypoint must be ingest.url_pool")
    if allocation.get("source_mode") != "url_execution":
        errors.append("single_url_first_allocation.source_mode must be url_execution")
    if allocation.get("allocation_policy") != "single_url_first":
        errors.append("single_url_first_allocation.allocation_policy must be single_url_first")

    for key in (
        "artifact_shape_readback_required",
        "window_hours_at_least_24",
        "rejection_rate_field_required",
        "inserted_valid_ratio_field_required",
        "guardrail_rollout_counts_required",
    ):
        if readback_expectations.get(key) is not True:
            errors.append(f"readback_expectations.{key} must be true")

    metrics = artifact.get("metrics_24h") if isinstance(artifact.get("metrics_24h"), Mapping) else {}
    total_attempts = int(metrics.get("total_attempts") or 0)
    if guardrail.get("channel") != "canary":
        errors.append("guardrail_rollout.channel must be canary")
    if guardrail.get("strict_enabled_samples") != total_attempts:
        errors.append("guardrail_rollout.strict_enabled_samples must equal total_attempts")
    if guardrail.get("canary_matched_samples") != total_attempts:
        errors.append("guardrail_rollout.canary_matched_samples must equal total_attempts")
    if guardrail.get("guardrail_rollout_counts_review_present") is not True:
        errors.append("guardrail_rollout.guardrail_rollout_counts_review_present must be true")

    for key in (
        "live_production_canary_claim",
        "metric_24h_live_readback_claim",
        "production_data_claim",
        "closure_claim",
    ):
        if live_boundaries.get(key) is not False:
            errors.append(f"live_boundaries.{key} must be false")

    expected_digest = _digest({key: value for key, value in artifact.items() if key != "snapshot_digest"})
    if artifact.get("snapshot_digest") != expected_digest:
        errors.append("snapshot_digest does not match artifact content")

    errors.extend(_metrics_failures(artifact))
    return errors


def write_24h_metrics_artifact(path: Path | str, artifact: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(artifact), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_24h_metrics_artifact(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("24h metrics artifact must be a JSON object")
    return payload


def run_24h_metrics_artifact_gate(*, path: Path | str, project_key: str = "demo_proj") -> dict[str, Any]:
    artifact = build_24h_metrics_artifact(project_key=project_key)
    write_24h_metrics_artifact(path, artifact)
    readback = read_24h_metrics_artifact(path)
    validation_errors = validate_24h_metrics_artifact(readback, project_key=project_key)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not validation_errors else "failed",
        "record_path": str(path),
        "write_performed": True,
        "readback_performed": True,
        "validation_errors": validation_errors,
        "readback_record": readback,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_check(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def run_check(*, record_path: Path | None = None) -> dict[str, Any]:
    token_results = [
        _token_check(
            REPO_ROOT / "main/backend/scripts/check_ingest_canary_24h_metrics_artifact.py",
            (
                "CONTRACT_VERSION",
                "build_24h_metrics_artifact",
                "validate_24h_metrics_artifact",
                "run_24h_metrics_artifact_gate",
                "metric_24h_live_readback_claim",
            ),
        )
    ]
    for doc in TOPIC_DOCS:
        token_results.append(_token_check(REPO_ROOT / doc, REQUIRED_DOC_TOKENS))

    if record_path is None:
        with tempfile.TemporaryDirectory(prefix="ingest-canary-24h-metrics-") as tmp_dir:
            gate = run_24h_metrics_artifact_gate(path=Path(tmp_dir) / "ingest_canary_24h_metrics_artifact.json")
    else:
        gate = run_24h_metrics_artifact_gate(path=record_path)

    artifact = gate["readback_record"]
    metrics = artifact["metrics_24h"]
    live_boundaries = artifact["live_boundaries"]
    runtime_results = [
        {
            "name": "write_read_validate_24h_metrics_artifact",
            "passed": gate["write_performed"] is True
            and gate["readback_performed"] is True
            and not gate["validation_errors"],
            "evidence": {
                "record_path": gate["record_path"],
                "snapshot_digest": artifact["snapshot_digest"],
            },
        },
        {
            "name": "24h_metric_shape_present",
            "passed": metrics["total_attempts"] > 0
            and metrics["rejection_rate"] == _rate(metrics["rejected_count"], metrics["total_attempts"])
            and metrics["inserted_valid_ratio"]
            == _rate(metrics["inserted_valid_count"], metrics["inserted_total_count"]),
            "evidence": {
                "window_hours": artifact["window"]["window_hours"],
                "rejection_rate": metrics["rejection_rate"],
                "inserted_valid_ratio": metrics["inserted_valid_ratio"],
            },
        },
        {
            "name": "live_24h_and_closure_claims_stay_open",
            "passed": live_boundaries["live_production_canary_claim"] is False
            and live_boundaries["metric_24h_live_readback_claim"] is False
            and live_boundaries["closure_claim"] is False,
            "evidence": {
                "live_production_canary_claim": live_boundaries["live_production_canary_claim"],
                "metric_24h_live_readback_claim": live_boundaries["metric_24h_live_readback_claim"],
                "closure_claim": live_boundaries["closure_claim"],
            },
        },
    ]
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_docs": [str(path) for path in TOPIC_DOCS],
        "token_results": token_results,
        "runtime_results": runtime_results,
        "gate": gate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check deterministic ingest canary 24h metrics artifact readback")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--write-artifact", type=Path, default=None, help="write the deterministic 24h artifact to this path")
    args = parser.parse_args(argv)

    result = run_check(record_path=args.write_artifact)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        artifact = result["gate"]["readback_record"]
        metrics = artifact["metrics_24h"]
        live_boundaries = artifact["live_boundaries"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"write_performed={str(result['gate']['write_performed']).lower()} "
            f"readback_performed={str(result['gate']['readback_performed']).lower()} "
            f"window_hours={artifact['window']['window_hours']} "
            f"rejection_rate={metrics['rejection_rate']} "
            f"inserted_valid_ratio={metrics['inserted_valid_ratio']} "
            f"metric_24h_live_readback_claim={str(live_boundaries['metric_24h_live_readback_claim']).lower()} "
            f"closure_claim={str(live_boundaries['closure_claim']).lower()}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
