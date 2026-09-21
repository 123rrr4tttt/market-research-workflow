#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time


ROOT = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13v")
CANDIDATE = ROOT / "candidate"
REPLAY = ROOT / "replay"
RELEASE_EVIDENCE = ROOT / "evidence"
OUT = Path(
    "/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/"
    "development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
    "stage3-evidence/r13v/artifacts/backend-migration-amd64-candidate-replay"
)
EXPECTED_COMMIT = "8427e3d626cd12f41e45d38e00223f2ef86d692f"
EXPECTED_TREE = "4146bcab51e437920a006875e06ed8cdcc32470a"
PLATFORM = "linux/amd64"
BUILDKIT_IMAGE = "moby/buildkit@sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8"
MIN_FREE_BYTES = 4 * 1024**3
ROLES = {
    "backend": "backend-runtime",
    "migration-runner": "migration-runner",
}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(argv: list[str], cwd: Path | None = None) -> dict:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "argv": argv,
        "cwd": str(cwd) if cwd else None,
        "exit_code": completed.returncode,
        "output": completed.stdout,
    }


def run_logged(name: str, argv: list[str], cwd: Path) -> int:
    write_json(OUT / f"{name}.command.json", {"argv": argv, "cwd": str(cwd)})
    started = time.time()
    with (OUT / f"{name}.log").open("w") as log:
        completed = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    write_json(
        OUT / f"{name}.exit.json",
        {
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.time() - started, 3),
            "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
        },
    )
    print(f"{name}: exit={completed.returncode}", flush=True)
    return completed.returncode


def git_snapshot(path: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()

    return {
        "path": str(path),
        "commit": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "backend_tree": git("rev-parse", "HEAD:main/backend"),
        "src_tree": git("rev-parse", "HEAD:src"),
        "dockerfile_sha256": sha256(path / "main/backend/Dockerfile"),
        "status_porcelain": git("status", "--porcelain=v1"),
        "clean": git("status", "--porcelain=v1") == "",
    }


def blob(bundle: tarfile.TarFile, digest: str) -> bytes:
    if not DIGEST.fullmatch(digest):
        raise ValueError(f"invalid digest: {digest}")
    member = f"blobs/sha256/{digest.removeprefix('sha256:')}"
    handle = bundle.extractfile(member)
    if handle is None:
        raise ValueError(f"missing OCI blob: {member}")
    payload = handle.read()
    if hashlib.sha256(payload).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"OCI blob digest mismatch: {digest}")
    return payload


