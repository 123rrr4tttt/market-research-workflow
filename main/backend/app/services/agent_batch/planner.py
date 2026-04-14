from __future__ import annotations

import re
from typing import Any

AGENT_BATCH_PLANNER_PROMPT_ID = "agent_batch_planner.v1"
AGENT_BATCH_PLANNER_CONTRACT_VERSION = "agent_batch_planner.contract.v1"
from .task_contract import (
    AGENT_BATCH_TASK_MANIFEST_VERSION,
    build_agent_batch_tasks_schema,
    get_agent_batch_known_channels,
    get_agent_batch_task_contract_specs,
    is_agent_batch_task_executable,
    normalize_agent_batch_task,
    normalize_query_terms,
)

REASON_SKILL_PLAN_INVALID_JSON = "skill_planner_invalid_json"
REASON_SKILL_PLAN_SCHEMA_INVALID = "skill_planner_schema_invalid"
REASON_SKILL_PLAN_EMPTY_TASKS = "skill_planner_empty_tasks"

_ALLOWED_PLAN_CHANNELS = get_agent_batch_known_channels()
_PROVIDER_ORDER = ("google", "serper", "serpapi", "serpstack", "ddg", "bing", "auto")
_PROVIDER_HINTS = {
    "google": ("google", "谷歌"),
    "serper": ("serper",),
    "serpapi": ("serpapi",),
    "serpstack": ("serpstack",),
    "ddg": ("ddg", "duckduckgo", "duck duck go"),
    "bing": ("bing", "必应"),
    "auto": ("auto", "自动"),
}
_PROVIDER_ALIAS_SET = {
    alias.lower()
    for aliases in _PROVIDER_HINTS.values()
    for alias in aliases
}

_CN_PREFIX_PATTERNS = (
    r"^请?\s*帮我\s*(搜索|查找|找|收集|整理)\s*",
    r"^麻烦\s*你\s*(帮我)?\s*(搜索|查找|找|收集|整理)\s*",
    r"^帮我\s*(搜索|查找|找|收集|整理)\s*",
)
_EN_PREFIX_PATTERNS = (
    r"^please\s+help\s+me\s+(search|find|look\s+up|collect)\s+",
    r"^help\s+me\s+(search|find|look\s+up|collect)\s+",
    r"^please\s+(search|find|look\s+up|collect)\s+",
)

_ACTION_NOISE = (
    r"\b(search|find|look\s*up|collect|gather|get|about|for|me|please|news|updates|information|results?)\b",
    r"(搜索|查找|收集|整理|帮我|帮忙|请|一下|一下子|相关|信息|资料|新闻|动态)",
)

_SPLIT_RE = re.compile(r"\s*(?:，|,|、|；|;|\band\b|\bor\b|和|与|及|以及|并且|还有)\s*", flags=re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_/\.]*|[\u4e00-\u9fff]{2,}")


def build_agent_batch_task_manifest() -> dict[str, Any]:
    """Authoritative callable task catalog used by planner prompt construction."""
    task_specs = get_agent_batch_task_contract_specs()
    manifest = {
        "manifest_version": AGENT_BATCH_TASK_MANIFEST_VERSION,
        "contract_version": AGENT_BATCH_PLANNER_CONTRACT_VERSION,
        "output_keys": ["intent", "strategy", "constraints", "tasks"],
        "constraints_schema": {
            "retrieval_mode": {
                "type": "string",
                "allowed": ["hybrid", "source_only", "web_only"],
                "default": "hybrid",
            }
        },
        "tasks_schema": build_agent_batch_tasks_schema(),
        "callable_tasks": [dict(task_specs[key]) for key in sorted(task_specs.keys())],
        "examples": [
            {
                "channel": "search.market",
                "query_terms": ["ai terminal product launches"],
                "max_items": 20,
                "provider": "auto",
                "language": "en",
                "days_back": 14,
            },
            {
                "channel": "source_library",
                "item_key": "ai_terminal.weekly",
                "query_terms": ["ai terminal product launches"],
                "max_items": 1,
                "language": "zh",
                "source_mode": "site_search",
            },
        ],
    }
    dynamic_entries = _collect_registered_agent_batch_task_manifest_entries()
    if dynamic_entries:
        merged = {str(item.get("channel") or "").strip().lower(): dict(item) for item in manifest["callable_tasks"]}
        for entry in dynamic_entries:
            channel = str(entry.get("channel") or "").strip().lower()
            if not channel:
                continue
            if channel not in _ALLOWED_PLAN_CHANNELS:
                continue
            base = dict(merged.get(channel) or {"channel": channel})
            base.update(dict(entry))
            base["channel"] = channel
            merged[channel] = base
        manifest["callable_tasks"] = [merged[key] for key in sorted(merged.keys())]
    return manifest


