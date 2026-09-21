#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import time


CANDIDATE = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13r/candidate")
REPLAY = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13r/replay")
EVIDENCE = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13r/evidence")
OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13r/artifacts")
R13Q = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13q/candidate")
PLATFORM = "linux/amd64"
BUILDKIT_IMAGE = "moby/buildkit@sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8"
ROLES = {
    "backend": (CANDIDATE, "main/backend/Dockerfile", "backend-runtime"),
    "migration-runner": (CANDIDATE, "main/backend/Dockerfile", "migration-runner"),
    "frontend": (CANDIDATE / "main/frontend-modern", "Dockerfile", "frontend-runtime"),
}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MIN_FREE_BYTES = 4 * 1024**3


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str, cwd: Path = CANDIDATE) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def command_output(argv: list[str]) -> dict:
    completed = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"argv": argv, "exit_code": completed.returncode, "output": completed.stdout}


def run_logged(name: str, argv: list[str], cwd: Path) -> int:
    write_json(OUT / f"{name}.command.json", {"argv": argv, "cwd": str(cwd)})
    started = time.time()
    with (OUT / f"{name}.log").open("w") as log:
        completed = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    write_json(
        OUT / f"{name}.exit.json",
        {"exit_code": completed.returncode, "elapsed_seconds": round(time.time() - started, 3)},
    )
    print(f"{name}: exit={completed.returncode}", flush=True)
    return completed.returncode


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


def inspect_archive(path: Path, phase: str, role: str) -> dict:
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
            images = [
                descriptor
                for descriptor in root["manifests"]
                if descriptor.get("platform", {}).get("os") == "linux"
                and descriptor.get("platform", {}).get("architecture") == "amd64"
                and descriptor.get("annotations", {}).get("vnd.docker.reference.type") != "attestation-manifest"
            ]
            attestations = [descriptor for descriptor in root["manifests"] if descriptor not in images]
            if len(images) != 1:
                raise ValueError(f"expected one linux/amd64 image descriptor, got {len(images)}")
            image_digest = images[0]["digest"]
            manifest = json.loads(blob(bundle, image_digest))
        else:
            image_digest = root_digest
            manifest = root
            attestations = []

        config_descriptor = manifest["config"]
        config = json.loads(blob(bundle, config_descriptor["digest"]))
        layers = manifest.get("layers") or []
        for descriptor in layers:
            blob(bundle, descriptor["digest"])

        statements = []
        for descriptor in attestations:
            attestation_manifest = json.loads(blob(bundle, descriptor["digest"]))
            for layer in attestation_manifest.get("layers") or []:
                payload = blob(bundle, layer["digest"])
                if "gzip" in str(layer.get("mediaType", "")):
                    payload = gzip.decompress(payload)
                statements.append(json.loads(payload))

        result = {
            "phase": phase,
            "role": role,
            "platform": f"{config.get('os')}/{config.get('architecture')}",
            "oci_root_digest": root_digest,
            "image_manifest_digest": image_digest,
            "image_config_digest": config_descriptor["digest"],
            "image_layer_digests": [descriptor["digest"] for descriptor in layers],
            "archive_sha256": sha256(path),
            "archive_bytes": path.stat().st_size,
            "attestation_manifest_count": len(attestations),
            "all_referenced_blobs_validated": True,
            "runtime_config": {
                key: config.get("config", {}).get(key)
                for key in ("Entrypoint", "Cmd", "Env", "WorkingDir", "User", "ExposedPorts", "Healthcheck")
            },
        }
        if phase == "canonical":
            provenance = [
                statement
                for statement in statements
                if str(statement.get("predicateType", "")).startswith("https://slsa.dev/provenance/")
            ]
            sbom = [
                statement
                for statement in statements
                if str(statement.get("predicateType", "")).startswith("https://spdx.dev/Document")
            ]
            result["slsa_provenance_count"] = len(provenance)
            result["spdx_sbom_count"] = len(sbom)
            if len(provenance) == 1:
                provenance_path = OUT / "canonical" / f"{role}.provenance.intoto.json"
                write_json(provenance_path, provenance[0])
                result["provenance_sha256"] = sha256(provenance_path)
            if len(sbom) == 1:
                sbom_path = OUT / "canonical" / f"{role}.sbom.spdx.intoto.json"
                write_json(sbom_path, sbom[0])
                result["sbom_sha256"] = sha256(sbom_path)
        write_json(OUT / phase / f"{role}.digest-inspection.json", result)
        return result