def inspect_archive(path: Path, environment: str, role: str) -> dict:
    with tarfile.open(path, "r") as bundle:
        index_handle = bundle.extractfile("index.json")
        if index_handle is None:
            raise ValueError("OCI archive has no index.json")
        index = json.load(index_handle)
        roots = index.get("manifests") or []
        if len(roots) != 1:
            raise ValueError(f"expected one OCI root descriptor, got {len(roots)}")
        root_digest = roots[0]["digest"]
        root = json.loads(blob(bundle, root_digest))
        if isinstance(root.get("manifests"), list):
            image_descriptors = [
                descriptor
                for descriptor in root["manifests"]
                if descriptor.get("platform", {}).get("os") == "linux"
                and descriptor.get("platform", {}).get("architecture") == "amd64"
                and descriptor.get("annotations", {}).get("vnd.docker.reference.type")
                != "attestation-manifest"
            ]
            attestation_descriptors = [
                descriptor for descriptor in root["manifests"] if descriptor not in image_descriptors
            ]
            if len(image_descriptors) != 1:
                raise ValueError(
                    f"expected one linux/amd64 image descriptor, got {len(image_descriptors)}"
                )
            image_digest = image_descriptors[0]["digest"]
            manifest = json.loads(blob(bundle, image_digest))
        else:
            image_digest = root_digest
            manifest = root
            attestation_descriptors = []

        config_descriptor = manifest["config"]
        config = json.loads(blob(bundle, config_descriptor["digest"]))
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError(f"unexpected image platform: {config.get('os')}/{config.get('architecture')}")
        layers = manifest.get("layers") or []
        if not layers:
            raise ValueError("image manifest has no layers")
        for descriptor in layers:
            blob(bundle, descriptor["digest"])

        statement_records = []
        for position, descriptor in enumerate(attestation_descriptors):
            attestation_manifest = json.loads(blob(bundle, descriptor["digest"]))
            descriptor_subject = descriptor.get("annotations", {}).get(
                "vnd.docker.reference.digest"
            )
            for layer_position, layer in enumerate(attestation_manifest.get("layers") or []):
                payload = blob(bundle, layer["digest"])
                if "gzip" in str(layer.get("mediaType", "")):
                    payload = gzip.decompress(payload)
                statement = json.loads(payload)
                statement_records.append(
                    {
                        "descriptor_position": position,
                        "layer_position": layer_position,
                        "descriptor_digest": descriptor["digest"],
                        "descriptor_subject_digest": descriptor_subject,
                        "descriptor_subject_matches_image": descriptor_subject == image_digest,
                        "statement": statement,
                    }
                )

    result = {
        "environment": environment,
        "role": role,
        "platform": PLATFORM,
        "oci_root_digest": root_digest,
        "image_manifest_digest": image_digest,
        "image_config_digest": config_descriptor["digest"],
        "image_layer_digests": [descriptor["digest"] for descriptor in layers],
        "archive_sha256": sha256(path),
        "archive_bytes": path.stat().st_size,
        "attestation_manifest_count": len(attestation_descriptors),
        "all_referenced_image_blobs_validated": True,
        "runtime_config": {
            key: config.get("config", {}).get(key)
            for key in (
                "Entrypoint",
                "Cmd",
                "Env",
                "WorkingDir",
                "User",
                "ExposedPorts",
                "Healthcheck",
            )
        },
    }

    if environment == "candidate":
        def select(predicate_prefix: str) -> list[dict]:
            return [
                record
                for record in statement_records
                if str(record["statement"].get("predicateType", "")).startswith(predicate_prefix)
            ]

        provenance = select("https://slsa.dev/provenance/")
        sbom = select("https://spdx.dev/Document")
        if len(provenance) != 1 or len(sbom) != 1:
            raise ValueError(
                f"expected one provenance and one SBOM statement, got {len(provenance)} and {len(sbom)}"
            )
        bindings = {}
        for label, record in (("provenance", provenance[0]), ("sbom", sbom[0])):
            statement = record["statement"]
            subjects = statement.get("subject") or []
            statement_subject_matches = any(
                isinstance(subject, dict)
                and subject.get("digest", {}).get("sha256") == image_digest.removeprefix("sha256:")
                for subject in subjects
            )
            statement_path = OUT / "candidate" / f"{role}.{label}.intoto.json"
            write_json(statement_path, statement)
            bindings[label] = {
                "predicate_type": statement.get("predicateType"),
                "statement_sha256": sha256(statement_path),
                "statement_subjects": subjects,
                "statement_subject_matches_image": statement_subject_matches,
                "descriptor_subject_digest": record["descriptor_subject_digest"],
                "descriptor_subject_matches_image": record[
                    "descriptor_subject_matches_image"
                ],
            }
        provenance_predicate = provenance[0]["statement"].get("predicate") or {}
        sbom_predicate = sbom[0]["statement"].get("predicate") or {}
        bindings["provenance"]["content_valid"] = bool(
            provenance_predicate.get("buildDefinition") or provenance_predicate.get("builder")
        )
        bindings["sbom"]["content_valid"] = bool(
            str(sbom_predicate.get("spdxVersion", "")).startswith("SPDX-")
            and isinstance(sbom_predicate.get("packages"), list)
        )
        bindings["sbom"]["package_count"] = len(sbom_predicate.get("packages") or [])
        descriptor_bound = all(value["descriptor_subject_matches_image"] for value in bindings.values())
        statement_bound = all(value["statement_subject_matches_image"] for value in bindings.values())
        content_valid = all(value["content_valid"] for value in bindings.values())
        result["attestations"] = {
            "bindings": bindings,
            "descriptor_bound_to_image": descriptor_bound,
            "statement_subject_bound_to_image": statement_bound,
            "content_valid": content_valid,
            "status": (
                "PASS_DESCRIPTOR_AND_STATEMENT_SUBJECT_BOUND"
                if descriptor_bound and statement_bound and content_valid
                else "PARTIAL_DESCRIPTOR_BOUND_STATEMENT_SUBJECT_GAP"
                if descriptor_bound and content_valid
                else "FAIL_UNBOUND_OR_INVALID"
            ),
        }
    write_json(OUT / environment / f"{role}.digest-inspection.json", result)
    return result


