#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Any


EVIDENCE = Path(__file__).resolve().parent
BUILD_KIT_IMAGE = "moby/buildkit:buildx-stable-1"
NONCE = f"{os.getpid()}-{int(time.time())}"
BUILDER = f"mrw-r13v-oci-smoke-{NONCE}"
TAG = f"mrw-r13v-oci-smoke.local/subject:{NONCE}"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(label: str, command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    write_json(EVIDENCE / f"{label}.command.json", {"argv": command, "cwd": str(cwd) if cwd else None})
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    elapsed = round(time.monotonic() - started, 3)
    (EVIDENCE / f"{label}.log").write_text(result.stdout, encoding="utf-8")
    write_json(EVIDENCE / f"{label}.exit.json", {"elapsed_seconds": elapsed, "exit_code": result.returncode})
    return result


def blob_json(tf: tarfile.TarFile, digest: str) -> dict[str, Any]:
    algorithm, value = digest.split(":", 1)
    if algorithm != "sha256":
        raise RuntimeError(f"unsupported digest: {digest}")
    member = tf.extractfile(f"blobs/sha256/{value}")
    if member is None:
        raise RuntimeError(f"missing blob: {digest}")
    data = member.read()
    if hashlib.sha256(data).hexdigest() != value:
        raise RuntimeError(f"blob digest mismatch: {digest}")
    return json.loads(data)


def inspect_oci(archive: Path, layout: Path) -> dict[str, Any]:
    with tarfile.open(archive, "r") as tf:
        index_member = tf.extractfile("index.json")
        if index_member is None:
            raise RuntimeError("OCI archive has no index.json")
        index = json.loads(index_member.read())
        root_descriptors = index.get("manifests", [])
        expanded_descriptors: list[dict[str, Any]] = []
        root_index_digests: list[str] = []
        for descriptor in root_descriptors:
            if descriptor.get("mediaType") == "application/vnd.oci.image.index.v1+json":
                root_index_digests.append(descriptor["digest"])
                nested_index = blob_json(tf, descriptor["digest"])
                expanded_descriptors.extend(nested_index.get("manifests", []))
            else:
                expanded_descriptors.append(descriptor)
        image_descriptors: list[dict[str, Any]] = []
        attestation_descriptors: list[dict[str, Any]] = []
        for descriptor in expanded_descriptors:
            annotations = descriptor.get("annotations") or {}
            if annotations.get("vnd.docker.reference.type") == "attestation-manifest":
                attestation_descriptors.append(descriptor)
            else:
                image_descriptors.append(descriptor)
        if len(image_descriptors) != 1:
            raise RuntimeError(f"expected one non-attestation image descriptor, found {len(image_descriptors)}")
        image_digest = image_descriptors[0]["digest"]
        image_hex = image_digest.split(":", 1)[1]
        image_manifest = blob_json(tf, image_digest)
        image_config = blob_json(tf, image_manifest["config"]["digest"])
        platform = {
            "os": image_config.get("os"),
            "architecture": image_config.get("architecture"),
        }
        if platform != {"os": "linux", "architecture": "amd64"}:
            raise RuntimeError(f"unexpected image config platform: {platform}")
        statements: dict[str, dict[str, Any]] = {}
        bindings: list[dict[str, Any]] = []
        for descriptor in attestation_descriptors:
            annotations = descriptor.get("annotations") or {}
            manifest = blob_json(tf, descriptor["digest"])
            bindings.append(
                {
                    "descriptor_digest": descriptor["digest"],
                    "descriptor_subject_digest": annotations.get("vnd.docker.reference.digest"),
                    "descriptor_subject_matches_image": annotations.get("vnd.docker.reference.digest") == image_digest,
                }
            )
            for layer in manifest.get("layers", []):
                statement = blob_json(tf, layer["digest"])
                predicate_type = statement.get("predicateType", "")
                if predicate_type == "https://slsa.dev/provenance/v1":
                    kind = "provenance"
                elif predicate_type == "https://spdx.dev/Document":
                    kind = "sbom"
                else:
                    kind = f"other-{len(statements)}"
                statements[kind] = statement
                write_json(EVIDENCE / f"{kind}.intoto.json", statement)
        statement_results: dict[str, Any] = {}
        for kind in ("provenance", "sbom"):
            statement = statements.get(kind)
            subjects = statement.get("subject", []) if statement else []
            digest_matches = [
                subject
                for subject in subjects
                if (subject.get("digest") or {}).get("sha256") == image_hex
            ]
            statement_results[kind] = {
                "present": statement is not None,
                "predicate_type": statement.get("predicateType") if statement else None,
                "subjects": subjects,
                "subject_contains_image_manifest_digest": bool(digest_matches),
            }
        tf.extractall(layout, filter="data")
    return {
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "explicit_tag": TAG,
        "oci_root_index_digests": root_index_digests,
        "image_manifest_digest": image_digest,
        "image_config_digest": image_manifest["config"]["digest"],
        "platform": platform,
        "image_descriptor_annotations": image_descriptors[0].get("annotations") or {},
        "attestation_descriptor_count": len(attestation_descriptors),
        "attestation_descriptor_bindings": bindings,
        "statements": statement_results,
    }


def main() -> int:
    temporary_root = Path(tempfile.mkdtemp(prefix="mrw-r13v-oci-smoke-"))
    context = temporary_root / "context"
    context.mkdir()
    (context / "Dockerfile").write_text(
        "FROM scratch\n"
        "ARG SOURCE_DATE_EPOCH=0\n"
        "LABEL org.opencontainers.image.title=mrw-r13v-oci-subject-smoke\n"
        "COPY payload.txt /payload.txt\n",
        encoding="utf-8",
    )
    (context / "payload.txt").write_text("offline tagged OCI smoke\n", encoding="utf-8")
    combined_archive = temporary_root / "tagged-provenance-sbom.oci.tar"
    fallback_archive = temporary_root / "tagged-provenance.oci.tar"
    layout = temporary_root / "layout"
    selected_archive: Path | None = None
    selected_build = None
    inspection: dict[str, Any] | None = None
    trivy_summary: dict[str, Any] = {
        "command_executed": False,
        "exit_code": None,
        "report_present": False,
        "report_bytes": 0,
        "report_json_valid": False,
        "input_consumed": False,
    }
    cleanup: dict[str, Any] = {"docker_prune_run": False}
    fatal_error: str | None = None
    versions: dict[str, Any] = {}
    try:
        for label, command in (
            ("docker-version", ["docker", "version", "--format", "{{json .}}"]),
            ("buildx-version", ["docker", "buildx", "version"]),
            ("trivy-version", ["trivy", "--version"]),
            ("buildkit-image-inspect", ["docker", "image", "inspect", BUILD_KIT_IMAGE, "--format", "{{.Id}}"]),
        ):
            result = run(label, command)
            versions[label] = {"exit_code": result.returncode, "output": result.stdout.strip()}
        write_json(EVIDENCE / "versions.json", versions)
        if any(item["exit_code"] != 0 for item in versions.values()):
            raise RuntimeError("required local runtime is unavailable")
        if subprocess.run(
            ["docker", "image", "inspect", TAG], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            raise RuntimeError(f"unique smoke tag unexpectedly existed before run: {TAG}")
        create = run(
            "builder-create",
            [
                "docker",
                "buildx",
                "create",
                "--name",
                BUILDER,
                "--driver",
                "docker-container",
                "--driver-opt",
                "network=none",
                "--driver-opt",
                f"image={BUILD_KIT_IMAGE}",
            ],
        )
        if create.returncode != 0:
            raise RuntimeError("offline builder creation failed")
        bootstrap = run("builder-bootstrap", ["docker", "buildx", "inspect", "--bootstrap", BUILDER])
        if bootstrap.returncode != 0:
            raise RuntimeError("offline builder bootstrap failed")
        common = [
            "docker",
            "buildx",
            "build",
            "--builder",
            BUILDER,
            "--platform",
            "linux/amd64",
            "--network",
            "none",
            "--no-cache",
            "--progress",
            "plain",
            "--tag",
            TAG,
            "--build-arg",
            "SOURCE_DATE_EPOCH=0",
        ]
        combined = run(
            "tagged-provenance-sbom-build",
            common
            + [
                "--provenance=mode=max",
                "--sbom=true",
                "--output",
                f"type=oci,dest={combined_archive},rewrite-timestamp=true",
                str(context),
            ],
        )
        if combined.returncode == 0 and combined_archive.is_file():
            selected_archive = combined_archive
            selected_build = "tagged-provenance-sbom-build"
        else:
            fallback = run(
                "tagged-provenance-only-build",
                common
                + [
                    "--provenance=mode=max",
                    "--sbom=false",
                    "--output",
                    f"type=oci,dest={fallback_archive},rewrite-timestamp=true",
                    str(context),
                ],
            )
            if fallback.returncode == 0 and fallback_archive.is_file():
                selected_archive = fallback_archive
                selected_build = "tagged-provenance-only-build"
            else:
                raise RuntimeError("both combined and provenance-only offline smoke builds failed")
        layout.mkdir()
        inspection = inspect_oci(selected_archive, layout)
        inspection["selected_build"] = selected_build
        inspection["combined_build_exit_code"] = combined.returncode
        write_json(EVIDENCE / "oci-inspection.json", inspection)
        report = EVIDENCE / "trivy-report.json"
        trivy = run(
            "trivy-oci-layout-directory",
            [
                "trivy",
                "image",
                "--input",
                str(layout),
                "--format",
                "json",
                "--output",
                str(report),
                "--skip-db-update",
                "--scanners",
                "vuln",
                "--exit-code",
                "0",
                "--no-progress",
            ],
        )
        trivy_summary["command_executed"] = True
        trivy_summary["exit_code"] = trivy.returncode
        if report.is_file():
            trivy_summary["report_present"] = True
            trivy_summary["report_bytes"] = report.stat().st_size
            try:
                parsed_report = json.loads(report.read_text(encoding="utf-8"))
                trivy_summary["report_json_valid"] = isinstance(parsed_report, dict)
                trivy_summary["artifact_type"] = parsed_report.get("ArtifactType")
                trivy_summary["result_count"] = len(parsed_report.get("Results") or [])
            except (OSError, json.JSONDecodeError) as error:
                trivy_summary["report_parse_error"] = f"{type(error).__name__}: {error}"
        trivy_summary["input_consumed"] = bool(
            trivy.returncode == 0
            and trivy_summary["report_present"]
            and trivy_summary["report_bytes"] > 0
            and trivy_summary["report_json_valid"]
        )
        write_json(EVIDENCE / "trivy-summary.json", trivy_summary)
    except Exception as error:
        fatal_error = f"{type(error).__name__}: {error}"
    finally:
        builder_cleanup = run("builder-cleanup", ["docker", "buildx", "rm", "-f", BUILDER])
        tag_cleanup = run("tag-cleanup", ["docker", "image", "rm", "-f", TAG])
        shutil.rmtree(temporary_root, ignore_errors=True)
        builder_names = subprocess.run(
            ["docker", "buildx", "ls", "--format", "{{.Name}}"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ).stdout.splitlines()
        image_names = subprocess.run(
            ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.splitlines()
        cleanup.update(
            {
                "builder_cleanup_exit_code": builder_cleanup.returncode,
                "tag_cleanup_exit_code": tag_cleanup.returncode,
                "builder_residue": BUILDER in builder_names,
                "tag_or_image_residue": TAG in image_names,
                "temporary_root_residue": temporary_root.exists(),
                "oci_archive_residue": combined_archive.exists() or fallback_archive.exists(),
                "oci_layout_residue": layout.exists(),
            }
        )
        write_json(EVIDENCE / "cleanup-residue.json", cleanup)
    provenance_pass = bool(
        inspection and inspection["statements"]["provenance"]["subject_contains_image_manifest_digest"]
    )
    sbom_pass = bool(inspection and inspection["statements"]["sbom"]["subject_contains_image_manifest_digest"])
    cleanup_pass = not any(
        cleanup.get(key, True)
        for key in (
            "builder_residue",
            "tag_or_image_residue",
            "temporary_root_residue",
            "oci_archive_residue",
            "oci_layout_residue",
        )
    )
    overall_pass = provenance_pass and sbom_pass and trivy_summary["input_consumed"] and cleanup_pass
    summary = {
        "schema": "mrw.stage3.r13v.oci-trivy-smoke.v1",
        "status": "PASS" if overall_pass else "FAIL",
        "authoritative": False,
        "authority_ceiling": "LOCAL_UNSIGNED_TASK_OWNED_SMOKE_NOT_RELEASE_AUTHORITY",
        "network_contract": {
            "dockerfile_base": "scratch",
            "dockerfile_run_instructions": 0,
            "build_network": "none",
            "builder_network": "none",
            "buildkit_image_preexisting_locally": versions.get("buildkit-image-inspect", {}).get("exit_code") == 0,
        },
        "explicit_tag": TAG,
        "selected_build": selected_build,
        "subject_binding": {
            "provenance_pass": provenance_pass,
            "sbom_pass": sbom_pass,
            "pass": provenance_pass and sbom_pass,
            "image_manifest_digest": inspection.get("image_manifest_digest") if inspection else None,
        },
        "trivy_oci_layout_directory": trivy_summary,
        "cleanup": cleanup,
        "cleanup_pass": cleanup_pass,
        "fatal_error": fatal_error,
        "final_reconciliation_included": {
            "path": str(EVIDENCE.parent / "backend-migration-amd64-final" / "result.json"),
            "exists": (EVIDENCE.parent / "backend-migration-amd64-final" / "result.json").is_file(),
        },
        "next_action": (
            "Return smoke PASS to supervisor; do not rebuild product images until separately authorized."
            if overall_pass
            else "Freeze the failed smoke fact; do not rebuild product images."
        ),
    }
    write_json(EVIDENCE / "summary.json", summary)
    checksum_lines = []
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(EVIDENCE)}")
    (EVIDENCE / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "summary": str(EVIDENCE / "summary.json")}, sort_keys=True))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
