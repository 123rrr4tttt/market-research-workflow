"""Read a versioned project declaration and compile a pure retrieval preview.

The checked-in declaration is a snapshot of source-owned research files. Reading
it never refreshes those files, and compiling a preview never searches, creates
an attempt, or claims that a historical query result belongs to a new run.
"""
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from functorial_kit import Failure

from .failures import retrieval_failure


_PROJECTS = Path(__file__).resolve().parents[2] / "project_customization" / "projects"
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_LIMIT_KEYS = ("max_queries", "max_materials", "max_followups")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _mode_rejected(message: str, *, site: str) -> Failure:
    return retrieval_failure("MODE_INVALID", message, site=site)


def _require_unique_ids(rows: object, key: str) -> dict[str, Mapping[str, Any]] | Failure:
    if not isinstance(rows, list):
        return _mode_rejected(f"{key} collection must be a list", site=f"mode.{key}")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key]:
            return _mode_rejected(f"entry lacks {key}", site=f"mode.{key}")
        if row[key] in result:
            return _mode_rejected(f"duplicate {key}: {row[key]}", site=f"mode.{key}")
        result[row[key]] = row
    return result


def _validate(snapshot: Mapping[str, Any], project_key: str) -> Failure | None:
    if snapshot.get("schema") != "mrw.project-retrieval-mode.v1":
        return _mode_rejected("unsupported retrieval mode schema", site="mode.schema")
    if snapshot.get("project_key") != project_key:
        return _mode_rejected("retrieval mode belongs to another project", site="mode.project_key")
    for field in ("mode_id", "version", "source_revision"):
        if not isinstance(snapshot.get(field), str) or not snapshot[field]:
            return _mode_rejected(f"retrieval mode needs {field}", site=f"mode.{field}")
    limits = snapshot.get("limits")
    if not isinstance(limits, dict) or set(limits) != set(_LIMIT_KEYS):
        return _mode_rejected("retrieval mode has invalid limits", site="mode.limits")
    for field in _LIMIT_KEYS:
        if type(limits[field]) is not int or limits[field] < (0 if field == "max_followups" else 1):
            return _mode_rejected(f"retrieval mode has invalid {field}", site=f"mode.limits.{field}")
    if not isinstance(snapshot.get("domain_vocabulary"), dict):
        return _mode_rejected("retrieval mode needs domain vocabulary", site="mode.domain_vocabulary")
    if not isinstance(snapshot.get("source_snapshot"), dict):
        return _mode_rejected("retrieval mode needs source snapshot", site="mode.source_snapshot")
    routes = _require_unique_ids(snapshot.get("routes"), "route_id")
    if isinstance(routes, Failure):
        return routes
    queries = _require_unique_ids(snapshot.get("queries"), "query_id")
    if isinstance(queries, Failure):
        return queries
    source_registry = _require_unique_ids(snapshot.get("source_registry", []), "source_id")
    if isinstance(source_registry, Failure):
        return source_registry
    for source in source_registry.values():
        route_ids = source.get("route_ids")
        if (not isinstance(route_ids, list) or not route_ids
                or any(not isinstance(item, str) or item not in routes for item in route_ids)
                or len(route_ids) != len(set(route_ids))):
            return _mode_rejected(f"source {source['source_id']} has invalid route_ids", site="mode.source_registry.route_ids")
        if not isinstance(source.get("url"), str) or not source["url"].startswith(("https://", "http://")):
            return _mode_rejected(f"source {source['source_id']} has invalid URL", site="mode.source_registry.url")
        path = source.get("snapshot_path")
        if (not isinstance(path, str) or not path or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts):
            return _mode_rejected(f"source {source['source_id']} has invalid snapshot_path", site="mode.source_registry.snapshot_path")
    for route in routes.values():
        if not isinstance(route.get("label"), str) or not route["label"]:
            return _mode_rejected("route needs label", site="mode.routes.label")
        ids = route.get("query_ids")
        if (not isinstance(ids, list) or any(not isinstance(item, str) for item in ids)
                or len(ids) != len(set(ids))):
            return _mode_rejected(f"route {route['route_id']} has invalid query_ids", site="mode.routes.query_ids")
        for query_id in ids:
            if query_id not in queries or queries[query_id].get("route_id") != route["route_id"]:
                return _mode_rejected(f"route {route['route_id']} refers to an unrelated query", site="mode.routes.query_ids")
    for query in queries.values():
        owner_id = query.get("route_id")
        if (not isinstance(owner_id, str) or owner_id not in routes
                or query["query_id"] not in routes[owner_id]["query_ids"]):
            return _mode_rejected(f"query {query['query_id']} has no owning route", site="mode.queries.route_id")
        if not isinstance(query.get("expression"), str) or not query["expression"].strip():
            return _mode_rejected(f"query {query['query_id']} has no expression", site="mode.queries.expression")
    return None