def parse_trivy(path: Path, exit_code: int) -> dict:
    if not path.is_file():
        return {"report_present": False, "exit_code": exit_code, "gate_status": "NOT_RUN"}
    report = json.loads(path.read_text())
    vulnerabilities = [
        vulnerability
        for result in report.get("Results") or []
        for vulnerability in result.get("Vulnerabilities") or []
    ]
    severity = {
        level: sum(1 for item in vulnerabilities if item.get("Severity") == level)
        for level in ("CRITICAL", "HIGH")
    }
    status_counts: dict[str, int] = {}
    for item in vulnerabilities:
        status = item.get("Status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = {
        "report_present": True,
        "exit_code": exit_code,
        "gate_status": "PASS" if exit_code == 0 else "FAIL",
        "threshold": "HIGH,CRITICAL",
        "package_types": ["os", "library"],
        "observation_count": len(vulnerabilities),
        "unique_vulnerability_id_count": len(
            {item.get("VulnerabilityID") for item in vulnerabilities}
        ),
        "affected_package_version_count": len(
            {(item.get("PkgName"), item.get("InstalledVersion")) for item in vulnerabilities}
        ),
        "observations_with_reported_fixed_version": sum(
            1 for item in vulnerabilities if item.get("FixedVersion")
        ),
        "severity": severity,
        "status_counts": status_counts,
        "report_sha256": sha256(path),
        "report_created_at": report.get("CreatedAt"),
        "reachability_exploitability": "NOT_ASSESSED_BY_TRIVY",
    }
    return summary


def remove_builder(role: str, environment: str, builder: str, cleanup_events: list[dict]) -> None:
    code = run_logged(
        f"{role}-{environment}-builder-cleanup",
        ["docker", "buildx", "rm", builder],
        OUT,
    )
    cleanup_events.append(
        {"kind": "builder", "environment": environment, "name": builder, "exit_code": code}
    )


