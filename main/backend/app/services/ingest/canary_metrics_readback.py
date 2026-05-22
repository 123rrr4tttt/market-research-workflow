from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION, CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION
from .canary_metrics import CONTRACT_VERSION as READINESS_CONTRACT_VERSION
from .canary_metrics import build_ingest_canary_metrics_readiness


CONTRACT_VERSION = "ingest.canary_metrics_readback.v1"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_canary_metrics_readback_record(
    *,
    handoff: Mapping[str, Any],
    project_key: str = "demo_proj",
) -> dict[str, Any]:
    readiness = build_ingest_canary_metrics_readiness(handoff=handoff, project_key=project_key)
    metrics_snapshot = handoff.get("metrics_snapshot") if isinstance(handoff.get("metrics_snapshot"), Mapping) else {}
    canary_status = {
        "readiness_contract_version": readiness.contract_version,
        "readiness_status": readiness.status,
        "deterministic_metrics_ready": readiness.deterministic_metrics_ready,
        "demo_proj_live_canary_open": readiness.demo_proj_live_canary_open,
        "metric_24h_readback_open": readiness.metric_24h_readback_open,
        "live_canary_validated": readiness.live_canary_validated,
        "metric_24h_readback_validated": readiness.metric_24h_readback_validated,
        "closure_claim": readiness.closure_claim,
        "remaining_live_gaps": list(readiness.remaining_live_gaps),
    }
    digest_payload = {
        "project_key": project_key,
        "source_handoff_contract_version": handoff.get("contract_version"),
        "source_metrics_contract_version": metrics_snapshot.get("contract_version"),
        "metrics_snapshot": dict(metrics_snapshot),
        "canary_status": canary_status,
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "project_key": project_key,
        "source_handoff_contract_version": handoff.get("contract_version"),
        "source_metrics_contract_version": metrics_snapshot.get("contract_version"),
        "metrics_snapshot": dict(metrics_snapshot),
        "canary_status": canary_status,
        "snapshot_digest": _digest(digest_payload),
        "live_production_canary_claim": False,
        "metric_24h_live_readback_claim": False,
        "closure_claim": False,
    }


def write_canary_metrics_readback_record(path: Path | str, record: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_canary_metrics_readback_record(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("canary metrics readback record must be a JSON object")
    return payload


def validate_canary_metrics_readback_record(
    record: Mapping[str, Any],
    *,
    project_key: str = "demo_proj",
) -> dict[str, Any]:
    metrics_snapshot = record.get("metrics_snapshot") if isinstance(record.get("metrics_snapshot"), Mapping) else {}
    canary_status = record.get("canary_status") if isinstance(record.get("canary_status"), Mapping) else {}
    expected_digest = _digest(
        {
            "project_key": record.get("project_key"),
            "source_handoff_contract_version": record.get("source_handoff_contract_version"),
            "source_metrics_contract_version": record.get("source_metrics_contract_version"),
            "metrics_snapshot": dict(metrics_snapshot),
            "canary_status": dict(canary_status),
        }
    )
    checks = {
        "contract_version": record.get("contract_version") == CONTRACT_VERSION,
        "project_key": record.get("project_key") == project_key,
        "source_handoff_contract_version": record.get("source_handoff_contract_version") == CANARY_HANDOFF_CONTRACT_VERSION,
        "source_metrics_contract_version": record.get("source_metrics_contract_version")
        == CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        "readiness_contract_version": canary_status.get("readiness_contract_version") == READINESS_CONTRACT_VERSION,
        "deterministic_metrics_ready": canary_status.get("deterministic_metrics_ready") is True,
        "demo_proj_live_canary_open": canary_status.get("demo_proj_live_canary_open") is True,
        "metric_24h_readback_open": canary_status.get("metric_24h_readback_open") is True,
        "no_live_production_canary_claim": record.get("live_production_canary_claim") is False,
        "no_metric_24h_live_readback_claim": record.get("metric_24h_live_readback_claim") is False,
        "no_closure_claim": record.get("closure_claim") is False and canary_status.get("closure_claim") is False,
        "snapshot_digest": record.get("snapshot_digest") == expected_digest,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not failed else "failed",
        "passed": not failed,
        "failed_checks": failed,
        "snapshot_digest": record.get("snapshot_digest"),
        "expected_snapshot_digest": expected_digest,
        "canary_status": dict(canary_status),
    }


def run_canary_metrics_readback_gate(
    *,
    handoff: Mapping[str, Any],
    path: Path | str,
    project_key: str = "demo_proj",
) -> dict[str, Any]:
    record = build_canary_metrics_readback_record(handoff=handoff, project_key=project_key)
    write_canary_metrics_readback_record(path, record)
    readback = read_canary_metrics_readback_record(path)
    validation = validate_canary_metrics_readback_record(readback, project_key=project_key)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": validation["status"],
        "record_path": str(path),
        "write_performed": True,
        "readback_performed": True,
        "validation": validation,
        "readback_record": readback,
    }


__all__ = [
    "CONTRACT_VERSION",
    "build_canary_metrics_readback_record",
    "read_canary_metrics_readback_record",
    "run_canary_metrics_readback_gate",
    "validate_canary_metrics_readback_record",
    "write_canary_metrics_readback_record",
]
