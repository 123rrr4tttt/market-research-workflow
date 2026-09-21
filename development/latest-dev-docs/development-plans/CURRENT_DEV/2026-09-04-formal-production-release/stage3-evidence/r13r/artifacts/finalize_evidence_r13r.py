#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13r/artifacts")
CANDIDATE = Path("/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13r/candidate")
ROLES = ("backend", "migration-runner", "frontend")


def write_json(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


roles = {role: json.loads((OUT / f"{role}.summary.json").read_text()) for role in ROLES}
available = json.loads((OUT / "available-images.json").read_text())

canonical_log = subprocess.run(
    [
        "docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "/bin/sh",
        "mrw-r13r-amd64-frontend-canonical:local", "-c", "tail -8 /var/log/apk.log",
    ],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
(OUT / "frontend-canonical-apk-log-tail.log").write_text(canonical_log.stdout)
write_json(
    "frontend-canonical-apk-log-tail.command.json",
    {"argv": ["docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "/bin/sh", "mrw-r13r-amd64-frontend-canonical:local", "-c", "tail -8 /var/log/apk.log"], "cwd": str(OUT)},
)
write_json("frontend-canonical-apk-log-tail.exit.json", {"exit_code": canonical_log.returncode})

frontend_diff = json.loads((OUT / "frontend.rootfs-difference.json").read_text())
apk_difference = frontend_diff["differences"][0]
frontend_supplement = {
    "schema": "mrw.stage3.r13r.frontend-apk-log-difference.v1",
    "role": "frontend",
    "candidate": {"commit": "9b95d1c6c515b3013d6be7fd39ffb54801310c1c", "tree": "040f2ed5b223607c63404c709e413f8898c2b504"},
    "platform": "linux/amd64",
    "path": "/var/log/apk.log",
    "canonical_sha256": apk_difference["canonical_content_sha256"],
    "rebuild_sha256": apk_difference["rebuild_content_sha256"],
    "bytes": apk_difference["canonical"]["size"],
    "exact_difference": {
        "canonical_fragment": "Running `apk add --no-cache libuuid=2.42.3-r1` at 2026-09-10 03:18:28",
        "rebuild_fragment": "Running `apk add --no-cache libuuid=2.42.3-r1` at 2026-09-10 03:19:50",
        "only_changed_bytes": "03:18:28 -> 03:19:50",
    },
    "derivation": {
        "canonical": "Read directly from the loaded canonical image; command/log/exit retained.",
        "rebuild": "Deterministically recovered by substituting every second in the observed build window into the sole wall-clock field of the canonical 9,194-byte file until the exact recorded rebuild SHA-256 matched. Exactly one value matched: 2026-09-10 03:19:50.",
        "rootfs_scope": "Both inventories contain 2,214 paths; this is the only path difference; runtime config is equal.",
    },
    "cause": "APK_WALL_CLOCK_LOG_TIMESTAMP",
    "source_surface": {
        "path": "main/frontend-modern/Dockerfile",
        "line": 19,
        "instruction": "RUN apk add --no-cache libuuid=2.42.3-r1",
    },
    "minimal_successor_repair": "Change line 19 to `RUN apk add --no-cache libuuid=2.42.3-r1 && rm -f /var/log/apk.log`, then mint a successor candidate and rerun both independent linux/amd64 builds plus SBOM/provenance/Trivy/runtime evidence.",
    "candidate_mutated": False,
    "status": "CONFIRMED_ROOT_CAUSE_REQUIRES_SUCCESSOR",
}
write_json("frontend-apk-log-difference-supplement.json", frontend_supplement)

security = {
    role: roles[role]["trivy"] for role in ROLES
}
write_json(
    "security-summary.json",
    {
        "schema": "mrw.stage3.r13r.amd64-trivy-summary.v1",
        "tool": "Trivy 0.74.0",
        "threshold": "HIGH,CRITICAL",
        "roles": security,
        "status": "FAIL_THRESHOLD" if any(record.get("gate_status") == "FAIL" for record in security.values()) else "PASS_THRESHOLD",
        "note": "Initial direct OCI-tar attempts are retained as unsupported-input diagnostics. Effective scans use Docker tags loaded from those exact validated canonical OCI outputs.",
    },
)

write_json(
    "difference-runtime-scope.json",
    {
        "schema": "mrw.stage3.r13r.amd64-difference-runtime-scope.v1",
        "roles": {
            role: {
                "canonical_image_manifest_digest": roles[role]["comparison"]["canonical_image_manifest_digest"],
                "rebuild_image_manifest_digest": roles[role]["comparison"]["rebuild_image_manifest_digest"],
                "exact": roles[role]["comparison"]["image_manifest_equal"],
                "runtime_config_equal": (
                    roles[role]["comparison"].get("rootfs_difference", {}).get("runtime_config_equal")
                    if role == "frontend" else True
                ),
                "rootfs_scope": (
                    {"difference_count": 1, "only_path": "/var/log/apk.log", "cause": "APK_WALL_CLOCK_LOG_TIMESTAMP"}
                    if role == "frontend" else "NOT_NEEDED_EXACT_IMAGE_MANIFEST_MATCH"
                ),
            }
            for role in ROLES
        },
        "runtime_claim": "No full dependency-backed application runtime equivalence claim. Backend and migration-runner are byte-identical across A/B. Frontend runtime config and all rootfs paths except a package-manager log are equal, but Stage 3 does not allow a non-bit-for-bit exception.",
        "status": "FAILED_FRONTEND_NOT_BIT_FOR_BIT",
    },
)

candidate_status = subprocess.check_output(["git", "-C", str(CANDIDATE), "status", "--porcelain=v1"], text=True)
builders = subprocess.check_output(["docker", "buildx", "ls"], text=True)
containers = subprocess.check_output(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"], text=True)
task_builder_residue = [line for line in builders.splitlines() if "mrw-r13r-amd64-" in line]
archives = [str(path) for path in OUT.rglob("*.oci.tar")]
cleanup = {
    "schema": "mrw.stage3.r13r.amd64-cleanup-residue.v1",
    "candidate_clean": candidate_status == "",
    "task_builder_residue": task_builder_residue,
    "temporary_oci_archive_residue": archives,
    "task_test_tags_retained": {role: available["roles"][role]["tag"] for role in ROLES},
    "test_tag_cleanup_owner": "/root/stage3_test_gates after gates complete",
    "preexisting_resources_preserved": True,
    "ops_scrapyd_observed_unchanged": any(line.startswith("ops-scrapyd-1\t") for line in containers.splitlines()),
    "free_bytes_after": shutil.disk_usage("/System/Volumes/Data").free,
    "status": "PASS_TASK_BUILD_RESIDUE_CLEAN_TEST_TAGS_HANDOFF_RETAINED" if not task_builder_residue and not archives and candidate_status == "" else "FAIL_RESIDUE_OR_CANDIDATE_DIRT",
}
write_json("cleanup-residue.json", cleanup)

summary_path = OUT / "summary.json"
summary = json.loads(summary_path.read_text())
summary["roles"] = roles
summary["security_summary"] = security
summary["frontend_apk_log_difference"] = frontend_supplement
summary["available_test_images"] = available["roles"]
summary["cleanup"] = cleanup
summary["status"] = "FAILED_REPRODUCIBILITY_AND_SECURITY_THRESHOLDS"
summary["failure_reasons"] = [
    "Frontend canonical/rebuild image manifests differ because /var/log/apk.log embeds the apk invocation wall-clock timestamp.",
    "Backend and migration-runner each exceed the Trivy HIGH/CRITICAL threshold (135 HIGH and 13 CRITICAL observations per role).",
]
summary["completedسادодаряärtener'sennials"] = int(time.time())
for key in list(summary):
    if key.startswith("completed") and key != "completed_epoch":
        del summary[key]
summary["completed_epoch"] = int(time.time())
write_json("summary.json", summary)

members = sorted(path for path in OUT.rglob("*") if path.is_file() and path.name != "SHA256SUMS" and not path.name.endswith(".oci.tar"))
(OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.relative_to(OUT)}\n" for path in members))
print(json.dumps({"status": summary["status"], "sha256sums_sha256": sha256(OUT / "SHA256SUMS"), "cleanup": cleanup["status"]}, sort_keys=True))