def normalized(name: str) -> str:
    value = str(PurePosixPath("/" + name.lstrip("./")))
    return value if value != "/." else "/"


def remove_inventory_path(inventory: dict[str, dict], path: str, descendants_only: bool = False) -> None:
    prefix = path.rstrip("/") + "/"
    for existing in list(inventory):
        if existing.startswith(prefix) or (not descendants_only and existing == path):
            del inventory[existing]


def archive_inventory(path: Path) -> tuple[dict[str, dict], dict]:
    final: dict[str, dict] = {}
    with tarfile.open(path, "r") as bundle:
        index = json.load(bundle.extractfile("index.json"))
        root = json.loads(blob(bundle, index["manifests"][0]["digest"]))
        if "manifests" in root:
            descriptors = [
                descriptor
                for descriptor in root["manifests"]
                if descriptor.get("platform", {}).get("os") == "linux"
                and descriptor.get("platform", {}).get("architecture") == "amd64"
                and descriptor.get("annotations", {}).get("vnd.docker.reference.type") != "attestation-manifest"
            ]
            manifest = json.loads(blob(bundle, descriptors[0]["digest"]))
        else:
            manifest = root
        config = json.loads(blob(bundle, manifest["config"]["digest"]))
        for descriptor in manifest.get("layers") or []:
            layer_handle = bundle.extractfile(f"blobs/sha256/{descriptor['digest'].removeprefix('sha256:')}")
            if layer_handle is None:
                raise ValueError(f"missing layer {descriptor['digest']}")
            with tarfile.open(fileobj=layer_handle, mode="r|*") as layer:
                for member in layer:
                    path_name = normalized(member.name)
                    basename = PurePosixPath(path_name).name
                    parent = str(PurePosixPath(path_name).parent)
                    if basename == ".wh..wh..opq":
                        remove_inventory_path(final, parent, descendants_only=True)
                        continue
                    if basename.startswith(".wh."):
                        remove_inventory_path(final, str(PurePosixPath(parent) / basename.removeprefix(".wh.")))
                        continue
                    entry = {
                        "type": (
                            "file" if member.isfile() else "directory" if member.isdir() else
                            "symlink" if member.issym() else "hardlink" if member.islnk() else "other"
                        ),
                        "mode": member.mode,
                        "uid": member.uid,
                        "gid": member.gid,
                        "mtime": member.mtime,
                        "size": member.size,
                    }
                    if member.isfile():
                        handle = layer.extractfile(member)
                        if handle is None:
                            raise ValueError(f"cannot read file {path_name}")
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                        entry["content_sha256"] = digest.hexdigest()
                    elif member.issym() or member.islnk():
                        entry["link_target"] = member.linkname
                    final[path_name] = entry
    return final, config


def rootfs_difference(role: str, canonical: Path, rebuild: Path) -> dict:
    left, left_config = archive_inventory(canonical)
    right, right_config = archive_inventory(rebuild)
    differences = []
    for path in sorted(set(left) | set(right)):
        a = left.get(path)
        b = right.get(path)
        if a == b:
            continue
        if a is None:
            kind = "added"
        elif b is None:
            kind = "removed"
        elif a.get("content_sha256") != b.get("content_sha256") or a.get("link_target") != b.get("link_target"):
            kind = "content_changed"
        else:
            changed = sorted(key for key in set(a) | set(b) if a.get(key) != b.get(key))
            kind = "timestamp_only" if changed == ["mtime"] else "metadata_changed"
        differences.append(
            {
                "path": path,
                "kind": kind,
                "canonical_content_sha256": (a or {}).get("content_sha256"),
                "rebuild_content_sha256": (b or {}).get("content_sha256"),
                "canonical": a,
                "rebuild": b,
            }
        )
    result = {
        "role": role,
        "canonical_paths": len(left),
        "rebuild_paths": len(right),
        "difference_count": len(differences),
        "runtime_config_equal": left_config.get("config") == right_config.get("config"),
        "differences": differences,
    }
    write_json(OUT / f"{role}.rootfs-difference.json", result)
    return result


