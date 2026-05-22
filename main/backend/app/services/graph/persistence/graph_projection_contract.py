from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..mapping import normalize_canonical_node_id, normalize_node_properties, normalize_node_type
from ..models import Graph
from .graph_node_writer import GraphNodeWriter


ALLOWED_GRAPH_PROJECTION_READ_MODES = {"a_only", "b_canary", "b_primary"}
ALLOWED_GRAPH_PROJECTION_WRITE_MODES = {"off", "shadow", "on"}


@dataclass(frozen=True)
class GraphProjectionDryRunNode:
    key: str
    node_type: str
    canonical_id: str
    display_name: str | None
    properties: dict[str, Any]
    source_doc_id: int | None
    node_schema_version: str


@dataclass(frozen=True)
class GraphProjectionDryRunEdge:
    edge_type: str
    from_key: str
    to_key: str
    resolved: bool
    duplicate: bool
    skip_reason: str | None
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphProjectionDryRunReport:
    mode: str
    schema_version: str
    live_db_validated: bool
    attempted_node_count: int
    unique_node_count: int
    duplicate_node_attempts: int
    skipped_node_count: int
    candidate_edge_count: int
    resolved_edge_attempts: int
    writeable_edge_count: int
    unresolved_edge_count: int
    duplicate_edge_attempts: int
    nodes: list[GraphProjectionDryRunNode]
    edges: list[GraphProjectionDryRunEdge]
    live_db_gap: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphProjectionReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GraphProjectionRolloutReadinessReport:
    mode: str
    live_db_validated: bool
    ready_for_live_db_dry_run: bool
    closure_claim: bool
    read_mode: str
    write_mode: str
    canary_projects: list[str]
    backfill_dry_run: bool
    backfill_limit: int | None
    max_dry_run_limit: int
    checks: list[GraphProjectionReadinessCheck]
    live_db_gap: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _readiness_check(name: str, passed: bool, detail: str) -> GraphProjectionReadinessCheck:
    return GraphProjectionReadinessCheck(name=name, passed=bool(passed), detail=detail)


def build_graph_projection_rollout_readiness(
    *,
    read_mode: str,
    write_mode: str,
    canary_projects: list[str] | tuple[str, ...] | set[str] | None,
    backfill_dry_run: bool,
    backfill_limit: int | None,
    migration_checks: dict[str, bool],
    failure_isolation_checks: dict[str, bool],
    max_dry_run_limit: int = 1000,
) -> GraphProjectionRolloutReadinessReport:
    """Validate the static pre-live rollout contract without opening a DB.

    This is a narrow preflight for the first tenant DB dry-run. It blocks
    unsafe read/write modes and missing migration/failure-isolation assets, but
    it deliberately keeps ``live_db_validated`` and ``closure_claim`` false.
    """
    normalized_read_mode = str(read_mode or "").strip().lower()
    normalized_write_mode = str(write_mode or "").strip().lower()
    projects = sorted({str(project).strip() for project in canary_projects or [] if str(project).strip()})
    max_limit = int(max_dry_run_limit or 1000)
    checks: list[GraphProjectionReadinessCheck] = [
        _readiness_check(
            "read_mode_allowed",
            normalized_read_mode in ALLOWED_GRAPH_PROJECTION_READ_MODES,
            f"read_mode={normalized_read_mode!r} allowed={sorted(ALLOWED_GRAPH_PROJECTION_READ_MODES)}",
        ),
        _readiness_check(
            "write_mode_allowed",
            normalized_write_mode in ALLOWED_GRAPH_PROJECTION_WRITE_MODES,
            f"write_mode={normalized_write_mode!r} allowed={sorted(ALLOWED_GRAPH_PROJECTION_WRITE_MODES)}",
        ),
        _readiness_check(
            "read_mode_pre_live_safe",
            normalized_read_mode in {"a_only", "b_canary"},
            "pre-live rollout must stay on a_only or scoped b_canary; b_primary requires live DB parity evidence",
        ),
        _readiness_check(
            "b_canary_has_project_scope",
            normalized_read_mode != "b_canary" or bool(projects),
            "b_canary requires at least one explicit canary project",
        ),
        _readiness_check(
            "write_mode_pre_live_safe",
            normalized_write_mode in {"off", "shadow"},
            "pre-live rollout must not enable write_mode=on before a bounded dry-run passes",
        ),
        _readiness_check(
            "backfill_dry_run_required",
            bool(backfill_dry_run),
            "first tenant rollout check must run backfill in dry-run mode",
        ),
        _readiness_check(
            "backfill_limit_bounded",
            backfill_limit is not None and 0 < int(backfill_limit) <= max_limit,
            f"dry-run limit must be between 1 and {max_limit}; got {backfill_limit!r}",
        ),
    ]

    for name in sorted(migration_checks):
        checks.append(
            _readiness_check(
                f"migration_precondition_{name}",
                bool(migration_checks[name]),
                f"required migration precondition {name} present={bool(migration_checks[name])}",
            )
        )

    for name in sorted(failure_isolation_checks):
        checks.append(
            _readiness_check(
                f"failure_isolation_{name}",
                bool(failure_isolation_checks[name]),
                f"required failure isolation guard {name} present={bool(failure_isolation_checks[name])}",
            )
        )

    ready = all(check.passed for check in checks)
    return GraphProjectionRolloutReadinessReport(
        mode="pre_live_db_dry_run_readiness",
        live_db_validated=False,
        ready_for_live_db_dry_run=ready,
        closure_claim=False,
        read_mode=normalized_read_mode,
        write_mode=normalized_write_mode,
        canary_projects=projects,
        backfill_dry_run=bool(backfill_dry_run),
        backfill_limit=backfill_limit,
        max_dry_run_limit=max_limit,
        checks=checks,
        live_db_gap=[
            "alembic current/upgrade against a configured tenant schema still must be run",
            "scripts/backfill_graph_nodes.py --dry-run still must be run against a live tenant DB",
            "b_canary or b_primary read-mode parity still must be compared against seeded tenant data",
        ],
    )


