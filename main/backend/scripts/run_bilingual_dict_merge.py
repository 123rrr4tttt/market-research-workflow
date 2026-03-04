#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import delete, func, or_, select

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.models.base import SessionLocal
from app.models.entities import GraphEdgeRecord, GraphNodeAliasRecord, GraphNodeRecord
from app.services.graph.node_merge_llm import is_merge_eligible_node
from app.services.graph.node_merge_scheduler import rank_candidates
from app.services.llm.provider import get_chat_model
from app.services.projects.context import bind_project


_ALIAS_SPLIT_RE = re.compile(r"[|,;/\\\n]+")
_NORM_SPACE_RE = re.compile(r"\s+")


@dataclass
class NodeRow:
    node_id: int
    node_type: str
    canonical_id: str
    display_name: str
    properties: dict[str, Any]
    aliases: list[str]
    alias_norms: set[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_alias(value: str) -> str:
    text = str(value or "").strip().lower()
    text = _NORM_SPACE_RE.sub(" ", text)
    return text


def _extract_alias_candidates(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for token in _ALIAS_SPLIT_RE.split(text):
        val = str(token or "").strip()
        if not val:
            continue
        key = _normalize_alias(val)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(val)
    return out


def _heuristic_bilingual_aliases(node: NodeRow) -> list[str]:
    base_texts = [node.display_name, node.canonical_id, *node.aliases]
    out: list[str] = []
    seen: set[str] = set()
    for raw in base_texts:
        txt = str(raw or "").strip()
        if not txt:
            continue

        variants = {
            txt,
            txt.lower(),
            txt.upper(),
            txt.replace("_", " "),
            txt.replace("-", " "),
            txt.replace(" ", ""),
            txt.replace("（", "(").replace("）", ")"),
        }
        for item in variants:
            val = str(item or "").strip()
            norm = _normalize_alias(val)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            out.append(val)
    return out


def _generate_aliases_with_llm(node: NodeRow, *, model_name: str, max_aliases: int) -> list[str]:
    prompt = (
        "You are generating bilingual aliases for graph node deduplication. "
        "Return strict JSON object: {\"aliases\": [\"...\"]}. "
        "Only include aliases that refer to the exact same entity/concept. "
        "Keep concise, no explanation.\n"
        f"node_type={node.node_type}\n"
        f"display_name={node.display_name}\n"
        f"canonical_id={node.canonical_id}\n"
        f"existing_aliases={json.dumps(node.aliases, ensure_ascii=False)}\n"
        f"max_aliases={max_aliases}"
    )
    model = get_chat_model(model=model_name, temperature=0.0, max_tokens=300)
    raw = getattr(model.invoke(prompt), "content", "")
    if isinstance(raw, list):
        raw = "\n".join(str(x) for x in raw)
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except Exception:
        return []
    aliases = payload.get("aliases") if isinstance(payload, dict) else []
    if not isinstance(aliases, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in aliases:
        val = str(item or "").strip()
        norm = _normalize_alias(val)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(val)
    return out[:max_aliases]


def _load_nodes(session, node_type: str | None, limit: int | None) -> list[NodeRow]:
    stmt = select(GraphNodeRecord).order_by(GraphNodeRecord.updated_at.desc())
    if node_type:
        stmt = stmt.where(GraphNodeRecord.node_type == node_type)
    if limit and limit > 0:
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        return []

    node_ids = [int(r.id) for r in rows]
    alias_rows = session.execute(
        select(GraphNodeAliasRecord).where(GraphNodeAliasRecord.node_id.in_(node_ids))
    ).scalars().all()
    alias_map: dict[int, list[GraphNodeAliasRecord]] = {}
    for row in alias_rows:
        alias_map.setdefault(int(row.node_id), []).append(row)

    out: list[NodeRow] = []
    for row in rows:
        aliases = [str(a.alias_text) for a in alias_map.get(int(row.id), [])]
        alias_norms = {_normalize_alias(str(a.alias_norm or "")) for a in alias_map.get(int(row.id), [])}
        alias_norms = {x for x in alias_norms if x}
        out.append(
            NodeRow(
                node_id=int(row.id),
                node_type=str(row.node_type),
                canonical_id=str(row.canonical_id),
                display_name=str(row.display_name or ""),
                properties=row.properties if isinstance(row.properties, dict) else {},
                aliases=aliases,
                alias_norms=alias_norms,
            )
        )
    return out


def _node_cache_key(node: NodeRow) -> str:
    return f"{node.node_type}::{node.canonical_id}"


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "entries": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        payload["entries"] = {}
    payload.setdefault("version", 1)
    return payload


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_llm_alias_dict(
    nodes: list[NodeRow],
    *,
    cache_path: Path,
    refresh_cache: bool,
    enable_llm: bool,
    llm_model: str,
    max_llm_nodes: int,
    max_aliases_per_node: int,
    llm_workers: int,
    llm_batch_size: int,
) -> tuple[dict[int, list[str]], dict[str, Any]]:
    cache = _load_cache(cache_path)
    entries: dict[str, Any] = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}

    llm_called = 0
    cache_hits = 0
    generated = 0
    failed = 0
    alias_map: dict[int, list[str]] = {}
    pending_nodes: list[NodeRow] = []

    for node in nodes:
        key = _node_cache_key(node)
        cached = entries.get(key) if isinstance(entries.get(key), dict) else None
        if cached and (not refresh_cache):
            aliases = cached.get("aliases") if isinstance(cached.get("aliases"), list) else []
            alias_map[node.node_id] = [str(x) for x in aliases if str(x).strip()]
            cache_hits += 1
            continue
        pending_nodes.append(node)

    llm_aliases_by_node: dict[int, list[str]] = {}
    if enable_llm:
        effective_workers = max(1, int(llm_workers))
        effective_batch_size = max(1, int(llm_batch_size))
        max_targets = max(0, int(max_llm_nodes))
        llm_targets = pending_nodes[:max_targets]

        for start in range(0, len(llm_targets), effective_batch_size):
            batch = llm_targets[start : start + effective_batch_size]
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                fut_map = {
                    executor.submit(
                        _generate_aliases_with_llm,
                        node,
                        model_name=llm_model,
                        max_aliases=max_aliases_per_node,
                    ): node.node_id
                    for node in batch
                }
                for fut in as_completed(fut_map):
                    node_id = fut_map[fut]
                    llm_called += 1
                    try:
                        llm_aliases_by_node[node_id] = fut.result() or []
                    except Exception:
                        failed += 1
                        llm_aliases_by_node[node_id] = []

    for node in pending_nodes:
        key = _node_cache_key(node)
        aliases = _heuristic_bilingual_aliases(node)
        aliases.extend(llm_aliases_by_node.get(node.node_id, []))

        dedup: list[str] = []
        seen: set[str] = set()
        for item in aliases:
            norm = _normalize_alias(item)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            dedup.append(str(item).strip())

        alias_map[node.node_id] = dedup
        entries[key] = {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "canonical_id": node.canonical_id,
            "display_name": node.display_name,
            "aliases": dedup[:max_aliases_per_node],
            "updated_at": _now_iso(),
        }
        generated += 1

    cache["entries"] = entries
    cache["updated_at"] = _now_iso()
    _save_cache(cache_path, cache)

    stats = {
        "cache_file": str(cache_path),
        "cache_hits": cache_hits,
        "generated": generated,
        "llm_called": llm_called,
        "llm_failed": failed,
    }
    return alias_map, stats


def _build_candidate_rows(nodes: list[NodeRow], llm_aliases: dict[int, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        aliases = list(node.aliases)
        aliases.extend(llm_aliases.get(node.node_id, []))

        dedup_aliases: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            norm = _normalize_alias(alias)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            dedup_aliases.append(str(alias).strip())

        node_text_parts = [node.display_name, node.canonical_id]
        node_text_parts.extend(dedup_aliases[:8])
        node_text = " | ".join([x for x in node_text_parts if str(x).strip()])
        rows.append(
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "display_name": node.display_name,
                "canonical_id": node.canonical_id,
                "properties": node.properties,
                "aliases": dedup_aliases,
                "node_text": node_text,
            }
        )
    return rows


def _group_candidates(
    candidates: list[dict[str, Any]],
    *,
    min_shared_aliases: int,
    max_group_size: int,
) -> list[dict[str, Any]]:
    by_id = {int(c["node_id"]): c for c in candidates}

    eligible: list[dict[str, Any]] = [c for c in candidates if is_merge_eligible_node(c)]
    parent: dict[int, int] = {int(c["node_id"]): int(c["node_id"]) for c in eligible}
    alias_to_nodes: dict[tuple[str, str], set[int]] = {}

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != x:
            nxt = parent[x]
            parent[x] = root
            x = nxt
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for row in eligible:
        node_id = int(row["node_id"])
        node_type = str(row.get("node_type") or "")
        for alias in row.get("aliases") or []:
            norm = _normalize_alias(alias)
            if not norm:
                continue
            alias_to_nodes.setdefault((node_type, norm), set()).add(node_id)

    for _, node_ids in alias_to_nodes.items():
        ids = sorted(node_ids)
        if len(ids) < 2:
            continue
        seed = ids[0]
        for nid in ids[1:]:
            union(seed, nid)

    groups: dict[int, list[int]] = {}
    for node_id in sorted(parent.keys()):
        groups.setdefault(find(node_id), []).append(node_id)

    out: list[dict[str, Any]] = []
    gid = 0
    for node_ids in groups.values():
        if len(node_ids) < 2:
            continue

        node_types = {str(by_id[i].get("node_type") or "") for i in node_ids if i in by_id}
        if len(node_types) != 1:
            continue

        shared_aliases: list[str] = []
        alias_counter: dict[str, int] = {}
        for nid in node_ids:
            for alias in by_id[nid].get("aliases") or []:
                norm = _normalize_alias(alias)
                if not norm:
                    continue
                alias_counter[norm] = alias_counter.get(norm, 0) + 1
        shared_aliases = [k for k, v in alias_counter.items() if v >= 2]
        if len(shared_aliases) < min_shared_aliases:
            continue

        ranked = rank_candidates([by_id[nid] for nid in node_ids])
        if not ranked:
            continue
        target_id = int(ranked[0].node_id)
        source_ids = sorted(dict.fromkeys(node_ids))[:max_group_size]

        gid += 1
        target = by_id[target_id]
        out.append(
            {
                "group_id": gid,
                "node_type": str(target.get("node_type") or ""),
                "source_node_ids": source_ids,
                "target_node_id": target_id,
                "merged_node": {
                    "node_type": str(target.get("node_type") or ""),
                    "display_name": str(target.get("display_name") or ""),
                    "canonical_id": str(target.get("canonical_id") or ""),
                },
                "shared_aliases": shared_aliases[:20],
                "reason": f"shared_aliases={len(shared_aliases)}",
                "confidence": min(1.0, 0.4 + 0.1 * len(shared_aliases)),
            }
        )

    out.sort(key=lambda x: (len(x.get("source_node_ids") or []), x.get("confidence") or 0), reverse=True)
    for idx, row in enumerate(out, start=1):
        row["group_id"] = idx
    return out


def _build_report(
    *,
    project_key: str,
    node_type: str | None,
    nodes: list[NodeRow],
    candidates: list[dict[str, Any]],
    merges: list[dict[str, Any]],
    cache_stats: dict[str, Any],
    apply: bool,
) -> dict[str, Any]:
    type_counter: dict[str, int] = {}
    for row in merges:
        t = str(row.get("node_type") or "")
        type_counter[t] = type_counter.get(t, 0) + 1

    return {
        "generated_at": _now_iso(),
        "project_key": project_key,
        "node_type": node_type,
        "apply": apply,
        "total_nodes": len(nodes),
        "merge_eligible_candidates": len([c for c in candidates if is_merge_eligible_node(c)]),
        "merge_groups": len(merges),
        "merge_groups_by_type": type_counter,
        "cache_stats": cache_stats,
        "merges": merges,
    }


def _snapshot_counts(session) -> dict[str, int]:
    total_nodes = int(session.scalar(select(func.count()).select_from(GraphNodeRecord)) or 0)
    total_edges = int(session.scalar(select(func.count()).select_from(GraphEdgeRecord)) or 0)
    return {"total_nodes": total_nodes, "total_edges": total_edges}


def _apply_single_merge(session, item: dict[str, Any]) -> dict[str, Any]:
    source_ids_raw = item.get("source_node_ids") if isinstance(item.get("source_node_ids"), list) else []
    source_ids: list[int] = []
    for sid in source_ids_raw:
        try:
            source_ids.append(int(sid))
        except Exception:
            continue
    source_ids = sorted(dict.fromkeys(source_ids))
    if len(source_ids) < 2:
        return {"applied": False, "reason": "insufficient_source_ids", "deleted_nodes": 0, "inserted_edges": 0, "inserted_aliases": 0}

    target_node_id = int(item.get("target_node_id") or source_ids[0])
    if target_node_id not in source_ids:
        source_ids = [target_node_id, *source_ids]
        source_ids = sorted(dict.fromkeys(source_ids))

    node_rows = session.execute(select(GraphNodeRecord).where(GraphNodeRecord.id.in_(source_ids))).scalars().all()
    if len(node_rows) < 2:
        return {"applied": False, "reason": "nodes_not_found", "deleted_nodes": 0, "inserted_edges": 0, "inserted_aliases": 0}

    node_type_set = {str(r.node_type) for r in node_rows}
    if len(node_type_set) != 1:
        return {"applied": False, "reason": "mixed_node_types", "deleted_nodes": 0, "inserted_edges": 0, "inserted_aliases": 0}

    target_row = None
    for row in node_rows:
        if int(row.id) == target_node_id:
            target_row = row
            break
    if target_row is None:
        return {"applied": False, "reason": "target_not_found", "deleted_nodes": 0, "inserted_edges": 0, "inserted_aliases": 0}

    delete_ids = [int(r.id) for r in node_rows if int(r.id) != target_node_id]
    if not delete_ids:
        return {"applied": False, "reason": "no_source_to_delete", "deleted_nodes": 0, "inserted_edges": 0, "inserted_aliases": 0}

    alias_rows = session.execute(select(GraphNodeAliasRecord).where(GraphNodeAliasRecord.node_id.in_(source_ids))).scalars().all()
    target_alias_rows = [a for a in alias_rows if int(a.node_id) == target_node_id]
    existing_alias_sig = {(str(a.alias_norm), str(a.alias_type)) for a in target_alias_rows}
    inserted_aliases = 0

    merged_aliases = item.get("shared_aliases") if isinstance(item.get("shared_aliases"), list) else []
    alias_inputs: list[tuple[str, str]] = []
    for row in alias_rows:
        alias_inputs.append((str(row.alias_text), str(row.alias_type)))
    for alias in merged_aliases:
        alias_inputs.append((str(alias), "llm_dict"))

    for alias_text, alias_type in alias_inputs:
        alias_text = str(alias_text or "").strip()
        alias_type = str(alias_type or "raw").strip() or "raw"
        alias_norm = _normalize_alias(alias_text)
        if not alias_norm:
            continue
        sig = (alias_norm, alias_type)
        if sig in existing_alias_sig:
            continue
        alias_exists = session.execute(
            select(GraphNodeAliasRecord.id)
            .where(
                GraphNodeAliasRecord.alias_norm == alias_norm,
                GraphNodeAliasRecord.alias_type == alias_type,
            )
            .limit(1)
        ).first()
        if alias_exists:
            continue
        session.add(
            GraphNodeAliasRecord(
                node_id=target_node_id,
                alias_text=alias_text,
                alias_norm=alias_norm,
                alias_type=alias_type,
            )
        )
        existing_alias_sig.add(sig)
        inserted_aliases += 1

    edge_rows = session.execute(
        select(GraphEdgeRecord).where(
            or_(
                GraphEdgeRecord.from_node_id.in_(source_ids),
                GraphEdgeRecord.to_node_id.in_(source_ids),
            )
        )
    ).scalars().all()

    new_edge_sig: set[tuple[str, int, int]] = set()
    inserted_edges = 0
    for edge in edge_rows:
        from_id = target_node_id if int(edge.from_node_id) in source_ids else int(edge.from_node_id)
        to_id = target_node_id if int(edge.to_node_id) in source_ids else int(edge.to_node_id)
        if from_id == to_id:
            continue
        edge_type = str(edge.edge_type)
        props = edge.properties if isinstance(edge.properties, dict) else {}
        sig = (edge_type, from_id, to_id)
        if sig in new_edge_sig:
            continue
        exists = session.execute(
            select(GraphEdgeRecord.id)
            .where(
                GraphEdgeRecord.edge_type == edge_type,
                GraphEdgeRecord.from_node_id == from_id,
                GraphEdgeRecord.to_node_id == to_id,
            )
            .limit(1)
        ).first()
        if exists:
            continue
        new_edge_sig.add(sig)
        session.add(
            GraphEdgeRecord(
                edge_type=edge_type,
                from_node_id=from_id,
                to_node_id=to_id,
                properties=props,
                edge_schema_version=getattr(edge, "edge_schema_version", "v1") or "v1",
            )
        )
        inserted_edges += 1

    session.execute(
        delete(GraphEdgeRecord).where(
            or_(
                GraphEdgeRecord.from_node_id.in_(delete_ids),
                GraphEdgeRecord.to_node_id.in_(delete_ids),
            )
        )
    )
    session.execute(delete(GraphNodeAliasRecord).where(GraphNodeAliasRecord.node_id.in_(delete_ids)))
    session.execute(delete(GraphNodeRecord).where(GraphNodeRecord.id.in_(delete_ids)))

    return {
        "applied": True,
        "reason": "ok",
        "target_node_id": target_node_id,
        "deleted_nodes": len(delete_ids),
        "inserted_edges": inserted_edges,
        "inserted_aliases": inserted_aliases,
    }


def _apply_merges(session, merges: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    applied = 0
    skipped = 0
    deleted_nodes = 0
    inserted_edges = 0
    inserted_aliases = 0

    for idx, item in enumerate(merges, start=1):
        try:
            with session.begin_nested():
                result = _apply_single_merge(session, item)
        except Exception as exc:
            result = {
                "applied": False,
                "reason": f"exception:{exc}",
                "deleted_nodes": 0,
                "inserted_edges": 0,
                "inserted_aliases": 0,
            }

        if result.get("applied"):
            applied += 1
        else:
            skipped += 1

        deleted_nodes += int(result.get("deleted_nodes") or 0)
        inserted_edges += int(result.get("inserted_edges") or 0)
        inserted_aliases += int(result.get("inserted_aliases") or 0)
        details.append({"idx": idx, "group_id": item.get("group_id"), **result})

    session.commit()
    return {
        "input_merge_items": len(merges),
        "applied_merge_items": applied,
        "skipped_merge_items": skipped,
        "deleted_source_nodes": deleted_nodes,
        "inserted_edges": inserted_edges,
        "inserted_aliases": inserted_aliases,
        "details": details,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bilingual dict driven graph-node merge pipeline")
    parser.add_argument("--project", required=True, help="project key")
    parser.add_argument("--node-type", default=None, help="optional node type filter")
    parser.add_argument("--limit", type=int, default=None, help="max nodes to scan")
    parser.add_argument("--min-shared-aliases", type=int, default=1, help="minimum shared normalized aliases in one group")
    parser.add_argument("--max-group-size", type=int, default=10, help="max source nodes per merge group")
    parser.add_argument("--cache-file", default=None, help="llm_dict cache path")
    parser.add_argument("--refresh-cache", action="store_true", help="ignore cached aliases and rebuild")
    parser.add_argument("--enable-llm", action="store_true", help="call LLM to enrich aliases")
    parser.add_argument("--llm-model", default="gpt-4o-mini", help="LLM model name for alias generation")
    parser.add_argument("--max-llm-nodes", type=int, default=200, help="max nodes to call LLM in one run")
    parser.add_argument("--llm-workers", type=int, default=8, help="parallel workers for LLM alias generation")
    parser.add_argument("--llm-batch-size", type=int, default=50, help="batch size for each LLM generation round")
    parser.add_argument("--max-aliases-per-node", type=int, default=20, help="alias cap per node in cache")
    parser.add_argument("--report-file", default=None, help="output report json path")
    parser.add_argument("--apply", action="store_true", help="apply merge operations")
    parser.add_argument("--print-full-report", action="store_true", help="print full merge list to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cache_path = Path(args.cache_file) if args.cache_file else (project_root / "tmp" / "bilingual_dict_cache" / f"{args.project}.json")
    report_path = Path(args.report_file) if args.report_file else (project_root / "tmp" / "bilingual_dict_merge_report" / f"{args.project}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    with bind_project(args.project):
        with SessionLocal() as session:
            nodes = _load_nodes(session, args.node_type, args.limit)
            llm_aliases, cache_stats = _build_llm_alias_dict(
                nodes,
                cache_path=cache_path,
                refresh_cache=bool(args.refresh_cache),
                enable_llm=bool(args.enable_llm),
                llm_model=str(args.llm_model),
                max_llm_nodes=int(args.max_llm_nodes),
                max_aliases_per_node=int(args.max_aliases_per_node),
                llm_workers=int(args.llm_workers),
                llm_batch_size=int(args.llm_batch_size),
            )
            candidates = _build_candidate_rows(nodes, llm_aliases)
            merges = _group_candidates(
                candidates,
                min_shared_aliases=max(1, int(args.min_shared_aliases)),
                max_group_size=max(2, int(args.max_group_size)),
            )

            report = _build_report(
                project_key=args.project,
                node_type=args.node_type,
                nodes=nodes,
                candidates=candidates,
                merges=merges,
                cache_stats=cache_stats,
                apply=bool(args.apply),
            )

            if args.apply:
                before = _snapshot_counts(session)
                apply_report = _apply_merges(session, merges)
                after = _snapshot_counts(session)
                report["apply_report"] = {
                    **apply_report,
                    "before": before,
                    "after": after,
                    "delta": {
                        "total_nodes": int(after["total_nodes"]) - int(before["total_nodes"]),
                        "total_edges": int(after["total_edges"]) - int(before["total_edges"]),
                    },
                }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "project_key": report.get("project_key"),
        "apply": report.get("apply"),
        "total_nodes": report.get("total_nodes"),
        "merge_groups": report.get("merge_groups"),
        "cache_stats": report.get("cache_stats"),
        "report_file": str(report_path),
    }
    if args.apply:
        summary["apply_report"] = report.get("apply_report")
    if args.print_full_report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
