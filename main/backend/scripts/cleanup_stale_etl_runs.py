#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


@dataclass
class JobRow:
    id: int
    job_type: str | None
    status: str | None
    started_at: datetime | None
    finished_at: datetime | None


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def resolve_db_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL is empty. Please set it in env or .env")
    return raw.replace("postgresql+psycopg2://", "postgresql://", 1)


def project_schema(project_key: str) -> str:
    key = (project_key or "").strip()
    if not key:
        raise ValueError("project_key is required")
    return f"project_{key}"


def fetch_candidates(
    conn: Any,
    schema: str,
    task_id: int | None,
    older_than_minutes: int,
) -> list[JobRow]:
    if task_id is not None:
        q = text(
            f"""
            SELECT id, job_type, status, started_at, finished_at
            FROM {schema}.etl_job_runs
            WHERE id = :task_id
            """
        )
        rows = conn.execute(q, {"task_id": task_id}).mappings().all()
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        q = text(
            f"""
            SELECT id, job_type, status, started_at, finished_at
            FROM {schema}.etl_job_runs
            WHERE status = 'running'
              AND started_at IS NOT NULL
              AND started_at < :cutoff
            ORDER BY started_at ASC
            """
        )
        rows = conn.execute(q, {"cutoff": cutoff}).mappings().all()

    result: list[JobRow] = []
    for r in rows:
        result.append(
            JobRow(
                id=int(r["id"]),
                job_type=r.get("job_type"),
                status=r.get("status"),
                started_at=r.get("started_at"),
                finished_at=r.get("finished_at"),
            )
        )
    return result


def mark_failed(conn: Any, schema: str, job_id: int, error_message: str) -> int:
    q = text(
        f"""
        UPDATE {schema}.etl_job_runs
        SET
          status = 'failed',
          finished_at = COALESCE(finished_at, now()),
          error = CASE
            WHEN error IS NULL OR error = '' THEN :error_message
            ELSE error || E'\\n' || :error_message
          END
        WHERE id = :job_id
        """
    )
    result = conn.execute(q, {"job_id": job_id, "error_message": error_message})
    return int(getattr(result, "rowcount", 0) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mark stale/running ETL jobs as failed in project schema."
    )
    parser.add_argument("--project-key", required=True, help="Project key, e.g. demo_proj")
    parser.add_argument("--task-id", type=int, default=None, help="Single etl_job_runs.id to repair")
    parser.add_argument(
        "--older-than-minutes",
        type=int,
        default=30,
        help="When --task-id is not provided, mark running jobs older than this threshold (default: 30)",
    )
    parser.add_argument(
        "--reason",
        default="stale running task repaired manually",
        help="Reason text appended into error column",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print candidates, no update")
    parser.add_argument(
        "--env-file",
        default="main/backend/.env",
        help="Path to .env (default: main/backend/.env)",
    )
    args = parser.parse_args()

    load_env(Path(args.env_file))
    db_url = resolve_db_url()
    schema = project_schema(args.project_key)
    engine = create_engine(db_url)

    with engine.begin() as conn:
        candidates = fetch_candidates(
            conn=conn,
            schema=schema,
            task_id=args.task_id,
            older_than_minutes=max(1, int(args.older_than_minutes)),
        )
        if not candidates:
            print("No matching jobs.")
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        reason = f"[{now_iso}] {args.reason}"
        print(f"Schema: {schema}")
        print(f"Candidates: {len(candidates)}")
        for c in candidates:
            print(
                f"- id={c.id} job_type={c.job_type} status={c.status} "
                f"started_at={c.started_at} finished_at={c.finished_at}"
            )

        if args.dry_run:
            print("Dry run mode: no rows updated.")
            return 0

        updated_rows = 0
        for c in candidates:
            updated_rows += mark_failed(
                conn=conn, schema=schema, job_id=c.id, error_message=reason
            )
        print(f"Updated rows: {updated_rows}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
