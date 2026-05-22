#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.persistence.graph_projection_contract import build_graph_projection_dry_run


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check graph projection canonical and edge contract without a DB")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()

    report = build_graph_projection_dry_run(_fixture_graph()).to_dict()
    failures = _validate(report)
    payload = {"status": "ok" if not failures else "failed", "failures": failures, "report": report}

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
        if failures:
            print("failures:")
            for failure in failures:
                print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