def parse_trivy(path: Path, exit_code: int) -> dict:
    if not path.is_file():
        return {"exit_code": exit_code, "report_present": False}
    report = json.loads(path.read_text())
    counts = {"HIGH": 0, "CRITICAL": 0}
    observations = []
    for result in report.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = vulnerability.get("Severity")
            if severity in counts:
                counts[severity] += 1
                observations.append(
                    {
                        "target": result.get("Target"),
                        "class": result.get("Class"),
                        "type": result.get("Type"),
                        "vulnerability_id": vulnerability.get("VulnerabilityID"),
                        "package": vulnerability.get("PkgName"),
                        "installed_version": vulnerability.get("InstalledVersion"),
                        "fixed_version": vulnerability.get("FixedVersion"),
                        "severity": severity,
                    }
                )
    return {
        "exit_code": exit_code,
        "threshold": "HIGH,CRITICAL",
        "vulnerability_types": "os,library",
        "counts": counts,
        "observation_count": len(observations),
        "gate_status": "PASS" if exit_code == 0 else "FAIL",
        "report_sha256": sha256(path),
        "reachability_exploitability": "NOT_ASSESSED_BY_TRIVY",
    }


def build_role(role: str) -> dict:
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

    context, dockerfile, target = ROLES[role]
    token = f"{os.getpid()}-{int(time.time())}"
    builders = {
        "canonical": f"mrw-r13r-amd64-{role}-a-{token}",
        "rebuild": f"mrw-r13r-amd64-{role}-b-{token}",
    }
    archives = {
        "canonical": OUT / "canonical" / f"{role}.oci.tar",
        "rebuild": OUT / "rebuild" / f"{role}.oci.tar",
    }
    created: list[str] = []
    cleanup_events = []
    result: dict = {
        "role": role,
        "platform": PLATFORM,
        "free_bytes_before": free_before,
        "builders": builders,
        "buildkit_image": BUILDKIT_IMAGE,
    }
    try:
        for phase in ("canonical", "rebuild"):
            builder = builders[phase]
            code = run_logged(
                f"{role}-{phase}-builder-create",
                ["docker", "buildx", "create", "--driver", "docker-container", "--driver-opt", f"image={BUILDKIT_IMAGE}", "--name", builder],
                OUT,
            )
            if code != 0:
                raise RuntimeError(f"{phase} builder creation failed with exit {code}")
            created.append(builder)
            code = run_logged(
                f"{role}-{phase}-builder-bootstrap",
                ["docker", "buildx", "inspect", "--bootstrap", builder],
                OUT,
            )
            if code != 0:
                raise RuntimeError(f"{phase} builder bootstrap failed with exit {code}")

        for phase in ("canonical", "rebuild"):
            metadata = OUT / phase / f"{role}.build-metadata.json"
            argv = [
                "docker", "buildx", "build", "--builder", builders[phase], "--progress", "plain", "--no-cache",
                "--platform", PLATFORM,
                f"--provenance={'true' if phase == 'canonical' else 'false'}",
                f"--sbom={'true' if phase == 'canonical' else 'false'}",
                "--build-arg", "SOURCE_DATE_EPOCH=0",
                "--file", dockerfile,
                "--target", target,
                "--metadata-file", str(metadata),
                "--output", f"type=oci,dest={archives[phase]},rewrite-timestamp=true",
                ".",
            ]
            code = run_logged(f"{role}-{phase}-build", argv, context)
            if code != 0:
                raise RuntimeError(f"{phase} build failed with exit {code}")

        inspections = {
            phase: inspect_archive(archives[phase], phase, role)
            for phase in ("canonical", "rebuild")
        }
        canonical = inspections["canonical"]
        rebuild = inspections["rebuild"]
        manifest_equal = canonical["image_manifest_digest"] == rebuild["image_manifest_digest"]
        config_equal = canonical["image_config_digest"] == rebuild["image_config_digest"]
        layers_equal = canonical["image_layer_digests"] == rebuild["image_layer_digests"]
        comparison = {
            "role": role,
            "platform": PLATFORM,
            "canonical_image_manifest_digest": canonical["image_manifest_digest"],
            "rebuild_image_manifest_digest": rebuild["image_manifest_digest"],
            "image_manifest_equal": manifest_equal,
            "image_config_equal": config_equal,
            "image_layers_equal_in_order": layers_equal,
            "status": "PASS_EXACT_IMAGE" if manifest_equal and config_equal and layers_equal else "MISMATCH",
            "rootfs_comparison": "NOT_NEEDED_EXACT_IMAGE_MANIFEST_MATCH" if manifest_equal else "PERFORMED",
            "runtime_scope": (
                "No separate runtime-equivalence smoke was needed: equal OCI image-manifest digest binds the identical config and ordered layer descriptors. "
                "This is build reproducibility evidence, not a full dependency-backed application runtime test."
                if manifest_equal else
                "Image mismatch requires bounded rootfs comparison; no claim of runtime equivalence is made by this lane."
            ),
        }
        if not manifest_equal:
            comparison["rootfs_difference"] = rootfs_difference(role, archives["canonical"], archives["rebuild"])
        write_json(OUT / f"{role}.reproducibility.json", comparison)

        trivy_report = OUT / "canonical" / f"{role}.trivy.json"
        trivy_code = run_logged(
            f"{role}-canonical-trivy",
            [
                "trivy", "image", "--input", str(archives["canonical"]), "--exit-code", "1",
                "--severity", "HIGH,CRITICAL", "--vuln-type", "os,library", "--format", "json",
                "--output", str(trivy_report),
            ],
            OUT,
        )
        scan = parse_trivy(trivy_report, trivy_code)
        write_json(OUT / "canonical" / f"{role}.trivy.summary.json", scan)

        result.update(
            {
                "status": comparison["status"] if comparison["status"] != "PASS_EXACT_IMAGE" else (
                    "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_FAIL" if trivy_code != 0 else "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_PASS"
                ),
                "inspections": inspections,
                "comparison": comparison,
                "trivy": scan,
                "attestation": {
                    "kind": "LOCAL_UNSIGNED_BUILDKIT_ATTESTATIONS",
                    "signature_present": False,
                    "registry_or_transparency_log_publication": False,
                    "provenance_statement_count": canonical.get("slsa_provenance_count"),
                    "sbom_statement_count": canonical.get("spdx_sbom_count"),
                },
            }
        )
    except Exception as exc:
        result["status"] = "FAILED_OR_INCOMPLETE"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for builder in reversed(created):
            code = run_logged(
                f"{role}-cleanup-builder-{len(cleanup_events) + 1}",
                ["docker", "buildx", "rm", builder],
                OUT,
            )
            cleanup_events.append({"builder": builder, "exit_code": code})
        for phase, archive in archives.items():
            if archive.exists():
                archive_sha = sha256(archive)
                archive_bytes = archive.stat().st_size
                archive.unlink()
                cleanup_events.append(
                    {
                        "archive": str(archive),
                        "phase": phase,
                        "sha256_before_removal": archive_sha,
                        "bytes_reclaimed": archive_bytes,
                        "removed": True,
                        "reason": "Digest/config/layer/SBOM/provenance/Trivy and any required rootfs evidence already extracted; retain compact final evidence under constrained disk budget.",
                    }
                )
        residue = command_output(["docker", "buildx", "ls"])
        residue_names = [name for name in builders.values() if name in residue["output"]]
        result["cleanup"] = {
            "events": cleanup_events,
            "builder_residue": residue_names,
            "temporary_oci_archives_present": [str(path) for path in archives.values() if path.exists()],
            "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
        }
        write_json(OUT / f"{role}.summary.json", result)
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "canonical").mkdir(exist_ok=True)
    (OUT / "rebuild").mkdir(exist_ok=True)
    commit, tree = git("rev-parse", "HEAD", "HEAD^{tree}").splitlines()
    candidate_status_before = git("status", "--porcelain=v1")
    role_trees = {
        "main/backend": git("rev-parse", "HEAD:main/backend"),
        "src": git("rev-parse", "HEAD:src"),
        "main/frontend-modern": git("rev-parse", "HEAD:main/frontend-modern"),
    }
    r13q_frontend_tree = git("rev-parse", "HEAD:main/frontend-modern", cwd=R13Q)
    identity = {
        "schema": "mrw.stage3.r13r.amd64-artifact-input.v1",
        "authoritative": False,
        "candidate": {"path": str(CANDIDATE), "commit": commit, "tree": tree, "clean": candidate_status_before == ""},
        "replay": {"path": str(REPLAY), "binding_evidence": str(EVIDENCE / "replay-r1-candidate-identity.r13r.json")},
        "candidate_manifest": {
            "path": str(EVIDENCE / "candidate-manifest.v5.json"),
            "sha256": sha256(EVIDENCE / "candidate-manifest.v5.json"),
        },
        "role_input_trees": role_trees,
        "frontend_r13q_reuse_check": {
            "r13q_tree": r13q_frontend_tree,
            "r13r_tree": role_trees["main/frontend-modern"],
            "equal": r13q_frontend_tree == role_trees["main/frontend-modern"],
            "reuse_scope": "Input identity record only; both r13r-bound amd64 builds and attestations are newly executed.",
        },
        "platform": PLATFORM,
        "authority_ceiling": "LOCAL_UNSIGNED_EVIDENCE_NOT_RELEASE_AUTHORITY",
    }
    write_json(OUT / "identity.json", identity)

    environment = {
        "schema": "mrw.stage3.r13r.amd64-build-environment.v1",
        "started_epoch": int(time.time()),
        "free_bytes_before": shutil.disk_usage("/System/Volumes/Data").free,
        "minimum_role_start_free_bytes": MIN_FREE_BYTES,
        "disk_strategy": "One role at a time; create two independent task-owned builders, inspect and scan, remove builders/caches and temporary OCI archives, retain compact evidence.",
        "docker_version": command_output(["docker", "version"]),
        "buildx_version": command_output(["docker", "buildx", "version"]),
        "trivy_version": command_output(["trivy", "version"]),
        "syft_version": command_output(["syft", "version"]),
        "buildkit_image": BUILDKIT_IMAGE,
        "preexisting_builders": command_output(["docker", "buildx", "ls"]),
        "preexisting_containers": command_output(["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}"]),
        "preservation": "No preexisting images, containers, volumes, builders, or caches are removed. ops-scrapyd is outside this lane and is preserved.",
    }
    write_json(OUT / "environment.pre.json", environment)

    roles = {}
    for role in ("backend", "migration-runner", "frontend"):
        print(f"ROLE_START {role} free={shutil.disk_usage('/System/Volumes/Data').free}", flush=True)
        roles[role] = build_role(role)
        print(f"ROLE_END {role} status={roles[role].get('status')}", flush=True)

    candidate_status_after = git("status", "--porcelain=v1")
    summary = {
        "schema": "mrw.stage3.r13r.local-amd64-artifact-evidence.v1",
        "authoritative": False,
        "authority_ceiling": "LOCAL_UNSIGNED_EVIDENCE_NOT_RELEASE_AUTHORITY",
        "candidate": {"commit": commit, "tree": tree, "clean_before": candidate_status_before == "", "clean_after": candidate_status_after == ""},
        "candidate_manifest_sha256": identity["candidate_manifest"]["sha256"],
        "platform": PLATFORM,
        "roles": roles,
        "scope": {
            "builds": "Two independent task-owned docker-container BuildKit instances per role; --no-cache; linux/amd64; local OCI output only.",
            "canonical": "Build A embeds one expected SLSA provenance statement and one expected SPDX SBOM statement; both are local and unsigned.",
            "rebuild": "Build B disables attestations so the image manifest/config/layers can be compared without an attestation-root difference.",
            "security": "Trivy 0.74.0 HIGH/CRITICAL os,library threshold; reachability and exploitability are not assessed.",
            "runtime": "If image manifests are exact, separate A/B runtime-equivalence testing is unnecessary because identical image manifests bind identical config and ordered layers. This lane does not claim dependency-backed application runtime success.",
            "excluded": ["registry push", "registry publication", "signing", "transparency log", "deployment", "remote dispatch", "authority transfer"],
        },
        "status": (
            "PASS_EXACT_REPRODUCIBILITY_SECURITY_GATE_FAILED"
            if all(str(record.get("status", "")).startswith("PASS_EXACT_IMAGE") for record in roles.values())
            and any(record.get("trivy", {}).get("gate_status") == "FAIL" for record in roles.values())
            else "PASS_EXACT_REPRODUCIBILITY_SECURITY_GATE_PASSED"
            if all(record.get("status") == "PASS_EXACT_IMAGE_SECURITY_THRESHOLD_PASS" for record in roles.values())
            else "FAILED_OR_INCOMPLETE"
        ),
        "completed_epoch": int(time.time()),
        "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
    }
    write_json(OUT / "summary.json", summary)

    members = sorted(
        path for path in OUT.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.endswith(".oci.tar")
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(OUT)}\n" for path in members)
    )
    print(f"COMPLETE status={summary['status']} sha256sums={sha256(OUT / 'SHA256SUMS')}", flush=True)
    return 0 if summary["status"].startswith("PASS_EXACT_REPRODUCIBILITY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
