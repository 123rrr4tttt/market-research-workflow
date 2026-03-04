from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import re
import unicodedata
from typing import Any, Iterable


_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class MergeCandidate:
    source_node_ids: list[int]
    score: float
    reason: str
    node_type: str


@dataclass(frozen=True)
class _PreparedNode:
    node_id: int
    node_type: str
    alias_set: set[str]


def _normalize_alias_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _SPACE_RE.sub(" ", text).strip().casefold()
    return text


def _iter_alias_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_alias_values(nested)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_alias_values(item)


def _extract_alias_set(node: dict[str, Any]) -> set[str]:
    raw_alias_dict = node.get("alias_dict")
    if raw_alias_dict is None:
        raw_alias_dict = node.get("aliases")

    aliases = {_normalize_alias_text(x) for x in _iter_alias_values(raw_alias_dict)}
    return {x for x in aliases if x}


def _prepare_nodes(nodes: list[dict[str, Any]]) -> list[_PreparedNode]:
    prepared: list[_PreparedNode] = []
    for node in nodes:
        try:
            node_id = int(node.get("node_id"))
        except Exception:
            continue
        node_type = str(node.get("node_type") or "").strip()
        if not node_type:
            continue
        alias_set = _extract_alias_set(node)
        if not alias_set:
            continue
        prepared.append(
            _PreparedNode(
                node_id=node_id,
                node_type=node_type.casefold(),
                alias_set=alias_set,
            )
        )
    return prepared


def _score_alias_sets(alias_a: set[str], alias_b: set[str]) -> tuple[float, float]:
    if not alias_a or not alias_b:
        return 0.0, 0.0
    shared = len(alias_a & alias_b)
    if shared <= 0:
        return 0.0, 0.0
    jaccard = shared / float(len(alias_a | alias_b))
    overlap = shared / float(min(len(alias_a), len(alias_b)))
    return jaccard, overlap


def _resolve_score(*, jaccard: float, overlap: float, metric: str) -> float:
    key = str(metric or "max").strip().lower()
    if key == "jaccard":
        return jaccard
    if key == "overlap":
        return overlap
    if key == "avg":
        return (jaccard + overlap) / 2.0
    return max(jaccard, overlap)


def suggest_merge_candidates(
    nodes: list[dict[str, Any]],
    *,
    threshold: float = 0.6,
    metric: str = "max",
) -> list[dict[str, Any]]:
    """Generate merge candidates for same-type nodes by alias overlap.

    Output shape:
      [{"source_node_ids":[id1,id2], "score":0.83, "reason":"...", "node_type":"entity"}]
    """
    prepared = _prepare_nodes(nodes)
    if not prepared:
        return []

    by_type: dict[str, list[_PreparedNode]] = {}
    for node in prepared:
        by_type.setdefault(node.node_type, []).append(node)

    out: list[MergeCandidate] = []
    for node_type, group in by_type.items():
        if len(group) < 2:
            continue
        for left, right in combinations(group, 2):
            jaccard, overlap = _score_alias_sets(left.alias_set, right.alias_set)
            if jaccard <= 0.0 and overlap <= 0.0:
                continue
            score = _resolve_score(jaccard=jaccard, overlap=overlap, metric=metric)
            if score < threshold:
                continue
            shared_aliases = sorted(left.alias_set & right.alias_set)[:5]
            reason = (
                "alias match "
                f"(jaccard={jaccard:.3f}, overlap={overlap:.3f}, metric={metric}); "
                f"shared={shared_aliases}"
            )
            out.append(
                MergeCandidate(
                    source_node_ids=sorted([left.node_id, right.node_id]),
                    score=round(score, 6),
                    reason=reason,
                    node_type=node_type,
                )
            )

    out.sort(key=lambda item: (item.score, -item.source_node_ids[0], -item.source_node_ids[1]), reverse=True)
    return [
        {
            "source_node_ids": item.source_node_ids,
            "score": item.score,
            "reason": item.reason,
            "node_type": item.node_type,
        }
        for item in out
    ]

