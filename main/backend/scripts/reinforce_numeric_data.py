#!/usr/bin/env python3
"""Backfill numeric normalization on existing stored data.

Use cases:
- Normalize `Document.extracted_data.market` numeric fields that were stored as text.
- Optionally normalize numeric fields hidden in `MarketStat.extra` into numeric columns.

Usage:
  python scripts/reinforce_numeric_data.py --scope lottery.market --doc-types market_info market --limit 200
"""
from __future__ import annotations

from contextlib import nullcontext
from decimal import Decimal
import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.models.base import SessionLocal
from app.models.entities import Document, MarketStat
from app.services.extraction.numeric import normalize_market_payload
from app.services.extraction.json_utils import extract_json_payload
from app.services.projects.context import bind_project
from app.services.llm.provider import get_chat_model
from app.services.llm.config_loader import get_llm_config, format_prompt_template

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 先根据文本中的数字进行抽取，再依据上下文谓词判断落到哪个字段。
_MKT_NUM_FIELD_KEYWORDS = {
    "sales_volume": {
        "sales",
        "销售",
        "销量",
        "volume",
        "market size",
        "sales volume",
        "销售额",
        "成交额",
        "market_data",
    },
    "revenue": {
        "revenue",
        "收入",
        "营收",
        "sales revenue",
        "营业收入",
        "总营收",
        "收入额",
    },
    "jackpot": {
        "jackpot",
        "奖池",
        "奖金",
        "头奖",
        "prize",
        "中彩金",
    },
    "ticket_price": {
        "ticket",
        "票价",
        "购买彩票",
        "每注",
        "ticket price",
        "彩票",
    },
    "yoy_change": {
        "同比",
        "yoy",
        "year over year",
        "同比增长",
        "比去年",
        "去年",
        "年度",
        "年增长",
    },
    "mom_change": {
        "环比",
        "mom",
        "month over month",
        "环比增长",
        "上月",
        "月度",
        "月增长",
        "较上月",
    },
    "growth_common": {
        "增长",
        "增长率",
        "增幅",
        "下降",
        "上升",
        "涨幅",
        "变动",
    },
}

