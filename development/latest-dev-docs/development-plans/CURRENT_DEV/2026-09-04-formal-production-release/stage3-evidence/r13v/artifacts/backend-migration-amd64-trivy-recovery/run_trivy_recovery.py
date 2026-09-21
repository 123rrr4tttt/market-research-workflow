#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil


BASE_RUNNER = Path(
    "/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/"
    "development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
    "stage3-evidence/r13v/artifacts/backend-migration-amd64-candidate-replay/"
    "run_r13v_backend_migration.py"
)
AB_OUT = Path(
    "/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/"
    "development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
    "stage3-evidence/r13v/artifacts/backend-migration-amd64-candidate-replay-retry4"
)
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r13v_base_runner", BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load base runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.OUT = OUT

EXPECTED = {
    role: json.loads((AB_OUT / f"{role}.reproducibility.json").read_text())
    for role in ("backend", "migration-runner")
}
TARGETS = {
    "backend": "backend-runtime",
    "migration-runner": "migration-runner",
}


def is_network_failure(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(errors="replace")
    return any(
        marker in text
        for marker in (
            "502  Bad Gateway",
            "failed to authorize:",
            "failed to do request:",
            "unexpected EOF",
            ": EOF",
        )
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scan-rebuild").mkdir(exist_ok=True)
    before_candidate = runner.git_snapshot(runner.CANDIDATE)
    before_replay = runner.git_snapshot(runner.REPLAY)
    token = str(int(__import__("time").time()))
    results: dict[str, dict] = {}

    for role, target in TARGETS.items():
        expected = EXPECTED[role]
        builder = f"mrw-r13v-trivy-{role}-{token}"
        archive = OUT / "scan-rebuild" / f"{role}.oci.tar"
        tag = f"mrw-r13v-trivy-{role}:local"
        result: dict = {
            "role": role,
            "target": target,
            "expected_image_manifest_digest": expected["candidate_image_manifest_digest"],
            "expected_image_config_digest": expected["candidate_image_config_digest"],
            "build_contract": (
                "candidate source, --no-cache, linux/amd64, provenance=false, sbom=false, "
                "SOURCE_DATE_EPOCH=0, OCI rewrite-timestamp=true"
            ),
            "fresh_scan_tag": tag,
            "free_bytes_before": shutil.disk_usage("/System/Volumes/Data").free,
        }
        cleanup: list[dict] = []
        builder_created = False
        image_preexisting = False
        loaded_id: str | None = None
        try:
            if result["free_bytes_before"] < runner.MIN_FREE_BYTES:
                raise RuntimeError("INSUFFICIENT_SAFE_DISK_BUDGET")
            attempts = []
            for attempt_index in range(2):
                suffix = "" if attempt_index == 0 else "-network-retry1"
                create_code = runner.run_logged(
                    f"{role}{suffix}-builder-create",
                    [
                        "docker",
                        "buildx",
                        "create",
                        "--driver",
                        "docker-container",
                        "--driver-opt",
                        f"image={runner.BUILDKIT_IMAGE}",
                        "--name",
                        builder,
                    ],
                    OUT,
                )
                if create_code != 0:
                    raise RuntimeError(f"builder create exit {create_code}")
                builder_created = True
                bootstrap_code = runner.run_logged(
                    f"{role}{suffix}-builder-bootstrap",
                    ["docker", "buildx", "inspect", "--bootstrap", builder],
                    OUT,
                )
                if bootstrap_code != 0:
                    raise RuntimeError(f"builder bootstrap exit {bootstrap_code}")
                if shutil.disk_usage("/System/Volumes/Data").free < runner.MIN_FREE_BYTES:
                    raise RuntimeError("INSUFFICIENT_SAFE_DISK_BUDGET before build")
                metadata = OUT / "scan-rebuild" / f"{role}{suffix}.build-metadata.json"
                argv = [
                    "docker",
                    "buildx",
                    "build",
                    "--builder",
                    builder,
                    "--progress",
                    "plain",
                    "--no-cache",
                    "--platform",
                    runner.PLATFORM,
                    "--provenance=false",
                    "--sbom=false",
                    "--build-arg",
                    "SOURCE_DATE_EPOCH=0",
                    "--file",
                    "main/backend/Dockerfile",
                    "--target",
                    target,
                    "--metadata-file",
                    str(metadata),
                    "--output",
                    f"type=oci,dest={archive},rewrite-timestamp=true",
                    ".",
                ]
                build_code = runner.run_logged(
                    f"{role}{suffix}-build", argv, runner.CANDIDATE
                )
                attempts.append({"attempt": attempt_index + 1, "exit_code": build_code})
                if build_code == 0:
                    break
                network = is_network_failure(OUT / f"{role}{suffix}-build.log")
                remove_code = runner.run_logged(
                    f"{role}{suffix}-failed-builder-cleanup",
                    ["docker", "buildx", "rm", builder],
                    OUT,
                )
                cleanup.append(
                    {
                        "kind": "failed_builder",
                        "attempt": attempt_index + 1,
                        "exit_code": remove_code,
                    }
                )
                builder_created = False
                if archive.exists():
                    archive.unlink()
                if not network or attempt_index == 1:
                    classification = "NETWORK_BLOCKED" if network else "BUILD_FAILED"
                    raise RuntimeError(f"{classification}: build exit {build_code}")
            result["build_attempts"] = attempts

            inspection = runner.inspect_archive(archive, "scan-rebuild", role)
            manifest_equal = (
                inspection["image_manifest_digest"]
                == expected["candidate_image_manifest_digest"]
            )
            config_equal = (
                inspection["image_config_digest"] == expected["candidate_image_config_digest"]
            )
            layers_equal = (
                inspection["image_layer_digests"]
                == expected["candidate_image_layer_digests"]
            )
            result["digest_binding"] = {
                "observed_image_manifest_digest": inspection["image_manifest_digest"],
                "observed_image_config_digest": inspection["image_config_digest"],
                "manifest_equal_to_ab_candidate": manifest_equal,
                "config_equal_to_ab_candidate": config_equal,
                "layers_equal_to_ab_candidate": layers_equal,
                "status": (
                    "PASS_EXACT_IMAGE" if manifest_equal and config_equal and layers_equal else "MISMATCH"
                ),
            }
            if result["digest_binding"]["status"] != "PASS_EXACT_IMAGE":
                raise RuntimeError("DIGEST_MISMATCH")

            expected_id = expected["candidate_image_config_digest"]
            precheck = runner.command_output(["docker", "image", "inspect", expected_id])
            image_preexisting = precheck["exit_code"] == 0
            result["image_id_preexisting_before_load"] = image_preexisting
            load_code = runner.run_logged(
                f"{role}-docker-load",
                ["docker", "load", "--input", str(archive)],
                OUT,
            )
            load_log = (OUT / f"{role}-docker-load.log").read_text(errors="replace")
            match = re.search(r"Loaded image ID: (sha256:[0-9a-f]{64})", load_log)
            if load_code != 0 or match is None:
                raise RuntimeError(f"docker load failed or image ID missing, exit {load_code}")
            loaded_id = match.group(1)
            result["loaded_image_id"] = loaded_id
            result["loaded_image_id_matches_expected_config"] = loaded_id == expected_id
            if loaded_id != expected_id:
                raise RuntimeError("LOADED_IMAGE_CONFIG_ID_MISMATCH")
            tag_code = runner.run_logged(
                f"{role}-docker-tag",
                ["docker", "tag", loaded_id, tag],
                OUT,
            )
            if tag_code != 0:
                raise RuntimeError(f"docker tag exit {tag_code}")
            inspect_result = runner.command_output(["docker", "image", "inspect", tag])
            runner.write_json(OUT / f"{role}.loaded-image-inspect.json", inspect_result)
            report = OUT / f"{role}.trivy.loaded-image.json"
            scan_code = runner.run_logged(
                f"{role}-loaded-image-trivy",
                [
                    "trivy",
                    "image",
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
                    str(report),
                    tag,
                ],
                OUT,
            )
            scan = runner.parse_trivy(report, scan_code)
            if not scan.get("report_present"):
                raise RuntimeError(f"TRIVY_FAILED_NO_REPORT exit {scan_code}")
            runner.write_json(OUT / f"{role}.trivy.summary.json", scan)
            result["trivy"] = scan
            result["status"] = "PASS_FRESH_SCAN_TRIVY_GATE_" + scan["gate_status"]
        except Exception as exc:
            result["status"] = (
                "NETWORK_BLOCKED" if "NETWORK_BLOCKED" in str(exc) else "FAILED_OR_INCOMPLETE"
            )
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            tag_inspect = runner.command_output(["docker", "image", "inspect", tag])
            if tag_inspect["exit_code"] == 0:
                code = runner.run_logged(
                    f"{role}-tag-cleanup", ["docker", "image", "rm", tag], OUT
                )
                cleanup.append({"kind": "task_tag", "tag": tag, "exit_code": code})
            if loaded_id and not image_preexisting:
                id_inspect = runner.command_output(["docker", "image", "inspect", loaded_id])
                if id_inspect["exit_code"] == 0:
                    code = runner.run_logged(
                        f"{role}-image-id-cleanup",
                        ["docker", "image", "rm", loaded_id],
                        OUT,
                    )
                    cleanup.append(
                        {"kind": "task_image_id", "image_id": loaded_id, "exit_code": code}
                    )
            if builder_created:
                code = runner.run_logged(
                    f"{role}-builder-cleanup",
                    ["docker", "buildx", "rm", builder],
                    OUT,
                )
                cleanup.append({"kind": "builder", "name": builder, "exit_code": code})
            if archive.exists():
                archive_sha = runner.sha256(archive)
                archive_bytes = archive.stat().st_size
                archive.unlink()
                cleanup.append(
                    {
                        "kind": "temporary_oci_archive",
                        "sha256_before_removal": archive_sha,
                        "bytes_reclaimed": archive_bytes,
                        "removed": True,
                    }
                )
            result["cleanup"] = {
                "events": cleanup,
                "tag_residue": runner.command_output(
                    ["docker", "image", "inspect", tag]
                )["exit_code"]
                == 0,
                "builder_residue": builder
                in runner.command_output(["docker", "buildx", "ls"])["output"],
                "archive_residue": archive.exists(),
                "docker_prune_run": False,
                "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
            }
            runner.write_json(OUT / f"{role}.result.json", result)
        results[role] = result

    after_candidate = runner.git_snapshot(runner.CANDIDATE)
    after_replay = runner.git_snapshot(runner.REPLAY)
    clean_inputs = (
        before_candidate == after_candidate
        and before_replay == after_replay
        and after_candidate["clean"]
        and after_replay["clean"]
    )
    complete = all(
        record.get("status", "").startswith("PASS_FRESH_SCAN_TRIVY_GATE_")
        and record.get("digest_binding", {}).get("status") == "PASS_EXACT_IMAGE"
        and not any(
            (
                record["cleanup"]["tag_residue"],
                record["cleanup"]["builder_residue"],
                record["cleanup"]["archive_residue"],
            )
        )
        for record in results.values()
    )
    summary = {
        "schema": "mrw.stage3.r13v.backend-migration-trivy-recovery.v1",
        "authoritative": False,
        "authority_ceiling": "LOCAL_UNSIGNED_TASK_OWNED_EVIDENCE_NOT_RELEASE_AUTHORITY",
        "status": "PASS_FRESH_LOADED_IMAGE_SCANS" if complete and clean_inputs else "FAILED_OR_INCOMPLETE",
        "source_ab_evidence": str(AB_OUT),
        "candidate_before": before_candidate,
        "candidate_after": after_candidate,
        "replay_before": before_replay,
        "replay_after": after_replay,
        "inputs_unchanged_and_clean": clean_inputs,
        "roles": results,
        "docker_prune_run": False,
        "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
    }
    runner.write_json(OUT / "summary.json", summary)
    members = sorted(
        path
        for path in OUT.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.endswith(".oci.tar")
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{runner.sha256(path)}  {path.relative_to(OUT)}\n" for path in members)
    )
    print(
        f"COMPLETE status={summary['status']} sha256sums={runner.sha256(OUT / 'SHA256SUMS')}",
        flush=True,
    )
    return 0 if summary["status"] == "PASS_FRESH_LOADED_IMAGE_SCANS" else 1


raise SystemExit(main())
