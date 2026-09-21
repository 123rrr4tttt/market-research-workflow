#!/usr/bin/env python3
"""Close the reviewed Gitleaks denominator without storing scanner values."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[8]
SECURITY = Path(__file__).resolve().parent
R13T = SECURITY.parents[1] / "r13t" / "security"
SEMANTIC = R13T / "gitleaks-semantic-review.r13t.json"
FRESH = R13T / "gitleaks-fresh-after-seed-redaction.r13t.json"
OUTPUT = SECURITY / "gitleaks-disposition.r13u.json"


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


semantic = json.loads(SEMANTIC.read_bytes())
fresh = json.loads(FRESH.read_bytes())
reviewed = {row[0]: row for row in semantic["groups"]}
fresh_groups: dict[str, dict[str, object]] = {}
for finding in fresh["findings"]:
    fresh_groups.setdefault(finding["stable_fingerprint"], finding)

assert len(fresh["findings"]) == 417
assert len(fresh_groups) == 403
assert set(fresh_groups) <= set(reviewed)

decisions = []
counts = {"CONTEXT_FALSE_POSITIVE_ACCEPTED": 0, "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED": 0}
for fingerprint, finding in sorted(fresh_groups.items()):
    row = reviewed[fingerprint]
    prior_status = row[8]
    if prior_status == "context-confirmed false positive":
        decision = "CONTEXT_FALSE_POSITIVE_ACCEPTED"
    elif prior_status == "frozen historical/snapshot requiring migration or exact exception decision":
        decision = "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED"
    else:
        raise AssertionError(f"unresolved semantic status: {prior_status}")
    counts[decision] += 1
    decisions.append(
        {
            "stable_fingerprint": fingerprint,
            "rule": finding["rule"],
            "relative_path": finding["relative_path"],
            "location": finding["location"],
            "decision": decision,
            "reason_code": row[9],
            "source_identity": row[10],
            "semantic_label": row[11],
        }
    )

assert counts == {
    "CONTEXT_FALSE_POSITIVE_ACCEPTED": 369,
    "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED": 34,
}

payload = {
    "schema_version": "mrw.stage3.gitleaks-disposition.v1",
    "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "status": "PASS_ALL_FRESH_FINDINGS_EXACTLY_DISPOSED_NOT_RELEASE_AUTHORITY",
    "authoritative_release_approval": False,
    "decision_basis": "Stage3 executor technical disposition under the user's instruction to complete Stage3; no credential value was stored, echoed, or externally tested.",
    "inputs": {"semantic_review": ref(SEMANTIC), "fresh_redacted_scan": ref(FRESH)},
    "denominator": {
        "raw_findings": 417,
        "stable_groups": 403,
        "disposition_counts": counts,
        "unresolved_groups": 0,
        "suspected_credentials_requiring_rotation": 0,
        "unknown_groups": 0,
    },
    "snapshot_decision": {
        "choice": "EXACT_LOCATION_EXCEPTION",
        "groups": 34,
        "scope": "Only the listed fingerprint, rule, path, and location tuples in four immutable imported README snapshots.",
        "migration_deferred": True,
        "reason": "The semantic review identifies imported public example material; preserving snapshot identity is preferable to rewriting frozen external evidence.",
    },
    "policy_effect": {
        "gitleaks_configuration_changed": False,
        "broad_allowlist_added": False,
        "directory_or_rule_ignore_added": False,
        "scanner_threshold_changed": False,
        "note": "This record is a reviewed exact disposition ledger, not a scanner configuration or suppression rule.",
    },
    "decisions": decisions,
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"output": str(OUTPUT), "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), **payload["denominator"]}, sort_keys=True))
