from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any

from .merge_policy import select_merge_policy
from .symbol_normalization import SymbolRuleExecutor

logger = logging.getLogger(__name__)


def get_merge_policy(*, project_key: str | None = None, node_type: str | None = None):
    policy, fallback_reason = select_merge_policy(project_key=project_key, node_type=node_type)
    setattr(get_merge_policy, "last_fallback_reason", fallback_reason)
    return policy


setattr(get_merge_policy, "last_fallback_reason", None)


_DATA_POINT_TYPE_KEYWORDS = (
    "datapoint",
    "data_point",
    "metric",
    "numeric",
    "observation",
    "timeseries",
    "time_series",
    "factpoint",
)

_CONTENT_LIKE_TYPE_KEYWORDS = (
    "post",
    "policy",
    "keypoint",
    "key_point",
    "document",
    "article",
)

_CONTENT_LIKE_TEXT_PATTERNS = (
    r"\bwith\b",
    r"\bthrough\b",
    r"\brelationship\b",
    r"\bagreement\b",
    r"\binitiative\b",
    r"\bcompetition\b",
)


def is_data_point_node(node: dict[str, Any]) -> bool:
    node_type = str(node.get("node_type") or "").strip().lower()
    if any(k in node_type for k in _DATA_POINT_TYPE_KEYWORDS):
        return True
    props = node.get("properties")
    if isinstance(props, dict):
        data_kind = str(props.get("data_kind") or props.get("value_type") or "").strip().lower()
        if data_kind in {"metric", "numeric", "datapoint", "observation"}:
            return True
    return False