def _collect_registered_agent_batch_task_manifest_entries() -> list[dict[str, Any]]:
    try:
        from app.services.skill_runtime import list_registered_agent_batch_task_manifest_entries

        entries = list_registered_agent_batch_task_manifest_entries()
        return [dict(x) for x in entries if isinstance(x, dict)]
    except Exception:
        return []


def validate_skill_planner_contract(candidate: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Validate skill planner output contract and return stable reason_code on failure."""
    if not isinstance(candidate, dict):
        return None, REASON_SKILL_PLAN_SCHEMA_INVALID

    tasks = candidate.get("tasks")
    if not isinstance(tasks, list):
        return None, REASON_SKILL_PLAN_SCHEMA_INVALID
    if len(tasks) == 0:
        return None, REASON_SKILL_PLAN_EMPTY_TASKS

    normalized_tasks: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            return None, REASON_SKILL_PLAN_SCHEMA_INVALID
        channel = str(task.get("channel") or "").strip().lower()
        if channel not in _ALLOWED_PLAN_CHANNELS:
            return None, REASON_SKILL_PLAN_SCHEMA_INVALID
        task = {**task, "channel": channel}
        normalized_task = normalize_agent_batch_task(task, idx=len(normalized_tasks) + 1, default_language="en")
        if not normalized_task:
            return None, REASON_SKILL_PLAN_SCHEMA_INVALID
        if not is_agent_batch_task_executable(normalized_task):
            return None, REASON_SKILL_PLAN_EMPTY_TASKS
        normalized_tasks.append(normalized_task)

    normalized = {
        "contract_version": AGENT_BATCH_PLANNER_CONTRACT_VERSION,
        "prompt_id": AGENT_BATCH_PLANNER_PROMPT_ID,
        "intent": str(candidate.get("intent") or "market_research_general"),
        "strategy": str(candidate.get("strategy") or "single_query"),
        "constraints": dict(candidate.get("constraints") or {}),
        "tasks": normalized_tasks,
    }
    return normalized, None


def plan_batch_search_command(command: str) -> dict[str, Any]:
    """Deterministic parser for zh/en natural-language batch search commands."""
    raw = _normalize_space(command)
    if not raw:
        raise ValueError("command is required")

    language = _detect_language(raw)
    cleaned = _strip_prefix_boilerplate(raw)
    constraints = _parse_constraints(cleaned)
    query_text = _remove_constraint_phrases(cleaned)
    terms = _extract_query_terms(query_text, language=language)

    if not terms:
        terms = ["market research" if language == "en" else "市场研究"]

    intent = _detect_intent(query_text)
    per_task_max = constraints["max_items"] if constraints["max_items"] is not None else 20
    task_provider = constraints["provider_hints"][0] if constraints["provider_hints"] else "auto"

    tasks: list[dict[str, Any]] = []
    for idx, term in enumerate(terms, start=1):
        tasks.append(
            {
                "task_id": f"search_{idx}",
                "channel": "search.market",
                "query_terms": [term],
                "max_items": per_task_max,
                "days_back": constraints["days_back"],
                "provider": task_provider,
                "language": language,
            }
        )

    strategy = "parallel_by_query_term" if len(tasks) > 1 else "single_query"
    return {
        "intent": intent,
        "tasks": tasks,
        "strategy": strategy,
        "constraints": constraints,
    }


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _detect_language(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"


def _strip_prefix_boilerplate(text: str) -> str:
    out = text.strip()
    for pattern in (*_CN_PREFIX_PATTERNS, *_EN_PREFIX_PATTERNS):
        out = re.sub(pattern, "", out, flags=re.IGNORECASE).strip()
    return out


def _parse_constraints(text: str) -> dict[str, Any]:
    lower = text.lower()
    max_items = _parse_max_items(text)
    days_back = _parse_days_back(text)

    provider_hints: list[str] = []
    for provider in _PROVIDER_ORDER:
        aliases = _PROVIDER_HINTS.get(provider, ())
        if any(alias in lower for alias in aliases):
            provider_hints.append(provider)

    return {
        "max_items": max_items,
        "days_back": days_back,
        "provider_hints": provider_hints,
    }


def _parse_max_items(text: str) -> int | None:
    patterns = (
        r"前\s*(\d{1,3})\s*条",
        r"最多\s*(\d{1,3})\s*条",
        r"(\d{1,3})\s*条",
        r"\b(top|first)\s*(\d{1,3})\b",
        r"\b(up\s*to|at\s*most|limit)\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*results?\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        value = next((g for g in m.groups()[::-1] if g and g.isdigit()), None)
        if value is None:
            continue
        return max(1, min(100, int(value)))
    return None


def _parse_days_back(text: str) -> int | None:
    patterns = (
        r"(?:最近|过去|近)\s*(\d{1,3})\s*天",
        r"\b(?:last|past|within)\s*(\d{1,3})\s*days?\b",
    )
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return max(1, min(365, int(m.group(1))))

    if re.search(r"最近一周|过去一周|last\s+week", text, flags=re.IGNORECASE):
        return 7
    if re.search(r"最近一个月|过去一个月|last\s+month", text, flags=re.IGNORECASE):
        return 30
    return None


def _remove_constraint_phrases(text: str) -> str:
    out = text
    patterns = (
        r"(?:最近|过去|近)\s*\d{1,3}\s*天",
        r"\b(?:last|past|within)\s*\d{1,3}\s*days?\b",
        r"最近一周|过去一周|last\s+week",
        r"最近一个月|过去一个月|last\s+month",
        r"前\s*\d{1,3}\s*条",
        r"最多\s*\d{1,3}\s*条",
        r"\d{1,3}\s*条",
        r"\b(top|first|up\s*to|at\s*most|limit)\s*\d{1,3}\b",
        r"\b\d{1,3}\s*results?\b",
        r"(优先|使用|via|with)\s*(google|serper|serpapi|serpstack|ddg|duckduckgo|bing|auto|谷歌|必应|自动)",
    )
    for pattern in patterns:
        out = re.sub(pattern, " ", out, flags=re.IGNORECASE)
    return _normalize_space(out)


def _extract_query_terms(text: str, *, language: str) -> list[str]:
    out = text
    for pattern in _ACTION_NOISE:
        out = re.sub(pattern, " ", out, flags=re.IGNORECASE)
    out = _normalize_space(out)

    terms: list[str] = []
    for segment in _SPLIT_RE.split(out):
        candidate = _clean_segment(segment)
        if not candidate:
            continue
        if candidate not in terms:
            terms.append(candidate)

    if terms:
        return terms[:8]

    # Last-resort token fallback keeps deterministic extraction and avoids raw whole sentence.
    tokens = _WORD_RE.findall(out)
    fallback = " ".join(tokens[:8]).strip() if language == "en" else "".join(tokens[:4]).strip()
    return [fallback] if fallback else []


def _clean_segment(segment: str) -> str:
    value = _normalize_space(segment)
    if not value:
        return ""
    value = re.sub(r"^[^0-9A-Za-z\u4e00-\u9fff]+|[^0-9A-Za-z\u4e00-\u9fff]+$", "", value)
    value = _normalize_space(value)

    if len(value) <= 1:
        return ""
    if re.fullmatch(r"[0-9]+", value):
        return ""
    if value.lower() in _PROVIDER_ALIAS_SET:
        return ""
    if value.lower() in {"and", "or", "the", "a", "an"}:
        return ""
    return value


def _detect_intent(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ("监管", "政策", "法规", "regulation", "policy", "compliance", "law")):
        return "regulatory_monitoring"
    if any(k in lower for k in ("竞品", "竞争", "对手", "competitor", "competition", "rival")):
        return "competitive_research"
    if any(k in lower for k in ("价格", "定价", "pricing", "price")):
        return "pricing_research"
    if any(k in lower for k in ("news", "动态", "趋势", "trend", "update")):
        return "market_news"
    return "market_research_general"
