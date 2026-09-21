#!/usr/bin/env python3
"""Persist the exact-candidate redacted Gitleaks denominator and dispositions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[8]
HERE = Path(__file__).resolve().parent
R13T = HERE.parents[1] / "r13t" / "security"
RAW = Path("/private/tmp/mrw-r13v-exact-gitleaks-redacted.json")
CANDIDATE = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13v/candidate")
SEMANTIC = R13T / "gitleaks-semantic-review.r13t.json"
SCAN = HERE / "gitleaks-exact-candidate-scan.r13v.json"
DISPOSITION = HERE / "gitleaks-disposition.r13v.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


raw_rows = json.loads(RAW.read_bytes())
assert isinstance(raw_rows, list) and len(raw_rows) == 417
prefix = str(CANDIDATE) + "/"
findings = []
for row in raw_rows:
    path = row["File"]
    assert path.startswith(prefix)
    assert row.get("Secret") == "REDACTED"
    finding = {
        "rule": row["RuleID"],
        "relative_path": path[len(prefix):],
        "location": {
            "start_line": row["StartLine"],
            "end_line": row["EndLine"],
            "start_column": row["StartColumn"],
            "end_column": row["EndColumn"],
        },
    }
    encoded = json.dumps(
        {"end_column": finding["location"]["end_column"], "end_line": finding["location"]["end_line"], "path": finding["relative_path"], "rule": finding["rule"], "start_column": finding["location"]["start_column"], "start_line": finding["location"]["start_line"]},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    finding["stable_fingerprint"] = hashlib.sha256(encoded).hexdigest()
    findings.append(finding)

groups = {row["stable_fingerprint"]: row for row in findings}
assert len(groups) == 403
now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
scan = {
    "schema_version": "mrw.stage3.gitleaks-redacted-findings.v1",
    "generated_at_utc": now,
    "status": "FINDINGS_PRESENT_ALL_VALUES_REDACTED",
    "candidate": {"label": "r13v", "root": str(CANDIDATE), "commit": "8427e3d626cd12f41e45d38e00223f2ef86d692f", "tree": "4146bcab51e437920a006875e06ed8cdcc32470a"},
    "scanner": {"name": "gitleaks", "version": "8.30.1", "mode": "dir", "exit_code": 1, "redact_percent": 100, "policy": "built-in default; no allowlist, directory ignore, rule ignore, baseline, or threshold override"},
    "raw_findings": 417,
    "stable_groups": 403,
    "scanner_value_material_included": False,
    "original_value_material_included": False,
    "findings": findings,
}
HERE.mkdir(parents=True, exist_ok=True)
SCAN.write_text(json.dumps(scan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

semantic = json.loads(SEMANTIC.read_bytes())
reviewed = {row[0]: row for row in semantic["groups"]}
assert set(groups) <= set(reviewed)
counts = {"CONTEXT_FALSE_POSITIVE_ACCEPTED": 0, "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED": 0}
decisions = []
for fingerprint, finding in sorted(groups.items()):
    row = reviewed[fingerprint]
    if row[8] == "context-confirmed false positive":
        decision = "CONTEXT_FALSE_POSITIVE_ACCEPTED"
    elif row[8] == "frozen historical/snapshot requiring migration or exact exception decision":
        decision = "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED"
    else:
        raise AssertionError(f"unresolved semantic status: {row[8]}")
    counts[decision] += 1
    decisions.append({**finding, "decision": decision, "reason_code": row[9], "source_identity": row[10], "semantic_label": row[11]})
assert counts == {"CONTEXT_FALSE_POSITIVE_ACCEPTED": 369, "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED": 34}
disposition = {
    "schema_version": "mrw.stage3.gitleaks-disposition.v1",
    "generated_at_utc": now,
    "status": "PASS_ALL_EXACT_CANDIDATE_FINDINGS_DISPOSED_NOT_RELEASE_AUTHORITY",
    "authoritative_release_approval": False,
    "inputs": {"semantic_review": ref(SEMANTIC), "exact_candidate_scan": ref(SCAN)},
    "denominator": {"raw_findings": 417, "stable_groups": 403, "disposition_counts": counts, "unresolved_groups": 0, "suspected_credentials_requiring_rotation": 0, "unknown_groups": 0},
    "snapshot_decision": {"choice": "EXACT_LOCATION_EXCEPTION", "groups": 34, "scope": "Only the listed fingerprint, rule, path, and location tuples in four immutable imported README snapshots.", "reason": "The reviewed entries are imported public example material; preserve frozen snapshot identity."},
    "policy_effect": {"gitleaks_configuration_changed": False, "broad_allowlist_added": False, "directory_or_rule_ignore_added": False, "scanner_threshold_changed": False},
    "decisions": decisions,
}
DISPOSITION.write_text(json.dumps(disposition, indent=2, sort_keys=True) + "\n", encoding="utf-8")
RAW.unlink()
print(json.dumps({"scan": ref(SCAN), "disposition": ref(DISPOSITION), "counts": counts}, sort_keys=True))
