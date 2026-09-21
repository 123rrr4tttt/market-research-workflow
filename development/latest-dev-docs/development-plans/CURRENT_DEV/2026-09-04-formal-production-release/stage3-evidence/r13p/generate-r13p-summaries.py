#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence")
R13O = ROOT / "r13o"
R13P = ROOT / "r13p"
ARTIFACTS = R13P / "artifacts"
SECURITY = R13P / "security"

R13O_COMMIT = "3669d4ddc19fb722058976b4e1f05e99eccfe96e"
R13O_TREE = "ce4e4b9ce1b633276192e809fa72007176224e0c"
R13P_COMMIT = "342d3b3c35ad987c47990da6ac550dfe936d4818"
R13P_TREE = "3f87e85dce02b312e445c657c238c11c6809850e"
MANIFEST_SHA = "64c04d1d3d6fc7d302d89d5247857bcd20115a83432043ea95e18bf74d52635e"


def read_json(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exit_code(path: Path) -> int:
    return int(path.read_text().strip())


source_artifact_summary = read_json(R13O / "artifacts" / "summary.json")
roles = ("backend", "frontend", "migration-runner")

role_inputs = {
    "backend": {
        "main/backend": "9dae51846ae3808587f734a5e2c071bfc2b083ae",
        "src": "0dfa137c2c9aba658d8b1f39281412ff69c3d67c",
    },
    "migration-runner": {
        "main/backend": "9dae51846ae3808587f734a5e2c071bfc2b083ae",
        "src": "0dfa137c2c9aba658d8b1f39281412ff69c3d67c",
    },
    "frontend": {
        "main/frontend-modern": "f89dc7733737c8a1e3a6350ff32a5d0568771245",
    },
}

artifact_summary = {
    "schema": "mrw.stage3.artifact-evidence.r13p.v1",
    "authoritative": False,
    "authority_ceiling": "LOCAL_ROLE_INPUT_EVIDENCE_NOT_RELEASE_AUTHORITY",
    "candidate": {
        "commit": R13P_COMMIT,
        "tree": R13P_TREE,
        "effective_manifest": {
            "path": "/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13p/evidence/candidate-manifest.v5.retry1.json",
            "sha256": MANIFEST_SHA,
        },
    },
    "role_input_identity": {
        "status": "EXACT_GIT_TREE_MATCH_R13O_TO_R13P",
        "trees": role_inputs,
        "scope": "Only backend, migration-runner, and frontend build inputs are covered; Compose and formal-release binding changes are excluded.",
    },
    "source_execution": {
        "candidate": {"commit": R13O_COMMIT, "tree": R13O_TREE},
        "evidence_root": str(R13O / "artifacts"),
        "platform": source_artifact_summary["platform"],
        "provenance_binding": "The embedded BuildKit SLSA statements name the r13o revision; they are not rewritten or represented as r13p provenance.",
    },
    "builds": {
        phase: {
            role: {
                "exit_code": source_artifact_summary["build_commands"][f"{phase}-{role}-build"]["exit_code"],
                "artifact_digest": source_artifact_summary[phase][role]["artifact_digest"],
                "oci_root_digest": source_artifact_summary[phase][role]["oci_root_digest"],
                "archive_sha256": source_artifact_summary[phase][role]["archive_sha256"],
                **(
                    {
                        "slsa_provenance_count": source_artifact_summary[phase][role].get("slsa_provenance_count", 0),
                        "spdx_sbom_count": source_artifact_summary[phase][role].get("spdx_sbom_count", 0),
                    }
                    if phase == "canonical"
                    else {}
                ),
            }
            for role in roles
        }
        for phase in ("canonical", "rebuild")
    },
    "reproducibility": source_artifact_summary["comparisons"],
    "collection_integrity": {
        "status": "LIMITED_DUPLICATE_WRITER_OBSERVED",
        "detail": "Two r13o runner instances briefly wrote the same evidence paths. The older untracked instance and its task-owned builders were terminated; OCI blob validation passed, but command/log/metadata-to-archive attribution is not sufficient for an independent reproducibility claim.",
    },
    "unexecuted_authority_items": [
        "required remote CI linux/amd64 build",
        "registry push and immutability verification",
        "artifact signing and transparency-log verification",
        "deployment or release approval",
    ],
    "status": "FAILED_OR_INCOMPLETE",
}
ARTIFACTS.mkdir(parents=True, exist_ok=True)
(ARTIFACTS / "summary.json").write_text(json.dumps(artifact_summary, indent=2, sort_keys=True) + "\n")

gitleaks = read_json(SECURITY / "gitleaks-current-tree.report.json")
rule_counts: dict[str, int] = {}
root_counts: dict[str, int] = {}
candidate_prefix = "/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13p/candidate/"
for finding in gitleaks:
    rule = finding["RuleID"]
    rule_counts[rule] = rule_counts.get(rule, 0) + 1
    relative = finding["File"].removeprefix(candidate_prefix)
    root = relative.split("/", 1)[0]
    root_counts[root] = root_counts.get(root, 0) + 1

trivy = {}
finding_index: dict[tuple[str, str, str, str, str, str], dict] = {}
for role in roles:
    report_path = SECURITY / f"{role}.trivy.r13o-role-input.json"
    report = read_json(report_path)
    vulnerabilities = [v for result in report.get("Results") or [] for v in (result.get("Vulnerabilities") or [])]
    trivy[role] = {
        "source_artifact_digest": source_artifact_summary["canonical"][role]["artifact_digest"],
        "exit_code": exit_code(SECURITY / f"{role}-trivy-r13o-role-input.exit.txt"),
        "high": sum(v.get("Severity") == "HIGH" for v in vulnerabilities),
        "critical": sum(v.get("Severity") == "CRITICAL" for v in vulnerabilities),
        "total_high_critical": len(vulnerabilities),
        "report_sha256": sha(report_path),
    }
    for result in report.get("Results") or []:
        package_class = result.get("Class") or "unknown"
        package_type = result.get("Type") or "unknown"
        for vulnerability in result.get("Vulnerabilities") or []:
            key = (
                package_class,
                package_type,
                vulnerability.get("PkgName") or "",
                vulnerability.get("InstalledVersion") or "",
                vulnerability.get("FixedVersion") or "",
                vulnerability.get("VulnerabilityID") or "",
            )
            entry = finding_index.setdefault(
                key,
                {
                    "package_class": package_class,
                    "package_type": package_type,
                    "package": vulnerability.get("PkgName"),
                    "installed_version": vulnerability.get("InstalledVersion"),
                    "fixed_version": vulnerability.get("FixedVersion") or None,
                    "vulnerability_id": vulnerability.get("VulnerabilityID"),
                    "severity": vulnerability.get("Severity"),
                    "status": vulnerability.get("Status") or "unknown",
                    "roles": [],
                    "reachability": "NOT_ASSESSED_BY_TRIVY",
                },
            )
            if role not in entry["roles"]:
                entry["roles"].append(role)

r13o_security = R13O / "security"
security_summary = {
    "schema": "mrw.stage3.security-evidence.r13p.v1",
    "authoritative": False,
    "authority_ceiling": "LOCAL_SECURITY_EVIDENCE_NOT_RELEASE_AUTHORITY",
    "candidate": {
        "commit": R13P_COMMIT,
        "tree": R13P_TREE,
        "effective_manifest_sha256": MANIFEST_SHA,
    },
    "role_input_identity": artifact_summary["role_input_identity"],
    "reused_unchanged_role_input_checks": {
        "bandit_high_high": {"exit_code": exit_code(r13o_security / "bandit.exit.txt"), "report_sha256": sha(r13o_security / "bandit.report.json")},
        "pip_audit_python_3_11": {"exit_code": exit_code(r13o_security / "pip-audit.exit.txt"), "report_sha256": sha(r13o_security / "pip-audit.report.json")},
        "pnpm_audit_prod_high": {"exit_code": exit_code(r13o_security / "frontend-audit.exit.txt"), "log_sha256": sha(r13o_security / "frontend-audit.log")},
        "fixed_git_dependency_audit": {"exit_code": exit_code(r13o_security / "functorial-kit-audit.exit.txt"), "report_sha256": sha(r13o_security / "functorial-kit-audit.report.json")},
    },
    "current_tree_gitleaks": {
        "exit_code": exit_code(SECURITY / "gitleaks-current-tree.exit.txt"),
        "finding_count": len(gitleaks),
        "by_rule": dict(sorted(rule_counts.items())),
        "by_top_level_path": dict(sorted(root_counts.items())),
        "report_sha256": sha(SECURITY / "gitleaks-current-tree.report.json"),
        "private_key_location": "docs/reference-pool/platformization/snapshots/readmes/getsops__sops.md:1606",
        "classification": "UNRESOLVED_REQUIRES_DISPOSITION",
        "redaction": "100 percent",
    },
    "trivy_high_critical": trivy,
    "limitations": [
        "Trivy reports scan validated r13o canonical OCI layouts whose role-input Git trees are byte-identical to r13p; they do not create r13p-bound provenance.",
        "Public vulnerability databases do not cover the pinned functorial-kit Git commit as a PyPI release; the fixed-Git checker covers declaration, checkout, installed bytes, and Bandit only.",
        "Gitleaks and Trivy findings require human disposition; no allowlist or suppression was applied.",
    ],
    "status": "FAILED_UNRESOLVED_FINDINGS",
}
(SECURITY / "summary.json").write_text(json.dumps(security_summary, indent=2, sort_keys=True) + "\n")

findings = sorted(
    finding_index.values(),
    key=lambda item: (
        0 if item["severity"] == "CRITICAL" else 1,
        item["package_type"],
        item["package"] or "",
        item["vulnerability_id"] or "",
    ),
)
repair_package = {
    "schema": "mrw.stage3.bounded-security-repair.r13p.v1",
    "candidate": {"commit": R13P_COMMIT, "tree": R13P_TREE},
    "gate": {"severity_threshold": ["HIGH", "CRITICAL"], "status": "FAILED"},
    "deduplicated_counts": {
        "role_observations": sum(item["total_high_critical"] for item in trivy.values()),
        "package_version_cve": len(findings),
        "unique_cves": len({item["vulnerability_id"] for item in findings}),
        "critical_cves": sorted({item["vulnerability_id"] for item in findings if item["severity"] == "CRITICAL"}),
    },
    "origin": {
        "os_package_findings": len(findings),
        "language_package_findings": 0,
        "unknown_origin_findings": 0,
    },
    "repair_surfaces": [
        {
            "file": "main/frontend-modern/Dockerfile",
            "line": 18,
            "roles": ["frontend"],
            "action": "Refresh the pinned nginx:1.27-alpine runtime digest to an image containing at least the Trivy-reported fixed package versions, then rebuild and rescan.",
            "acceptance": "Trivy HIGH/CRITICAL count is zero for the rebuilt frontend runtime image.",
        },
        {
            "file": "main/backend/Dockerfile",
            "lines": [1, 11, 16],
            "roles": ["backend", "migration-runner"],
            "action": "Refresh the pinned python:3.11-slim base and remove build-only packages from runtime stages where feasible. Trivy reports no fixed version for the current Debian 13.6 findings, so do not invent package pins; rebuild against a base with vendor fixes or produce explicit VEX/risk disposition for remaining findings.",
            "acceptance": "Rebuilt backend and migration images either have zero HIGH/CRITICAL findings or each remaining finding has approved VEX/risk disposition tied to its exact package/version/CVE.",
        },
    ],
    "findings": findings,
    "gitleaks_disposition": {
        "finding_count": len(gitleaks),
        "report": "gitleaks-current-tree.report.json",
        "required_action": "Review redacted findings; rotate/remove confirmed credentials and record narrowly justified allowlist entries only for verified fixtures or vendored reference snapshots.",
        "priority_location": "docs/reference-pool/platformization/snapshots/readmes/getsops__sops.md:1606",
    },
}
(SECURITY / "bounded-repair-package.json").write_text(json.dumps(repair_package, indent=2, sort_keys=True) + "\n")

critical_lines = []
for finding in findings:
    if finding["severity"] != "CRITICAL":
        continue
    critical_lines.append(
        f"| {', '.join(finding['roles'])} | {finding['package_type']} | {finding['package']} | "
        f"{finding['installed_version']} | {finding['fixed_version'] or 'none reported'} | "
        f"{finding['vulnerability_id']} | {finding['status']} |"
    )
repair_markdown = """# r13p bounded Stage 3 security repair package

Gate result: **FAILED** at the required HIGH/CRITICAL threshold. Trivy found only OS-package findings; it did not establish runtime reachability or exploitability. Backend and migration results are identical and are deduplicated into shared repair work.

## Exact critical findings

| Roles | Origin | Package | Installed | Fixed | CVE | Status |
|---|---|---|---|---|---|---|
""" + "\n".join(critical_lines) + """

## Bounded repair ownership

- `main/frontend-modern/Dockerfile:18`: refresh the pinned nginx Alpine runtime digest so the 36 reported findings reach their listed fixed versions; rebuild and require zero HIGH/CRITICAL findings.
- `main/backend/Dockerfile:1,11-16`: refresh the pinned Python slim base and keep build-only packages out of runtime layers where feasible. The current Debian 13.6 report provides no fixed version for 148 backend/migration observations; any remainder needs exact VEX/risk disposition, not silent suppression.
- Gitleaks: disposition all 410 redacted current-tree findings. Inspect the private-key signature in the vendored/reference README snapshot first; rotate/remove any real secret, and allowlist only verified non-secret fixtures with narrow paths/rules.

The complete package/version/CVE/role list is in `bounded-repair-package.json`.
"""
(SECURITY / "bounded-repair-package.md").write_text(repair_markdown)

sum_paths = sorted(path for path in SECURITY.iterdir() if path.is_file() and path.name != "SHA256SUMS")
(SECURITY / "SHA256SUMS").write_text("".join(f"{sha(path)}  {path.name}\n" for path in sum_paths))
