"""Numeric normalization utilities for extraction and market ingestion pipelines.

目标：统一处理从 LLM / 文本解析 / 外部 API 进入的数值，让市场链路在口径上保持一致。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

_PERCENT_SYMBOLS = ("%", "％")
CORE_SCOPE = "core"
PROJECT_SCOPE_PREFIX = "project."


def _to_project_scope(project_key: str) -> str:
    if not project_key:
        return PROJECT_SCOPE_PREFIX + "market"
    if project_key.startswith(PROJECT_SCOPE_PREFIX):
        return project_key
    return PROJECT_SCOPE_PREFIX + project_key


_UNIT_SCALE = {
    # English suffixes
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "million": 1_000_000.0,
    "mn": 1_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    # 中文数量级
    "千": 1_000.0,
    "万": 10_000.0,
    "十万": 100_000.0,
    "百万": 1_000_000.0,
    "千万": 10_000_000.0,
    "亿": 100_000_000.0,
    "十亿": 1_000_000_000.0,
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def _clean_text(text: str) -> str:
    t = text.strip()
    if not t:
        return ""
    # 统一符号与空白
    t = t.replace("\u00a0", " ").replace("\t", " ").replace(",", "")
    t = t.replace("$", "").replace("¥", "").replace("€", "").replace("￥", "")
    t = t.replace("％", "%")
    # 过滤常见噪音词
    t = t.replace("约", "").replace("左右", "").replace("约等于", "")
    return t.strip()


def _detect_percent(text: str) -> bool:
    return any(symbol in text for symbol in _PERCENT_SYMBOLS)


def _extract_number(text: str) -> Tuple[str | None, str]:
    """Extract number string and suffix part."""
    m = re.search(r"([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)", text)
    if not m:
        return None, text
    number = m.group(1)
    suffix = text[m.end() :].strip().lower()
    # 去掉常见连接词
    suffix = suffix.replace("/", "").replace("(", "").replace(")", "")
    suffix = suffix.replace("元", "").replace("人民币", "").replace("usd", "")
    return number, suffix


def _scale_from_suffix(suffix: str) -> float:
    # 处理像“百万美元”这种结构
    for unit in sorted(_UNIT_SCALE.keys(), key=len, reverse=True):
        if unit in suffix:
            return _UNIT_SCALE[unit]
    return 1.0


def normalize_numeric_with_meta(
    value: Any,
    *,
    expect_percent: bool = False,
    scope: str = CORE_SCOPE,
) -> Tuple[float | None, Dict[str, Any]]:
    """Normalize one scalar to float.

    Returns:
        (normalized_value, metadata)
    metadata 说明是否解析成功、输入是否有单位/百分号和最终单位口径。
    """
    raw = _to_text(value)
    meta: Dict[str, Any] = {
        "raw": raw,
        "parsed": False,
        "unit": None,
        "raw_unit_detected": False,
        "scope": scope,
        "data_class": "core" if scope == CORE_SCOPE else "project_extension",
    }

    if not raw:
        meta["error"] = "empty_value"
        return None, meta

    text = _clean_text(raw)
    if not text:
        meta["error"] = "empty_after_clean"
        return None, meta

    # 去除括号中的注释性说明，例如 “10% (估计)”
    text = re.sub(r"\(.*?\)", "", text).strip()
    percent_hint = _detect_percent(text)

    if percent_hint:
        text = text.replace("%", "")

    number_text, suffix = _extract_number(text)
    if not number_text:
        meta["error"] = "numeric_token_not_found"
        return None, meta

    try:
        num = float(number_text)
    except ValueError:
        meta["error"] = "invalid_float"
        return None, meta

    scale = 1.0
    if suffix:
        scale = _scale_from_suffix(suffix)
        if scale != 1.0:
            meta["raw_unit_detected"] = True

    normalized = num * scale

    # 若 expect_percent 且原始输入没有显式百分号，且数值像 ratio（<=1），转为百分比数
    if expect_percent and not percent_hint and abs(normalized) <= 1:
        normalized *= 100
        meta["converted_from_ratio"] = True

    if expect_percent and percent_hint:
        # 仅保留百分比单位语义，不再额外缩放
        meta["unit"] = "percent"
    elif expect_percent:
        meta["unit"] = "percent"
    else:
        meta["unit"] = "value"

    meta["parsed"] = True
    meta["input_scale"] = scale
    return normalized, meta


def normalize_numeric_scalar(value: Any, *, expect_percent: bool = False) -> float | None:
    value_norm, _ = normalize_numeric_with_meta(value, expect_percent=expect_percent)
    return value_norm


def normalize_market_payload(
    market: Dict[str, Any],
    *,
    scope: str = "lottery.market",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Normalize market payload numeric fields in-place semantics and return quality report."""
    if not isinstance(market, dict):
        return market, {
            "scope": _to_project_scope(scope),
            "data_class": "project_extension",
            "parsed_fields": {},
            "issues": ["market_payload_not_dict"],
            "quality_score": 0.0,
        }

    normalized = dict(market)
    project_scope = _to_project_scope(scope)
    data_class = "project_extension" if project_scope.startswith(PROJECT_SCOPE_PREFIX) else "core"
    quality: Dict[str, Any] = {
        "scope": project_scope,
        "data_class": data_class,
        "parsed_fields": {},
        "issues": [],
        "quality_score": 0.0,
    }

    field_rules = {
        "sales_volume": False,
        "revenue": False,
        "jackpot": False,
        "ticket_price": False,
        "yoy_change": True,
        "mom_change": True,
    }

    parsed_count = 0
    for field, expect_percent in field_rules.items():
        raw = normalized.get(field)
        value, meta = normalize_numeric_with_meta(
            raw,
            expect_percent=expect_percent,
            scope=project_scope,
        )

        if raw is None:
            quality["parsed_fields"][field] = {"status": "missing", "metadata": meta}
            continue

        if value is None:
            quality["parsed_fields"][field] = {"status": "parse_failed", "metadata": meta}
            quality["issues"].append(f"{field}:parse_failed")
            continue

        if value != raw and f"{field}_raw" not in normalized:
            normalized[f"{field}_raw"] = raw

        parsed_count += 1
        normalized[field] = value
        quality["parsed_fields"][field] = {
            "status": "ok",
            "metadata": meta,
        }

    quality_total = max(1, len(field_rules))
    quality["quality_score"] = round(parsed_count * 100 / quality_total, 2)
    return normalized, quality
