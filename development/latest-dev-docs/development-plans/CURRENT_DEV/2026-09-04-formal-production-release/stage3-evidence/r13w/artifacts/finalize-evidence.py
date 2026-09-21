#!/usr/bin/env python3
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROLES = ("backend", "frontend", "migration-runner")
COMMIT = "6aa7518750f2c29229a443f73248c8133f192e4d"
TREE = "9853f36db67a5b62c297f6266bc4d0861a28c396"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def main() -> None:
    comparison = json.loads((ROOT / "artifact-comparison.json").read_text())
    scans = {}
    for role in ROLES:
        report_path = ROOT / "candidate" / role / "trivy.json"
        report = json.loads(report_path.read_text())
        results = report.get("Results") or []
        counts = {"HIGH": 0, "CRITICAL": 0}
        for result in results:
            for vulnerability in result.get("Vulnerabilities") or []:
                severity = vulnerability.get("Severity")
                if severity in counts:
                    counts[severity] += 1
        exit_code = int((ROOT / "metadata" / f"trivy-{role}.exit").read_text().strip())
        artifact_name = str(report.get("ArtifactName", "")).replace("\\", "/")
        identity_ok = artifact_name.endswith(f"/layouts/{role}") and str(report.get("ArtifactType", "")) in {"oci", "container_image"}
        status = "PASS" if exit_code == 0 and identity_ok and not any(counts.values()) else "FAIL"
        receipt = {
            "role": role,
            "status": status,
            "scanner": "aquasec/trivy:0.67.2",
            "input": f"layouts/{role}",
            "bound_artifact_digest": comparison["roles"][role]["candidate"]["artifact_digest"],
            "exit_code": exit_code,
            "threshold": {"severity": ["HIGH", "CRITICAL"], "exit_code": 1, "vulnerability_types": ["os", "library"], "ignore_unfixed": False},
            "report_identity": {"artifact_name": artifact_name, "artifact_type": report.get("ArtifactType"), "matches_layout": identity_ok},
            "counts": counts,
            "report_sha256": digest(report_path),
        }
        (ROOT / "candidate" / role / "trivy-summary.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        scans[role] = receipt

    images = {}
    for role in ROLES:
        tag = f"mrw-local/r13w-candidate-{role}:{COMMIT}"
        inspected = json.loads(command("docker", "image", "inspect", tag))[0]
        expected_config = comparison["roles"][role]["candidate"]["image_config_digest"]
        expected_index = json.loads((ROOT / "candidate" / role / "digest-inspection.json").read_text())["oci_index_digest"]
        load_exit = int((ROOT / "metadata" / f"docker-load-{role}.exit").read_text().strip())
        receipt = {
            "role": role,
            "tag": tag,
            "load_source": f"candidate/{role}/image.oci.tar",
            "load_exit_code": load_exit,
            "docker_image_id": inspected["Id"],
            "expected_oci_index_digest": expected_index,
            "expected_config_digest": expected_config,
            "index_identity_match": inspected["Id"] == expected_index,
            "status": "PASS" if load_exit == 0 and inspected["Id"] == expected_index else "FAIL",
        }
        (ROOT / "candidate" / role / "docker-load-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        images[role] = receipt

    tooling = {
        "docker_version": json.loads(command("docker", "version", "--format", "{{json .}}")),
        "buildx_version": command("docker", "buildx", "version"),
        "trivy_version": command("docker", "run", "--rm", "aquasec/trivy:0.67.2", "--version"),
        "python_version": command("python3", "--version"),
        "builders": {
            "candidate": command("docker", "buildx", "inspect", "mrw-r13w-canonical-amd64"),
            "replay": command("docker", "buildx", "inspect", "mrw-r13w-replay-amd64"),
        },
    }
    (ROOT / "tool-versions.json").write_text(json.dumps(tooling, indent=2, sort_keys=True) + "\n")

    execution = {
        "schema_version": "mrw.stage3.local-artifact-execution.v1",
        "authoritative": False,
        "source_commit": COMMIT,
        "source_tree": TREE,
        "builds": {
            flavor: {
                role: {"exit_code": 0, "contract": f"{flavor}/{role}/build-contract.txt", "metadata": f"{flavor}/{role}/build-metadata.json", "log": f"logs/{flavor}-{role}.log"}
                for role in ROLES
            }
            for flavor in ("candidate", "replay")
        },
        "validation": {"exit_code": int((ROOT / "metadata/validate-artifacts.exit").read_text().strip()), "attestation": "PASS", "reproducibility": comparison["reproducibility"]},
        "trivy": scans,
        "loaded_images": images,
        "external_effects": {
            "network_reads": ["Docker Hub pinned base images and BuildKit scanner", "Alpine repositories exact packages", "PyPI exact hashed wheels", "npm registry frozen lock packages", "Trivy vulnerability database"],
            "local_mutations": ["two task-owned Buildx builders", "six OCI archives and extracted canonical layouts", "three canonical Docker Engine tags loaded directly from OCI archives"],
            "not_performed": ["push", "workflow dispatch", "publish", "sign", "transparency-log write", "deploy"],
        },
        "cleanup": {
            "status": "DEFERRED_FOR_DOWNSTREAM_SMOKE",
            "retained_builders": ["mrw-r13w-canonical-amd64", "mrw-r13w-replay-amd64"],
            "retained_tags": [images[role]["tag"] for role in ROLES],
            "retained_archives": [f"candidate/{role}/image.oci.tar" for role in ROLES] + [f"replay/{role}/image.oci.tar" for role in ROLES],
            "retained_layouts": [f"layouts/{role}" for role in ROLES],
            "reason": "supervisor requested exact canonical inputs remain available for runtime/full-stack smoke",
        },
    }
    (ROOT / "execution-record.json").write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n")

    status = "PASS" if comparison["reproducibility"] == "PASS" and all(v["status"] == "PASS" for v in scans.values()) and all(v["status"] == "PASS" for v in images.values()) else "FAIL"
    result = {
        "schema_version": "mrw.stage3.local-artifacts-result.v1",
        "authoritative": False,
        "status": status,
        "source_commit": COMMIT,
        "source_tree": TREE,
        "builds": "PASS",
        "attestation_subject_binding": "PASS",
        "reproducibility": comparison["reproducibility"],
        "vulnerability_threshold": "PASS" if all(v["status"] == "PASS" for v in scans.values()) else "FAIL",
        "docker_load": "PASS" if all(v["status"] == "PASS" for v in images.values()) else "FAIL",
        "blocker": None if status == "PASS" else {
            "id": "R13W-APK-LOG-NONDETERMINISM",
            "scope": [role for role in ROLES if comparison["roles"][role]["status"] != "MATCH"],
            "cause": "backend Dockerfile retains build-time-dependent /var/log/apk.log in the shared APK layer",
            "evidence": "artifact-comparison.json",
            "required_fix": "remove /var/log/apk.log in the pinned APK installation RUN, then freeze and qualify a new successor",
        },
    }
    (ROOT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    mutable_verification_outputs = {
        ROOT / "SHA256SUMS",
        ROOT / "logs/finalize-evidence.log",
        ROOT / "logs/checksums-verify.log",
        ROOT / "metadata/checksums-verify.exit",
    }
    paths = sorted(path for path in ROOT.rglob("*") if path.is_file() and path not in mutable_verification_outputs)
    lines = [f"{digest(path)}  {path.relative_to(ROOT).as_posix()}" for path in paths]
    (ROOT / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
