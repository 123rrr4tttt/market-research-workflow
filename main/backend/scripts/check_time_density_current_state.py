#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


CONTRACT_VERSION = "time-density-current-state-doc-provenance.v1"

STALE_TAXONOMY_MARKERS = (
    "doc_stale",
    "doc_drift",
    "external_gap",
)


@dataclass(frozen=True)
class EvidenceTopic:
    key: str
    label: str
    path: str
    current_markers: tuple[str, ...]


EVIDENCE_TOPICS = (
    EvidenceTopic(
        key="time_statistics",
        label="Time Statistics",
        path=(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-03-05-time-statistics-remediation-plan/"
            "09_wave14-time-density-current-state-evidence-2026-05-22.md"
        ),
        current_markers=(
            "Time Statistics",
            "Source Time Window",
            "Time Semantics Density",
            "check_time_density_current_state.py",
            "status=passed_with_known_gaps",
            "failures=[]",
        ),
    ),
    EvidenceTopic(
        key="source_time_window",
        label="Source Time Window",
        path=(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-03-02-source-time-window-smart-timestamp-plan/"
            "05_wave12-time-density-decision-log-provenance-evidence-2026-05-22.md"
        ),
        current_markers=(
            "check_time_density_decision_log_contract.py",
            "status=passed_with_known_gaps",
            "failures=[]",
        ),
    ),
    EvidenceTopic(
        key="time_semantics_density",
        label="Time Semantics Density",
        path=(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-03-14-time-semantics-density-merged-plan/"
            "09_wave12-time-density-decision-log-contract-evidence-2026-05-22.md"
        ),
        current_markers=(
            "check_time_density_decision_log_contract.py",
            "status=passed_with_known_gaps",
            "failures=[]",
        ),
    ),
)


def _contains_marker(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def classify_evidence_markers(
    text: str,
    *,
    current_markers: tuple[str, ...],
    stale_markers: tuple[str, ...] = STALE_TAXONOMY_MARKERS,
) -> dict[str, Any]:
    missing_current = [marker for marker in current_markers if not _contains_marker(text, marker)]
    missing_stale = [marker for marker in stale_markers if not _contains_marker(text, marker)]
    is_current = not missing_current and not missing_stale
    return {
        "status": "current" if is_current else "stale",
        "current_markers_present": not missing_current,
        "stale_taxonomy_markers_present": not missing_stale,
        "missing_current_markers": missing_current,
        "missing_stale_taxonomy_markers": missing_stale,
    }


def _load_script_module(script_name: str):
    module_path = BACKEND_ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.removesuffix(".py"), module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runtime_contracts() -> dict[str, dict[str, Any]]:
    time_semantics = _load_script_module("check_time_semantics_ope_contract.py")
    decision_log = _load_script_module("check_time_density_decision_log_contract.py")
    return {
        "time_semantics_ope": time_semantics.build_contract(),
        "time_density_decision_log": decision_log.build_contract(),
    }


def _runtime_contract_is_current(contract: dict[str, Any]) -> bool:
    return contract.get("status") == "passed_with_known_gaps" and not contract.get("failures")


def build_current_state(
    *,
    repo_root: Path | str = REPO_ROOT,
    runtime_contracts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    for topic in EVIDENCE_TOPICS:
        path = root / topic.path
        if not path.is_file():
            failures.append(f"evidence.{topic.key}.missing_file")
            evidence[topic.key] = {
                "label": topic.label,
                "path": topic.path,
                "status": "missing",
            }
            continue
        text = path.read_text(encoding="utf-8")
        marker_state = classify_evidence_markers(text, current_markers=topic.current_markers)
        evidence[topic.key] = {
            "label": topic.label,
            "path": topic.path,
            **marker_state,
        }
        if marker_state["status"] != "current":
            failures.append(f"evidence.{topic.key}.stale_markers")

    contracts = runtime_contracts if runtime_contracts is not None else _load_runtime_contracts()
    runtime_checks = {
        name: {
            "status": contract.get("status"),
            "failures": contract.get("failures") or [],
            "current": _runtime_contract_is_current(contract),
        }
        for name, contract in contracts.items()
    }
    for name, check in runtime_checks.items():
        if not check["current"]:
            failures.append(f"runtime.{name}.not_current")

    remaining_gaps = sorted(
        {
            str(gap)
            for contract in contracts.values()
            for gap in (contract.get("remaining_gaps") or [])
            if str(gap).strip()
        }
    )

    checks = {
        "runtime_contracts_current": all(check["current"] for check in runtime_checks.values()),
        "evidence_markers_current": all(
            item.get("status") == "current" for item in evidence.values()
        ),
        "stale_taxonomy_markers_present": all(
            item.get("stale_taxonomy_markers_present") is True for item in evidence.values()
        ),
    }
    for key, passed in checks.items():
        if not passed:
            failures.append(f"checks.{key}")

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "time_density_current_state_docs_and_deterministic_contracts",
        "status": "failed" if failures else "passed_with_known_gaps",
        "checks": checks,
        "runtime": runtime_checks,
        "evidence": evidence,
        "failures": sorted(set(failures)),
        "remaining_gaps": remaining_gaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check current-state/stale markers for time-density development docs."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    state = build_current_state(repo_root=Path(args.repo_root))
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, sort_keys=True))
    return 0 if not state["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