def is_content_like_node(node: dict[str, Any]) -> bool:
    node_type = str(node.get("node_type") or "").strip().lower()
    if any(k in node_type for k in _CONTENT_LIKE_TYPE_KEYWORDS):
        return True

    label = ""
    for key in ("display_name", "canonical_id", "node_text"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            label = val.strip()
            break
    if not label:
        return False

    lowered = label.lower()
    if len(label) > 80 or len(label.split()) > 10:
        return True
    if any(ch in label for ch in (".", ";", ":", "?", "!", "\n")):
        return True
    if sum(1 for p in (",", "(", ")", "/") if p in label) >= 2:
        return True
    if any(re.search(p, lowered) for p in _CONTENT_LIKE_TEXT_PATTERNS):
        return True
    return False


def is_merge_eligible_node(node: dict[str, Any]) -> bool:
    return (not is_data_point_node(node)) and (not is_content_like_node(node))


def _node_ids(candidates: list[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    for row in candidates:
        try:
            result.append(int(row.get("node_id")))
        except Exception:
            continue
    return sorted(result)


def get_chat_model(**kwargs):  # noqa: ANN003
    """Compatibility wrapper so tests/callers can patch chat-model creation."""
    from ..llm.provider import get_chat_model as _provider_get_chat_model

    return _provider_get_chat_model(**kwargs)


def _extract_text_content(resp: Any) -> str:
    content = getattr(resp, "content", "")
    if isinstance(content, list):
        return "\n".join(str(x) for x in content)
    return str(content or "")


def _parse_json_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _legacy_llm_merges(
    *,
    query_text: str,
    filtered_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(filtered_candidates) < 2:
        return []
    model = get_chat_model(model="gpt-4o-mini", temperature=0.1, max_tokens=1800)
    prompt = (
        "Given a query and candidate graph nodes, return JSON with key 'merges'. "
        "Each merge must include source_node_ids, merged_node, confidence, reason.\n"
        f"query_text={query_text}\n"
        f"candidates={json.dumps(filtered_candidates, ensure_ascii=False)}"
    )
    raw = _extract_text_content(model.invoke(prompt))
    payload = _parse_json_payload(raw)
    merges = payload.get("merges")
    return merges if isinstance(merges, list) else []


def _normalize_merges(
    merges: list[dict[str, Any]],
    *,
    filtered_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for row in filtered_candidates:
        try:
            by_id[int(row.get("node_id"))] = row
        except Exception:
            continue

    normalized: list[dict[str, Any]] = []
    for item in merges:
        if not isinstance(item, dict):
            continue
        src_ids_raw = item.get("source_node_ids")
        if not isinstance(src_ids_raw, list):
            continue
        src_ids: list[int] = []
        for node_id in src_ids_raw:
            try:
                src_ids.append(int(node_id))
            except Exception:
                continue
        src_ids = sorted(dict.fromkeys(src_ids))
        if len(src_ids) < 2:
            continue
        if any(node_id not in by_id for node_id in src_ids):
            continue

        node_types = {
            str((by_id[node_id].get("node_type") or "")).strip().lower()
            for node_id in src_ids
        }
        if len(node_types) != 1:
            continue

        merged_node = item.get("merged_node") if isinstance(item.get("merged_node"), dict) else {}
        merged_node = dict(merged_node)
        merged_node.setdefault("node_type", str(by_id[src_ids[0]].get("node_type") or "Entity"))
        merged_node.setdefault(
            "display_name",
            str(merged_node.get("canonical_id") or by_id[src_ids[0]].get("display_name") or "").strip(),
        )
        merged_node.setdefault(
            "canonical_id",
            str(merged_node.get("display_name") or by_id[src_ids[0]].get("canonical_id") or "").strip().casefold(),
        )

        try:
            confidence = float(item.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        reason = str(item.get("reason") or "")
        normalized.append(
            {
                "merged_node": merged_node,
                "source_node_ids": src_ids,
                "confidence": confidence,
                "reason": reason,
            }
        )
    return normalized


def _build_normalization_context(
    *,
    project_key: str | None,
    node_type: str | None,
    normalization_context: dict[str, Any] | None,
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if isinstance(normalization_context, dict):
        context.update(normalization_context)
    if project_key is not None and str(project_key).strip():
        context["project_key"] = str(project_key).strip()
    if node_type is not None and str(node_type).strip():
        context["node_type"] = str(node_type).strip()
    return context


def _normalize_merge_inputs(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    context: dict[str, Any] | None,
) -> tuple[str, list[dict[str, Any]]]:
    executor = SymbolRuleExecutor()
    normalized_query = executor.normalize(query_text, context=context)

    normalized_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidate = dict(candidate)
        candidate_node_type = str(candidate.get("node_type") or "").strip()
        candidate_context = dict(context or {})
        if candidate_node_type:
            candidate_context.setdefault("node_type", candidate_node_type)
        normalized_candidate["display_name"] = executor.normalize(
            candidate.get("display_name"),
            context=candidate_context,
        )
        normalized_candidate["canonical_id"] = executor.normalize(
            candidate.get("canonical_id"),
            context=candidate_context,
        )
        normalized_candidate["node_text"] = executor.normalize(
            candidate.get("node_text"),
            context=candidate_context,
        )

        aliases = candidate.get("aliases")
        if isinstance(aliases, list):
            normalized_aliases: list[str] = []
            for alias in aliases:
                normalized_alias = executor.normalize(alias, context=candidate_context)
                if normalized_alias:
                    normalized_aliases.append(normalized_alias)
            normalized_candidate["aliases"] = normalized_aliases

        normalized_candidates.append(normalized_candidate)
    return normalized_query, normalized_candidates


def suggest_node_merges_with_llm(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1800,
    project_key: str | None = None,
    node_type: str | None = None,
    normalization_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del model, temperature, max_tokens

    filtered = [c for c in candidates if is_merge_eligible_node(c)]
    context = _build_normalization_context(
        project_key=project_key,
        node_type=node_type,
        normalization_context=normalization_context,
    )
    normalized_query_text, normalized_filtered = _normalize_merge_inputs(
        query_text=query_text,
        candidates=filtered,
        context=context or None,
    )
    resolved_node_type = str(node_type or "").strip()
    if not resolved_node_type:
        normalized_types = {
            str(item.get("node_type") or "").strip()
            for item in normalized_filtered
            if str(item.get("node_type") or "").strip()
        }
        if len(normalized_types) == 1:
            resolved_node_type = next(iter(normalized_types))
    try:
        policy = get_merge_policy(project_key=project_key, node_type=resolved_node_type or None)
    except TypeError:
        # Backward-compatible path for tests/callers monkeypatching get_merge_policy() without kwargs.
        policy = get_merge_policy()
    fallback_reason = getattr(get_merge_policy, "last_fallback_reason", None)
    if fallback_reason:
        logger.warning("node_merge_llm policy fallback applied: %s", fallback_reason)
    policy_result = policy.evaluate(query_text=normalized_query_text, candidates=normalized_filtered)

    merges = policy_result.evidence.get("merges") if isinstance(policy_result.evidence, dict) else []
    if not isinstance(merges, list):
        merges = []
    merges = [m for m in merges if isinstance(m, dict)]
    if not merges:
        merges = _legacy_llm_merges(query_text=normalized_query_text, filtered_candidates=normalized_filtered)
    merges = _normalize_merges(merges, filtered_candidates=filtered)

    used_ids: set[int] = set()
    for merge in merges:
        src_ids = merge.get("source_node_ids") if isinstance(merge, dict) else []
        if isinstance(src_ids, list):
            for node_id in src_ids:
                try:
                    used_ids.add(int(node_id))
                except Exception:
                    continue

    allowed_node_ids = set(_node_ids(filtered))
    unmerged_node_ids = sorted(allowed_node_ids - used_ids)

    return {
        "merges": merges,
        "unmerged_node_ids": unmerged_node_ids,
        "policy": getattr(policy, "name", "default"),
        "policy_fallback_reason": fallback_reason,
        "policy_result": dataclasses.asdict(policy_result),
    }
