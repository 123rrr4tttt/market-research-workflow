from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RankedCandidate:
    node_id: int
    rank_score: float


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return np.empty((0, 0), dtype=float)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1e-12
    normalized = vectors / norms
    return np.matmul(normalized, normalized.T)


def rank_candidates(candidates: list[dict[str, Any]]) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    for row in candidates:
        try:
            node_id = int(row.get("node_id"))
        except Exception:
            continue
        aliases = row.get("aliases") or []
        alias_count = len(aliases) if isinstance(aliases, list) else 0
        node_text = str(row.get("node_text") or "")
        props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        prop_count = len(props)
        text_len = len(node_text)
        # Rank richer canonical nodes first to maximize early cluster quality.
        score = (alias_count * 2.0) + (prop_count * 0.5) + min(text_len / 120.0, 2.5)
        ranked.append(RankedCandidate(node_id=node_id, rank_score=score))
    ranked.sort(key=lambda x: (x.rank_score, -x.node_id), reverse=True)
    return ranked


def build_disjoint_related_groups(
    *,
    candidates: list[dict[str, Any]],
    vectors: np.ndarray,
    similarity_threshold: float = 0.78,
    fallback_similarity_threshold: float = 0.72,
    min_group_size: int = 2,
    max_group_size: int = 10,
    max_groups: int = 20,
) -> list[list[int]]:
    if not candidates:
        return []
    if vectors.shape[0] != len(candidates):
        raise ValueError("vectors row count must match candidates length")

    sim = cosine_similarity_matrix(vectors)
    ranked = rank_candidates(candidates)
    id_to_idx = {}
    for idx, row in enumerate(candidates):
        try:
            id_to_idx[int(row.get("node_id"))] = idx
        except Exception:
            continue

    remaining = set(id_to_idx.keys())
    groups: list[list[int]] = []
    for ranked_item in ranked:
        if len(groups) >= max_groups:
            break
        seed = ranked_item.node_id
        if seed not in remaining:
            continue
        seed_idx = id_to_idx[seed]
        neighbors: list[tuple[int, float]] = []
        for nid in remaining:
            if nid == seed:
                continue
            nidx = id_to_idx[nid]
            score = float(sim[seed_idx, nidx])
            if score >= similarity_threshold:
                neighbors.append((nid, score))
        neighbors.sort(key=lambda x: x[1], reverse=True)
        group_ids = [seed] + [nid for nid, _ in neighbors[: max(0, max_group_size - 1)]]
        groups.append(group_ids)
        for gid in group_ids:
            if gid in remaining:
                remaining.remove(gid)

    # Remaining nodes become singleton groups first.
    for nid in sorted(remaining):
        if len(groups) >= max_groups:
            break
        groups.append([nid])

    if not groups:
        return groups

    # Supplemental grouping:
    # For too-small groups, try attaching to highest-similarity existing group.
    # If the best target is also too-small, merge the two small groups.
    node_to_group: dict[int, int] = {}
    for gi, grp in enumerate(groups):
        for nid in grp:
            node_to_group[nid] = gi

    def _group_size(group_idx: int) -> int:
        return len(groups[group_idx]) if 0 <= group_idx < len(groups) else 0

    small_group_indices = [idx for idx, grp in enumerate(groups) if 0 < len(grp) < min_group_size]
    for gidx in small_group_indices:
        if _group_size(gidx) == 0 or _group_size(gidx) >= min_group_size:
            continue
        source_nodes = list(groups[gidx])
        best_id: int | None = None
        best_score = -1.0
        for nid in source_nodes:
            src_idx = id_to_idx[nid]
            for other_id, other_idx in id_to_idx.items():
                if other_id in source_nodes:
                    continue
                score = float(sim[src_idx, other_idx])
                if score > best_score:
                    best_score = score
                    best_id = other_id

        if best_id is None or best_score < fallback_similarity_threshold:
            continue

        other_group = node_to_group.get(best_id)
        if other_group is None or other_group == gidx or _group_size(other_group) == 0:
            continue

        if _group_size(other_group) >= min_group_size:
            merged = [*groups[other_group], *source_nodes]
            merged = list(dict.fromkeys(merged))
            if len(merged) <= max_group_size:
                groups[other_group] = merged
                groups[gidx] = []
                for x in merged:
                    node_to_group[x] = other_group
            continue

        merged = [*source_nodes, *groups[other_group]]
        merged = list(dict.fromkeys(merged))
        if len(merged) <= max_group_size:
            groups[gidx] = merged
            groups[other_group] = []
            for x in merged:
                node_to_group[x] = gidx

    # Compact empty groups.
    groups = [g for g in groups if g]
    # Keep deterministic order and max_groups bound.
    groups = groups[:max_groups]
    return groups
