#!/usr/bin/env python3
"""Re-extract structured data for all documents in the database.

Uses the demo/trunk LLM extraction modules:
- social_sentiment: extract_structured_sentiment + extract_entities_relations
- policy / policy_regulation: extract_policy_info + extract_entities_relations
- market_info: extract_market_info + extract_entities_relations

Run in Docker: docker compose exec backend python scripts/re_extract_all_structured.py [options]
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.models.base import SessionLocal
from app.models.entities import Material
from app.services.projects.context import bind_project
from app.services.llm.extraction import extract_structured_sentiment, extract_market_info
from app.services.extraction.extract import (
    extract_policy_info,
    extract_market_info as extract_market_full,
    extract_entities_relations,
)
from app.services.llm.provider import get_chat_model
from app.services.llm.config_loader import get_llm_config, format_prompt_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _classify_social_to_market_or_sentiment(text: str) -> str:
    """Classify social doc: return 'market_info' or 'social_sentiment'."""
    if not text or len(text.strip()) < 30:
        return "social_sentiment"
    snippet = text[:1500].strip()
    config = get_llm_config("doc_type_classification")
    if config and config.get("user_prompt_template"):
        prompt = format_prompt_template(config["user_prompt_template"], text=snippet)
    else:
        prompt = (
            "判断以下文本更偏向哪一类，只回答一个词：\n"
            "- market_info: 市场数据、销售、规模、融资、订单、出货量等\n"
            "- social_sentiment: 舆论、观点、讨论、情感、社区反馈等\n\n"
            f"文本：\n{snippet}\n\n"
            "只回答 market_info 或 social_sentiment，不要其他内容。"
        )
    try:
        model = get_chat_model(model=config.get("model") if config else None)
        resp = model.invoke(prompt)
        out = (resp.content if hasattr(resp, "content") else str(resp)).strip().lower()
        if "market" in out or "market_info" in out:
            return "market_info"
        return "social_sentiment"
    except Exception as e:
        logger.warning("classify_social failed: %s, default to social_sentiment", e)
        return "social_sentiment"


# material_type -> (extract_primary, extract_er, primary_key)
_EXTRACTORS = {
    "social_sentiment": (
        extract_structured_sentiment,
        True,
        "sentiment",
        ["keywords"],  # derived from sentiment.key_phrases
    ),
    "policy": (
        extract_policy_info,
        True,
        "policy",
        [],
    ),
    "policy_regulation": (
        extract_policy_info,
        True,
        "policy",
        [],
    ),
    "market_info": (
        extract_market_full,
        True,
        "market",
        [],
    ),
}


def _get_text(doc: Material) -> str:
    """Get text content from document for extraction."""
    text = None
    if doc.extracted_data and isinstance(doc.extracted_data, dict):
        text = doc.extracted_data.get("text")
    if not text and doc.extracted_data and isinstance(doc.extracted_data, str):
        try:
            data = json.loads(doc.extracted_data)
            text = data.get("text") if isinstance(data, dict) else None
        except Exception:
            pass
    if not text:
        text = doc.content or doc.summary or doc.title or ""
    return (text or "").strip()


def _min_text_len(material_type: str) -> int:
    if material_type == "social_sentiment":
        return 20
    return 50


def _process_social_docs(
    session,
    limit: Optional[int],
    dry_run: bool,
    force: bool,
    skip_entities: bool,
    stats: dict,
) -> dict:
    """For demo_proj: classify material_type=social -> market_info or social_sentiment, then extract."""
    conditions = [Material.material_type == "social"]
    query = select(Material).where(*conditions)
    if limit:
        query = query.limit(limit)
    docs = list(session.execute(query).scalars().all())
    stats["social"]["total"] = len(docs)
    logger.info("Processing %d social docs (classify -> market_info or social_sentiment)", len(docs))

    for i, doc in enumerate(docs, 1):
        try:
            text = _get_text(doc)
            if len(text) < 20:
                stats["social"]["skipped"] += 1
                continue
            new_type = _classify_social_to_market_or_sentiment(text)
            doc.material_type = new_type
            logger.info("  Doc %s classified -> %s", doc.id, new_type)

            if isinstance(doc.extracted_data, str):
                try:
                    doc.extracted_data = json.loads(doc.extracted_data)
                except Exception:
                    doc.extracted_data = {}
            if not isinstance(doc.extracted_data, dict):
                doc.extracted_data = {}

            extract_fn, do_er, primary_key, _ = _EXTRACTORS[new_type]
            primary_data = extract_fn(text[:2000] if new_type == "social_sentiment" else text[:3000])
            updated = False
            if primary_data:
                doc.extracted_data[primary_key] = primary_data
                updated = True
                if primary_key == "sentiment" and "key_phrases" in primary_data:
                    doc.extracted_data["keywords"] = primary_data["key_phrases"]
            if do_er and not skip_entities:
                try:
                    er_data = extract_entities_relations(text[:3000])
                    if er_data and (er_data.get("entities") or er_data.get("relations")):
                        doc.extracted_data["entities_relations"] = er_data
                        updated = True
                except Exception:
                    pass
            if updated:
                flag_modified(doc, "extracted_data")
            if not dry_run:
                session.add(doc)
                if i % 5 == 0:
                    session.commit()
            stats["social"]["success"] += 1 if updated else 0
            if not updated:
                stats["social"]["skipped"] += 1
        except Exception as e:
            logger.error("Doc %s failed: %s", doc.id, e, exc_info=True)
            stats["social"]["error"] += 1

    if not dry_run and stats["social"]["success"] > 0:
        session.commit()
    return stats["social"]


def re_extract_all(
    project_key: str = "business_survey",
    material_types: Optional[list[str]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    force: bool = False,
    skip_entities: bool = False,
) -> dict:
    """
    Re-extract structured data for all documents.

    Args:
        project_key: Project context (business_survey, demo_proj, etc.)
        material_types: List of material_types to process (default: all supported)
        limit: Max documents per type (None = no limit)
        dry_run: If True, do not persist changes
        force: If True, re-extract even when primary key exists
        skip_entities: If True, skip entities_relations extraction

    Returns:
        Stats dict: {material_type: {total, success, error, skipped}}
    """
    types_to_process = material_types or list(_EXTRACTORS.keys())
    if "social" not in types_to_process and project_key == "demo_proj":
        types_to_process = ["social"] + [t for t in types_to_process if t != "social"]
    stats: dict = {t: {"total": 0, "success": 0, "error": 0, "skipped": 0} for t in types_to_process}

    with bind_project(project_key):
        with SessionLocal() as session:
            for material_type in types_to_process:
                if material_type == "social" and project_key == "demo_proj":
                    stats["social"] = _process_social_docs(
                        session, limit, dry_run, force, skip_entities, stats
                    )
                    continue
                if material_type not in _EXTRACTORS:
                    logger.warning("Unknown material_type %s, skipping", material_type)
                    continue

                extract_fn, do_er, primary_key, derived_keys = _EXTRACTORS[material_type]

                conditions = [Material.material_type == material_type]
                if not force:
                    conditions.append(
                        ~Material.extracted_data.has_key(primary_key)
                        if primary_key
                        else Material.extracted_data.is_(None)
                    )

                query = select(Material).where(*conditions)
                if limit:
                    query = query.limit(limit)
                docs = list(session.execute(query).scalars().all())
                stats[material_type]["total"] = len(docs)

                logger.info("Processing %d documents of type %s", len(docs), material_type)

                for i, doc in enumerate(docs, 1):
                    try:
                        text = _get_text(doc)
                        min_len = _min_text_len(material_type)
                        if len(text) < min_len:
                            logger.debug("Doc %s text too short (%d chars), skip", doc.id, len(text))
                            stats[material_type]["skipped"] += 1
                            continue

                        if isinstance(doc.extracted_data, str):
                            try:
                                doc.extracted_data = json.loads(doc.extracted_data)
                            except Exception as e:
                                logger.error("Doc %s invalid extracted_data: %s", doc.id, e)
                                stats[material_type]["error"] += 1
                                continue

                        if not isinstance(doc.extracted_data, dict):
                            doc.extracted_data = {}

                        updated = False

                        # Primary extraction
                        primary_data = extract_fn(text[:3000] if material_type != "social_sentiment" else text[:2000])
                        if primary_data:
                            doc.extracted_data[primary_key] = primary_data
                            updated = True
                            if primary_key == "sentiment" and "key_phrases" in primary_data:
                                doc.extracted_data["keywords"] = primary_data["key_phrases"]
                                updated = True

                        # Entities & relations
                        if do_er and not skip_entities:
                            try:
                                er_data = extract_entities_relations(text[:3000])
                                if er_data and (er_data.get("entities") or er_data.get("relations")):
                                    doc.extracted_data["entities_relations"] = er_data
                                    updated = True
                            except Exception as e:
                                logger.debug("Doc %s entities extraction failed: %s", doc.id, e)

                        if updated:
                            flag_modified(doc, "extracted_data")
                            if not dry_run:
                                session.add(doc)
                                if i % 10 == 0:
                                    session.commit()
                                    logger.info("  Committed %d/%d %s", i, len(docs), material_type)
                            stats[material_type]["success"] += 1
                            logger.debug("Doc %s extracted", doc.id)
                        else:
                            stats[material_type]["skipped"] += 1

                    except Exception as e:
                        logger.error("Doc %s failed: %s", doc.id, e, exc_info=True)
                        stats[material_type]["error"] += 1

                if not dry_run and stats[material_type]["success"] > 0:
                    session.commit()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Re-extract structured data for all documents")
    parser.add_argument("--project", default="business_survey", help="Project key")
    parser.add_argument("--types", nargs="+", default=None, help="Doc types (social_sentiment, policy, policy_regulation, market_info)")
    parser.add_argument("--limit", type=int, default=None, help="Max docs per type")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist")
    parser.add_argument("--force", action="store_true", help="Re-extract even if already has data")
    parser.add_argument("--no-entities", action="store_true", help="Skip entities_relations extraction")

    args = parser.parse_args()

    print("Re-extract all structured data")
    print("  project=%s types=%s limit=%s dry_run=%s force=%s" % (
        args.project, args.types or "all", args.limit, args.dry_run, args.force))
    print("-" * 60)

    result = re_extract_all(
        project_key=args.project,
        material_types=args.types,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        skip_entities=args.no_entities,
    )

    print("-" * 60)
    for material_type, s in result.items():
        print("  %s: total=%d success=%d error=%d skipped=%d" % (
            material_type, s["total"], s["success"], s["error"], s["skipped"]))
    if args.dry_run:
        print("\n(dry-run: no changes persisted)")
