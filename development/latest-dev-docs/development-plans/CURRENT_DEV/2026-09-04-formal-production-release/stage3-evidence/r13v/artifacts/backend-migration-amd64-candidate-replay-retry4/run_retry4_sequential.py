#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil


BASE_RUNNER = Path(
    "/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/"
    "development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
    "stage3-evidence/r13v/artifacts/backend-migration-amd64-candidate-replay/"
    "run_r13v_backend_migration.py"
)
spec = importlib.util.spec_from_file_location("r13v_base_runner", BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load base runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.OUT = Path(__file__).resolve().parent


def is_network_failure(log_path: Path) -> bool:
    if not log_path.is_file():
        return False
    text = log_path.read_text(errors="replace")
    markers = (
        "502  Bad Gateway",
        'failed to authorize:',
        'failed to do request:',
        'unexpected EOF',
        ': EOF',
    )
    return any(marker in text for marker in markers)


def sequential_build_role(role: str, target: str, builders: dict[str, str]) -> dict:
    free_before = shutil.disk_usage("/System/Volumes/Data").free
    if free_before < runner.MIN_FREE_BYTES:
        result = {
            "role": role,
            "status": "NOT_RUN_INSUFFICIENT_SAFE_DISK_BUDGET",
            "free_bytes": free_before,
            "minimum_required_bytes": runner.MIN_FREE_BYTES,
        }
        runner.write_json(runner.OUT / f"{role}.summary.json", result)
        return result

    archives = {
        "candidate": runner.OUT / "candidate" / f"{role}.oci.tar",
        "replay": runner.OUT / "replay" / f"{role}.oci.tar",
    }
    inspections: dict[str, dict] = {}
    cleanup_events: list[dict] = []
    active_builders: dict[str, str] = {}
    result: dict = {
        "role": role,
        "target": target,
        "platform": runner.PLATFORM,
        "free_bytes_before": free_before,
        "builders": builders,
        "orchestration": "candidate inspect/scan/cleanup, then replay build/inspect/cleanup",
    }

    def create_builder(environment: str, suffix: str = "") -> None:
        builder = builders[environment]
        prefix = f"{role}-{environment}{suffix}"
        code = runner.run_logged(
            f"{prefix}-builder-create",
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
            runner.OUT,
        )
        if code != 0:
            raise RuntimeError(f"{environment}{suffix} builder creation failed with exit {code}")
        active_builders[environment] = builder
        code = runner.run_logged(
            f"{prefix}-builder-bootstrap",
            ["docker", "buildx", "inspect", "--bootstrap", builder],
            runner.OUT,
        )
        if code != 0:
            raise RuntimeError(f"{environment}{suffix} builder bootstrap failed with exit {code}")

    def remove_builder(environment: str, suffix: str = "") -> None:
        builder = active_builders.pop(environment, None)
        if builder is None:
            return
        prefix = f"{role}-{environment}{suffix}"
        code = runner.run_logged(
            f"{prefix}-builder-cleanup",
            ["docker", "buildx", "rm", builder],
            runner.OUT,
        )
        cleanup_events.append(
            {
                "kind": "builder",
                "environment": environment,
                "attempt": suffix or "initial",
                "name": builder,
                "exit_code": code,
            }
        )

    def remove_archive(environment: str) -> None:
        archive = archives[environment]
        if not archive.exists():
            return
        archive_sha = runner.sha256(archive)
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
            }
        )

    def build(environment: str, suffix: str = "") -> int:
        free_before_build = shutil.disk_usage("/System/Volumes/Data").free
        if free_before_build < runner.MIN_FREE_BYTES:
            raise RuntimeError(
                "INSUFFICIENT_SAFE_DISK_BUDGET before "
                f"{environment}{suffix} build: {free_before_build} < {runner.MIN_FREE_BYTES}"
            )
        source = runner.CANDIDATE if environment == "candidate" else runner.REPLAY
        metadata = runner.OUT / environment / f"{role}{suffix}.build-metadata.json"
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
            runner.PLATFORM,
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
        return runner.run_logged(f"{role}-{environment}{suffix}-build", argv, source)

    try:
        create_builder("candidate")
        candidate_code = build("candidate")
        if candidate_code != 0:
            classification = (
                "NETWORK_BLOCKED" if is_network_failure(runner.OUT / f"{role}-candidate-build.log")
                else "BUILD_FAILED"
            )
            raise RuntimeError(f"{classification}: candidate build exit {candidate_code}")
        inspections["candidate"] = runner.inspect_archive(
            archives["candidate"], "candidate", role
        )
        trivy_report = runner.OUT / "candidate" / f"{role}.trivy.json"
        trivy_code = runner.run_logged(
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
            runner.OUT,
        )
        trivy_summary = runner.parse_trivy(trivy_report, trivy_code)
        runner.write_json(
            runner.OUT / "candidate" / f"{role}.trivy.summary.json", trivy_summary
        )
        remove_builder("candidate")
        remove_archive("candidate")

        create_builder("replay")
        replay_code = build("replay")
        replay_attempts = [{"attempt": "initial", "exit_code": replay_code}]
        if replay_code != 0 and is_network_failure(
            runner.OUT / f"{role}-replay-build.log"
        ):
            remove_builder("replay", "-failed-initial")
            remove_archive("replay")
            create_builder("replay", "-network-retry1")
            replay_code = build("replay", "-network-retry1")
            replay_attempts.append({"attempt": "network-retry1", "exit_code": replay_code})
        result["replay_attempts"] = replay_attempts
        if replay_code != 0:
            retry_log = (
                runner.OUT / f"{role}-replay-network-retry1-build.log"
                if len(replay_attempts) == 2
                else runner.OUT / f"{role}-replay-build.log"
            )
            classification = "NETWORK_BLOCKED" if is_network_failure(retry_log) else "BUILD_FAILED"
            raise RuntimeError(f"{classification}: replay build exit {replay_code}")
        inspections["replay"] = runner.inspect_archive(archives["replay"], "replay", role)

        candidate = inspections["candidate"]
        replay = inspections["replay"]
        comparison = {
            "role": role,
            "platform": runner.PLATFORM,
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
                "Candidate root includes provenance/SBOM attestations; replay disables attestations."
            ),
        }
        comparison["status"] = (
            "PASS_EXACT_IMAGE"
            if comparison["image_manifest_equal"]
            and comparison["image_config_equal"]
            and comparison["image_layers_equal_in_order"]
            else "MISMATCH"
        )
        runner.write_json(runner.OUT / f"{role}.reproducibility.json", comparison)
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
                "attestation_status": candidate.get("attestations", {}).get("status"),
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
        result["status"] = (
            "NETWORK_BLOCKED" if "NETWORK_BLOCKED" in str(exc) else "FAILED_OR_INCOMPLETE"
        )
        result["error"] = f"{type(exc).__name__}: {exc}"
        if inspections:
            result["inspections"] = inspections
        if "trivy_summary" in locals():
            result["trivy"] = trivy_summary
    finally:
        for environment in tuple(active_builders):
            remove_builder(environment, "-final")
        for environment in archives:
            remove_archive(environment)
        builder_listing = runner.command_output(["docker", "buildx", "ls"])
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
        runner.write_json(runner.OUT / f"{role}.summary.json", result)
    return result


runner.build_role = sequential_build_role
raise SystemExit(runner.main())