def _load_mode_result(project_key: str, *, version: str | None = None) -> dict[str, Any] | Failure:
    if not _PROJECT_KEY.fullmatch(project_key):
        return _mode_rejected("invalid project key", site="load_mode.project_key")
    if version is not None and (not version or not re.fullmatch(r"[A-Za-z0-9_.-]+", version)):
        return _mode_rejected("invalid retrieval mode version", site="load_mode.version")
    directory = _PROJECTS / project_key
    current_path = directory / "retrieval_mode.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    if not isinstance(current, dict):
        return _mode_rejected("retrieval mode root must be an object", site="load_mode.root")
    invalid = _validate(current, project_key)
    if invalid is not None:
        return invalid
    if version is None or version == current["version"]:
        return current
    path = directory / f"retrieval_mode.v{version}.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        return _mode_rejected("retrieval mode root must be an object", site="load_mode.historical_root")
    invalid = _validate(snapshot, project_key)
    if invalid is not None:
        return invalid
    if snapshot["version"] != version:
        return _mode_rejected("requested retrieval mode version does not match snapshot", site="load_mode.historical_version")
    return snapshot


def load_mode(project_key: str, *, version: str | None = None) -> dict[str, Any]:
    """Read a checked-in snapshot, retaining the public ValueError contract."""
    result = _load_mode_result(project_key, version=version)
    if isinstance(result, Failure):
        # kit:boundary owner=project_retrieval.mode.file_entry class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_load_mode_rejects_invalid_project_key
        raise ValueError(result.message)
    return result


