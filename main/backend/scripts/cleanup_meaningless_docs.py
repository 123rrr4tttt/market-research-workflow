#!/usr/bin/env python3
"""
Cleanup meaningless documents in project schema with a safe two-step flow.

Default mode is dry-run (preview only). Recommended workflow:
1) Dry run and export IDs:
   python scripts/cleanup_meaningless_docs.py --project demo_proj --write-id-file /tmp/meaningless_ids.txt
2) Apply by explicit IDs:
   python scripts/cleanup_meaningless_docs.py --project demo_proj --apply --id-file /tmp/meaningless_ids.txt
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Float, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm.attributes import flag_modified

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.ingest.llm_dirty_review import LlmDirtyReviewService
from app.services.ingest.meaningful_gate import normalize_content_for_ingest
from app.services.ingest.meaningful_gate import content_quality_check
from app.services.ingest.structured_extraction import (
    build_structured_summary,
    extract_structured_enriched_safe,
)
from app.services.projects import bind_project
from app.services.extraction.application import ExtractionApplicationService


STRICT_LOW_VALUE_PATH_KEYWORDS = (
    "/search",
    "/login",
    "/home",
    "/showcase",
    "/topics/",
    "/stargazers",
    "/sitemap",
)

STRICT_LOW_VALUE_DOMAINS = (
    "news.google.com",
    "x.com",
    "actiontoaction.ai",
)
MOJIBAKE_TITLE_MARKERS = (
    "ã",
    "â",
    "è",
    "æ",
    "é©¾",
)
MOJIBAKE_CONTENT_MARKERS = (
    "Ã",
    "Â",
    "�",
    "â€”",
    "â€œ",
    "â€",
    "è",
    "æ",
    "é©¾",
    "å·",
    "ç",
)


def _build_reason_expr(low_quality_threshold: float, target_mode: str = "all") -> Any:
    """Build reason tag with strict-first ordering."""
    content_lower = func.lower(func.coalesce(Document.content, ""))
    uri_lower = func.lower(func.coalesce(Document.uri, ""))
    title_lower = func.lower(func.coalesce(Document.title, ""))
    structured_status = func.lower(func.coalesce(Document.extracted_data["structured_extraction_status"].astext, ""))
    quality_score_text = func.nullif(Document.extracted_data["quality_score"].astext, "")
    quality_score_num = cast(quality_score_text, Float)
    degradation_flags_text = func.lower(func.coalesce(Document.extracted_data["degradation_flags"].astext, ""))

    empty_content = or_(Document.content.is_(None), func.btrim(Document.content) == "")
    pdf_binary = content_lower.like("%pdf-1.%")
    google_wiz_shell = content_lower.like("%window.wiz_progre%")
    wix_shell = content_lower.like("%var bodycacheable = true%")
    x_error_shell = content_lower.like("%errorcontainer%")
    next_hydration_shell = content_lower.like("%self.__next_f%")

    low_value_domain = or_(*[uri_lower.like(f"%{d}%") for d in STRICT_LOW_VALUE_DOMAINS])
    low_value_path = or_(*[uri_lower.like(f"%{p}%") for p in STRICT_LOW_VALUE_PATH_KEYWORDS])
    ddg_intermediate_page = and_(
        Document.doc_type == "url_fetch",
        or_(
            uri_lower.like("%html.duckduckgo.com/html?%"),
            and_(uri_lower.like("%duckduckgo.com/%"), uri_lower.like("%?q=%")),
            uri_lower.like("%duckduckgo.com/l/?%"),
        ),
    )
    github_api_intermediate = and_(
        Document.doc_type == "url_fetch",
        uri_lower.like("%api.github.com/repos/%"),
    )
    github_repo_intermediate = and_(
        Document.doc_type == "url_fetch",
        uri_lower.like("%github.com/%"),
        or_(
            content_lower.like("%source: github repository page%"),
            content_lower.like("%page type: repo_root%"),
            content_lower.like("%page type: stargazers%"),
            content_lower.like("%page type: issues%"),
            content_lower.like("%page type: pulls%"),
            content_lower.like("%skip to content%"),
            content_lower.like("%search or jump to%"),
        ),
    )
    api_status_wrapper = and_(
        or_(Document.doc_type == "url_fetch", Document.doc_type == "news"),
        content_lower.like("{%"),
        content_lower.like("%\"url\"%"),
        content_lower.like("%\"status\"%"),
        or_(content_lower.like("%\"text\": \"\"%"), content_lower.like("%\"text\":\"\"%")),
    )
    rss_feed_shell = and_(
        or_(Document.doc_type == "url_fetch", Document.doc_type == "news", Document.doc_type == "social_sentiment"),
        or_(uri_lower.like("%/rss%"), uri_lower.like("%/feed%"), uri_lower.like("%.xml%")),
        or_(
            content_lower.like("%no archive specified%"),
            content_lower.like("%archives are:%"),
            content_lower.like("%rss%"),
            content_lower.like("%feed%"),
        ),
    )
    js_template_shell = and_(
        Document.doc_type == "url_fetch",
        or_(
            content_lower.like("%__dopostback%"),
            content_lower.like("%__eventtarget%"),
            content_lower.like("%@font-face%"),
            content_lower.like("%:root%"),
            content_lower.like("%window.%"),
            content_lower.like("%document.%"),
            content_lower.like("%sourcemappingurl%"),
        ),
        func.length(func.coalesce(Document.content, "")) < 20000,
    )
    mojibake_title = or_(*[title_lower.like(f"%{m}%") for m in MOJIBAKE_TITLE_MARKERS])
    mojibake_content = or_(*[content_lower.like(f"%{m.lower()}%") for m in MOJIBAKE_CONTENT_MARKERS])
    script_shell_heavy = and_(
        content_lower.like("%window.%"),
        content_lower.like("%var %"),
        content_lower.like("%function%"),
    )
    mojibake_script_shell = and_(
        Document.doc_type == "url_fetch",
        mojibake_title,
        script_shell_heavy,
    )
    mojibake_garbled = and_(
        Document.doc_type == "url_fetch",
        or_(mojibake_title, mojibake_content),
    )
    search_summary_doc = and_(
        Document.doc_type == "url_fetch",
        or_(
            title_lower.like("search results - %"),
            uri_lower.like("%html.duckduckgo.com/html?%"),
            uri_lower.like("%/search?q=%"),
        ),
    )
    structured_failed = structured_status == literal("failed")
    low_quality_score = and_(
        quality_score_text.is_not(None),
        quality_score_num < float(low_quality_threshold),
    )
    structured_failed_flag = or_(
        degradation_flags_text.like("%structured_extraction_empty%"),
        degradation_flags_text.like("%structured_extraction_exception%"),
        degradation_flags_text.like("%structured_extraction_failed%"),
    )

    # For URL fetch rows, low-value domain/path is considered strict noise.
    url_fetch_low_value = and_(Document.doc_type == "url_fetch", or_(low_value_domain, low_value_path))

    if str(target_mode).strip().lower() == "quality_only":
        return case(
            (structured_failed, literal("structured_extraction_failed")),
            (low_quality_score, literal("quality_score_below_threshold")),
            (structured_failed_flag, literal("structured_extraction_failed_flag")),
            else_=literal(None),
        )

    return case(
        (empty_content, literal("empty_content")),
        (pdf_binary, literal("binary_pdf_raw")),
        (google_wiz_shell, literal("google_wiz_shell")),
        (wix_shell, literal("wix_shell")),
        (x_error_shell, literal("x_error_shell")),
        (next_hydration_shell, literal("next_hydration_shell")),
        (api_status_wrapper, literal("api_or_status_wrapper")),
        (rss_feed_shell, literal("rss_or_feed_shell")),
        (js_template_shell, literal("js_template_shell")),
        (ddg_intermediate_page, literal("ddg_intermediate_page")),
        (github_api_intermediate, literal("github_api_intermediate")),
        (github_repo_intermediate, literal("github_repo_intermediate")),
        (mojibake_script_shell, literal("mojibake_script_shell")),
        (mojibake_garbled, literal("mojibake_or_encoding_garbled")),
        (search_summary_doc, literal("search_summary_doc")),
        (structured_failed, literal("structured_extraction_failed")),
        (low_quality_score, literal("quality_score_below_threshold")),
        (structured_failed_flag, literal("structured_extraction_failed_flag")),
        (url_fetch_low_value, literal("url_fetch_low_value_endpoint")),
        else_=literal(None),
    )


def _load_ids_from_file(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    ids: list[int] = []
    for raw in text.replace(",", "\n").splitlines():
        item = raw.strip()
        if not item:
            continue
        if not item.isdigit():
            raise ValueError(f"Invalid id in file: {item!r}")
        ids.append(int(item))
    return sorted(set(ids))


def _write_ids(path: Path, ids: list[int]) -> None:
    content = "\n".join(str(x) for x in ids)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def run_dry(
    project_key: str,
    limit: int,
    write_id_file: Path | None,
    low_quality_threshold: float,
    target_mode: str,
    *,
    llm_review: bool = False,
    llm_review_model: str | None = None,
    llm_review_min_confidence: float = 0.75,
    llm_gate_ids: bool = False,
    llm_review_max_items: int = 50,
    llm_review_workers: int = 8,
) -> int:
    reason_expr = _build_reason_expr(
        low_quality_threshold=low_quality_threshold,
        target_mode=target_mode,
    ).label("reason")
    stmt = (
        select(
            Document.id,
            Document.doc_type,
            Document.title,
            Document.uri,
            func.substr(func.coalesce(Document.content, ""), 1, 600).label("content_preview"),
            func.length(func.coalesce(Document.content, "")).label("content_len"),
            reason_expr,
        )
        .where(reason_expr.is_not(None))
        .order_by(Document.id.asc())
    )

    with bind_project(project_key):
        with SessionLocal() as session:
            rows = list(session.execute(stmt).all())

    ids = [int(r.id) for r in rows]
    breakdown = Counter(str(r.reason) for r in rows)
    by_type = Counter(str(r.doc_type) for r in rows)
    llm_approved_ids: list[int] = []

    print(f"[dry-run] project={project_key}")
    print(f"[dry-run] low_quality_threshold={low_quality_threshold}")
    print(f"[dry-run] target_mode={target_mode}")
    print(f"[dry-run] candidate_count={len(rows)}")
    if not rows:
        if write_id_file:
            _write_ids(write_id_file, [])
            print(f"[dry-run] wrote empty id file: {write_id_file}")
        return 0

    print("[dry-run] reason_breakdown:")
    for reason, cnt in sorted(breakdown.items(), key=lambda x: (-x[1], x[0])):
        print(f"  - {reason}: {cnt}")

    print("[dry-run] doc_type_breakdown:")
    for doc_type, cnt in sorted(by_type.items(), key=lambda x: (-x[1], x[0])):
        print(f"  - {doc_type}: {cnt}")

    print(f"[dry-run] sample_top_{limit}:")
    for r in rows[:limit]:
        title = (r.title or "").replace("\n", " ")[:80]
        uri = (r.uri or "")[:120]
        print(
            f"  id={r.id} type={r.doc_type} len={r.content_len} reason={r.reason} "
            f"title={title!r} uri={uri!r}"
        )

    if llm_review and rows:
        reviewer = LlmDirtyReviewService(model=llm_review_model, temperature=0.0)
        review_rows = rows[: max(1, int(llm_review_max_items))]
        review_payloads = [
            {
                "doc_id": int(r.id),
                "uri": str(r.uri or ""),
                "title": str(r.title or ""),
                "doc_type": str(r.doc_type or ""),
                "rule_reason": str(r.reason or ""),
                "content_preview": str(r.content_preview or ""),
            }
            for r in review_rows
        ]
        decisions = reviewer.review_candidates(
            review_payloads,
            max_workers=max(1, int(llm_review_workers)),
        )
        llm_delete = 0
        llm_keep = 0
        llm_error = 0
        print(
            f"[dry-run][llm-review] start review_count={len(review_rows)} "
            f"workers={max(1, int(llm_review_workers))}"
        )
        for r in review_rows:
            decision = decisions.get(int(r.id))
            if decision is None:
                llm_error += 1
                print(f"[dry-run][llm-review] id={int(r.id)} missing_decision=True")
                continue
            if decision.category in {"llm_error", "llm_parse_error"}:
                llm_error += 1
            should_delete = bool(decision.delete and decision.confidence >= llm_review_min_confidence)
            if should_delete:
                llm_delete += 1
                llm_approved_ids.append(int(r.id))
            else:
                llm_keep += 1
            print(
                f"[dry-run][llm-review] id={int(r.id)} rule={str(r.reason)} "
                f"delete={decision.delete} conf={decision.confidence:.2f} "
                f"gate_delete={should_delete} category={decision.category} reason={decision.reason[:120]!r}"
            )
        print(
            f"[dry-run][llm-review] summary delete={llm_delete} keep={llm_keep} "
            f"errors={llm_error} threshold={llm_review_min_confidence}"
        )

    output_ids = llm_approved_ids if (llm_review and llm_gate_ids) else ids

    if write_id_file:
        _write_ids(write_id_file, output_ids)
        mode = "llm_gated" if (llm_review and llm_gate_ids) else "rule_only"
        print(f"[dry-run] wrote id file: {write_id_file} (count={len(output_ids)} mode={mode})")
    else:
        print("[dry-run] ids:")
        print(",".join(str(x) for x in output_ids))
    return len(rows)


def run_apply(project_key: str, id_file: Path) -> int:
    ids = _load_ids_from_file(id_file)
    if not ids:
        print(f"[apply] id file has no ids: {id_file}")
        return 0

    with bind_project(project_key):
        with SessionLocal() as session:
            rows = list(
                session.execute(
                    select(Document.id, Document.doc_type)
                    .where(Document.id.in_(ids))
                    .order_by(Document.id.asc())
                ).all()
            )
            found_ids = {int(r.id) for r in rows}
            missing = [x for x in ids if x not in found_ids]

            if missing:
                print("[apply] warning: some ids are missing (already deleted or invalid).")
                print("[apply] missing_ids=" + ",".join(str(x) for x in missing))

            deleted = (
                session.query(Document)
                .filter(Document.id.in_(list(found_ids)))
                .delete(synchronize_session=False)
            )
            session.commit()

    type_counter = Counter(str(r.doc_type) for r in rows)
    print(f"[apply] project={project_key}")
    print(f"[apply] requested={len(ids)} deleted={deleted}")
    print("[apply] deleted_doc_type_breakdown:")
    for doc_type, cnt in sorted(type_counter.items(), key=lambda x: (-x[1], x[0])):
        print(f"  - {doc_type}: {cnt}")
    return int(deleted)


def run_sanitize(project_key: str, id_file: Path, *, apply: bool, max_chars: int = 50000) -> int:
    ids = _load_ids_from_file(id_file)
    if not ids:
        print(f"[sanitize] id file has no ids: {id_file}")
        return 0

    changed = 0
    inspected = 0
    with bind_project(project_key):
        with SessionLocal() as session:
            docs = list(
                session.execute(
                    select(Document).where(Document.id.in_(ids)).order_by(Document.id.asc())
                ).scalars()
            )
            found_ids = {int(d.id) for d in docs}
            missing = [x for x in ids if x not in found_ids]
            if missing:
                print("[sanitize] warning: some ids are missing (already deleted or invalid).")
                print("[sanitize] missing_ids=" + ",".join(str(x) for x in missing))

            for doc in docs:
                inspected += 1
                old = str(doc.content or "")
                new = normalize_content_for_ingest(old, max_chars=max_chars)
                if new != old:
                    changed += 1
                    if apply:
                        doc.content = new
                        if doc.summary and len(str(doc.summary or "")) > 500:
                            doc.summary = str(new[:400] or None)
            if apply and changed > 0:
                session.commit()

    mode = "apply" if apply else "dry-run"
    print(f"[sanitize] project={project_key} mode={mode}")
    print(f"[sanitize] requested={len(ids)} inspected={inspected} changed={changed}")
    return int(changed)


def _has_structured_signal(extracted_data: dict[str, Any]) -> bool:
    if not isinstance(extracted_data, dict):
        return False
    for key in (
        "market",
        "policy",
        "sentiment",
        "company_structured",
        "product_structured",
        "operation_structured",
        "entities_relations",
    ):
        value = extracted_data.get(key)
        if isinstance(value, dict) and value:
            return True
    summary = extracted_data.get("_structured_summary")
    if isinstance(summary, dict):
        if int(summary.get("entity_count") or 0) > 0:
            return True
        for key in ("has_market", "has_policy", "has_sentiment", "has_company", "has_product", "has_operation"):
            if bool(summary.get(key)):
                return True
    return False


def _is_unstructured_or_pseudo_success(doc: Document) -> bool:
    extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
    status = str(extracted_data.get("structured_extraction_status") or "").strip().lower()
    if status in {"", "none", "failed"}:
        return True
    if status == "ok" and not _has_structured_signal(extracted_data):
        return True
    return False


def _is_real_low_quality(doc: Document, quality_threshold: float) -> tuple[bool, str]:
    extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
    status = str(extracted_data.get("structured_extraction_status") or "").strip().lower()
    quality_score = None
    try:
        quality_score = float(extracted_data.get("quality_score"))
    except Exception:
        quality_score = None
    content = str(doc.content or "")
    gate = content_quality_check(
        uri=str(doc.uri or ""),
        content=content,
        doc_type=str(doc.doc_type or ""),
        extraction_status={"extraction_enabled": status == "ok"},
        config={"enable_strict_gate": True},
    )
    if status == "failed":
        return True, "structured_failed"
    if quality_score is not None and quality_score < float(quality_threshold):
        return True, "quality_below_threshold"
    if gate.blocked:
        return True, f"content_gate:{gate.reason}"
    return False, "ok"


def run_recent_quality_pipeline(
    project_key: str,
    *,
    recent_limit: int,
    apply: bool,
    quality_threshold: float,
    reextract_unstructured: bool,
    delete_real_low_quality: bool,
) -> dict[str, Any]:
    extraction_app = ExtractionApplicationService()
    with bind_project(project_key):
        with SessionLocal() as session:
            docs = list(
                session.execute(
                    select(Document).order_by(Document.id.desc()).limit(max(1, int(recent_limit)))
                ).scalars()
            )
            low_quality_ids_pre: list[int] = []
            low_quality_reason_pre: dict[int, str] = {}
            for doc in docs:
                is_low_pre, reason_pre = _is_real_low_quality(doc, quality_threshold)
                if is_low_pre:
                    low_quality_ids_pre.append(int(doc.id))
                    low_quality_reason_pre[int(doc.id)] = reason_pre
            low_quality_id_set_pre = set(low_quality_ids_pre)
            # Token optimization: low-quality docs are never re-extracted.
            unstructured = [d for d in docs if _is_unstructured_or_pseudo_success(d) and int(d.id) not in low_quality_id_set_pre]
            reextract_changed = 0
            reextract_ok = 0
            reextract_failed = 0
            reextract_ids: list[int] = []
            summary_backfilled = 0
            if reextract_unstructured and unstructured:
                for doc in unstructured:
                    payload = "\n\n".join(
                        [x for x in [str(doc.title or "").strip(), str(doc.summary or "").strip(), str(doc.content or "").strip()] if x]
                    )
                    result = extract_structured_enriched_safe(
                        extraction_app=extraction_app,
                        payload=payload,
                        include_market=True,
                        include_policy=True,
                        include_sentiment=True,
                        include_company=True,
                        include_product=True,
                        include_operation=True,
                    )
                    extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
                    changed = False
                    if result.data:
                        extracted_data.update(result.data)
                        extracted_data["structured_extraction_status"] = "ok"
                        extracted_data.pop("structured_extraction_reason", None)
                        extracted_data.pop("structured_extraction_error", None)
                        reextract_ok += 1
                        changed = True
                    else:
                        extracted_data["structured_extraction_status"] = "failed"
                        if result.reason:
                            extracted_data["structured_extraction_reason"] = str(result.reason)
                        if result.error:
                            extracted_data["structured_extraction_error"] = str(result.error)
                        reextract_failed += 1
                        changed = True
                    if changed:
                        extracted_data["_structured_summary"] = build_structured_summary(
                            extracted_data,
                            extraction_enabled=bool(result.status == "ok"),
                            chunks_used=1,
                            extraction_mode="cleanup_reextract",
                        )
                        doc.extracted_data = extracted_data
                        reextract_changed += 1
                        reextract_ids.append(int(doc.id))
                        if apply:
                            flag_modified(doc, "extracted_data")
                            session.add(doc)
                if apply and reextract_changed > 0:
                    session.commit()

            # backfill summary for "pseudo-success": status=ok with structured signals but missing summary
            docs_for_summary = list(
                session.execute(
                    select(Document).order_by(Document.id.desc()).limit(max(1, int(recent_limit)))
                ).scalars()
            )
            for doc in docs_for_summary:
                extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
                status = str(extracted_data.get("structured_extraction_status") or "").strip().lower()
                has_summary = isinstance(extracted_data.get("_structured_summary"), dict)
                if status == "ok" and (not has_summary) and _has_structured_signal(extracted_data):
                    extracted_data["_structured_summary"] = build_structured_summary(
                        extracted_data,
                        extraction_enabled=True,
                        chunks_used=1,
                        extraction_mode="cleanup_backfill",
                    )
                    doc.extracted_data = extracted_data
                    summary_backfilled += 1
                    if apply:
                        flag_modified(doc, "extracted_data")
                        session.add(doc)
            if apply and summary_backfilled > 0:
                session.commit()

            # re-query after optional reextract commit
            docs_after = list(
                session.execute(
                    select(Document).order_by(Document.id.desc()).limit(max(1, int(recent_limit)))
                ).scalars()
            )
            low_quality_ids: list[int] = []
            low_quality_reasons: dict[int, str] = {}
            for doc in docs_after:
                is_low, reason = _is_real_low_quality(doc, quality_threshold)
                if is_low:
                    low_quality_ids.append(int(doc.id))
                    low_quality_reasons[int(doc.id)] = reason

            deleted = 0
            if delete_real_low_quality and apply and low_quality_ids:
                deleted = (
                    session.query(Document)
                    .filter(Document.id.in_(low_quality_ids))
                    .delete(synchronize_session=False)
                )
                session.commit()

    result = {
        "project": project_key,
        "recent_limit": int(recent_limit),
        "apply": bool(apply),
        "reextract_unstructured": bool(reextract_unstructured),
        "delete_real_low_quality": bool(delete_real_low_quality),
        "low_quality_candidates_pre": len(low_quality_ids_pre),
        "low_quality_ids_pre_sample": low_quality_ids_pre[:20],
        "low_quality_reason_pre_sample": {k: low_quality_reason_pre[k] for k in low_quality_ids_pre[:20]},
        "reextract_candidates": len(unstructured) if reextract_unstructured else 0,
        "reextract_changed": int(reextract_changed),
        "reextract_ok": int(reextract_ok),
        "reextract_failed": int(reextract_failed),
        "reextract_ids_sample": reextract_ids[:20],
        "summary_backfilled": int(summary_backfilled),
        "low_quality_candidates": len(low_quality_ids),
        "low_quality_ids_sample": low_quality_ids[:20],
        "low_quality_reason_sample": {k: low_quality_reasons[k] for k in low_quality_ids[:20]},
        "deleted": int(deleted),
    }
    print("[recent-quality-pipeline] " + str(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup meaningless documents safely")
    parser.add_argument("--project", default="demo_proj", help="Project key (default: demo_proj)")
    parser.add_argument("--limit", type=int, default=30, help="Dry-run sample limit")
    parser.add_argument(
        "--write-id-file",
        type=Path,
        default=None,
        help="Write dry-run candidate IDs to file",
    )
    parser.add_argument(
        "--low-quality-threshold",
        type=float,
        default=70.0,
        help="Quality-score threshold used by cleanup rule (default: 70.0)",
    )
    parser.add_argument(
        "--target-mode",
        choices=["all", "quality_only"],
        default="all",
        help="Cleanup target scope: all legacy rules or quality-only rules (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply delete (requires --id-file)",
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Run in-place content sanitization instead of deleting rows (requires --id-file)",
    )
    parser.add_argument(
        "--sanitize-max-chars",
        type=int,
        default=50000,
        help="Max chars for sanitized content (default: 50000)",
    )
    parser.add_argument(
        "--id-file",
        type=Path,
        default=None,
        help="ID file generated from dry-run",
    )
    parser.add_argument(
        "--llm-review",
        action="store_true",
        help="Enable LLM manual-review module for cleanup candidates",
    )
    parser.add_argument(
        "--llm-review-model",
        default="gpt-4o-mini",
        help="LLM model for review (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--llm-review-min-confidence",
        type=float,
        default=0.75,
        help="Delete only when LLM confidence >= threshold (default: 0.75)",
    )
    parser.add_argument(
        "--llm-gate-ids",
        action="store_true",
        help="When --llm-review is on, write only LLM-approved IDs to id-file",
    )
    parser.add_argument(
        "--llm-review-max-items",
        type=int,
        default=50,
        help="Max candidates to review by LLM in one run (default: 50)",
    )
    parser.add_argument(
        "--llm-review-workers",
        type=int,
        default=8,
        help="Parallel LLM review workers (default: 8)",
    )
    parser.add_argument(
        "--recent-quality-pipeline",
        action="store_true",
        help="Inspect recent docs, re-extract unstructured/pseudo-success docs, then detect/delete real low quality",
    )
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=20,
        help="Recent document count used by --recent-quality-pipeline (default: 20)",
    )
    parser.add_argument(
        "--reextract-unstructured",
        action="store_true",
        help="With --recent-quality-pipeline: re-extract docs with structured_status none/failed or pseudo-success",
    )
    parser.add_argument(
        "--delete-real-low-quality",
        action="store_true",
        help="With --recent-quality-pipeline: delete docs classified as real low quality",
    )
    args = parser.parse_args()

    if args.recent_quality_pipeline:
        run_recent_quality_pipeline(
            args.project,
            recent_limit=max(1, int(args.recent_limit)),
            apply=bool(args.apply),
            quality_threshold=float(args.low_quality_threshold),
            reextract_unstructured=bool(args.reextract_unstructured),
            delete_real_low_quality=bool(args.delete_real_low_quality),
        )
        return

    if args.apply:
        if args.id_file is None:
            raise SystemExit("--apply requires --id-file")
        if args.sanitize:
            run_sanitize(
                args.project,
                args.id_file,
                apply=True,
                max_chars=max(1000, int(args.sanitize_max_chars)),
            )
            return
        run_apply(args.project, args.id_file)
        return

    if args.sanitize:
        if args.id_file is None:
            raise SystemExit("--sanitize requires --id-file")
        run_sanitize(
            args.project,
            args.id_file,
            apply=False,
            max_chars=max(1000, int(args.sanitize_max_chars)),
        )
        return

    run_dry(
        args.project,
        args.limit,
        args.write_id_file,
        low_quality_threshold=float(args.low_quality_threshold),
        target_mode=str(args.target_mode),
        llm_review=bool(args.llm_review),
        llm_review_model=(str(args.llm_review_model).strip() or None),
        llm_review_min_confidence=float(args.llm_review_min_confidence),
        llm_gate_ids=bool(args.llm_gate_ids),
        llm_review_max_items=max(1, int(args.llm_review_max_items)),
        llm_review_workers=max(1, int(args.llm_review_workers)),
    )


if __name__ == "__main__":
    main()
