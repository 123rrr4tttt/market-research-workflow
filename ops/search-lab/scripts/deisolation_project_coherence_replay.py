#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.agent_core import AgentCore, AgentCoreRequest, CoreModelStep, CoreToolCall, FakeCoreProvider, build_project_core_tool_registry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.local_index import LocalIndexChunk, LocalIndexQuery, LocalIndexService
from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available
from app.services.source_library.source_candidate_trust import build_source_candidate_plan


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_agent_searxng_search(project_key: str, query: str, max_results: int) -> tuple[dict[str, Any], list[str]]:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="SearXNG de-isolation coherence replay",
        project_key=project_key,
        task_blueprints=[],
    )
    registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
    provider = FakeCoreProvider(
        [
            CoreModelStep.tools(
                CoreToolCall(
                    tool_name="source.web.search",
                    call_id="call-searxng-coherence",
                    arguments={
                        "query": query,
                        "provider": "searxng",
                        "language": "en",
                        "max_results": max_results,
                        "min_trust_score": 40,
                    },
                )
            ),
            CoreModelStep.final("已完成 SearXNG 外部搜索候选召回。"),
        ]
    )
    out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
        AgentCoreRequest(
            message="Use SearXNG to find external robotics policy source candidates.",
            session_id=bundle["session"]["session_id"],
            project_key=project_key,
        )
    )
    sse_lines = [f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}" for event in out.events]
    result = out.tool_results[0].structured_content if out.tool_results else {}
    summary = {
        "status": out.stop_reason,
        "final_answer": out.final_answer,
        "tool_result_count": len(out.tool_results),
        "candidate_count": result.get("candidate_count", 0),
        "accepted_candidate_count": result.get("accepted_candidate_count", 0),
        "provider": result.get("provider"),
        "provider_diagnostics": result.get("provider_diagnostics"),
        "candidates": result.get("candidates", []),
    }
    return summary, sse_lines


def build_candidate_review(project_key: str, query: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    urls = [item.get("url") or item.get("link") or item.get("normalized_url") for item in candidates]
    return build_source_candidate_plan(
        project_key=project_key,
        query=query,
        urls=urls,
        source_library_items=[],
        max_candidates=20,
        min_trust_score=40,
    )


def run_lancedb_material_retrieval(dataset_dir: Path, query: str) -> dict[str, Any]:
    chunks = _read_jsonl(dataset_dir / "chunks.jsonl", limit=80)
    local_chunks = [
        LocalIndexChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            source_id=str(row["source_id"]),
            source_type=str(row.get("source_type") or "material"),
            title=str(row.get("title") or ""),
            url=str(row.get("url") or ""),
            content=str(row.get("content") or ""),
            language=str(row.get("language") or "mixed"),
            created_at=str(row.get("created_at") or ""),
            metadata=dict(row.get("metadata") or {}),
        )
        for row in chunks
    ]
    if not is_lancedb_available():
        return {
            "backend_replay_status": "blocked_by_env",
            "frontend_status": "blocked_by_env",
            "error_type": "MissingOptionalDependency",
            "error": "lancedb is not available on PYTHONPATH",
            "result_count": 0,
            "results": [],
        }
    service = LocalIndexService(LanceDBLocalIndexAdapter())
    upsert_status = service.upsert_chunks(local_chunks)
    results = service.search(LocalIndexQuery(query=query, project_id="latest-dev-docs", top_k=10))
    result_payload = [item.to_dict() for item in results]
    return {
        "backend_replay_status": "passed",
        "frontend_status": "blocked_by_env",
        "frontend_blocker": "No frontend dev server/e2e session was started in this replay; backend material retrieval evidence is provided.",
        "query": query,
        "upsert_status": upsert_status,
        "result_count": len(result_payload),
        "results": result_payload,
        "selected_context": result_payload[:3],
        "boundary": {
            "source_library_schema_modified": False,
            "indexed_records": "fetched document/material chunks only",
            "required_fields": ["document_id", "chunk_id", "source_id", "title", "content"],
        },
    }


def write_summary(path: Path, *, agent_summary: dict[str, Any], review: dict[str, Any], material: dict[str, Any]) -> None:
    lines = [
        "# De-Isolation Project Coherence Summary",
        "",
        "## Status",
        "",
        f"- backend_replay_status: {'passed' if agent_summary.get('candidate_count', 0) >= 10 and material.get('backend_replay_status') == 'passed' else 'failed'}",
        f"- frontend_status: {material.get('frontend_status')}",
        "",
        "## Chain A: Agent SearXNG Search",
        "",
        f"- provider: {agent_summary.get('provider')}",
        f"- candidate_count: {agent_summary.get('candidate_count')}",
        f"- accepted_candidate_count: {agent_summary.get('accepted_candidate_count')}",
        f"- auto_chain_unchanged: {'searxng' in (agent_summary.get('provider_diagnostics') or {}).get('explicit_experimental_providers', [])}",
        "",
        "## Chain B: Source Candidate Review",
        "",
        f"- candidate_urls: {(review.get('counts') or {}).get('candidate_urls')}",
        f"- rejected_urls: {(review.get('counts') or {}).get('rejected_urls')}",
        f"- next_gate: {review.get('next_gate')}",
        "",
        "## Chain C/D: Writing Material Retrieval And Local Index",
        "",
        f"- backend_replay_status: {material.get('backend_replay_status')}",
        f"- result_count: {material.get('result_count')}",
        "- local_index_backend: LanceDB FTS prototype",
        "- source_library_schema_modified: false",
        "",
        "## Remaining Work",
        "",
        "- Run browser/e2e WritingWorkbench flow once the frontend stack is available.",
        "- Add vector/hybrid LanceDB retrieval before treating it as the final local index backend.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="development/latest-dev-docs/automation-runs/deisolation-project-coherence/2026-05-14")
    parser.add_argument("--dataset-dir", default="development/latest-dev-docs/automation-runs/local-index-backend-evaluation/2026-05-14/dataset")
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--query", default="robotics policy national commission")
    parser.add_argument("--material-query", default="source_library database boundary")
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    agent_summary, sse_lines = run_agent_searxng_search(args.project_key, args.query, args.max_results)
    (out_dir / "agent_searxng_search.sse.txt").write_text("\n\n".join(sse_lines) + "\n", encoding="utf-8")
    _write_json(out_dir / "agent_searxng_search.summary.json", agent_summary)

    review = build_candidate_review(args.project_key, args.query, list(agent_summary.get("candidates") or []))
    _write_json(out_dir / "source_candidate_review_from_searxng.json", review)

    material = run_lancedb_material_retrieval(Path(args.dataset_dir), args.material_query)
    _write_json(out_dir / "writing_workbench_material_retrieval.json", material)
    with (out_dir / "local_index_lancedb_project_prototype.jsonl").open("w", encoding="utf-8") as f:
        for item in material.get("results") or []:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    (out_dir / "README.md").write_text(
        "# De-Isolation Project Coherence Replay\n\n"
        "This run verifies backend coherence across SearXNG agent search, source candidate review, and LanceDB local material retrieval. "
        "Frontend WritingWorkbench e2e is marked blocked_by_env in this replay.\n",
        encoding="utf-8",
    )
    write_summary(out_dir / "coherence_summary.md", agent_summary=agent_summary, review=review, material=material)
    ok = agent_summary.get("candidate_count", 0) >= 10 and material.get("backend_replay_status") == "passed"
    print(json.dumps({"out_dir": str(out_dir), "ok": ok, "candidate_count": agent_summary.get("candidate_count"), "material_result_count": material.get("result_count")}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