def build_graph_projection_dry_run(graph: Graph, *, schema_version: str = "v1") -> GraphProjectionDryRunReport:
    """Build a deterministic no-DB projection report for rollout evidence.

    The report mirrors storage canonicalization and in-graph edge endpoint
    resolution without touching tenant tables. It is intentionally not live DB
    migration evidence.
    """
    schema = schema_version or "v1"
    nodes_by_key: dict[str, GraphProjectionDryRunNode] = {}
    attempted_node_count = 0
    duplicate_node_attempts = 0
    skipped_node_count = 0

    for node in graph.nodes.values():
        attempted_node_count += 1
        node_type = normalize_node_type(node.type)
        canonical_id = normalize_canonical_node_id(node.id)
        if not node_type or not canonical_id:
            skipped_node_count += 1
            continue
        properties = normalize_node_properties(node.properties)
        key = f"{node_type}:{canonical_id}"
        if key in nodes_by_key:
            duplicate_node_attempts += 1
        nodes_by_key[key] = GraphProjectionDryRunNode(
            key=key,
            node_type=node_type,
            canonical_id=canonical_id,
            display_name=GraphNodeWriter._display_name(properties),
            properties=properties,
            source_doc_id=GraphNodeWriter._source_doc_id(node_type, canonical_id),
            node_schema_version=schema,
        )

    edges: list[GraphProjectionDryRunEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    duplicate_edge_attempts = 0

    for edge in graph.edges:
        edge_type = GraphNodeWriter._normalize_edge_type(edge.type)
        from_type = normalize_node_type(edge.from_node.type)
        from_id = normalize_canonical_node_id(edge.from_node.id)
        to_type = normalize_node_type(edge.to_node.type)
        to_id = normalize_canonical_node_id(edge.to_node.id)
        from_key = f"{from_type}:{from_id}" if from_type and from_id else ""
        to_key = f"{to_type}:{to_id}" if to_type and to_id else ""

        missing: list[str] = []
        if not from_key or from_key not in nodes_by_key:
            missing.append("from")
        if not to_key or to_key not in nodes_by_key:
            missing.append("to")
        resolved = not missing

        duplicate = False
        if resolved:
            sig = (edge_type, from_key, to_key)
            if sig in seen_edges:
                duplicate = True
                duplicate_edge_attempts += 1
            else:
                seen_edges.add(sig)

        skip_reason = None
        if missing:
            skip_reason = f"missing_{'_and_'.join(missing)}_endpoint"
        elif duplicate:
            skip_reason = "duplicate_edge"

        edge_props = edge.properties if isinstance(edge.properties, dict) else {}
        edges.append(
            GraphProjectionDryRunEdge(
                edge_type=edge_type,
                from_key=from_key,
                to_key=to_key,
                resolved=resolved,
                duplicate=duplicate,
                skip_reason=skip_reason,
                properties=normalize_node_properties(edge_props),
            )
        )

    resolved_edge_attempts = sum(1 for edge in edges if edge.resolved)
    writeable_edge_count = sum(1 for edge in edges if edge.resolved and not edge.duplicate)
    unresolved_edge_count = sum(1 for edge in edges if not edge.resolved)

    return GraphProjectionDryRunReport(
        mode="no_db_dry_run",
        schema_version=schema,
        live_db_validated=False,
        attempted_node_count=attempted_node_count,
        unique_node_count=len(nodes_by_key),
        duplicate_node_attempts=duplicate_node_attempts,
        skipped_node_count=skipped_node_count,
        candidate_edge_count=len(edges),
        resolved_edge_attempts=resolved_edge_attempts,
        writeable_edge_count=writeable_edge_count,
        unresolved_edge_count=unresolved_edge_count,
        duplicate_edge_attempts=duplicate_edge_attempts,
        nodes=sorted(nodes_by_key.values(), key=lambda node: node.key),
        edges=edges,
        live_db_gap=[
            "alembic current/upgrade against a configured tenant schema was not run",
            "scripts/backfill_graph_nodes.py --dry-run against a live tenant DB was not run",
            "b_primary read-mode parity against seeded tenant data was not run",
        ],
    )
