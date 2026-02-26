from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TOPIC_FIELDS = {
    "company": "company_structured",
    "product": "product_structured",
    "operation": "operation_structured",
}


def empty_topic_structured() -> dict[str, Any]:
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


def topic_has_data(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(
        payload.get("entities") or payload.get("relations") or payload.get("facts") or payload.get("topics") or payload.get("signals")
    )


def merge_topic_structured(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = existing if isinstance(existing, dict) else {}
    nxt = incoming if isinstance(incoming, dict) else {}

    def _dedupe(items: list[Any], key_fn):
        seen = set()
        out = []
        for item in items:
            try:
                k = key_fn(item)
            except Exception:
                k = str(item)
            if k in seen:
                continue
            seen.add(k)
            out.append(item)
        return out

    entities = _dedupe(
        list(base.get("entities") or []) + list(nxt.get("entities") or []),
        lambda e: f"{str((e or {}).get('text') or '').strip().lower()}::{str((e or {}).get('type') or '').strip().lower()}",
    )
    relations = _dedupe(
        list(base.get("relations") or []) + list(nxt.get("relations") or []),
        lambda r: "::".join([
            str((r or {}).get("subject") or "").strip().lower(),
            str((r or {}).get("predicate") or "").strip().lower(),
            str((r or {}).get("object") or "").strip().lower(),
        ]),
    )
    facts = _dedupe(
        list(base.get("facts") or []) + list(nxt.get("facts") or []),
        lambda f: f"{str((f or {}).get('fact_type') or '').strip().lower()}::{str(sorted((f or {}).items()))}",
    )
    topics = _dedupe(
        [str(x).strip() for x in (list(base.get("topics") or []) + list(nxt.get("topics") or [])) if str(x).strip()],
        lambda x: x.lower(),
    )
    signals = dict(base.get("signals") or {})
    signals.update(nxt.get("signals") or {})
    try:
        confidence = max(float(base.get("confidence") or 0.0), float(nxt.get("confidence") or 0.0))
    except Exception:
        confidence = 0.0
    source_excerpt = str(nxt.get("source_excerpt") or base.get("source_excerpt") or "")[:800]
    out = {
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
    extracted_data: dict[str, Any] | None,
    er: dict[str, Any] | None,
    dicts: dict[str, Any],
) -> tuple[int, list[str]]:
    s = str(chunk_text or "").lower()
    score = 0
    matched: list[str] = []
    predicates = [str(x).lower() for x in (dicts.get("predicates") or [])]
    modifiers = [str(x).lower() for x in (dicts.get("modifiers") or [])]
    topic_nouns = [str(x).lower() for x in (dicts.get(f"{topic}_nouns") or [])]
    component_nouns = [str(x).lower() for x in (dicts.get("components") or [])]

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

    ex = extracted_data if isinstance(extracted_data, dict) else {}
    if topic == "operation" and (isinstance(ex.get("market"), dict) or isinstance(ex.get("sentiment"), dict)):
        score += 1
        matched.append("__market_or_sentiment_signal__")
    if topic == "company":
        ents = (er or {}).get("entities") if isinstance(er, dict) else []
        if any(str((e or {}).get("type") or "").upper() == "ORG" for e in (ents or [])):
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
    all_terms = set()
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


def _extract_topic_from_chunk(extraction_app: Any, topic: str, text: str) -> dict[str, Any]:
    kwargs = {
        "include_company": topic == "company",
        "include_product": topic == "product",
        "include_operation": topic == "operation",
    }
    result = extraction_app.extract_structured_enriched(text, **kwargs) or {}
    field = TOPIC_FIELDS[topic]
    payload = result.get(field) if isinstance(result, dict) else None
    return payload if isinstance(payload, dict) else empty_topic_structured()


def run_topic_extraction_workflow(
    *,
    extraction_app: Any,
    text: str,
    topics: list[str],
    extracted_data: dict[str, Any] | None,
    dictionaries: dict[str, Any],
    max_selected_chunks: int = 6,
    fallback_max_chunks: int = 8,
) -> dict[str, Any]:
    ex = extracted_data if isinstance(extracted_data, dict) else {}
    er = ex.get("entities_relations") if isinstance(ex.get("entities_relations"), dict) else None
    chunks = segment_text(text, target_size=1000, overlap=120, max_chunks=30)
    if not chunks:
        return {"results": {t: empty_topic_structured() for t in topics}, "diagnostics": {"chunks_total": 0}}

    topic_results: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, Any] = {"chunks_total": len(chunks), "topics": {}}

    for topic in topics:
        scored: list[TopicChunk] = []
        for ch in chunks:
            score, matched = score_chunk_for_topic(topic, ch.text, extracted_data=ex, er=er, dicts=dictionaries)
            scored.append(TopicChunk(ch.chunk_id, ch.text, ch.start, ch.end, matched, score))
        selected, coverage = select_chunks_with_coverage(scored, max_chunks=max_selected_chunks, min_score=1)
        merged = empty_topic_structured()
        for ch in selected:
            merged = merge_topic_structured(merged, _extract_topic_from_chunk(extraction_app, topic, ch.text))
        fallback_used = False
        if (not topic_has_data(merged) or coverage < 0.5) and len(chunks) > len(selected):
            fallback_used = True
            selected_ids = {c.chunk_id for c in selected}
            residual = [c for c in chunks if c.chunk_id not in selected_ids][:fallback_max_chunks]
            for ch in residual:
                merged = merge_topic_structured(merged, _extract_topic_from_chunk(extraction_app, topic, ch.text))
        topic_results[topic] = merged
        diagnostics["topics"][topic] = {
            "selected_chunks": [c.chunk_id for c in selected],
            "selected_count": len(selected),
            "coverage_ratio": round(float(coverage), 4),
            "fallback_used": fallback_used,
            "max_score": max([c.score for c in scored], default=0),
        }

    return {"results": topic_results, "diagnostics": diagnostics}

