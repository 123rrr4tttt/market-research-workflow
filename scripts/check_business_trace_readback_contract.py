#!/usr/bin/env python3
"""Check offline business artifacts for trace/source readback contract fields."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Iterable, Sequence

try:
    from scripts._automation_runtime import repo_root, utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now


SCHEMA_VERSION = "business_trace_readback_contract.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
BUSINESS_LINES = ("search", "dashboard", "admin", "ingest")

TRACE_KEYS = {"trace_chain", "trace_id"}
SOURCE_KEYS = {"source_refs", "source_query"}
SEARCH_READBACK_KEYS = {"provider_trace", "retrieval_run_readback", "index_freshness"}
ADMIN_EVIDENCE_KEYS = {"evidence_preview"}
ADMIN_RISK_KEYS = {"risk_tags", "risk_labels"}
INGEST_IDENTITY_KEYS = {"submission_id", "task_id", "retrieval_run_id"}


@dataclass(frozen=True)
class FieldMatch:
    key: str
    path: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", help="JSON artifact path(s) to inspect.")
    parser.add_argument("--root", default=None, help="Repository root used for relative artifact paths.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Return exit code 0 even when JSON status remains failed.",
    )
    return parser.parse_args(argv)


def normalize_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return True


def dotted(parent: str, key: object) -> str:
    key_text = str(key)
    return f"{parent}.{key_text}" if parent else key_text


def iter_dict_items(value: Any) -> Iterable[tuple[str, Any, str]]:
    stack: list[tuple[Any, str]] = [(value, "")]
    while stack:
        current, parent = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                path = dotted(parent, key)
                yield normalize_key(key), child, path
                if isinstance(child, (dict, list)):
                    stack.append((child, path))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                path = dotted(parent, index)
                if isinstance(child, (dict, list)):
                    stack.append((child, path))


def find_present_fields(payload: Any, keys: set[str]) -> list[FieldMatch]:
    matches: list[FieldMatch] = []
    for key, value, path in iter_dict_items(payload):
        if key in keys and is_present(value):
            matches.append(FieldMatch(key=key, path=path))
    return matches


def _dict_child(payload: Any, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _top_level_identity_matches(payload: Any, prefix: str = "") -> list[FieldMatch]:
    if not isinstance(payload, dict):
        return []
    matches: list[FieldMatch] = []
    for key in INGEST_IDENTITY_KEYS:
        value = payload.get(key)
        if is_present(value):
            matches.append(FieldMatch(key=key, path=dotted(prefix, key)))
    return matches


def find_ingest_identity_matches(payload: Any) -> list[FieldMatch]:
    matches = _top_level_identity_matches(payload)

    data_payload = _dict_child(payload, "data")
    matches.extend(_top_level_identity_matches(data_payload, "data"))

    for _key, trace_chain, trace_chain_path in iter_dict_items(payload):
        if not trace_chain_path.endswith("trace_chain"):
            continue
        matches.extend(_top_level_identity_matches(trace_chain, trace_chain_path))
        if isinstance(trace_chain, dict):
            ids = trace_chain.get("ids")
            if isinstance(ids, dict):
                for id_key in INGEST_IDENTITY_KEYS:
                    value = ids.get(id_key)
                    if is_present(value):
                        matches.append(FieldMatch(key=id_key, path=dotted(dotted(trace_chain_path, "ids"), id_key)))
            continue
        if not isinstance(trace_chain, list):
            continue
        for index, trace_item in enumerate(trace_chain):
            if not isinstance(trace_item, dict):
                continue
            ids = trace_item.get("ids")
            if not isinstance(ids, dict):
                continue
            for id_key in INGEST_IDENTITY_KEYS:
                value = ids.get(id_key)
                if is_present(value):
                    matches.append(
                        FieldMatch(
                            key=id_key,
                            path=dotted(dotted(dotted(trace_chain_path, index), "ids"), id_key),
                        )
                    )
    return matches


def find_string_matches(payload: Any, needles: Sequence[str]) -> set[str]:
    found: set[str] = set()
    for key, value, _path in iter_dict_items(payload):
        text = ""
        if isinstance(value, str):
            text = normalize_key(value)
        elif key in {"business_line", "line", "kind", "type", "artifact_type", "route", "endpoint", "lane"}:
            text = normalize_key(value)
        for needle in needles:
            if needle in key or needle in text:
                found.add(needle)
    return found


def detect_business_line(path: Path, payload: Any) -> str:
    path_text = normalize_key(path.as_posix())
    for line in BUSINESS_LINES:
        if line in path_text:
            return line

    field_lines = find_string_matches(payload, BUSINESS_LINES)
    for line in BUSINESS_LINES:
        if line in field_lines:
            return line

    if find_present_fields(payload, SEARCH_READBACK_KEYS | {"retrieval_run", "retrieval_run_id"}):
        return "search"
    if find_present_fields(payload, {"submission_id", "ingest_action", "idempotency_key"}):
        return "ingest"
    if find_present_fields(payload, {"operation_preview", "preview", "risk_labels"}):
        return "admin"
    if find_present_fields(payload, {"dashboard", "quality_gate", "report_detail"}):
        return "dashboard"
    return "generic"


def relative_artifact_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def check_payload(path: Path, payload: Any) -> dict[str, Any]:
    business_line = detect_business_line(path, payload)
    trace_matches = find_present_fields(payload, TRACE_KEYS)
    source_matches = find_present_fields(payload, SOURCE_KEYS)
    search_matches = find_present_fields(payload, SEARCH_READBACK_KEYS)
    admin_evidence_matches = find_present_fields(payload, ADMIN_EVIDENCE_KEYS)
    admin_risk_matches = find_present_fields(payload, ADMIN_RISK_KEYS)
    ingest_identity_matches = find_ingest_identity_matches(payload)

    missing: list[str] = []
    if not trace_matches:
        missing.append("trace_chain_or_trace_id")
    if not source_matches:
        missing.append("source_refs_or_source_query")
    if business_line == "search" and not search_matches:
        missing.append("provider_trace_or_retrieval_run_readback_or_index_freshness")
    if business_line == "admin":
        if not admin_evidence_matches:
            missing.append("evidence_preview")
        if not admin_risk_matches:
            missing.append("risk_tags_or_risk_labels")
    if business_line == "ingest" and not ingest_identity_matches:
        missing.append("ingest_trace_identity")

    checks: dict[str, Any] = {
        "trace_readback": {
            "status": STATUS_PASSED if trace_matches else STATUS_FAILED,
            "required_any_of": sorted(TRACE_KEYS),
            "matched_paths": [match.path for match in trace_matches],
        },
        "source_readback": {
            "status": STATUS_PASSED if source_matches else STATUS_FAILED,
            "required_any_of": sorted(SOURCE_KEYS),
            "matched_paths": [match.path for match in source_matches],
        },
    }
    if business_line == "search":
        checks["search_provider_or_readback"] = {
            "status": STATUS_PASSED if search_matches else STATUS_FAILED,
            "required_any_of": sorted(SEARCH_READBACK_KEYS),
            "matched_paths": [match.path for match in search_matches],
        }
    if business_line == "admin":
        checks["admin_preview_evidence"] = {
            "status": STATUS_PASSED
            if admin_evidence_matches and admin_risk_matches
            else STATUS_FAILED,
            "required": sorted(ADMIN_EVIDENCE_KEYS),
            "required_any_risk_of": sorted(ADMIN_RISK_KEYS),
            "evidence_preview_matched_paths": [match.path for match in admin_evidence_matches],
            "risk_matched_paths": [match.path for match in admin_risk_matches],
        }
    if business_line == "ingest":
        checks["ingest_trace_identity"] = {
            "status": STATUS_PASSED if ingest_identity_matches else STATUS_FAILED,
            "required_any_of": sorted(INGEST_IDENTITY_KEYS),
            "matched_paths": [match.path for match in ingest_identity_matches],
        }

    return {
        "business_line": business_line,
        "status": STATUS_PASSED if not missing else STATUS_FAILED,
        "missing_contract_fields": missing,
        "reason": "artifact satisfies trace/source readback contract"
        if not missing
        else "artifact is missing required trace/source readback contract fields",
        "checks": checks,
    }


def inspect_artifact(path: Path, root: Path, observed_at: str) -> dict[str, Any]:
    artifact_path = relative_artifact_path(path, root)
    row: dict[str, Any] = {
        "artifact_path": artifact_path,
        "absolute_path": str(path.resolve()),
        "observed_at": observed_at,
    }
    if not path.exists():
        row.update(
            {
                "business_line": "unknown",
                "status": STATUS_FAILED,
                "missing_contract_fields": ["artifact_file"],
                "reason": "artifact file does not exist",
                "checks": {},
            }
        )
        return row

    payload, error = load_artifact(path)
    if error is not None:
        row.update(
            {
                "business_line": "unknown",
                "status": STATUS_FAILED,
                "missing_contract_fields": ["valid_json"],
                "reason": error,
                "checks": {},
            }
        )
        return row

    row.update(check_payload(path, payload))
    return row


def build_report(
    artifact_paths: Sequence[str | Path], root: Path | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=business_trace_readback_artifacts "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    resolved_root = root.resolve() if root else repo_root()
    observed_at = utc_now()
    artifacts = [inspect_artifact(Path(path), resolved_root, observed_at) for path in artifact_paths]
    passed_count = sum(1 for artifact in artifacts if artifact["status"] == STATUS_PASSED)
    failed_count = sum(1 for artifact in artifacts if artifact["status"] == STATUS_FAILED)
    status = STATUS_PASSED if artifacts and failed_count == 0 else STATUS_FAILED
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "summary": {
            "artifact_count": len(artifacts),
            "passed_count": passed_count,
            "failed_count": failed_count,
        },
        "recommended_command": "python3 scripts/check_business_trace_readback_contract.py --json <artifact.json> [...]",
        "artifacts": artifacts,
    }


def print_human(report: dict[str, Any]) -> None:
    if report["status"] == STATUS_PASSED:
        print("OK business trace/source readback contract satisfied")
        return

    print("FAILED business trace/source readback contract")
    for artifact in report["artifacts"]:
        if artifact["status"] == STATUS_PASSED:
            continue
        missing = ", ".join(artifact["missing_contract_fields"]) or "<unknown>"
        print(f"- {artifact['artifact_path']}: {artifact['business_line']} missing={missing}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else repo_root()
    report = build_report(args.artifacts, root=root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)
    if report["status"] == STATUS_PASSED or args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