_NUMERIC_MENTION_RE = re.compile(
    r"""(?P<num>
        [+-]?
        (?:(?:\d{1,3}(?:,\d{3})+)|\d+)
        (?:\.\d+)?
        (?:\s*[kKmMbB])?
        (?:\s*%)?
        (?:\s*(?:万|千|百万|千万|亿|十亿|元|人民币|usd|USD|美元|eur|EUR|欧元|¥|￥|\$))?
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_DATE_LIKE_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{1,2}[/-]?\d{0,2})\b")
_SHORT_NUMBER_RE = re.compile(r"^\d+$")

_MARKET_SEMANTIC_KEYWORDS = (
    "销售",
    "收入",
    "营收",
    "jackpot",
    "奖金",
    "增长",
    "同比",
    "环比",
    "ticket",
    "票价",
    "volume",
    "revenue",
    "market",
    "prize",
    "彩票",
)

_MEANINGFUL_NUMBER_UNITS = {
    "%",
    "$",
    "¥",
    "￥",
    "€",
    "元",
    "万",
    "千",
    "百万",
    "千万",
    "亿",
    "十亿",
    "美元",
    "人民币",
    "usd",
    "eur",
}
_MARKET_NUMERIC_FIELDS = ("sales_volume", "revenue", "jackpot", "ticket_price", "yoy_change", "mom_change")


def _to_project_ctx(project_key: str | None):
    if project_key:
        return bind_project(project_key)
    return nullcontext()


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _normalize_market_dict(market: Dict[str, Any], scope: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    normalized, quality = normalize_market_payload(
        dict(market),
        scope=scope,
    )
    return normalized, quality


def _has_dict_value(payload: Dict[str, Any], key: str) -> bool:
    if key not in payload:
        return False
    v = payload.get(key)
    return not (v is None or (isinstance(v, str) and not v.strip()))


def _extract_text_candidates(document: Document) -> str:
    parts = [document.title, document.summary, document.content]
    return "\n\n".join([x for x in parts if isinstance(x, str) and x.strip()]).strip()


def _clean_numeric_token(raw: str) -> str:
    return (raw or "").strip().replace(",", "")


def _is_meaningful_numeric(raw: str, context: str) -> bool:
    raw_clean = _clean_numeric_token(raw)
    if not raw_clean:
        return False

    # 排除疑似手机号/超长 ID
    if re.fullmatch(r"\d{11,}", raw_clean):
        return False

    # 排除纯短数字（一般是页码、序号等）
    if _SHORT_NUMBER_RE.fullmatch(raw_clean) and len(raw_clean) <= 2:
        return False

    # 进一步排除：像日期片段、范围/比例分母这样的片段
    if _DATE_LIKE_RE.search(context):
        return False
    if re.fullmatch(r"\d{4}[-/]\d{1,2}%", raw_clean):
        return False
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{1,2}", raw_clean):
        return False

    # 上下文必须包含有效市场语义
    if not any(kw in context for kw in _MARKET_SEMANTIC_KEYWORDS):
        return False

    # 有些数字虽然有上下文，但明显像章节号、序号
    if any(marker in context for marker in ("第", "章", "节", "项", "页", "附件")) and _SHORT_NUMBER_RE.fullmatch(raw_clean):
        return False

    # 有单位/符号的数字更容易是业务指标，缺单位且仅短数字优先弃用
    has_unit = any(unit in raw for unit in _MEANINGFUL_NUMBER_UNITS)
    if not has_unit and _SHORT_NUMBER_RE.fullmatch(raw_clean) and len(raw_clean) == 3:
        return False

    # 排除明显的序号/ID：以0开头的超短数，或重复高位整数
    if raw_clean.startswith("0") and len(raw_clean) == 3 and not has_unit:
        return False

    return True


def _numeric_context_score(field: str, context: str, raw_token: str) -> int:
    ctx = context.lower()
    score = 0
    for keyword in _MKT_NUM_FIELD_KEYWORDS.get(field, set()):
        if keyword.lower() in ctx:
            score += 3

    for keyword in _MKT_NUM_FIELD_KEYWORDS.get("growth_common", set()):
        if keyword in ctx:
            score += 1

    if field in {"yoy_change", "mom_change"} and "%" in raw_token:
        score += 1

    if field in {"sales_volume", "revenue", "jackpot", "ticket_price"}:
        if re.search(r"\b(?:万|千|百万|千万|亿|十亿|k|m|b|bn)\b", raw_token.lower()):
            score += 1
        if any(s in raw_token for s in ("$", "\u00a5", "¥", "€” , "元", "美元")):
            score += 1

    return score


def _infer_market_payload_from_text(text: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if not text:
        return payload

    lower_text = text.lower()
    candidate_meta: Dict[str, tuple[int, Any]] = {}

    for match in _NUMERIC_MENTION_RE.finditer(text):
        raw = (match.group("num") or "").strip()
        if not raw:
            continue

        raw_clean = _clean_numeric_token(raw)
        if not raw_clean:
            continue

        context = lower_text[max(0, match.start() - 90): min(len(text), match.end() + 90)]

        # 先做无意义数字过滤
        if not _is_meaningful_numeric(raw, context):
            continue

        selected_field = None
        best_score = 0
        for field in ("sales_volume", "revenue", "jackpot", "ticket_price", "yoy_change", "mom_change"):
            score = _numeric_context_score(field, context, raw)
            if score > best_score:
                best_score = score
                selected_field = field

        # 没有明确命中且得分低于2时认为是噪音
        if best_score <= 1:
            # 后备规则：无显式高置信关键词时按常见上下文补判定
            if "%" in raw and any(kw in context for kw in ("同比", "year over year", "yoy")):
                selected_field = "yoy_change"
                best_score = 1
            elif "%" in raw and any(kw in context for kw in ("环比", "month over month", "mom", "上月", "较上月")):
                selected_field = "mom_change"
                best_score = 1
            elif any(kw in context for kw in ("jackpot", "奖金", "奖池", "头奖")):
                selected_field = "jackpot"
                best_score = 1
            elif any(kw in context for kw in ("票价", "ticket", "每注")):
                selected_field = "ticket_price"
                best_score = 1
            elif any(
                kw in context
                for kw in ("销售", "sales", "销量", "成交", "销售量", "收入", "营收", "revenue")
            ):
                selected_field = "revenue"
                best_score = 1

        # 最低置信阈值
        if not selected_field or best_score < 1:
            continue

        if not selected_field:
            continue

        prev = candidate_meta.get(selected_field)
        if prev is None or best_score > prev[0]:
            candidate_meta[selected_field] = (best_score, raw)

    for field, (_, raw) in candidate_meta.items():
        payload[field] = raw

    return payload


def _fallback_infer_market_payload_from_llm(text: str, *, target_fields: Sequence[str] | None = None) -> Dict[str, Any]:
    """回退到LLM抽取：只提取市场数字字段，避免规则无法覆盖时的空漏。"""
    if not text:
        return {}

    prompt_fields = ", ".join(_MARKET_NUMERIC_FIELDS)
    if target_fields:
        prompt_fields = ", ".join([f for f in target_fields if f in _MARKET_NUMERIC_FIELDS])
    if not prompt_fields:
        return {}

    snippet = text[:3000].strip()
    if not snippet:
        return {}

    config = get_llm_config("market_info_extraction")
    if config and config.get("user_prompt_template"):
        # 使用项目已配置的提示词；新增约束确保只输出 JSON 与关键字段
        prompt = format_prompt_template(
            config["user_prompt_template"],
            text=snippet,
            fields=prompt_fields,
        )
        if "JSON" not in prompt.upper() and "json" not in prompt:
            prompt = f"{prompt}\n\n请只返回 JSON，不要额外说明。\n"
    else:
        prompt = (
            "你是结构化抽取助手。仅抽取以下数字字段："
            f"{prompt_fields}。\n"
            "仅输出严格 JSON 对象，不要任何说明。\n"
            "规则：只能返回字符串、数字或 null；若某字段未出现请返回 null。\n"
            f"文本：\n{snippet}"
        )

    try:
        model = get_chat_model(
            model=config.get("model") if config else None,
            temperature=config.get("temperature") if config else 0.1,
            max_tokens=config.get("max_tokens") if config else 600,
            top_p=config.get("top_p") if config else None,
            presence_penalty=config.get("presence_penalty") if config else None,
            frequency_penalty=config.get("frequency_penalty") if config else None,
        )
    except Exception as exc:
        logger.debug("llm market fallback unavailable: %s", exc)
        return {}

    try:
        response = model.invoke(f"{prompt}\n\n只输出 JSON 对象。")
        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_payload(content)
        if not isinstance(data, dict):
            return {}

        if "market" in data and isinstance(data["market"], dict):
            data = data["market"]

        out: Dict[str, Any] = {}
        for field in _MARKET_NUMERIC_FIELDS:
            if target_fields and field not in target_fields:
                continue
            if field not in data:
                continue
            value = data.get(field)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            out[field] = value
        return out
    except Exception as exc:
        logger.debug("llm market fallback failed: %s", exc)
        return {}


def reinforce_documents(
    session,
    *,
    doc_types: Sequence[str] | None = None,
    scope: str = "lottery.market",
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 100,
    infer_from_text: bool = False,
    llm_fallback: bool = False,
) -> Dict[str, int]:
    conditions = [Document.extracted_data.isnot(None)]
    if doc_types:
        conditions.append(Document.doc_type.in_(doc_types))

    query = select(Document).where(*conditions)
    if limit:
        query = query.limit(int(limit))
    documents = list(session.execute(query).scalars().all())

    stats: Dict[str, int] = {
        "total": len(documents),
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": 0,
        "inferred": 0,
        "llm_inferred": 0,
    }

    pending = 0
    for document in documents:
        try:
            extracted = document.extracted_data
            if not isinstance(extracted, dict):
                stats["skipped"] += 1
                continue

            baseline_market = extracted.get("market") if isinstance(extracted.get("market"), dict) else {}

            inferred_market: Dict[str, Any] = {}
            text_candidates = _extract_text_candidates(document)
            if infer_from_text:
                symbolic_market = _infer_market_payload_from_text(text_candidates)
                if symbolic_market:
                    inferred_market = symbolic_market
                    stats["inferred"] += len(inferred_market)

                if llm_fallback:
                    merged_for_missing = dict(baseline_market)
                    for field, value in inferred_market.items():
                        merged_for_missing[field] = value
                    target_fields = [
                        f
                        for f in _MARKET_NUMERIC_FIELDS
                        if not _has_dict_value(merged_for_missing, f)
                    ]
                    if target_fields:
                        llm_market = _fallback_infer_market_payload_from_llm(
                            text_candidates,
                            target_fields=target_fields,
                        )
                        if llm_market:
                            for field, value in llm_market.items():
                                if field in target_fields and not _has_dict_value(merged_for_missing, field):
                                    inferred_market[field] = value
                                    stats["llm_inferred"] += 1
                            if llm_market:
                                stats["inferred"] += len(llm_market)

            merged_market = dict(baseline_market)
            for field, value in inferred_market.items():
                if not _has_dict_value(merged_market, field):
                    merged_market[field] = value

            if not any(
                _has_dict_value(merged_market, k)
                for k in (
                    "sales_volume",
                    "revenue",
                    "jackpot",
                    "ticket_price",
                    "yoy_change",
                    "mom_change",
                )
            ):
                if baseline_market:
                    stats["unchanged"] += 1
                else:
                    stats["skipped"] += 1
                continue

            normalized_market, quality = _normalize_market_dict(merged_market, scope=scope)
            if not isinstance(normalized_market, dict):
                stats["errors"] += 1
                continue

            if normalized_market == baseline_market:
                stats["unchanged"] += 1
                continue

            existing_quality = baseline_market.get("numeric_quality")
            if isinstance(existing_quality, dict):
                numeric_quality = {
                    "source": existing_quality,
                    "supplement": quality,
                }
            else:
                numeric_quality = quality
            normalized_market["numeric_quality"] = numeric_quality

            extracted = dict(extracted)
            extracted["market"] = normalized_market
            document.extracted_data = extracted
            flag_modified(document, "extracted_data")

            stats["updated"] += 1
            pending += 1
            if pending >= batch_size and not dry_run:
                session.flush()
                session.commit()
                pending = 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("document reinforce failed doc_id=%s err=%s", document.id, exc)
            stats["errors"] += 1

    if pending and not dry_run:
        session.flush()
        session.commit()

    return stats


def _pick_raw_market_fields(extra: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}

    sales_volume = next((extra.get(k) for k in ["sales_volume", "sales_volume_raw"] if extra.get(k) not in (None, "")), None)
    if sales_volume is not None:
        payload["sales_volume"] = sales_volume

    revenue = next((extra.get(k) for k in ["revenue", "revenue_raw"] if extra.get(k) not in (None, "")), None)
    if revenue is not None:
        payload["revenue"] = revenue

    jackpot = next((extra.get(k) for k in ["jackpot", "jackpot_raw"] if extra.get(k) not in (None, "")), None)
    if jackpot is not None:
        payload["jackpot"] = jackpot

    ticket_price = next((extra.get(k) for k in ["ticket_price", "ticket_price_raw"] if extra.get(k) not in (None, "")), None)
    if ticket_price is not None:
        payload["ticket_price"] = ticket_price

    yoy = next((extra.get(k) for k in ["yoy", "yoy_change", "yoy_change_raw"] if extra.get(k) not in (None, "")), None)
    if yoy is not None:
        payload["yoy_change"] = yoy

    mom = next((extra.get(k) for k in ["mom", "mom_change", "mom_change_raw"] if extra.get(k) not in (None, "")), None)
    if mom is not None:
        payload["mom_change"] = mom

    return payload


def reinforce_market_stats(
    session,
    *,
    scope: str = "lottery.market",
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 100,
    force: bool = False,
) -> Dict[str, int]:
    query = select(MarketStat)
    if limit:
        query = query.limit(int(limit))
    rows = list(session.execute(query).scalars().all())

    stats: Dict[str, int] = {
        "total": len(rows),
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": 0,
    }

    pending = 0
    for row in rows:
        try:
            extra = row.extra
            if not isinstance(extra, dict):
                stats["skipped"] += 1
                continue

            payload = _pick_raw_market_fields(extra)
            if not payload:
                stats["unchanged"] += 1
                continue

            normalized_market, quality = _normalize_market_dict(payload, scope=scope)
            changed = False

            if force or row.sales_volume is None:
                if normalized_market.get("sales_volume") is not None:
                    row.sales_volume = _decimal_or_none(normalized_market["sales_volume"])
                    changed = True
            if force or row.revenue is None:
                if normalized_market.get("revenue") is not None:
                    row.revenue = _decimal_or_none(normalized_market["revenue"])
                    changed = True
            if force or row.jackpot is None:
                if normalized_market.get("jackpot") is not None:
                    row.jackpot = _decimal_or_none(normalized_market["jackpot"])
                    changed = True
            if force or row.ticket_price is None:
                if normalized_market.get("ticket_price") is not None:
                    row.ticket_price = _decimal_or_none(normalized_market["ticket_price"])
                    changed = True

            existing_quality = extra.get("numeric_quality")
            if isinstance(existing_quality, dict):
                extra["numeric_quality"] = {
                    "source": existing_quality,
                    "supplement": quality,
                }
            else:
                extra["numeric_quality"] = quality

            if changed:
                flag_modified(row, "extra")
                stats["updated"] += 1
                pending += 1
                if pending >= batch_size and not dry_run:
                    session.flush()
                    session.commit()
                    pending = 0
            else:
                stats["unchanged"] += 1

            row.extra = extra
        except Exception as exc:  # noqa: BLE001
            logger.warning("market_stat reinforce failed id=%s err=%s", row.id, exc)
            stats["errors"] += 1

    if pending and not dry_run:
        session.flush()
        session.commit()

    return stats


def _parse_doc_types(raw: str | None) -> List[str] | None:
    if not raw:
        return None
    values = [v.strip() for v in raw.split(",") if v.strip()]
    return values or None


def main() -> int:
    parser = argparse.ArgumentParser(description="数字化补齐工具（数值标准化）")
    parser.add_argument("--project-key", default=None, help="绑定项目（例如 online_lottery）")
    parser.add_argument("--scope", default="lottery.market", help="normalize_market_payload scope")
    parser.add_argument(
        "--doc-types",
        default="market_info,market",
        help="文档类型过滤，逗号分隔；空值表示处理所有 doc_type",
    )
    parser.add_argument("--limit", type=int, default=None, help="限制处理记录数（可选）")
    parser.add_argument("--batch-size", type=int, default=100, help="批量提交大小")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不入库")
    parser.add_argument("--include-market-stats", action="store_true", help="同时处理 MarketStat.extra 上的候选数字")
    parser.add_argument(
        "--no-infer-from-text",
        action="store_true",
        help="不进行文本数字搜索与谓词匹配，保持仅处理已抽取 market 字段",
    )
    parser.add_argument(
        "--llm-fallback",
        action="store_true",
        help="当文本符号化无结果时启用 LLM 回退抽取",
    )
    parser.add_argument(
        "--force-market-stats",
        action="store_true",
        help="MarketStat 数值列有值时也覆盖（默认仅补齐空值）",
    )

    args = parser.parse_args()
    doc_types = _parse_doc_types(args.doc_types)

    with _to_project_ctx(args.project_key):
        with SessionLocal() as session:
            doc_stats = reinforce_documents(
                session,
                doc_types=doc_types,
                scope=args.scope,
                limit=args.limit,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                infer_from_text=not args.no_infer_from_text,
                llm_fallback=args.llm_fallback,
            )
            market_stat_stats = None
            if args.include_market_stats:
                market_stat_stats = reinforce_market_stats(
                    session,
                    scope=args.scope,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                    force=args.force_market_stats,
                )

            if args.dry_run:
                session.rollback()

            logger.info("documents stats=%s", doc_stats)
            if market_stat_stats is not None:
                logger.info("market_stats stats=%s", market_stat_stats)
            print("documents:", doc_stats)
            if market_stat_stats is not None:
                print("market_stats:", market_stat_stats)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
