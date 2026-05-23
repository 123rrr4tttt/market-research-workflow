#!/usr/bin/env python3
"""Wave19 schema/readback gate for the local open-search health artifact.

The gate reads the Wave18 health artifact and validates its shape as evidence,
without starting services or converting a live probe into provider closure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_open_search_health_artifact import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_HEALTH_ARTIFACT,
    LOCAL_OPEN_SEARCH_FAMILY,
    OPEN_SEARCH_TOPIC_DIRS,
    PROVIDERS,
    _first_existing_path,
    display_path,
    load_json,
)


CONTRACT_VERSION = "wave19-open-search-health-artifact-schema-readback.v1"
SOURCE_CONTRACT_VERSION = "wave18-open-search-health-artifact.v1"
TOPIC_DOC = _first_existing_path(
    *(
        topic_dir / "15_wave19-open-search-health-artifact-schema-readback-2026-05-22.md"
        for topic_dir in OPEN_SEARCH_TOPIC_DIRS
    )
).relative_to(REPO_ROOT)
REQUIRED_ROOT_FIELDS = (
    "contract_version",
    "status",
    "health_state",
    "closure_claim_allowed",
    "provider_auto_promotion_allowed",
    "live_probe",
    "compose_expectations",
    "provider_health",
    "unsupported_claims",
)
REQUIRED_PROVIDER_FACTS = (
    "configured_endpoint_valid",
    "compose_service_expected",
    "search_provider_explicit_only",
    "current_service_running",
    "live_probe_open",
    "service_not_started_connect_error",
    "live_query_unsealed",
    "no_live_closure_claim",
    "no_provider_auto_promotion",
)
REQUIRED_UNSUPPORTED_CLAIM_CODES = {
    "service_status_not_live_closure",
    "live_probe_not_quality_closure",
}
LIVE_RESPONSE_STATES = {
    "live_query_returned",
    "live_query_empty",
    "live_query_trace_failed",
}
LIVE_RESPONSE_STATUSES = {"ready", "empty", "trace_failed"}
RUNTIME_PROBE_ERROR_CLASSES = {
    "service_unreachable_timeout",
    "endpoint_responded_with_http_error",
    "endpoint_query_error",
    "endpoint_returned_non_contract_json",
}
CLASSIFICATION_KEYS = (
    "compose_config_evidence",
    "service_not_started_connect_error",
    "real_live_probe_response",
    "runtime_probe_error_unsealed",
    "invalid_runtime_class",
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _artifact_digest(artifact: dict[str, Any]) -> str:
    encoded = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unsupported_claim_codes(artifact: dict[str, Any]) -> set[str]:
    return {
        str(item.get("code"))
        for item in artifact.get("unsupported_claims") or []
        if isinstance(item, dict) and item.get("code")
    }


def _compose_config_readback(provider: str, row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    facts = _mapping(row.get("facts"))
    endpoint = _mapping(row.get("configured_endpoint"))
    compose = _mapping(row.get("compose_expectations"))
    expected_route = f"explicit:{provider}"
    explicit_only = (
        row.get("provider_route") == expected_route
        and row.get("provider_family") == LOCAL_OPEN_SEARCH_FAMILY
        and row.get("provider_auto_included") is False
        and facts.get("search_provider_explicit_only") is True
    )
    compose_present = (
        facts.get("configured_endpoint_valid") is True
        and endpoint.get("endpoint_state") == "configured_endpoint"
        and facts.get("compose_service_expected") is True
        and compose.get("all_expected_surfaces_present") is True
        and explicit_only
    )
    if not compose_present:
        failures.append("compose/config evidence lane is incomplete")
    return (
        {
            "readback_kind": "compose_config_evidence",
            "state": "present" if compose_present else "missing",
            "base_url": endpoint.get("base_url"),
            "endpoint_state": endpoint.get("endpoint_state"),
            "configured_endpoint_valid": facts.get("configured_endpoint_valid") is True,
            "compose_service_expected": facts.get("compose_service_expected") is True,
            "compose_all_expected_surfaces_present": compose.get("all_expected_surfaces_present") is True,
            "provider_route_explicit_only": explicit_only,
            "provider_auto_included": row.get("provider_auto_included"),
        },
        failures,
    )


def _runtime_readback(provider: str, row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    facts = _mapping(row.get("facts"))
    runtime = _mapping(row.get("wave15_runtime_boundary"))
    classification = runtime.get("boundary_classification")
    runtime_state = runtime.get("runtime_state")
    live_probe_status = runtime.get("live_probe_status")
    live_result_count = runtime.get("live_result_count")

    if classification == "service_not_started_connect_error":
        readback_kind = "service_not_started_connect_error"
        if facts.get("service_not_started_connect_error") is not True:
            failures.append("service_not_started_connect_error fact is not true")
        if runtime_state != "service_not_started":
            failures.append(f"service_not_started runtime_state drifted to {runtime_state!r}")
        if live_probe_status != "unavailable":
            failures.append(f"service_not_started live_probe_status drifted to {live_probe_status!r}")
        if live_result_count != 0:
            failures.append(f"service_not_started live_result_count must be 0, got {live_result_count!r}")
        if runtime.get("error_type") not in {"ConnectError", "ConnectTimeout"}:
            failures.append(f"service_not_started error_type must be a connect error, got {runtime.get('error_type')!r}")
    elif classification == "live_query_unsealed":
        readback_kind = "real_live_probe_response"
        if facts.get("live_query_unsealed") is not True:
            failures.append("live_query_unsealed fact is not true")
        if facts.get("service_not_started_connect_error") is True:
            failures.append("live response cannot also be classified as service_not_started_connect_error")
        if runtime_state not in LIVE_RESPONSE_STATES:
            failures.append(f"live response runtime_state drifted to {runtime_state!r}")
        if live_probe_status not in LIVE_RESPONSE_STATUSES:
            failures.append(f"live response live_probe_status drifted to {live_probe_status!r}")
        if not isinstance(live_result_count, int) or live_result_count < 0:
            failures.append(f"live response result count must be a non-negative integer, got {live_result_count!r}")
    elif classification in RUNTIME_PROBE_ERROR_CLASSES:
        readback_kind = "runtime_probe_error_unsealed"
    else:
        readback_kind = "invalid_runtime_class"
        failures.append(f"unexpected runtime boundary classification {classification!r}")

    closure_claimed = not (
        runtime.get("live_closure_claim_allowed") is False
        and runtime.get("provider_auto_promotion_allowed") is False
        and facts.get("no_live_closure_claim") is True
        and facts.get("no_provider_auto_promotion") is True
    )
    if closure_claimed:
        failures.append("runtime readback claims live closure or provider auto promotion")

    return (
        {
            "readback_kind": readback_kind,
            "boundary_classification": classification,
            "runtime_state": runtime_state,
            "live_probe_status": live_probe_status,
            "live_result_count": live_result_count,
            "fallback_reason": runtime.get("fallback_reason"),
            "error_type": runtime.get("error_type"),
            "service_not_started_connect_error": readback_kind == "service_not_started_connect_error",
            "real_live_probe_response": readback_kind == "real_live_probe_response",
            "live_closure_claim_allowed": runtime.get("live_closure_claim_allowed"),
            "provider_auto_promotion_allowed": runtime.get("provider_auto_promotion_allowed"),
            "external_provider_closure_claimed": closure_claimed,
        },
        failures,
    )


def _provider_readback(provider: str, artifact: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    provider_health = _mapping(artifact.get("provider_health"))
    row = _mapping(provider_health.get(provider))
    if not row:
        return (
            {
                "provider": provider,
                "status": "failed",
                "compose_config_evidence": {"readback_kind": "compose_config_evidence", "state": "missing"},
                "runtime_evidence": {"readback_kind": "invalid_runtime_class"},
                "no_external_provider_closure": False,
            },
            [f"{provider} provider_health row is missing"],
        )

    facts = _mapping(row.get("facts"))
    for fact_name in REQUIRED_PROVIDER_FACTS:
        if fact_name not in facts:
            failures.append(f"missing provider fact {fact_name}")

    compose_readback, compose_failures = _compose_config_readback(provider, row)
    runtime_readback, runtime_failures = _runtime_readback(provider, row)
    failures.extend(compose_failures)
    failures.extend(runtime_failures)

    no_external_provider_closure = (
        artifact.get("closure_claim_allowed") is False
        and artifact.get("provider_auto_promotion_allowed") is False
        and runtime_readback["external_provider_closure_claimed"] is False
    )
    if not no_external_provider_closure:
        failures.append("provider readback does not preserve no external provider closure")

    return (
        {
            "provider": provider,
            "status": "passed" if not failures else "failed",
            "compose_config_evidence": compose_readback,
            "runtime_evidence": runtime_readback,
            "no_external_provider_closure": no_external_provider_closure,
        },
        failures,
    )


def build_schema_readback(
    artifact: dict[str, Any],
    *,
    source_path: Path | None = None,
    load_failures: list[str] | None = None,
) -> dict[str, Any]:
    failures = list(load_failures or [])
    if not isinstance(artifact, dict):
        artifact = {}
        failures.append("source artifact must be a JSON object")

    for field in REQUIRED_ROOT_FIELDS:
        if field not in artifact:
            failures.append(f"source artifact missing root field {field}")
    if artifact.get("contract_version") != SOURCE_CONTRACT_VERSION:
        failures.append(
            f"source artifact contract_version expected {SOURCE_CONTRACT_VERSION!r}, "
            f"got {artifact.get('contract_version')!r}"
        )
    if artifact.get("status") != "passed":
        failures.append(f"source artifact status must be passed, got {artifact.get('status')!r}")
    if artifact.get("health_state") != "partial":
        failures.append(f"source artifact health_state must be partial, got {artifact.get('health_state')!r}")
    if artifact.get("closure_claim_allowed") is not False:
        failures.append("source artifact closure_claim_allowed must be false")
    if artifact.get("provider_auto_promotion_allowed") is not False:
        failures.append("source artifact provider_auto_promotion_allowed must be false")

    live_probe = _mapping(artifact.get("live_probe"))
    if live_probe.get("open") is not True:
        failures.append("source artifact live_probe.open must be true")
    if live_probe.get("does_not_start_services") is not True:
        failures.append("source artifact live_probe must be documented as no-container-start")

    unsupported_codes = _unsupported_claim_codes(artifact)
    missing_claim_codes = sorted(REQUIRED_UNSUPPORTED_CLAIM_CODES - unsupported_codes)
    for code in missing_claim_codes:
        failures.append(f"source artifact missing unsupported claim code {code}")

    provider_readbacks: dict[str, Any] = {}
    classification_counts = {key: 0 for key in CLASSIFICATION_KEYS}
    for provider in PROVIDERS:
        readback, provider_failures = _provider_readback(provider, artifact)
        provider_readbacks[provider] = readback
        if readback["compose_config_evidence"].get("state") == "present":
            classification_counts["compose_config_evidence"] += 1
        runtime_kind = str(readback["runtime_evidence"].get("readback_kind") or "invalid_runtime_class")
        classification_counts[runtime_kind if runtime_kind in classification_counts else "invalid_runtime_class"] += 1
        failures.extend(f"{provider}: {item}" for item in provider_failures)

    external_provider_closure_claimed = (
        artifact.get("closure_claim_allowed") is not False
        or artifact.get("provider_auto_promotion_allowed") is not False
        or any(
            readback["runtime_evidence"].get("external_provider_closure_claimed") is True
            for readback in provider_readbacks.values()
        )
    )
    if external_provider_closure_claimed:
        failures.append("external provider closure claim must remain false")

    source_path_text = display_path(source_path) if source_path is not None else None
    readback = {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not failures else "failed",
        "source_artifact": {
            "path": source_path_text,
            "contract_version": artifact.get("contract_version"),
            "status": artifact.get("status"),
            "health_state": artifact.get("health_state"),
            "digest_sha256": _artifact_digest(artifact),
        },
        "schema_gate": {
            "required_root_fields": list(REQUIRED_ROOT_FIELDS),
            "required_provider_facts": list(REQUIRED_PROVIDER_FACTS),
            "required_unsupported_claim_codes": sorted(REQUIRED_UNSUPPORTED_CLAIM_CODES),
            "runtime_classes": {
                "compose_config_evidence": "repo compose/config/explicit-provider surfaces only",
                "service_not_started_connect_error": "bounded live probe reached a connect error; service is not claimed live",
                "real_live_probe_response": "bounded live probe returned a response; still unsealed",
                "runtime_probe_error_unsealed": "bounded live probe produced an unsealed runtime error",
            },
        },
        "classification_counts": classification_counts,
        "provider_readbacks": provider_readbacks,
        "external_provider_closure_claimed": external_provider_closure_claimed,
        "closure_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
        "readback_semantics": {
            "status_passed_means": (
                "the health artifact shape distinguishes compose/config evidence, stopped-service "
                "connect errors, and real live probe responses"
            ),
            "status_passed_does_not_mean": [
                "SearXNG or YaCy live availability is closed",
                "live result quality, freshness, or latency stability is closed",
                "local open-search providers may be promoted into provider=auto",
            ],
        },
        "topic_doc": display_path(REPO_ROOT / TOPIC_DOC),
        "failures": failures,
    }
    return readback


def _resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def write_output(path: Path, readback: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Wave19 open-search health artifact schema/readback.")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_HEALTH_ARTIFACT, help="Wave18 health artifact JSON path.")
    parser.add_argument("--json", action="store_true", help="Print the full readback contract JSON.")
    parser.add_argument("--write-output", type=Path, help="Write the full readback contract JSON.")
    args = parser.parse_args(argv)

    artifact_path = _resolve_repo_path(args.artifact)
    artifact, load_failures = load_json(artifact_path)
    readback = build_schema_readback(artifact, source_path=artifact_path, load_failures=load_failures)

    if args.write_output is not None:
        output_path = _resolve_repo_path(args.write_output)
        write_output(output_path, readback)

    if args.json:
        print(json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = readback["classification_counts"]
        print(
            "OK open_search_health_artifact_schema_readback={status} "
            "compose_config_evidence={compose} "
            "service_not_started_connect_error={stopped} "
            "real_live_probe_response={live} "
            "external_provider_closure_claimed={closure}".format(
                status=readback["status"],
                compose=counts["compose_config_evidence"],
                stopped=counts["service_not_started_connect_error"],
                live=counts["real_live_probe_response"],
                closure=str(bool(readback["external_provider_closure_claimed"])).lower(),
            )
        )
        if readback["failures"]:
            print(json.dumps({"failures": readback["failures"]}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0 if readback["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
