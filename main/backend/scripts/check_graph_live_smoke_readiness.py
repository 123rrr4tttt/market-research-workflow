#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph.persistence.graph_live_smoke_readiness import build_graph_live_smoke_readiness
from app.services.graph.persistence.graph_projection_contract import (
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)
from app.settings.config import settings

from check_graph_projection_contract import (  # noqa: E402
    DEFAULT_MIGRATION_ROOT,
    _failure_isolation_checks,
    _fixture_graph,
    _migration_checks,
    _split_projects,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
FRONTEND_ROOT = REPO_ROOT / "main" / "frontend-modern"


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return data if isinstance(data, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def _contains_all(source: str, needles: list[str]) -> bool:
    return all(needle in source for needle in needles)


def _frontend_contract_checks(frontend_root: Path) -> dict[str, bool]:
    package_text = _read_file(frontend_root / "package.json")
    try:
        package_json = json.loads(package_text)
    except json.JSONDecodeError:
        package_json = {}
    scripts = package_json.get("scripts") if isinstance(package_json, dict) else {}
    scripts = scripts if isinstance(scripts, dict) else {}
    graph_page = _read_file(frontend_root / "src" / "pages" / "GraphPage.tsx")
    force_checker = _read_file(frontend_root / "scripts" / "check_graph_force3d_frontend_contract.mjs")
    e2e = _read_file(frontend_root / "tests" / "e2e" / "graphpage.spec.ts")
    return {
        "force3d_contract_script_registered": scripts.get("check:graph-force3d-frontend-contract")
        == "node scripts/check_graph_force3d_frontend_contract.mjs",
        "force3d_contract_checker_exists": bool(force_checker)
        and "Graph force3d frontend contract check passed" in force_checker,
        "graphpage_backend_data_query_uses_api_wrappers": _contains_all(
            graph_page,
            [
                "getGraphConfig",
                "getMarketGraph",
                "getPolicyGraph",
                "getSocialGraph",
                "useQuery",
            ],
        ),
        "graphpage_force3d_debug_stats_exposed": _contains_all(
            graph_page,
            [
                "window.__graph3dDebug = debugApi",
                "getVisibilityStats: () => force3DVisibilityStatsGetterRef.current()",
                'data-testid="graph-force3d-canvas-host"',
            ],
        ),
        "mocked_force3d_e2e_exists": _contains_all(
            e2e,
            [
                "graph page renders force3d canvas backed by graph scene nodes",
                "graph-force3d-canvas-host",
                "__graph3dDebug",
            ],
        ),
    }


def _backend_data_contract_checks(repo_root: Path) -> dict[str, bool]:
    admin_source = _read_file(repo_root / "main" / "backend" / "app" / "api" / "admin.py")
    endpoints_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "endpoints.ts")
    graph_api_source = _read_file(
        repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "domains" / "graph-workflow.ts"
    )
    return {
        "admin_backend_data_graph_routes_exist": _contains_all(
            admin_source,
            [
                '@router.get("/market-graph"',
                '@router.get("/policy-graph"',
                '@router.get("/content-graph"',
                "def get_market_graph",
                "def get_policy_graph",
                "def get_content_graph",
            ],
        ),
        "admin_graph_routes_use_failure_isolation_tail": _contains_all(
            admin_source,
            [
                "_finalize_graph_response(",
                "_rollback_quietly(session, context=\"graph_b_write\")",
                "_rollback_quietly(session, context=\"graph_b_read\")",
                "graph_b_read_fallback_to_a",
            ],
        ),
        "frontend_backend_data_endpoints_exist": _contains_all(
            endpoints_source,
            [
                "marketGraph:",
                "policyGraph:",
                "contentGraph:",
                "/admin/market-graph",
                "/admin/policy-graph",
                "/admin/content-graph",
            ],
        ),
        "frontend_backend_data_wrappers_exist": _contains_all(
            graph_api_source,
            [
                "export async function getMarketGraph",
                "export async function getPolicyGraph",
                "export async function getSocialGraph",
                "endpoints.admin.marketGraph",
                "endpoints.admin.policyGraph",
                "endpoints.admin.contentGraph",
            ],
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify Wave12 graph live smoke readiness without claiming closure")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--database-url", default=str(settings.database_url or ""))
    parser.add_argument("--read-mode", default=str(settings.graph_node_projection_read_mode or "a_only"))
    parser.add_argument("--write-mode", default=str(settings.graph_node_projection_write_mode or "shadow"))
    parser.add_argument("--canary-projects", default=str(settings.graph_node_projection_canary_projects or "demo_proj"))
    parser.add_argument("--backfill-limit", type=int, default=10)
    parser.add_argument("--max-dry-run-limit", type=int, default=1000)
    parser.add_argument("--migration-root", default=str(DEFAULT_MIGRATION_ROOT))
    parser.add_argument("--live-db-evidence-json", default="")
    parser.add_argument("--frontend-backend-evidence-json", default="")
    args = parser.parse_args()

    no_db_report = build_graph_projection_dry_run(_fixture_graph())
    readiness_report = build_graph_projection_rollout_readiness(
        read_mode=args.read_mode,
        write_mode=args.write_mode,
        canary_projects=_split_projects(args.canary_projects),
        backfill_dry_run=True,
        backfill_limit=args.backfill_limit,
        migration_checks=_migration_checks(Path(args.migration_root)),
        failure_isolation_checks=_failure_isolation_checks(),
        max_dry_run_limit=args.max_dry_run_limit,
    )
    report = build_graph_live_smoke_readiness(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        database_url=args.database_url,
        frontend_contract_checks=_frontend_contract_checks(FRONTEND_ROOT),
        backend_data_contract_checks=_backend_data_contract_checks(REPO_ROOT),
        live_db_evidence=_read_json(args.live_db_evidence_json),
        frontend_backend_evidence=_read_json(args.frontend_backend_evidence_json),
    )
    payload = report.to_dict()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={payload['status']}")
        print(f"closure_claim={payload['closure_claim']}")
        print(f"live_db_validated={payload['live_db_validated']}")
        print(f"frontend_backend_data_smoke_validated={payload['frontend_backend_data_smoke_validated']}")
        for stage in payload["stages"]:
            print(f"{stage['name']}={stage['status']} passed={stage['passed']} validated={stage['validated']}")
        if payload["remaining_live_gaps"]:
            print("remaining_live_gaps:")
            for gap in payload["remaining_live_gaps"]:
                print(f"- {gap}")
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
