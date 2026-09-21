#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import time


OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13r/artifacts")
ROLES = ("backend", "migration-runner", "frontend")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


records = {}
for role in ROLES:
    exit_path = OUT / f"{role}-canonical-build.exit.json"
    archive = OUT / "canonical" / f"{role}.oci.tar"
    inspection_path = OUT / "canonical" / f"{role}.digest-inspection.json"
    deadline = time.time() + 3 * 60 * 60
    while time.time() < deadline:
        if (
            exit_path.is_file()
            and json.loads(exit_path.read_text()).get("exit_code") == 0
            and archive.is_file()
            and inspection_path.is_file()
        ):
            break
        time.sleep(2)
    else:
        records[role] = {"status": "TIMEOUT_WAITING_FOR_CANONICAL_OCI"}
        continue

    load = subprocess.run(
        ["docker", "load", "--input", str(archive)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (OUT / f"{role}-canonical-docker-load.log").write_text(load.stdout)
    write_json(
        OUT / f"{role}-canonical-docker-load.command.json",
        {"argv": ["docker", "load", "--input", str(archive)], "cwd": str(OUT)},
    )
    write_json(OUT / f"{role}-canonical-docker-load.exit.json", {"exit_code": load.returncode})
    match = re.search(r"Loaded image ID: (sha256:[0-9a-f]{64})", load.stdout)
    if load.returncode != 0 or match is None:
        records[role] = {"status": "LOAD_FAILED", "exit_code": load.returncode}
        continue
    loaded_id = match.group(1)
    tag = f"mrw-r13r-amd64-{role}-canonical:local"
    tag_result = subprocess.run(
        ["docker", "tag", loaded_id, tag],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (OUT / f"{role}-canonical-docker-tag.log").write_text(tag_result.stdout)
    write_json(OUT / f"{role}-canonical-docker-tag.command.json", {"argv": ["docker", "tag", loaded_id, tag], "cwd": str(OUT)})
    write_json(OUT / f"{role}-canonical-docker-tag.exit.json", {"exit_code": tag_result.returncode})
    inspect = subprocess.run(
        ["docker", "image", "inspect", tag],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (OUT / f"{role}-canonical-docker-image-inspect.json").write_text(inspect.stdout)
    inspected = json.loads(inspect.stdout)[0] if inspect.returncode == 0 else None
    digest_inspection = json.loads(inspection_path.read_text())
    records[role] = {
        "status": "AVAILABLE_FOR_LOCAL_TEST_GATES" if tag_result.returncode == 0 and inspect.returncode == 0 else "TAG_OR_INSPECT_FAILED",
        "tag": tag,
        "loaded_image_id": loaded_id,
        "image_manifest_digest": digest_inspection["image_manifest_digest"],
        "image_config_digest": digest_inspection["image_config_digest"],
        "platform": digest_inspection["platform"],
        "docker_inspect": {
            "id": (inspected or {}).get("Id"),
            "os": (inspected or {}).get("Os"),
            "architecture": (inspected or {}).get("Architecture"),
            "repo_tags": (inspected or {}).get("RepoTags"),
        },
        "load_method": f"docker load --input {archive} (performed before bounded archive cleanup), then docker tag {loaded_id} {tag}",
        "cleanup_owner": "/root/stage3_test_gates after all local stack/migration gates complete",
    }
    write_json(OUT / "available-images.partial.json", records)
    print(f"AVAILABLE {role} {tag} {digest_inspection['image_manifest_digest']}", flush=True)

write_json(
    OUT / "available-images.json",
    {
        "schema": "mrw.stage3.r13r.amd64-local-test-images.v1",
        "authoritative": False,
        "scope": "Task-local Docker tags loaded from the exact canonical OCI outputs before compact evidence cleanup; no registry push/publication/signing.",
        "roles": records,
    },
)
print("IMAGE_HANDOFF_COMPLETE", flush=True)
