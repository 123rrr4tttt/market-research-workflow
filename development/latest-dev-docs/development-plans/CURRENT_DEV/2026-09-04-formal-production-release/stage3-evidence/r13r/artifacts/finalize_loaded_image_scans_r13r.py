#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time


OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13r/artifacts")
ROLES = ("backend", "migration-runner", "frontend")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_summary(path: Path, exit_code: int) -> dict:
    report = json.loads(path.read_text())
    counts = {"HIGH": 0, "CRITICAL": 0}
    observations = 0
    packages = set()
    cves = set()
    fixed = 0
    for result in report.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = vulnerability.get("Severity")
            if severity not in counts:
                continue
            observations += 1
            counts[severity] += 1
            packages.add((vulnerability.get("PkgName"), vulnerability.get("InstalledVersion")))
            cves.add(vulnerability.get("VulnerabilityID"))
            if vulnerability.get("FixedVersion"):
                fixed += 1
    return {
        "exit_code": exit_code,
        "threshold": "HIGH,CRITICAL",
        "package_types": ["os", "library"],
        "scanner": "vulnerability",
        "counts": counts,
        "observation_count": observations,
        "affected_package_version_count": len(packages),
        "unique_vulnerability_id_count": len(cves),
        "observations_with_reported_fixed_version": fixed,
        "gate_status": "PASS" if exit_code == 0 else "FAIL",
        "report_sha256": sha256(path),
        "reachability_exploitability": "NOT_ASSESSED_BY_TRIVY",
    }


def main() -> int:
    available_path = OUT / "available-images.json"
    deadline = time.time() + 3 * 60 * 60
    while time.time() < deadline and not available_path.is_file():
        time.sleep(2)
    if not available_path.is_file():
        raise SystemExit("available-images.json not created before timeout")
    available = json.loads(available_path.read_text())
    scans = {}
    for role in ROLES:
        tag = available["roles"][role]["tag"]
        report_path = OUT / "canonical" / f"{role}.trivy.loaded-image.json"
        argv = [
            "trivy", "image", "--scanners", "vuln", "--pkg-types", "os,library",
            "--severity", "HIGH,CRITICAL", "--exit-code", "1", "--format", "json",
            "--output", str(report_path), tag,
        ]
        write_json(OUT / f"{role}-loaded-image-trivy.command.json", {"argv": argv, "cwd": str(OUT)})
        with (OUT / f"{role}-loaded-image-trivy.log").open("w") as log:
            completed = subprocess.run(argv, cwd=OUT, stdout=log, stderr=subprocess.STDOUT)
        write_json(OUT / f"{role}-loaded-image-trivy.exit.json", {"exit_code": completed.returncode})
        if not report_path.is_file():
            scans[role] = {"exit_code": completed.returncode, "status": "FAILED_NO_REPORT"}
            continue
        scans[role] = scan_summary(report_path, completed.returncode)
        write_json(OUT / "canonical" / f"{role}.trivy.summary.json", scans[role])
        role_path = OUT / f"{role}.summary.json"
        role_summary = json.loads(role_path.read_text())
        role_summary["trivy"] = scans[role]
        role_summary["trivy_input_recovery"] = {
            "initial_oci_tar_attempt": "UNSUPPORTED_OCI_TAR_INPUT_RETAINED_AS_DIAGNOSTIC",
            "effective_scan_subject": tag,
            "identity_binding": available["roles"][role],
        }
        if role_summary.get("comparison", {}).get("status") == "PASS_EXACT_IMAGE":
            role_summary["status"] = (
                "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_FAIL"
                if scans[role].get("gate_status") == "FAIL"
                else "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_PASS"
            )
        write_json(role_path, role_summary)
        print(f"SCAN {role} exit={completed.returncode} counts={scans[role].get('counts')}", flush=True)

    summary_path = OUT / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["roles"] = {role: json.loads((OUT / f"{role}.summary.json").read_text()) for role in ROLES}
    summary["effective_image_scans"] = scans
    exact = all(record.get("comparison", {}).get("status") == "PASS_EXACT_IMAGE" for record in summary["roles"].values())
    complete_scans = all(record.get("gate_status") in {"PASS", "FAIL"} for record in scans.values())
    any_fail = any(record.get("gate_status") == "FAIL" for record in scans.values())
    summary["status"] = (
        "PASS_EXACT_REPRODUCIBILITY_SECURITY_GATE_FAILED" if exact and complete_scans and any_fail
        else "PASS_EXACT_REPRODUCIBILITY_SECURITY_GATE_PASSED" if exact and complete_scans
        else "FAILED_OR_INCOMPLETE"
    )
    summary["completed_epoch"] = int(time.time())
    write_json(summary_path, summary)

    members = sorted(
        path for path in OUT.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.endswith(".oci.tar")
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(OUT)}\n" for path in members)
    )
    print(f"FINALIZED {summary['status']} SHA256SUMS={sha256(OUT / 'SHA256SUMS')}", flush=True)
    return 0 if exact and complete_scans else 1


if __name__ == "__main__":
    raise SystemExit(main())
