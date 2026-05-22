#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.persistence.graph_projection_contract import (
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATION_ROOT = BACKEND_ROOT / "migrations" / "versions"


def _fixture_graph() -> Graph:
    post = GraphNode(type="Post", id=" 42 ", properties={"title": "Projection Fixture"})
    entity_upper = GraphNode(type="Entity", id=" ACME\u200b Corp ", properties={"name": "ACME Corp"})
    entity_lower = GraphNode(type="Entity", id="acme corp", properties={"name": "acme corp duplicate"})
    keyword = GraphNode(type="Keyword", id=" Lottery   AI ", properties={"label": "Lottery AI"})
    missing = GraphNode(type="Entity", id="Missing Co", properties={"name": "Missing Co"})

    return Graph(
        nodes={
            "Post:raw-42": post,
            "Entity:upper": entity_upper,
            "Entity:lower": entity_lower,
            "Keyword:lottery-ai": keyword,
        },
        edges=[
            GraphEdge(
                type="MENTIONS_ENTITY",
                from_node=GraphNode(type="Post", id="42"),
                to_node=entity_upper,
                properties={},
            ),
            GraphEdge(
                type="MENTIONS_KEYWORD",
                from_node=post,
                to_node=GraphNode(type="Keyword", id="Lottery AI"),
                properties={},
            ),
            GraphEdge(type="MENTIONS_ENTITY", from_node=post, to_node=missing, properties={}),
        ],
        schema_version="v1",
    )


def _validate(report: dict) -> list[str]:
    failures: list[str] = []
    node_keys = {str(node.get("key")) for node in report.get("nodes", [])}
    expected_nodes = {"Post:42", "Entity:acme corp", "Keyword:lottery ai"}
    if node_keys != expected_nodes:
        failures.append(f"node_keys expected={sorted(expected_nodes)} actual={sorted(node_keys)}")
    if report.get("attempted_node_count") != 4:
        failures.append(f"attempted_node_count expected=4 actual={report.get('attempted_node_count')}")
    if report.get("unique_node_count") != 3:
        failures.append(f"unique_node_count expected=3 actual={report.get('unique_node_count')}")
    if report.get("duplicate_node_attempts") != 1:
        failures.append(f"duplicate_node_attempts expected=1 actual={report.get('duplicate_node_attempts')}")
    if report.get("candidate_edge_count") != 3:
        failures.append(f"candidate_edge_count expected=3 actual={report.get('candidate_edge_count')}")
    if report.get("writeable_edge_count") != 2:
        failures.append(f"writeable_edge_count expected=2 actual={report.get('writeable_edge_count')}")
    if report.get("unresolved_edge_count") != 1:
        failures.append(f"unresolved_edge_count expected=1 actual={report.get('unresolved_edge_count')}")

    resolved_pairs = {
        (str(edge.get("edge_type")), str(edge.get("from_key")), str(edge.get("to_key")))
        for edge in report.get("edges", [])
        if edge.get("resolved") and not edge.get("duplicate")
    }
    expected_pairs = {
        ("MENTIONS_ENTITY", "Post:42", "Entity:acme corp"),
        ("MENTIONS_KEYWORD", "Post:42", "Keyword:lottery ai"),
    }
    if resolved_pairs != expected_pairs:
        failures.append(f"resolved_pairs expected={sorted(expected_pairs)} actual={sorted(resolved_pairs)}")

    if report.get("live_db_validated") is not False:
        failures.append("live_db_validated must remain false for no-DB checker evidence")
    if not report.get("live_db_gap"):
        failures.append("live_db_gap must retain tenant DB rollout gaps")
    return failures


def _split_projects(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _migration_checks(migration_root: Path) -> dict[str, bool]:
    node_migration = _read_file(migration_root / "20260303_000004_add_graph_node_projection_tables.py")
    edge_migration = _read_file(migration_root / "20260303_000005_add_graph_edge_projection_table.py")
    return {
        "graph_nodes_table": "graph_nodes" in node_migration and "uq_graph_nodes_type_canonical" in node_migration,
        "graph_node_aliases_table": "graph_node_aliases" in node_migration
        and "uq_graph_node_aliases_norm_type" in node_migration,
        "graph_edges_table": "graph_edges" in edge_migration and "uq_graph_edges_type_from_to" in edge_migration,
        "edge_depends_on_node_migration": 'down_revision = "20260303_000004"' in edge_migration,
    }


def _failure_isolation_checks() -> dict[str, bool]:
    admin_source = _read_file(BACKEND_ROOT / "app" / "api" / "admin.py")
    backfill_source = _read_file(BACKEND_ROOT / "app" / "services" / "graph" / "backfill_graph_nodes.py")
    return {
        "admin_shadow_write_rollback_and_continue": "_rollback_quietly(session, context=\"graph_b_write\")" in admin_source
        and "graph_b_write_failed" in admin_source,
        "admin_b_read_fallback_to_a": "_rollback_quietly(session, context=\"graph_b_read\")" in admin_source
        and "graph_b_read_fallback_to_a" in admin_source,
        "backfill_apply_rollback_on_failure": "_rollback_quietly(session)" in backfill_source
        and "except Exception:" in backfill_source
        and "raise" in backfill_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check graph projection canonical and edge contract without a DB")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--read-mode", default="a_only", help="planned graph_node_projection_read_mode")
    parser.add_argument("--write-mode", default="shadow", help="planned graph_node_projection_write_mode")
    parser.add_argument("--canary-projects", default="demo_proj", help="comma-separated canary project keys")
    parser.add_argument("--backfill-limit", type=int, default=10, help="bounded dry-run document limit")
    parser.add_argument("--max-dry-run-limit", type=int, default=1000)
    parser.add_argument("--backfill-apply", action="store_true", help="validate apply-mode readiness; should fail pre-live")
    parser.add_argument("--migration-root", default=str(DEFAULT_MIGRATION_ROOT))
    args = parser.parse_args()

    report = build_graph_projection_dry_run(_fixture_graph()).to_dict()
    readiness = build_graph_projection_rollout_readiness(
        read_mode=args.read_mode,
        write_mode=args.write_mode,
        canary_projects=_split_projects(args.canary_projects),
        backfill_dry_run=not args.backfill_apply,
        backfill_limit=args.backfill_limit,
        migration_checks=_migration_checks(Path(args.migration_root)),
        failure_isolation_checks=_failure_isolation_checks(),
        max_dry_run_limit=args.max_dry_run_limit,
    ).to_dict()
    failures = _validate(report)
    failures.extend(
        f"readiness.{check['name']}: {check['detail']}"
        for check in readiness.get("checks", [])
        if not check.get("passed")
    )
    if readiness.get("closure_claim") is not False or readiness.get("live_db_validated") is not False:
        failures.append("readiness must not claim live DB validation or closure")

    payload = {
        "status": "ok" if not failures else "failed",
        "failures": failures,
        "report": report,
        "readiness": readiness,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={payload['status']}")
        for key in (
            "mode",
            "live_db_validated",
            "unique_node_count",
            "duplicate_node_attempts",
            "writeable_edge_count",
            "unresolved_edge_count",
        ):
            print(f"{key}={report.get(key)}")
        print(f"ready_for_live_db_dry_run={readiness.get('ready_for_live_db_dry_run')}")
        print(f"closure_claim={readiness.get('closure_claim')}")
        if failures:
            print("failures:")
            for failure in failures:
                print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
