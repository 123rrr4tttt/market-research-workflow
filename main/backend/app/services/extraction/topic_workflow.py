from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass
from typing import NoReturn, Protocol, TypeGuard, TypeVar, runtime_checkable

from functorial_kit import Failure

from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

from ..ingest.postprocess_frontdoor import run_frontdoor_extraction

TOPIC_FIELDS = {
    "company": "company_structured",
    "product": "product_structured",
    "operation": "operation_structured",
}

TopicPayload = dict[str, object]
TopicMap = dict[object, object]
TopicExtractor = Callable[[str, str], object]
ItemT = TypeVar("ItemT")


@runtime_checkable
class _ObjectIterable(Protocol):
    def __iter__(self) -> Iterator[object]: ...


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _object_view(value: object) -> TopicMap:
    return value if _is_object_dict(value) else {}


_TOPIC_FAILURE_WITNESS = "test:test_topic_merge_preserves_invalid_item_and_confidence_semantics"
_TOPIC_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _payload_failure(message: str, *, site: str, **details: object) -> Failure:
    context: dict[str, object] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": ingest_operation_failures.name,
        "operation": "merge_topic_structured",
        "owner": site,
        "public_exception": "TypeError",
        "public_message": message,
        "site": site,
        "witness": _TOPIC_FAILURE_WITNESS,
    }
    context.update(details)
    return ingest_operation_failures.fail("extraction_payload_invalid", message, context)


def _raise_payload_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not ingest_operation_failures.matches(failure)
        or _TOPIC_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("failure_family") != ingest_operation_failures.name
        or context.get("public_exception") != "TypeError"
    ):
        # kit:boundary owner=extraction.topic_workflow.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_topic_merge_preserves_invalid_item_and_confidence_semantics
        raise TypeError("topic payload failure lift context is incomplete or inconsistent")
    # kit:boundary owner=extraction.topic_workflow.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_topic_merge_preserves_invalid_item_and_confidence_semantics
    raise TypeError(str(context["public_message"]))


def _object_list(value: object) -> list[object] | Failure:
    if not value:
        return []
    if isinstance(value, _ObjectIterable):
        return list(value)
    return _payload_failure(
        f"topic collection is not iterable: {type(value).__name__}",
        site="extraction.topic_workflow.collection",
        actual_type=type(value).__name__,
    )


def _item_view(value: object) -> TopicMap | Failure:
    if not value:
        return {}
    if _is_object_dict(value):
        return value
    return _payload_failure(
        f"topic item is not an object: {type(value).__name__}",
        site="extraction.topic_workflow.item",
        actual_type=type(value).__name__,
    )


def _required_object_list(value: object) -> list[object]:
    result = _object_list(value)
    if isinstance(result, Failure):
        _raise_payload_failure(result)
    return result


def _required_item_view(value: object) -> TopicMap:
    result = _item_view(value)
    if isinstance(result, Failure):
        _raise_payload_failure(result)
    return result


def _text_list(value: object) -> list[str]:
    return [str(item).lower() for item in _required_object_list(value)]


