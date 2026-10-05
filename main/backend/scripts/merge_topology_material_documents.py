"""Migrate current placements to canonical material addresses, preserving history."""
from __future__ import annotations

import argparse
import json

from functorial_kit import Failure
from sqlalchemy import inspect, select

from app.models.base import SessionLocal
from app.models.entities import Project
from app.services.project_retrieval.topology import build_topology_service
from app.services.projects.context import bind_project, bind_schema, project_schema_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--project-key")
    targets.add_argument("--all-projects", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with bind_schema("public"), SessionLocal() as session:
        projects = list(session.execute(select(Project).order_by(Project.id)).scalars())
        selected = projects if args.all_projects else [p for p in projects if p.project_key == args.project_key]
        if not selected:
            print(json.dumps({"code": "NOT_FOUND", "project_key": args.project_key}))
            return 1
        ready = []
        for project in selected:
            if project.schema_name != project_schema_name(project.project_key):
                print(json.dumps({"code": "SCHEMA_IDENTITY_MISMATCH", "project_key": project.project_key}))
                return 1
            ready.append((project.project_key, inspect(session.connection()).has_table(
                "information_topology_states", schema=project.schema_name,
            )))
    results = []
    failed = False
    for key, has_topology in ready:
        if not has_topology:
            results.append({"project_key": key, "migrated_states": 0, "status": "no_topology_table"})
            continue
        with bind_project(key):
            service = build_topology_service()
            if args.dry_run:
                with service.dependencies.session_factory() as session:
                    rows = service.repository.list_current_states(session, key)
                result = {"project_key": key, "pending_states": sum(
                    row["profile_id"].startswith("retrieval.domain.") and not row["profile_version"].startswith("3+")
                    for row in rows
                ), "current_states": len(rows)}
            else:
                result = service.merge_materials(key)
        if isinstance(result, Failure):
            failed = True
            results.append({"project_key": key, "code": result.code, "message": result.message,
                            "context": dict(result.context or {})})
        else:
            results.append(result)
    print(json.dumps({"dry_run": args.dry_run, "projects": results}))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