def build_role(role: str, target: str, builders: dict[str, str]) -> dict:
    free_before = shutil.disk_usage("/System/Volumes/Data").free
    if free_before < MIN_FREE_BYTES:
        result = {
            "role": role,
            "status": "NOT_RUN_INSUFFICIENT_SAFE_DISK_BUDGET",
            "free_bytes": free_before,
            "minimum_required_bytes": MIN_FREE_BYTES,
        }
        write_json(OUT / f"{role}.summary.json", result)
        return result

    archives = {
        "candidate": OUT / "candidate" / f"{role}.oci.tar",
        "replay": OUT / "replay" / f"{role}.oci.tar",
    }
    created: list[tuple[str, str]] = []
    cleanup_events: list[dict] = []
    result: dict = {
        "role": role,
        "target": target,
        "platform": PLATFORM,
        "free_bytes_before": free_before,
        "builders": builders,
    }
    try:
        for environment in ("candidate", "replay"):
            builder = builders[environment]
            code = run_logged(
                f"{role}-{environment}-builder-create",
                [
                    "docker",
                    "buildx",
                    "create",
                    "--driver",
                    "docker-container",
                    "--driver-opt",
                    f"image={BUILDKIT_IMAGE}",
                    "--name",
                    builder,
                ],
                OUT,
            )
            if code != 0:
                raise RuntimeError(f"{environment} builder creation failed with exit {code}")
            created.append((environment, builder))
            code = run_logged(
                f"{role}-{environment}-builder-bootstrap",
                ["docker", "buildx", "inspect", "--bootstrap", builder],
                OUT,
            )
            if code != 0:
                raise RuntimeError(f"{environment} builder bootstrap failed with exit {code}")

        for environment in ("candidate", "replay"):
            free_before_build = shutil.disk_usage("/System/Volumes/Data").free
            if free_before_build < MIN_FREE_BYTES:
                raise RuntimeError(
                    "INSUFFICIENT_SAFE_DISK_BUDGET before "
                    f"{environment} build: {free_before_build} < {MIN_FREE_BYTES}"
                )
            source = CANDIDATE if environment == "candidate" else REPLAY
            metadata = OUT / environment / f"{role}.build-metadata.json"
            argv = [
                "docker",
                "buildx",
                "build",
                "--builder",
                builders[environment],
                "--progress",
                "plain",
                "--no-cache",
                "--platform",
                PLATFORM,
                f"--provenance={'true' if environment == 'candidate' else 'false'}",
                f"--sbom={'true' if environment == 'candidate' else 'false'}",
                "--build-arg",
                "SOURCE_DATE_EPOCH=0",
                "--file",
                "main/backend/Dockerfile",
                "--target",
                target,
                "--metadata-file",
                str(metadata),
                "--output",
                f"type=oci,dest={archives[environment]},rewrite-timestamp=true",
                ".",
            ]
            code = run_logged(f"{role}-{environment}-build", argv, source)
            if code != 0:
                raise RuntimeError(f"{environment} build failed with exit {code}")

        inspections = {
            environment: inspect_archive(archives[environment], environment, role)
            for environment in ("candidate", "replay")
        }
        candidate = inspections["candidate"]
        replay = inspections["replay"]
        comparison = {
            "role": role,
            "platform": PLATFORM,
            "candidate_image_manifest_digest": candidate["image_manifest_digest"],
            "replay_image_manifest_digest": replay["image_manifest_digest"],
            "candidate_image_config_digest": candidate["image_config_digest"],
            "replay_image_config_digest": replay["image_config_digest"],
            "candidate_image_layer_digests": candidate["image_layer_digests"],
            "replay_image_layer_digests": replay["image_layer_digests"],
            "image_manifest_equal": candidate["image_manifest_digest"]
            == replay["image_manifest_digest"],
            "image_config_equal": candidate["image_config_digest"]
            == replay["image_config_digest"],
            "image_layers_equal_in_order": candidate["image_layer_digests"]
            == replay["image_layer_digests"],
            "oci_root_equal": candidate["oci_root_digest"] == replay["oci_root_digest"],
            "oci_root_difference_expected": (
                "Candidate root includes provenance/SBOM attestation manifests; replay root intentionally disables attestations."
            ),
        }
        comparison["status"] = (
            "PASS_EXACT_IMAGE"
            if comparison["image_manifest_equal"]
            and comparison["image_config_equal"]
            and comparison["image_layers_equal_in_order"]
            else "MISMATCH"
        )
        write_json(OUT / f"{role}.reproducibility.json", comparison)

        trivy_report = OUT / "candidate" / f"{role}.trivy.json"
        trivy_code = run_logged(
            f"{role}-candidate-trivy",
            [
                "trivy",
                "image",
                "--input",
                str(archives["candidate"]),
                "--scanners",
                "vuln",
                "--pkg-types",
                "os,library",
                "--severity",
                "HIGH,CRITICAL",
                "--exit-code",
                "1",
                "--format",
                "json",
                "--output",
                str(trivy_report),
            ],
            OUT,
        )
        trivy_summary = parse_trivy(trivy_report, trivy_code)
        write_json(OUT / "candidate" / f"{role}.trivy.summary.json", trivy_summary)
        attestation_status = inspections["candidate"].get("attestations", {}).get("status")
        result.update(
            {
                "status": (
                    "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_FAIL"
                    if comparison["status"] == "PASS_EXACT_IMAGE" and trivy_code != 0
                    else "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_PASS"
                    if comparison["status"] == "PASS_EXACT_IMAGE"
                    else "MISMATCH"
                ),
                "inspections": inspections,
                "comparison": comparison,
                "trivy": trivy_summary,
                "attestation_status": attestation_status,
                "trivy_replay_reuse": {
                    "scan_executed_against": "candidate OCI archive",
                    "applies_to_replay_by_exact_image_manifest_digest": comparison[
                        "image_manifest_equal"
                    ],
                    "fresh_replay_scan_executed": False,
                },
            }
        )
    except Exception as exc:
        result["status"] = "FAILED_OR_INCOMPLETE"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for environment, builder in reversed(created):
            remove_builder(role, environment, builder, cleanup_events)
        for environment, archive in archives.items():
            if archive.exists():
                archive_sha = sha256(archive)
                archive_bytes = archive.stat().st_size
                archive.unlink()
                cleanup_events.append(
                    {
                        "kind": "temporary_oci_archive",
                        "environment": environment,
                        "path": str(archive),
                        "sha256_before_removal": archive_sha,
                        "bytes_reclaimed": archive_bytes,
                        "removed": True,
                        "reason": (
                            "Digest/config/layers, attestation statements, Trivy report, and build metadata were retained as compact evidence."
                        ),
                    }
                )
        builder_listing = command_output(["docker", "buildx", "ls"])
        result["cleanup"] = {
            "events": cleanup_events,
            "builder_residue": [
                name for name in builders.values() if name in builder_listing["output"]
            ],
            "temporary_oci_archives_present": [
                str(path) for path in archives.values() if path.exists()
            ],
            "docker_prune_run": False,
            "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
        }
        write_json(OUT / f"{role}.summary.json", result)
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidate").mkdir(exist_ok=True)
    (OUT / "replay").mkdir(exist_ok=True)

    candidate_before = git_snapshot(CANDIDATE)
    replay_before = git_snapshot(REPLAY)
    identity_equal = all(
        candidate_before[key] == replay_before[key]
        for key in ("commit", "tree", "backend_tree", "src_tree", "dockerfile_sha256")
    )
    identity = {
        "schema": "mrw.stage3.r13v.backend-migration-amd64-input.v1",
        "authoritative": False,
        "candidate": candidate_before,
        "replay": replay_before,
        "expected_commit": EXPECTED_COMMIT,
        "expected_tree": EXPECTED_TREE,
        "candidate_replay_input_identity_equal": identity_equal,
        "candidate_manifest": {
            "path": str(RELEASE_EVIDENCE / "candidate-manifest.v5.json"),
            "sha256": sha256(RELEASE_EVIDENCE / "candidate-manifest.v5.json"),
        },
        "platform": PLATFORM,
        "authority_ceiling": "LOCAL_UNSIGNED_TASK_OWNED_EVIDENCE_NOT_RELEASE_AUTHORITY",
    }
    write_json(OUT / "identity.json", identity)
    if not (
        candidate_before["commit"] == EXPECTED_COMMIT
        and candidate_before["tree"] == EXPECTED_TREE
        and replay_before["commit"] == EXPECTED_COMMIT
        and replay_before["tree"] == EXPECTED_TREE
        and candidate_before["clean"]
        and replay_before["clean"]
        and identity_equal
    ):
        write_json(
            OUT / "summary.json",
            {
                "status": "NOT_RUN_IDENTITY_OR_CLEANLINESS_GATE_FAILED",
                "identity": identity,
            },
        )
        return 1

    token = f"{os.getpid()}-{int(time.time())}"
    builders = {
        "candidate": f"mrw-r13v-amd64-candidate-{token}",
        "replay": f"mrw-r13v-amd64-replay-{token}",
    }
    environment = {
        "schema": "mrw.stage3.r13v.backend-migration-amd64-environment.v1",
        "started_epoch": int(time.time()),
        "free_bytes_before": shutil.disk_usage("/System/Volumes/Data").free,
        "minimum_build_start_free_bytes": MIN_FREE_BYTES,
        "disk_strategy": (
            "One role at a time; two independent task-owned builders are recreated using the same unique names per role, then removed with their caches. Temporary OCI archives are removed after inspection and Trivy scanning."
        ),
        "builders": builders,
        "buildkit_image": BUILDKIT_IMAGE,
        "docker_version": command_output(["docker", "version"]),
        "buildx_version": command_output(["docker", "buildx", "version"]),
        "trivy_version_before": command_output(["trivy", "version"]),
        "preexisting_builders": command_output(["docker", "buildx", "ls"]),
        "preexisting_containers": command_output(
            ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}"]
        ),
        "preservation": (
            "No preexisting images, containers, volumes, builders, or caches are removed. No Docker prune is run."
        ),
    }
    write_json(OUT / "environment.pre.json", environment)
    update_code = run_logged(
        "trivy-db-update",
        ["trivy", "image", "--download-db-only"],
        OUT,
    )
    write_json(
        OUT / "trivy-version-after-update.json",
        command_output(["trivy", "version"]),
    )

    roles: dict[str, dict] = {}
    for role, target in ROLES.items():
        print(
            f"ROLE_START {role} free={shutil.disk_usage('/System/Volumes/Data').free}",
            flush=True,
        )
        roles[role] = build_role(role, target, builders)
        print(f"ROLE_END {role} status={roles[role].get('status')}", flush=True)
        if roles[role].get("status") in {
            "NOT_RUN_INSUFFICIENT_SAFE_DISK_BUDGET",
            "FAILED_OR_INCOMPLETE",
        }:
            break

    candidate_after = git_snapshot(CANDIDATE)
    replay_after = git_snapshot(REPLAY)
    builder_listing_after = command_output(["docker", "buildx", "ls"])
    container_listing_after = command_output(
        ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}"]
    )
    cleanup_residue = {
        "task_builder_names": list(builders.values()),
        "task_builder_residue": [
            name for name in builders.values() if name in builder_listing_after["output"]
        ],
        "task_builder_container_residue": [
            name for name in builders.values() if name in container_listing_after["output"]
        ],
        "temporary_oci_archives": [
            str(path) for path in OUT.rglob("*.oci.tar") if path.is_file()
        ],
        "docker_prune_run": False,
        "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
    }
    write_json(OUT / "cleanup-residue.json", cleanup_residue)

    all_roles_present = set(roles) == set(ROLES)
    exact = all(
        record.get("comparison", {}).get("status") == "PASS_EXACT_IMAGE"
        for record in roles.values()
    ) and all_roles_present
    security_failed = any(
        record.get("trivy", {}).get("gate_status") == "FAIL" for record in roles.values()
    )
    subject_gaps = {
        role: record.get("inspections", {})
        .get("candidate", {})
        .get("attestations", {})
        .get("status")
        for role, record in roles.items()
        if record.get("inspections", {})
        .get("candidate", {})
        .get("attestations", {})
        .get("status")
        != "PASS_DESCRIPTOR_AND_STATEMENT_SUBJECT_BOUND"
    }
    inputs_unchanged = all(
        before[key] == after[key]
        for before, after in ((candidate_before, candidate_after), (replay_before, replay_after))
        for key in ("commit", "tree", "backend_tree", "src_tree", "dockerfile_sha256")
    ) and candidate_after["clean"] and replay_after["clean"]
    cleanup_clean = not any(
        (
            cleanup_residue["task_builder_residue"],
            cleanup_residue["task_builder_container_residue"],
            cleanup_residue["temporary_oci_archives"],
        )
    )
    if exact and inputs_unchanged and cleanup_clean:
        status = "PASS_EXACT_REPRODUCIBILITY"
        if security_failed:
            status += "_TRIVY_GATE_FAILED"
        else:
            status += "_TRIVY_GATE_PASSED"
        if subject_gaps:
            status += "_WITH_ATTESTATION_SUBJECT_GAP"
    else:
        status = "FAILED_OR_INCOMPLETE"
    summary = {
        "schema": "mrw.stage3.r13v.backend-migration-amd64-result.v1",
        "authoritative": False,
        "authority_ceiling": "LOCAL_UNSIGNED_TASK_OWNED_EVIDENCE_NOT_RELEASE_AUTHORITY",
        "status": status,
        "candidate_before": candidate_before,
        "candidate_after": candidate_after,
        "replay_before": replay_before,
        "replay_after": replay_after,
        "candidate_replay_inputs_equal": identity_equal,
        "inputs_unchanged_and_clean": inputs_unchanged,
        "platform": PLATFORM,
        "build_contract": {
            "candidate": "--no-cache, provenance=true, sbom=true, SOURCE_DATE_EPOCH=0, rewrite-timestamp=true",
            "replay": "--no-cache, provenance=false, sbom=false, SOURCE_DATE_EPOCH=0, rewrite-timestamp=true",
            "comparison": "image manifest, config, and ordered layer digests",
        },
        "trivy_db_update_exit_code": update_code,
        "roles": roles,
        "attestation_subject_gaps": subject_gaps,
        "cleanup": cleanup_residue,
        "completed_epoch": int(time.time()),
        "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
        "excluded": [
            "product modification",
            "registry push or publication",
            "signing",
            "transparency log",
            "deployment",
            "authority transfer",
            "Docker prune",
        ],
    }
    write_json(OUT / "summary.json", summary)

    members = sorted(
        path
        for path in OUT.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.endswith(".oci.tar")
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(OUT)}\n" for path in members)
    )
    print(
        f"COMPLETE status={status} sha256sums={sha256(OUT / 'SHA256SUMS')}",
        flush=True,
    )
    return 0 if status.startswith("PASS_EXACT_REPRODUCIBILITY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