def current_mode(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The small project mode view used by the frontend selector."""
    return {
        "project_key": snapshot["project_key"], "mode_id": snapshot["mode_id"],
        "version": snapshot["version"], "source_revision": snapshot["source_revision"],
        "routes": [{"route_id": route["route_id"], "label": route["label"],
                    "query_ids": list(route["query_ids"])}
                   for route in snapshot["routes"] if route.get("status") == "active"],
        "queries": [{"query_id": query["query_id"], "route_id": query["route_id"],
                     "expression": query["expression"]} for query in snapshot["queries"]],
        "outline_summary": dict(snapshot.get("outline_summary") or {}),
        "domain_vocabulary": dict(snapshot["domain_vocabulary"]),
        "evidence_contract": "retrieval.evidence.v2",
        "source_registry_count": len(snapshot.get("source_registry") or []),
        "limits": dict(snapshot["limits"]),
    }


def _compile_preview_result(
    snapshot: Mapping[str, Any], *, route_id: str,
    query_ids: Sequence[str] | None = None, limits: Mapping[str, int] | None = None,
) -> dict[str, Any] | Failure:
    """Compile an immutable-intent plan; execution owns attempt and topology IDs."""
    invalid = _validate(snapshot, str(snapshot.get("project_key", "")))
    if invalid is not None:
        return invalid
    routes = {route["route_id"]: route for route in snapshot["routes"]}
    route = routes.get(route_id)
    if route is None or route.get("status") != "active":
        return retrieval_failure("PLAN_INVALID", "unknown or inactive retrieval route", site="compile_preview.route_id")
    ceilings = snapshot["limits"]
    if limits is None:
        selected_limits = dict(ceilings)
    else:
        if not isinstance(limits, Mapping) or not set(limits).issubset(_LIMIT_KEYS):
            return retrieval_failure("PLAN_INVALID", "invalid retrieval limits", site="compile_preview.limits")
        selected_limits = {key: limits.get(key, ceilings[key]) for key in _LIMIT_KEYS}
    for key, maximum in ceilings.items():
        value = selected_limits[key]
        if type(value) is not int or value < (0 if key == "max_followups" else 1) or value > maximum:
            return retrieval_failure("PLAN_INVALID", f"{key} must stay within the mode budget", site=f"compile_preview.limits.{key}")
    selected_ids = list(route["query_ids"][:selected_limits["max_queries"]]) if query_ids is None else list(query_ids)
    if (not selected_ids or any(not isinstance(item, str) for item in selected_ids)
            or len(selected_ids) != len(set(selected_ids)) or len(selected_ids) > selected_limits["max_queries"]
            or any(item not in route["query_ids"] for item in selected_ids)):
        return retrieval_failure("PLAN_INVALID", "query_ids must be a nonempty, unique subset of the route within budget", site="compile_preview.query_ids")
    query_map = {query["query_id"]: query for query in snapshot["queries"]}
    selected_queries = [dict(query_map[query_id]) for query_id in selected_ids]
    source = dict(snapshot["source_snapshot"])
    basis = {"project_key": snapshot["project_key"], "mode_id": snapshot["mode_id"],
             "mode_version": snapshot["version"], "source_revision": snapshot["source_revision"],
             "route_id": route_id, "query_ids": selected_ids, "queries": selected_queries,
             "limits": selected_limits, "evidence_contract": "retrieval.evidence.v2"}
    plan_id = "retrieval-plan:" + sha256(_canonical(basis)).hexdigest()
    # This is an intent projection only. No historical query status or attempt is
    # copied into the new source bundle.
    topology_seed = {
        "namespace": "retrieval", "source_revision": snapshot["source_revision"],
        "domain_vocabulary": dict(snapshot["domain_vocabulary"]),
        "domain_source_ref": dict(snapshot["domain_source_ref"]),
        "source_routes": [{"route_id": route_id, "pool": route["pool"],
                           "outline_anchor": route["outline_anchor"],
                           "outline_section": "；".join(route["outline_sections"]),
                           "perspective": "；".join(route["perspectives"]),
                           "proposed_node_type": "；".join(route["node_types"]),
                           "proposed_edge_type": "；".join(route["target_edges"]),
                           "entry": "；".join(route["source_leads"]),
                           "status": "planned"}],
        "keyword_plans": [{"plan_id": query["query_id"], "kind": "query",
                           "expression": query["expression"], "source_route_id": route_id,
                           "execution_status": "not_executed"} for query in selected_queries],
        "attempts": [], "candidates": [], "gaps": [],
        "source_registry": [{
            "source_id": source["source_id"], "route_id": route_id,
            "url": source["url"], "status": source["status"],
            "snapshot_path": source["snapshot_path"],
        } for source in snapshot.get("source_registry", []) if route_id in source["route_ids"]],
    }
    return {
        **basis, "plan_id": plan_id, "queries": selected_queries,
        "steps": [{"kind": "discover_candidates", "query_id": query_id} for query_id in selected_ids]
                 + [{"kind": "review_candidates", "max_materials": selected_limits["max_materials"]},
                    {"kind": "fetch_materials"}, {"kind": "read_materials"},
                    {"kind": "judge_materials"}, {"kind": "validate_evidence"}]
                 + ([{"kind": "followup_search", "max_rounds": selected_limits["max_followups"]}]
                    if selected_limits["max_followups"] else [])
                 + [{"kind": "write_topology"}, {"kind": "report"}],
        "diagnostics": [], "source_snapshot": source,
        "domain_vocabulary": dict(snapshot["domain_vocabulary"]),
        "topology_seed": topology_seed,
    }


def compile_preview(
    snapshot: Mapping[str, Any], *, route_id: str,
    query_ids: Sequence[str] | None = None, limits: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Preserve the public ValueError contract for an invalid preview intent."""
    result = _compile_preview_result(snapshot, route_id=route_id, query_ids=query_ids, limits=limits)
    if isinstance(result, Failure):
        # kit:boundary owner=project_retrieval.mode.preview_entry class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_preview_rejects_cross_route_queries_and_budget_increase
        raise ValueError(result.message)
    return result