def _float_value(value: object) -> float | Failure:
    if value is None:
        return 0.0
    if isinstance(value, (str, int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return _payload_failure(
        f"topic confidence is not numeric: {type(value).__name__}",
        site="extraction.topic_workflow.confidence",
        actual_type=type(value).__name__,
    )


def _dedupe(items: list[ItemT], key_fn: Callable[[ItemT], str]) -> list[ItemT]:
    seen: set[str] = set()
    out: list[ItemT] = []
    for item in items:
        try:
            key = key_fn(item)
        except Exception:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def empty_topic_structured() -> TopicPayload:
    return {
        "entities": [],
        "relations": [],
        "facts": [],
        "topics": [],
        "signals": {},
        "confidence": 0.0,
        "source_excerpt": "",
        "_status": "no_topic_signal",
    }


def topic_has_data(payload: object) -> bool:
    view = _object_view(payload)
    return bool(
        view.get("entities")
        or view.get("relations")
        or view.get("facts")
        or view.get("topics")
        or view.get("signals")
    )


def merge_topic_structured(existing: object, incoming: object) -> TopicPayload:
    base = _object_view(existing)
    nxt = _object_view(incoming)

    entities = _dedupe(
        _required_object_list(base.get("entities")) + _required_object_list(nxt.get("entities")),
        lambda entity: (
            f"{str(_required_item_view(entity).get('text') or '').strip().lower()}::"
            f"{str(_required_item_view(entity).get('type') or '').strip().lower()}"
        ),
    )
    relations = _dedupe(
        _required_object_list(base.get("relations")) + _required_object_list(nxt.get("relations")),
        lambda relation: "::".join([
            str(_required_item_view(relation).get("subject") or "").strip().lower(),
            str(_required_item_view(relation).get("predicate") or "").strip().lower(),
            str(_required_item_view(relation).get("object") or "").strip().lower(),
        ]),
    )
    facts = _dedupe(
        _required_object_list(base.get("facts")) + _required_object_list(nxt.get("facts")),
        lambda fact: (
            f"{str(_required_item_view(fact).get('fact_type') or '').strip().lower()}::"
            f"{str(sorted(_required_item_view(fact).items()))}"
        ),
    )
    topics = _dedupe(
        [
            str(item).strip()
            for item in _required_object_list(base.get("topics")) + _required_object_list(nxt.get("topics"))
            if str(item).strip()
        ],
        lambda topic: topic.lower(),
    )
    signals = dict(_object_view(base.get("signals")))
    signals.update(_object_view(nxt.get("signals")))
    base_confidence = _float_value(base.get("confidence"))
    next_confidence = _float_value(nxt.get("confidence"))
    confidence = (
        0.0
        if isinstance(base_confidence, Failure) or isinstance(next_confidence, Failure)
        else max(base_confidence, next_confidence)
    )
    source_excerpt = str(nxt.get("source_excerpt") or base.get("source_excerpt") or "")[:800]
    out: TopicPayload = {
        "entities": entities[:80],
        "relations": relations[:80],
        "facts": facts[:80],
        "topics": topics[:50],
        "signals": signals,
        "confidence": confidence,
        "source_excerpt": source_excerpt,
    }
    if not topic_has_data(out):
        out["_status"] = str(nxt.get("_status") or base.get("_status") or "no_topic_signal")
    return out


@dataclass(slots=True)
class TopicChunk:
    chunk_id: int
    text: str
    start: int
    end: int
    matched_terms: list[str]
    score: int


def segment_text(text: str, *, target_size: int = 1000, overlap: int = 120, max_chunks: int = 30) -> list[TopicChunk]:
    raw = str(text or "").strip()
    if not raw:
        return []
    paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
    if not paras:
        paras = [raw]
    chunks: list[TopicChunk] = []
    cursor = 0
    buf = ""
    start = 0
    for para in paras:
        candidate = para if not buf else (buf + "\n\n" + para)
        if buf and len(candidate) > target_size and len(chunks) < max_chunks:
            chunks.append(TopicChunk(len(chunks), buf, start, start + len(buf), [], 0))
            carry = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            start = max(0, (start + len(buf)) - len(carry))
            buf = (carry + ("\n\n" if carry else "") + para).strip()
        else:
            if not buf:
                start = cursor
            buf = candidate
        cursor += len(para) + 2
        if len(chunks) >= max_chunks:
            break
    if buf and len(chunks) < max_chunks:
        chunks.append(TopicChunk(len(chunks), buf, start, start + len(buf), [], 0))
    # hard split any oversized chunk
    final: list[TopicChunk] = []
    for ch in chunks:
        if len(ch.text) <= target_size * 1.5:
            final.append(ch)
            continue
        step = max(200, target_size - overlap)
        i = 0
        while i < len(ch.text) and len(final) < max_chunks:
            t = ch.text[i:i + target_size].strip()
            if t:
                final.append(TopicChunk(len(final), t, ch.start + i, ch.start + i + len(t), [], 0))
            i += step
    return final[:max_chunks]


def score_chunk_for_topic(
    topic: str,
    chunk_text: str,
    *,
    extracted_data: object,
    er: object,
    dicts: Mapping[str, object],
) -> tuple[int, list[str]]:
    s = str(chunk_text or "").lower()
    score = 0
    matched: list[str] = []
    predicates = _text_list(dicts.get("predicates"))
    modifiers = _text_list(dicts.get("modifiers"))
    topic_nouns = _text_list(dicts.get(f"{topic}_nouns"))
    component_nouns = _text_list(dicts.get("components"))

    for token, weight in [(predicates, 1), (modifiers, 1), (topic_nouns, 2)]:
        for t in token:
            if t and t in s:
                score += weight
                matched.append(t)

    if topic == "product":
        for t in component_nouns:
            if t and t in s:
                score += 1
                matched.append(t)

    ex = _object_view(extracted_data)
    if topic == "operation" and (_is_object_dict(ex.get("market")) or _is_object_dict(ex.get("sentiment"))):
        score += 1
        matched.append("__market_or_sentiment_signal__")
    if topic == "company":
        ents = _required_object_list(_object_view(er).get("entities"))
        if any(str(_object_view(entity).get("type") or "").upper() == "ORG" for entity in ents):
            score += 2
            matched.append("__org_entity__")

    # simple positional bias
    if len(chunk_text) and len(s) and any(matched):
        score += 1
    return score, list(dict.fromkeys(matched))


def select_chunks_with_coverage(scored_chunks: list[TopicChunk], *, max_chunks: int = 6, min_score: int = 1) -> tuple[list[TopicChunk], float]:
    candidates = [c for c in scored_chunks if c.score >= min_score]
    if not candidates:
        return [], 0.0
    all_terms: set[str] = set()
    for c in candidates:
        all_terms.update([t for t in c.matched_terms if not t.startswith("__")])
    selected: list[TopicChunk] = []
    covered: set[str] = set()
    remaining = sorted(candidates, key=lambda c: (c.score, len(c.matched_terms), -c.chunk_id), reverse=True)
    while remaining and len(selected) < max_chunks:
        best = None
        best_gain = -1
        for c in remaining:
            gain_terms = set([t for t in c.matched_terms if not t.startswith("__")]) - covered
            gain = len(gain_terms) * 3 + c.score
            if gain > best_gain:
                best_gain = gain
                best = c
        if best is None:
            break
        selected.append(best)
        covered.update([t for t in best.matched_terms if not t.startswith("__")])
        remaining = [c for c in remaining if c.chunk_id != best.chunk_id]
        if all_terms and (len(covered) / max(1, len(all_terms))) >= 0.8:
            break
    coverage_ratio = (len(covered) / max(1, len(all_terms))) if all_terms else (1.0 if selected else 0.0)
    return selected, coverage_ratio


def _default_topic_extractor(topic: str, text: str) -> TopicMap:
    result = run_frontdoor_extraction(
        title=None,
        content=text,
        extraction_plan={
            "enabled": True,
            "mode": "topic_workflow",
            "include_policy": False,
            "include_market": False,
            "include_sentiment": False,
            "include_company": topic == "company",
            "include_product": topic == "product",
            "include_operation": topic == "operation",
        },
    )
    domains = _object_view(result.get("domains"))
    field = TOPIC_FIELDS[topic]
    payload = domains.get(field)
    return _object_view(payload) if _is_object_dict(payload) else _object_view(empty_topic_structured())


def _extract_topic_from_chunk(topic_extractor: TopicExtractor, topic: str, text: str) -> TopicMap:
    payload = topic_extractor(topic, text)
    return _object_view(payload) if _is_object_dict(payload) else _object_view(empty_topic_structured())


def _resolve_topic_extractor(value: object) -> TopicExtractor:
    return value if callable(value) else _default_topic_extractor


def _resolve_parallel_workers(total_tasks: int) -> int:
    if total_tasks <= 1:
        return 1
    cap_raw = str(os.getenv("TOPIC_WORKFLOW_MAX_PARALLEL", "8")).strip()
    try:
        cap = max(1, int(cap_raw))
    except Exception:
        cap = 8
    return max(1, min(total_tasks, cap))


def _run_topic_chunk_tasks(
    *,
    topic_extractor: TopicExtractor,
    tasks: list[tuple[str, TopicChunk]],
) -> dict[str, list[TopicMap]]:
    if not tasks:
        return {}
    grouped: dict[str, list[TopicMap]] = {}
    workers = _resolve_parallel_workers(len(tasks))
    if workers == 1:
        for topic, ch in tasks:
            payload = _extract_topic_from_chunk(topic_extractor, topic, ch.text)
            grouped.setdefault(topic, []).append(payload)
        return grouped

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="topic-workflow") as executor:
        # Propagate project contextvars into worker threads.
        future_map = {
            executor.submit(copy_context().run, _extract_topic_from_chunk, topic_extractor, topic, ch.text): topic
            for topic, ch in tasks
        }
        for future in as_completed(future_map):
            topic = future_map[future]
            try:
                payload = future.result()
            except Exception:
                payload = _object_view(empty_topic_structured())
            grouped.setdefault(topic, []).append(payload)
    return grouped


def run_topic_extraction_workflow(
    *,
    extraction_app: object | None,
    text: str,
    topics: list[str],
    extracted_data: object,
    dictionaries: Mapping[str, object],
    max_selected_chunks: int = 6,
    fallback_max_chunks: int = 8,
    topic_extractor: object | None = None,
) -> dict[str, object]:
    del extraction_app  # Retained for backward-compatible call sites; topic extraction now routes via topic_extractor/frontdoor.
    ex = _object_view(extracted_data)
    er = _object_view(ex.get("entities_relations"))
    chunks = segment_text(text, target_size=1000, overlap=120, max_chunks=30)
    if not chunks:
        return {"results": {t: empty_topic_structured() for t in topics}, "diagnostics": {"chunks_total": 0}}
    effective_topic_extractor = _resolve_topic_extractor(topic_extractor)

    topic_results: dict[str, TopicPayload] = {}
    topic_diagnostics: dict[str, object] = {}
    diagnostics: dict[str, object] = {
        "chunks_total": len(chunks),
        "topics": topic_diagnostics,
    }
    total_chunk_tasks = 0

    for topic in topics:
        scored: list[TopicChunk] = []
        for ch in chunks:
            score, matched = score_chunk_for_topic(topic, ch.text, extracted_data=ex, er=er, dicts=dictionaries)
            scored.append(TopicChunk(ch.chunk_id, ch.text, ch.start, ch.end, matched, score))
        selected, coverage = select_chunks_with_coverage(scored, max_chunks=max_selected_chunks, min_score=1)
        total_chunk_tasks += len(selected)
        merged = empty_topic_structured()
        selected_payloads = _run_topic_chunk_tasks(
            topic_extractor=effective_topic_extractor,
            tasks=[(topic, ch) for ch in selected],
        )
        for payload in selected_payloads.get(topic, []):
            merged = merge_topic_structured(merged, payload)
        fallback_used = False
        if (not topic_has_data(merged) or coverage < 0.5) and len(chunks) > len(selected):
            fallback_used = True
            selected_ids = {c.chunk_id for c in selected}
            residual = [c for c in chunks if c.chunk_id not in selected_ids][:fallback_max_chunks]
            total_chunk_tasks += len(residual)
            residual_payloads = _run_topic_chunk_tasks(
                topic_extractor=effective_topic_extractor,
                tasks=[(topic, ch) for ch in residual],
            )
            for payload in residual_payloads.get(topic, []):
                merged = merge_topic_structured(merged, payload)
        topic_results[topic] = merged
        topic_diagnostics[topic] = {
            "selected_chunks": [c.chunk_id for c in selected],
            "selected_count": len(selected),
            "coverage_ratio": round(float(coverage), 4),
            "fallback_used": fallback_used,
            "max_score": max([c.score for c in scored], default=0),
        }

    diagnostics["parallel_workers"] = _resolve_parallel_workers(total_chunk_tasks)
    diagnostics["total_chunk_tasks"] = total_chunk_tasks
    return {"results": topic_results, "diagnostics": diagnostics}
