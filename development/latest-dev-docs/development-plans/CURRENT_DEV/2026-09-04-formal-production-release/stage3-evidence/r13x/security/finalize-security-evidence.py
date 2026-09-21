#!/usr/bin/env python3
"""Finalize non-authoritative exact-r13x source security evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


REPO = Path("/Users/wangyiliang/market-research-workflow")
STAGE = REPO / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence"
HERE = STAGE / "r13x/security"
RAW = HERE / "raw"
META = HERE / "metadata"
CANDIDATE = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13x/candidate")
R13V_SCAN = STAGE / "r13v/security/gitleaks-exact-candidate-scan.r13v.json"
R13V_DISPOSITION = STAGE / "r13v/security/gitleaks-disposition.r13v.json"
ARTIFACTS = STAGE / "r13x/artifacts"
EXPECTED_COMMIT = "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
EXPECTED_TREE = "ce7c67c831b51f9d64b4c2f1a470a724a50b19df"
PRIOR_COMMIT = "8427e3d626cd12f41e45d38e00223f2ef86d692f"


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, object]:
    try:
        label = str(path.relative_to(REPO))
    except ValueError:
        label = str(path)
    return {"path": label, "sha256": sha(path), "bytes": path.stat().st_size}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cmd(*parts: str) -> str:
    return subprocess.check_output(parts, text=True).strip()


def exit_code(name: str) -> int:
    return int((META / name).read_text(encoding="utf-8").strip())


generated = now()
commit = cmd("git", "-C", str(CANDIDATE), "rev-parse", "HEAD")
tree = cmd("git", "-C", str(CANDIDATE), "rev-parse", "HEAD^{tree}")
status = cmd("git", "-C", str(CANDIDATE), "status", "--short", "--untracked-files=all")
assert (commit, tree, status) == (EXPECTED_COMMIT, EXPECTED_TREE, "")

workflow = CANDIDATE / ".github/workflows/backend-tests.yml"
runtime_lock = CANDIDATE / "main/backend/requirements-runtime-linux-amd64-py311.lock.txt"
frontend_lock = CANDIDATE / "main/frontend-modern/pnpm-lock.yaml"
frontend_package = CANDIDATE / "main/frontend-modern/package.json"

tool_versions = {
    "schema_version": "mrw.stage3.security-tool-versions.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "python": (RAW / "python-version.log").read_text().strip(),
    "bandit": (RAW / "bandit-version.log").read_text().strip(),
    "pip_audit": (RAW / "pip-audit-version.log").read_text().strip(),
    "gitleaks": (RAW / "gitleaks-version.log").read_text().strip(),
    "node": (RAW / "node-version.log").read_text().strip(),
    "pnpm": (RAW / "pnpm-version.log").read_text().strip(),
    "workflow_input": ref(workflow),
}
write(HERE / "tool-versions.r13x.json", tool_versions)

bandit_raw = load(RAW / "bandit.report.json")
bandit_result_count = len(bandit_raw.get("results", []))
assert exit_code("bandit.exit") == 0 and bandit_result_count == 0
bandit = {
    "schema_version": "mrw.stage3.bandit-gate.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS",
    "candidate": {"commit": commit, "tree": tree},
    "command": (
        "bandit -q -r main/backend/app -x main/backend/tests "
        "--severity-level high --confidence-level high -f json -o <security>/raw/bandit.report.json"
    ),
    "workflow_required_command": (
        "bandit -q -r main/backend/app -x main/backend/tests "
        "--severity-level high --confidence-level high"
    ),
    "cwd": str(CANDIDATE),
    "exit_code": 0,
    "threshold": {"severity": "high", "confidence": "high"},
    "findings_at_or_above_threshold": bandit_result_count,
    "metrics": bandit_raw["metrics"]["_totals"],
    "report": ref(RAW / "bandit.report.json"),
    "limitations": ["Local source scan only; this is not release or security approval."],
}
write(HERE / "bandit.r13x.json", bandit)

derived_lock = RAW / "mrw-public-pypi-requirements.txt"
pip_raw = load(RAW / "pip-audit.report.json")
pip_vulns = [v for dep in pip_raw.get("dependencies", []) for v in dep.get("vulns", [])]
assert exit_code("pip-audit-input-derivation.exit") == 0
assert exit_code("pip-audit.attempt1.exit") != 0
assert exit_code("pip-audit.attempt2.exit") == 0 and not pip_vulns
pip_audit = {
    "schema_version": "mrw.stage3.pip-audit-gate.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS",
    "candidate": {"commit": commit, "tree": tree},
    "source_lock": ref(runtime_lock),
    "derived_public_pypi_input": ref(derived_lock),
    "input_derivation": {
        "status": "PASS",
        "workflow_semantics": (
            "Remove at most one local --find-links ./vendor option and exactly the "
            "./vendor/functorial_kit-0.1.0-py3-none-any.whl chunk; reject other non-PyPI entries."
        ),
        "excluded_non_pypi_entries": ["./vendor/functorial_kit-0.1.0-py3-none-any.whl"],
    },
    "command": (
        "pip-audit -r <task-tmp>/mrw-public-pypi-requirements.txt --strict "
        "--require-hashes --no-deps --disable-pip --format json --output <security>/raw/pip-audit.report.json"
    ),
    "workflow_required_command": (
        "pip-audit -r ${RUNNER_TEMP}/mrw-public-pypi-requirements.txt --strict "
        "--require-hashes --no-deps --disable-pip"
    ),
    "cwd": str(CANDIDATE / "main/backend"),
    "attempts": [
        {
            "attempt": 1,
            "exit_code": exit_code("pip-audit.attempt1.exit"),
            "status": "EXTERNAL_QUERY_ERROR",
            "reason": "PyPI HTTPS request ended with SSL unexpected EOF; no vulnerability conclusion was drawn.",
            "stderr": ref(RAW / "pip-audit.attempt1.stderr.log"),
        },
        {
            "attempt": 2,
            "exit_code": 0,
            "status": "PASS",
            "stderr": ref(RAW / "pip-audit.attempt2.stderr.log"),
        },
    ],
    "dependencies": len(pip_raw.get("dependencies", [])),
    "known_vulnerabilities": len(pip_vulns),
    "report": ref(RAW / "pip-audit.report.json"),
    "limitations": [
        "The fixed lock input is exact, while advisory availability results reflect the PyPI service available at scan time.",
        "The fixed Git dependency is intentionally excluded by the workflow's separate dependency-audit lane.",
        "Local source dependency evidence only; this is not release or security approval.",
    ],
}
write(HERE / "pip-audit.r13x.json", pip_audit)

pnpm_raw = load(RAW / "pnpm-audit.report.json")
pnpm_counts = pnpm_raw["metadata"]["vulnerabilities"]
assert exit_code("pnpm-install.exit") == 0 and exit_code("pnpm-audit.exit") == 0
assert pnpm_counts["high"] == 0 and pnpm_counts["critical"] == 0
frontend = {
    "schema_version": "mrw.stage3.frontend-dependency-audit-gate.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS",
    "candidate": {"commit": commit, "tree": tree},
    "inputs": {"package_json": ref(frontend_package), "pnpm_lock": ref(frontend_lock)},
    "immutable_mirror": {
        "method": "git archive HEAD main/frontend-modern extracted into the task-owned temporary directory",
        "source_commit": commit,
        "reason": "Run frozen installation without writing node_modules into the canonical candidate.",
    },
    "commands": ["pnpm install --frozen-lockfile", "pnpm audit --prod --audit-level high --json"],
    "workflow_required_commands": ["pnpm install --frozen-lockfile", "pnpm audit --prod --audit-level high"],
    "cwd": "<task-tmp>/main/frontend-modern",
    "canonical_workflow_cwd": str(CANDIDATE / "main/frontend-modern"),
    "install_exit_code": 0,
    "audit_exit_code": 0,
    "threshold": "high",
    "scope": "production dependencies",
    "vulnerability_counts": pnpm_counts,
    "dependency_counts": {k: v for k, v in pnpm_raw["metadata"].items() if k != "vulnerabilities"},
    "report": ref(RAW / "pnpm-audit.report.json"),
    "limitations": [
        "The package and frozen lock inputs are exact; registry advisory results reflect the service available at scan time.",
        "Local frontend dependency evidence only; this is not release or security approval.",
    ],
}
write(HERE / "frontend-dependency-audit.r13x.json", frontend)

gitleaks_raw = load(RAW / "gitleaks-redacted.report.json")
assert isinstance(gitleaks_raw, list) and exit_code("gitleaks.exit") == 1
prefix = str(CANDIDATE) + os.sep
findings = []
for row in gitleaks_raw:
    assert row.get("Secret") == "REDACTED"
    path = row["File"]
    assert path.startswith(prefix)
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
    payload = {
        "end_column": finding["location"]["end_column"],
        "end_line": finding["location"]["end_line"],
        "path": finding["relative_path"],
        "rule": finding["rule"],
        "start_column": finding["location"]["start_column"],
        "start_line": finding["location"]["start_line"],
    }
    finding["stable_fingerprint"] = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    findings.append(finding)

prior_scan = load(R13V_SCAN)
prior_disposition = load(R13V_DISPOSITION)
def tuple_key(row: dict[str, object]) -> tuple[object, ...]:
    location = row["location"]
    return (
        row["rule"], row["relative_path"], location["start_line"], location["end_line"],
        location["start_column"], location["end_column"], row["stable_fingerprint"],
    )

assert Counter(map(tuple_key, findings)) == Counter(map(tuple_key, prior_scan["findings"]))
groups = {row["stable_fingerprint"]: row for row in findings}
assert len(findings) == 417 and len(groups) == 403

reuse_rows = []
for relative_path in sorted({row["relative_path"] for row in findings}):
    old_blob = cmd("git", "-C", str(CANDIDATE), "rev-parse", f"{PRIOR_COMMIT}:{relative_path}")
    new_blob = cmd("git", "-C", str(CANDIDATE), "rev-parse", f"{EXPECTED_COMMIT}:{relative_path}")
    worktree_blob = cmd("git", "-C", str(CANDIDATE), "hash-object", str(CANDIDATE / relative_path))
    assert old_blob == new_blob == worktree_blob
    reuse_rows.append({
        "relative_path": relative_path,
        "r13v_blob_oid": old_blob,
        "r13x_blob_oid": new_blob,
        "r13x_worktree_blob_oid": worktree_blob,
        "unchanged": True,
    })

reuse_proof = {
    "schema_version": "mrw.stage3.gitleaks-unchanged-input-reuse-proof.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS_ALL_FINDING_INPUT_FILES_BYTE_IDENTICAL",
    "prior_commit": PRIOR_COMMIT,
    "current_commit": commit,
    "finding_paths": len(reuse_rows),
    "raw_finding_multiset_equal": True,
    "stable_group_set_equal": True,
    "new_or_changed_findings": 0,
    "proof_method": (
        "For every path containing a finding, compare the r13v commit blob OID, r13x commit blob OID, "
        "and the clean r13x worktree hash-object; separately compare the complete rule/path/location/fingerprint multiset."
    ),
    "files": reuse_rows,
    "limitations": ["Reuse applies only to these exact paths, bytes, locations, rules, and fingerprints."],
}
write(HERE / "gitleaks-reuse-proof.r13x.json", reuse_proof)

scan = {
    "schema_version": "mrw.stage3.gitleaks-redacted-findings.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "FINDINGS_PRESENT_ALL_VALUES_REDACTED",
    "candidate": {"label": "r13x", "root": str(CANDIDATE), "commit": commit, "tree": tree},
    "command": (
        f"gitleaks dir --redact=100 --no-banner --no-color --report-format json "
        f"--report-path {RAW / 'gitleaks-redacted.report.json'} {CANDIDATE}"
    ),
    "cwd": str(CANDIDATE),
    "scanner": {
        "name": "gitleaks", "version": tool_versions["gitleaks"], "mode": "dir", "exit_code": 1,
        "redact_percent": 100,
        "policy": "built-in default; no allowlist, directory ignore, rule ignore, baseline, or threshold override",
    },
    "raw_findings": len(findings),
    "stable_groups": len(groups),
    "scanner_value_material_included": False,
    "original_value_material_included": False,
    "raw_report": ref(RAW / "gitleaks-redacted.report.json"),
    "findings": findings,
}
write(HERE / "gitleaks-exact-candidate-scan.r13x.json", scan)

prior_decisions = {row["stable_fingerprint"]: row for row in prior_disposition["decisions"]}
assert set(groups) == set(prior_decisions)
decisions = []
counts = Counter()
for fingerprint, finding in sorted(groups.items()):
    prior = prior_decisions[fingerprint]
    assert tuple_key(finding) == tuple_key(prior)
    decision = {
        **finding,
        "decision": prior["decision"],
        "reason_code": prior["reason_code"],
        "source_identity": prior["source_identity"],
        "semantic_label": prior["semantic_label"],
        "reuse_basis": "EXACT_TUPLE_AND_UNCHANGED_FILE_BLOB",
    }
    counts[decision["decision"]] += 1
    decisions.append(decision)
assert counts == {"CONTEXT_FALSE_POSITIVE_ACCEPTED": 369, "EXACT_SNAPSHOT_EXCEPTION_ACCEPTED": 34}
disposition = {
    "schema_version": "mrw.stage3.gitleaks-disposition.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS_ALL_EXACT_CANDIDATE_FINDINGS_DISPOSED_NOT_RELEASE_AUTHORITY",
    "inputs": {
        "current_scan": ref(HERE / "gitleaks-exact-candidate-scan.r13x.json"),
        "reuse_proof": ref(HERE / "gitleaks-reuse-proof.r13x.json"),
        "prior_exact_scan": ref(R13V_SCAN),
        "prior_disposition": ref(R13V_DISPOSITION),
    },
    "denominator": {
        "raw_findings": len(findings), "stable_groups": len(groups),
        "disposition_counts": dict(counts), "new_or_changed_groups": 0,
        "unresolved_groups": 0, "suspected_credentials_requiring_rotation": 0, "unknown_groups": 0,
    },
    "reuse_boundary": (
        "Every reused decision is bound to the same rule/path/location/fingerprint tuple and a file whose "
        "r13v commit blob, r13x commit blob, and r13x clean-worktree blob are identical."
    ),
    "snapshot_decision": prior_disposition["snapshot_decision"],
    "policy_effect": {
        "gitleaks_configuration_changed": False, "broad_allowlist_added": False,
        "directory_or_rule_ignore_added": False, "scanner_threshold_changed": False,
    },
    "decisions": decisions,
}
write(HERE / "gitleaks-disposition.r13x.json", disposition)

artifact_result = load(ARTIFACTS / "result.json")
comparison = load(ARTIFACTS / "artifact-comparison.json")
assert artifact_result["source_commit"] == commit and artifact_result["source_tree"] == tree
assert artifact_result["vulnerability_threshold"] == "PASS"
trivy_roles = {}
for role in ("backend", "frontend", "migration-runner"):
    summary_path = ARTIFACTS / f"candidate/{role}/trivy-summary.json"
    report_path = ARTIFACTS / f"candidate/{role}/trivy.json"
    inspection_path = ARTIFACTS / f"candidate/{role}/digest-inspection.json"
    image_path = ARTIFACTS / f"candidate/{role}/image.oci.tar"
    summary = load(summary_path)
    inspection = load(inspection_path)
    expected_digest = comparison["roles"][role]["candidate"]["artifact_digest"]
    assert summary["authoritative"] is False
    assert summary["status"] == "PASS" and summary["exit_code"] == 0
    assert summary["counts"] == {"CRITICAL": 0, "HIGH": 0}
    assert summary["bound_artifact_digest"] == inspection["artifact_digest"] == expected_digest
    assert summary["report_sha256"] == sha(report_path)
    assert int((ARTIFACTS / f"metadata/trivy-{role}.exit").read_text().strip()) == 0
    trivy_roles[role] = {
        "status": "PASS",
        "bound_artifact_digest": expected_digest,
        "artifact_tar": ref(image_path),
        "digest_inspection": ref(inspection_path),
        "report": ref(report_path),
        "summary": ref(summary_path),
        "counts": summary["counts"],
        "exit_code": summary["exit_code"],
        "report_identity": summary["report_identity"],
    }

trivy = {
    "schema_version": "mrw.stage3.exact-artifact-trivy-reference.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS_REFERENCED_EXACT_R13X_TRIVY_EVIDENCE",
    "candidate": {"commit": commit, "tree": tree},
    "scanner": "aquasec/trivy:0.67.2",
    "threshold": {"severity": ["HIGH", "CRITICAL"], "exit_code": 1, "ignore_unfixed": False, "vulnerability_types": ["os", "library"]},
    "artifacts_checksum_manifest": ref(ARTIFACTS / "SHA256SUMS"),
    "artifacts_checksum_verification": ref(RAW / "artifacts-sha256-verify.log"),
    "roles": trivy_roles,
    "execution": "Not rerun in this task; exact r13x digest-bound reports from the artifacts lane were verified and referenced.",
    "limitations": ["Trivy evidence is local and non-authoritative; it does not grant release or production authority."],
}
write(HERE / "trivy-exact-artifact-reference.r13x.json", trivy)

identity = {
    "schema_version": "mrw.stage3.security-candidate-identity.v1",
    "authoritative": False,
    "generated_at_utc": generated,
    "status": "PASS",
    "candidate": {"root": str(CANDIDATE), "commit": commit, "tree": tree, "clean_before": True, "clean_after": True},
    "workflow": ref(workflow),
    "source_inputs": {"runtime_lock": ref(runtime_lock), "frontend_lock": ref(frontend_lock), "frontend_package": ref(frontend_package)},
}
write(HERE / "candidate-identity.r13x.json", identity)

task_tmp = Path((META / "task-tmp-path.txt").read_text(encoding="utf-8").strip())
assert str(task_tmp).startswith("/private/tmp/mrw-r13x-security-") and task_tmp.is_dir()
shutil.rmtree(task_tmp)
assert not task_tmp.exists()
cleanup = {
    "schema_version": "mrw.stage3.security-task-cleanup.v1",
    "authoritative": False,
    "generated_at_utc": now(),
    "status": "PASS",
    "task_owned_path": str(task_tmp),
    "removed": True,
    "exists_after_cleanup": False,
    "candidate_clean_after_cleanup": cmd("git", "-C", str(CANDIDATE), "status", "--short", "--untracked-files=all") == "",
}
assert cleanup["candidate_clean_after_cleanup"]
write(HERE / "cleanup.r13x.json", cleanup)
(RAW / "candidate-status.after.log").write_text("", encoding="utf-8")

gates = {
    "bandit": {"status": "PASS", "evidence": ref(HERE / "bandit.r13x.json")},
    "pip_audit": {"status": "PASS", "evidence": ref(HERE / "pip-audit.r13x.json")},
    "gitleaks": {"status": "PASS", "evidence": ref(HERE / "gitleaks-disposition.r13x.json")},
    "frontend_dependency_audit": {"status": "PASS", "evidence": ref(HERE / "frontend-dependency-audit.r13x.json")},
    "image_trivy": {"status": "PASS_REFERENCED", "evidence": ref(HERE / "trivy-exact-artifact-reference.r13x.json")},
}
aggregation = {
    "schema_version": "mrw.stage3.security-gate-aggregation.v1",
    "authoritative": False,
    "generated_at_utc": now(),
    "status": "PASS_REQUIRED_LOCAL_SOURCE_SECURITY_GATES_NOT_AUTHORITY",
    "candidate": {"commit": commit, "tree": tree, "clean": True},
    "contract_source": {"workflow": ref(workflow), "workflow_security_block_lines": "747-850"},
    "required_gates": gates,
    "summary": {
        "bandit_high_high_findings": 0,
        "pip_audit_dependencies": len(pip_raw.get("dependencies", [])),
        "pip_audit_known_vulnerabilities": 0,
        "gitleaks_raw_findings": len(findings),
        "gitleaks_stable_groups": len(groups),
        "gitleaks_new_or_changed_groups": 0,
        "gitleaks_unresolved_groups": 0,
        "frontend_high": pnpm_counts["high"],
        "frontend_critical": pnpm_counts["critical"],
        "trivy_high": sum(row["counts"]["HIGH"] for row in trivy_roles.values()),
        "trivy_critical": sum(row["counts"]["CRITICAL"] for row in trivy_roles.values()),
    },
    "authority_ceiling": (
        "Local evidence only; authoritative=false. This aggregation is not Stage 3 acceptance, release approval, "
        "production authority, signing authority, deployment authority, or publication authority."
    ),
    "limitations": [
        "pip-audit attempt 1 was an external TLS EOF; the same exact command and input passed on attempt 2, and both attempts are retained.",
        "Gitleaks scanner exit 1 denotes findings; gate PASS follows only from the exact 403-group disposition with zero unresolved groups.",
        "Image Trivy was not rerun; existing exact r13x digest-bound reports and their checksum manifest were revalidated.",
        "Tool-native raw JSON schemas do not carry authority fields; every interpreting r13x wrapper and this aggregation explicitly set authoritative=false.",
    ],
}
write(HERE / "security-gate-aggregation.r13x.json", aggregation)

print(json.dumps({"status": aggregation["status"], "gates": gates, "cleanup": cleanup}, sort_keys=True))
