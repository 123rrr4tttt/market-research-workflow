#!/usr/bin/env python3
"""Run the isolated Stage 5 migration failure-recovery drill."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
BASE_SCRIPT = OUT / "run-recovery.py"
PROJECT = "mrw-stage5-migration-recovery"
MIGRATION_DB = "mrw_stage5_migration_probe"
HEAD = "20260905_000001"
PARENT = "20260830_000001"

spec = importlib.util.spec_from_file_location("stage5_recovery_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load Stage 5 recovery helper")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.COMPOSE[3] = PROJECT
base.PROJECT = PROJECT


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(payload: dict[str, Any]) -> None:
    payload.setdefault("authoritative", False)
    (OUT / "migration-recovery-result.json").write_text(
        json.dumps(base.scrub_value(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resources() -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={PROJECT}"

    def lines(args: list[str]) -> list[str]:
        completed = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return sorted(line for line in completed.stdout.splitlines() if line.strip())

    return {
        "containers": lines(["docker", "ps", "-a", "--filter", label, "--format", "{{.Names}}"]),
        "networks": lines(["docker", "network", "ls", "--filter", label, "--format", "{{.Name}}"]),
        "volumes": lines(["docker", "volume", "ls", "--filter", label, "--format", "{{.Name}}"]),
    }


def cleanup() -> dict[str, Any]:
    completed = base.run(
        "m90-compose-down",
        base.compose_args("down", "--volumes", "--remove-orphans", "--timeout", "30"),
        check=False,
        timeout=180,
    )
    residue = resources()
    return {
        "status": "PASS" if completed.returncode == 0 and not any(residue.values()) else "FAIL",
        "down_exit_code": completed.returncode,
        "project_residue": residue,
    }


def database_digest(path: Path) -> str:
    return base.sha256_bytes(path.read_bytes())


def main() -> int:
    started_at = utc_now()
    before = resources()
    result: dict[str, Any] = {
        "schema_version": "mrw.stage5.migration-failure-recovery.v1",
        "status": "FAIL",
        "started_at": started_at,
        "compose_project": PROJECT,
        "database": MIGRATION_DB,
        "source": {
            "classification": "RETAINED_TASK_OWNED_SYNTHETIC_SNAPSHOT_NOT_BACKUP_ARTIFACT",
            "path": str(base.SNAPSHOT),
            "sha256": base.sha256_bytes(base.SNAPSHOT.read_bytes()),
        },
        "project_resources_before": before,
    }
    if any(before.values()):
        result["error"] = "migration recovery Compose project collision"
        write_json(result)
        return 1
    started = False
    try:
        identity = base.image_identity(base.MIGRATION_IMAGE)
        if identity["id"] != base.MIGRATION_IMAGE_ID:
            raise RuntimeError("migration runner identity mismatch")
        result["migration_image"] = identity
        base.run(
            "m01-migration-db-up",
            base.compose_args("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", "migration-db"),
            timeout=180,
        )
        started = True
        container = base.run("m02-migration-db-container", base.compose_args("ps", "-q", "migration-db")).stdout.strip()
        base.run("m03-snapshot-copy", ["docker", "cp", str(base.SNAPSHOT), f"{container}:/tmp/stage5-snapshot.dump"])
        base.run(
            "m04-snapshot-restore",
            ["docker", "exec", container, "pg_restore", "-U", "postgres", "-d", MIGRATION_DB,
             "--exit-on-error", "/tmp/stage5-snapshot.dump"],
            timeout=300,
        )
        base.run(
            "m05-before-dump",
            ["docker", "exec", container, "pg_dump", "-U", "postgres", "-Fc", "-d", MIGRATION_DB,
             "-f", "/tmp/before.dump"],
        )
        base.run("m06-before-copy", ["docker", "cp", f"{container}:/tmp/before.dump", str(OUT / "migration-before.dump")])
        before_digest = database_digest(OUT / "migration-before.dump")
        current = base.alembic("m07-current-head", "current")
        if HEAD not in current.stdout:
            raise RuntimeError(f"snapshot did not start at migration head: {current.stdout}")
        base.psql(
            "m08-induce-version-drift", "migration-db", MIGRATION_DB,
            f"UPDATE public.alembic_version SET version_num = '{PARENT}';",
        )
        failure_started_at = utc_now()
        failure_started_monotonic = time.monotonic()
        failure = base.alembic("m30-upgrade-expected-failure", "upgrade", "head", check=False)
        failure_log = (OUT / "m30-upgrade-expected-failure.log").read_text(encoding="utf-8")
        observed_collision = "source_kind" in failure_log and "already exists" in failure_log
        if failure.returncode == 0 or not observed_collision:
            raise RuntimeError("expected migration metadata-drift collision did not occur")
        base.alembic("m31-forward-fix-stamp-head", "stamp", HEAD)
        recovery = base.alembic("m32-upgrade-after-forward-fix", "upgrade", "head")
        recovered_current = base.alembic("m33-current-after-recovery", "current")
        base.run(
            "m34-after-dump",
            ["docker", "exec", container, "pg_dump", "-U", "postgres", "-Fc", "-d", MIGRATION_DB,
             "-f", "/tmp/after.dump"],
        )
        base.run("m35-after-copy", ["docker", "cp", f"{container}:/tmp/after.dump", str(OUT / "migration-after.dump")])
        after_digest = database_digest(OUT / "migration-after.dump")
        rto_ms = int((time.monotonic() - failure_started_monotonic) * 1000)
        preserved = before_digest == after_digest
        reached_head = HEAD in recovered_current.stdout
        if not preserved or not reached_head:
            raise RuntimeError("migration recovery failed to preserve bytes or reach head")
        result.update(
            {
                "status": "PASS_LOCAL_STAGE5_MIGRATION_RECOVERY_NOT_AUTHORITY",
                "ended_at": utc_now(),
                "initial_head": HEAD,
                "failure_mode": "CONTROLLED_ALEMBIC_VERSION_POINTER_DRIFT",
                "induced_parent": PARENT,
                "failure": {
                    "exit_code": failure.returncode,
                    "observed_collision": observed_collision,
                    "log": "m30-upgrade-expected-failure.log",
                },
                "recovery": {
                    "method": f"alembic stamp {HEAD}; alembic upgrade head",
                    "upgrade_exit_code": recovery.returncode,
                    "current_head": reached_head,
                    "before_dump_sha256": before_digest,
                    "after_dump_sha256": after_digest,
                    "database_bytes_preserved": preserved,
                    "rto_ms": rto_ms,
                    "rto_boundary": "controlled failure start through post-fix current and byte comparison",
                },
            }
        )
    except Exception as exc:  # noqa: BLE001 - retain failure evidence
        result["error"] = str(exc)
        result["ended_at"] = utc_now()
    finally:
        result["cleanup"] = cleanup() if started else {"status": "NOT_RUN"}
        if result["cleanup"].get("status") != "PASS":
            result["status"] = "FAIL"
            result.setdefault("error", "migration recovery Compose resources remain")
        write_json(result)
    return 0 if result.get("status") == "PASS_LOCAL_STAGE5_MIGRATION_RECOVERY_NOT_AUTHORITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
