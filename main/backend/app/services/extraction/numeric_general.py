"""General numeric extraction facade for structured extraction pipelines.

This module reuses `numeric.py` parsing capability and standardizes:
- numeric parsing result schema
- unit / currency normalization metadata
- quality scoring
- error codes
- raw value retention
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Tuple

from .numeric import CORE_SCOPE, normalize_numeric_with_meta

GENERAL_NUMERIC_OK = "OK"
GENERAL_NUMERIC_PARSE_FAILED = "NUMERIC_PARSE_FAILED"
GENERAL_NUMERIC_EMPTY = "NUMERIC_EMPTY"
GENERAL_NUMERIC_EMPTY_AFTER_CLEAN = "NUMERIC_EMPTY_AFTER_CLEAN"
GENERAL_NUMERIC_TOKEN_NOT_FOUND = "NUMERIC_TOKEN_NOT_FOUND"
GENERAL_NUMERIC_INVALID_FLOAT = "NUMERIC_INVALID_FLOAT"

_ERROR_MAP: Dict[str, str] = {
    "empty_value": GENERAL_NUMERIC_EMPTY,
    "empty_after_clean": GENERAL_NUMERIC_EMPTY_AFTER_CLEAN,
    "numeric_token_not_found": GENERAL_NUMERIC_TOKEN_NOT_FOUND,
    "invalid_float": GENERAL_NUMERIC_INVALID_FLOAT,
}

_CURRENCY_PATTERN = re.compile(
    r"(usd|eur|gbp|cny|rmb|jpy|yen|人民币|美元|欧元|英镑|日元|\$|€|£|¥|￥|円)",
    re.IGNORECASE,
)
_CURRENCY_MAP: Dict[str, str] = {
    "$": "USD",
    "usd": "USD",
    "美元": "USD",
    "€": "EUR",
    "eur": "EUR",
    "欧元": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "英镑": "GBP",
    "¥": "CNY",
    "￥": "CNY",
    "cny": "CNY",
    "rmb": "CNY",
    "人民币": "CNY",
    "円": "JPY",
    "jpy": "JPY",
    "yen": "JPY",
    "日元": "JPY",
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def _map_error_code(meta_error: str | None) -> str:
    if not meta_error:
        return GENERAL_NUMERIC_OK
    return _ERROR_MAP.get(meta_error, GENERAL_NUMERIC_PARSE_FAILED)


def _detect_currency(raw_text: str, default_currency: str | None = None) -> str | None:
    if not raw_text:
        return default_currency
    m = _CURRENCY_PATTERN.search(raw_text)
    if not m:
        return default_currency
    token = m.group(1).strip().lower()
    return _CURRENCY_MAP.get(token, default_currency)


def _score_quality(parsed: bool, meta: Mapping[str, Any]) -> float:
    if not parsed:
        return 0.0

    score = 100.0
    if bool(meta.get("converted_from_ratio")):
        score -= 10.0
    if bool(meta.get("raw_unit_detected")):
        score -= 5.0
    return max(0.0, min(100.0, score))


def extract_numeric_general(
    value: Any,
    *,
    expect_percent: bool = False,
    default_currency: str | None = None,
    scope: str = CORE_SCOPE,
) -> Dict[str, Any]:
    """Extract one numeric value with unified metadata and quality signal."""
    raw_text = _to_text(value)
    parsed_value, meta = normalize_numeric_with_meta(
        value,
        expect_percent=expect_percent,
        scope=scope,
    )

    parsed = bool(meta.get("parsed")) and parsed_value is not None
    error_code = _map_error_code(meta.get("error"))
    quality_score = _score_quality(parsed, meta)
    normalized_unit = "percent" if expect_percent else "value"
    currency = _detect_currency(raw_text, default_currency=default_currency)

    return {
        "value": parsed_value,
        "raw": raw_text,
        "parsed": parsed,
        "normalized_unit": normalized_unit,
        "currency": currency,
        "quality_score": quality_score,
        "error_code": error_code,
        "meta": dict(meta),
    }


def extract_numeric_fields(
    payload: Mapping[str, Any],
    *,
    field_rules: Mapping[str, Mapping[str, Any]],
    scope: str = CORE_SCOPE,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract multiple fields according to rules.

    rule shape:
    {
      "expect_percent": bool,
      "default_currency": "CNY" | "USD" | ...,
      "preserve_raw": bool,  # default True
    }
    """
    normalized: Dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
    fields_report: Dict[str, Any] = {}
    issues: list[str] = []
    total_score = 0.0
    field_count = 0

    for field, rule in field_rules.items():
        field_count += 1
        rule_dict = dict(rule) if isinstance(rule, Mapping) else {}
        raw_value = payload.get(field) if isinstance(payload, Mapping) else None
        result = extract_numeric_general(
            raw_value,
            expect_percent=bool(rule_dict.get("expect_percent", False)),
            default_currency=rule_dict.get("default_currency"),
            scope=scope,
        )
        total_score += float(result.get("quality_score", 0.0))
        fields_report[field] = result

        if result["parsed"]:
            if rule_dict.get("preserve_raw", True) and f"{field}_raw" not in normalized:
                normalized[f"{field}_raw"] = raw_value
            normalized[field] = result["value"]
        else:
            issues.append(f"{field}:{result['error_code']}")

    aggregate_score = round(total_score / max(1, field_count), 2)
    report = {
        "scope": scope,
        "fields": fields_report,
        "issues": issues,
        "quality_score": aggregate_score,
    }
    return normalized, report


__all__ = [
    "extract_numeric_general",
    "extract_numeric_fields",
    "GENERAL_NUMERIC_OK",
    "GENERAL_NUMERIC_PARSE_FAILED",
    "GENERAL_NUMERIC_EMPTY",
    "GENERAL_NUMERIC_EMPTY_AFTER_CLEAN",
    "GENERAL_NUMERIC_TOKEN_NOT_FOUND",
    "GENERAL_NUMERIC_INVALID_FLOAT",
]
