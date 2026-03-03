from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ...settings.config import settings


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    blocked: bool
    reason: str
    quality_score: float
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "blocked": self.blocked,
            "reason": self.reason,
            "quality_score": self.quality_score,
            "diagnostics": dict(self.diagnostics),
        }


_DEFAULT_LOW_VALUE_DOMAINS = ("news.google.com", "x.com", "actiontoaction.ai")
_DEFAULT_LOW_VALUE_PATH_KEYWORDS = ("/search", "/login", "/home", "/showcase", "/topics/", "/stargazers", "/sitemap")
_DEFAULT_SHELL_SIGNATURES = ("window.wiz_progre", "var bodycacheable = true", "self.__next_f", "errorcontainer")
_URL_CLEAN_RE = re.compile(r"https?://\S+")
_NON_TEXT_RE = re.compile(r"[^a-zA-Z0-9\u4e00-\u9fff]+")
_LINE_NOISE_MARKERS = (
    "skip to content",
    "accessibility help",
    "more menu",
    "watch live",
    "your account",
    "privacy policy",
    "terms of use",
    "cookies",
    "sourcemappingurl",
    "window.__",
    "window.wiz_",
    "self.__next_f",
    "var bodycacheable",
)
_NAV_NOISE_WORDS = {
    "home",
    "news",
    "sport",
    "sports",
    "business",
    "tech",
    "technology",
    "science",
    "video",
    "videos",
    "live",
    "menu",
    "search",
    "about",
    "contact",
    "help",
    "account",
    "login",
    "log",
    "signin",
    "sign",
    "register",
    "subscribe",
    "privacy",
    "policy",
    "terms",
    "cookie",
    "cookies",
    "settings",
    "首页",
    "新闻",
    "体育",
    "科技",
    "视频",
    "菜单",
    "搜索",
    "关于",
    "联系",
    "登录",
    "注册",
    "隐私",
    "条款",
    "设置",
}
_NOISE_LINE_PATTERNS = (
    re.compile(r"^\s*(privacy|terms|cookie|all rights reserved)\b", re.IGNORECASE),
    re.compile(r"^\s*(sign in|log in|register|subscribe)\b", re.IGNORECASE),
)
_JS_TEMPLATE_MARKERS = (
    "__dopostback",
    "__eventtarget",
    "__next",
    "window.",
    "document.",
    "function(",
    "var ",
    "@font-face",
    ":root",
    "sourcemappingurl",
)
_RSS_FEED_SHELL_MARKERS = (
    "no archive specified",
    "archives are:",
    "rss",
    "atom",
    "feed",
)
_MOJIBAKE_MARKERS = ("Ã", "Â", "�", "â€”", "â€œ", "â€", "è", "æ", "é©¾", "å·", "ç")
_REASON_CODE_RE = re.compile(r"[^a-z0-9_]+")


def _parse_config_list(raw: Any, defaults: tuple[str, ...]) -> list[str]:
    if raw is None:
        return list(defaults)
    if isinstance(raw, list):
        values = [str(x).strip() for x in raw if str(x or "").strip()]
        return values or list(defaults)
    text = str(raw).strip()
    if not text:
        return list(defaults)
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                values = [str(x).strip() for x in parsed if str(x or "").strip()]
                return values or list(defaults)
        except Exception:
            pass
    values = [x.strip() for x in text.split(",") if x.strip()]
    return values or list(defaults)


def normalize_reason_code(reason: Any, *, default: str = "unknown_rejection_reason") -> str:
    raw = str(reason or "").strip().lower()
    if not raw:
        return default
    normalized = _REASON_CODE_RE.sub("_", raw)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or default


def _resolve_gate_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    try:
        settings_map = settings.model_dump()
    except Exception:
        settings_map = {}
    strict_gate_default = bool(settings_map.get("ingest_enable_strict_gate", False))
    low_value_domains_default = settings_map.get("ingest_low_value_domains", ",".join(_DEFAULT_LOW_VALUE_DOMAINS))
    low_value_paths_default = settings_map.get("ingest_low_value_path_keywords", ",".join(_DEFAULT_LOW_VALUE_PATH_KEYWORDS))
    shell_signatures_default = settings_map.get("ingest_shell_signatures", ",".join(_DEFAULT_SHELL_SIGNATURES))
    min_semantic_len_default = int(settings_map.get("ingest_min_semantic_len", 500))
    return {
        "enable_strict_gate": bool(cfg.get("enable_strict_gate", strict_gate_default)),
        "low_value_domains": [
            x.lower() for x in _parse_config_list(cfg.get("low_value_domains", low_value_domains_default), _DEFAULT_LOW_VALUE_DOMAINS)
        ],
        "low_value_path_keywords": [
            x.lower() for x in _parse_config_list(cfg.get("low_value_path_keywords", low_value_paths_default), _DEFAULT_LOW_VALUE_PATH_KEYWORDS)
        ],
        "shell_signatures": [
            x.lower() for x in _parse_config_list(cfg.get("shell_signatures", shell_signatures_default), _DEFAULT_SHELL_SIGNATURES)
        ],
        "min_semantic_len": int(cfg.get("min_semantic_len", min_semantic_len_default)),
    }


def _semantic_text_len(content: str) -> int:
    text = str(content or "").strip()
    if not text:
        return 0
    text = _URL_CLEAN_RE.sub(" ", text)
    text = _NON_TEXT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text)


def _mojibake_hits(text: str) -> int:
    sample = str(text or "")
    if not sample:
        return 0
    return sum(sample.count(marker) for marker in _MOJIBAKE_MARKERS)


def _is_api_status_wrapper(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw.startswith("{") or not raw.endswith("}"):
        return False
    try:
        payload = json.loads(raw)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if "url" not in payload or "status" not in payload:
        return False
    body = str(payload.get("text") or "").strip()
    title = str(payload.get("title") or "").strip()
    return not body and not title


def _js_template_hits(lower_text: str) -> int:
    return sum(lower_text.count(marker) for marker in _JS_TEMPLATE_MARKERS)


def normalize_content_for_ingest(content: str, *, max_chars: int = 50000) -> str:
    text = str(content or "").replace("\x00", "").strip()
    if not text:
        return ""
    raw_lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line and line.strip()]
    if len(raw_lines) <= 1:
        raw_lines = [line.strip() for line in re.split(r"(?<=[.!?])\s+", text) if line and line.strip()]
    kept: list[str] = []
    seen_kept: set[str] = set()

    def _is_noise_line(line: str) -> bool:
        lower = line.lower()
        if any(marker in lower for marker in _LINE_NOISE_MARKERS):
            return True
        if any(p.search(line) for p in _NOISE_LINE_PATTERNS):
            return True
        script_hits = sum(1 for marker in _JS_TEMPLATE_MARKERS if marker in lower)
        if script_hits >= 2 and len(line) < 240:
            return True
        tokens = re.findall(r"[a-zA-Z\u4e00-\u9fff]+", lower)
        if len(tokens) >= 4:
            nav_hits = sum(1 for t in tokens if t in _NAV_NOISE_WORDS)
            if nav_hits / float(len(tokens)) >= 0.6 and len(tokens) <= 24:
                return True
        sep_hits = line.count("|") + line.count("›") + line.count("»") + line.count("•")
        if sep_hits >= 3 and len(tokens) <= 24:
            return True
        return False

    for line in raw_lines:
        if _is_noise_line(line):
            continue
        if len(line) < 3:
            continue
        key = line.strip().lower()
        if key in seen_kept:
            continue
        seen_kept.add(key)
        kept.append(line)
    normalized = "\n".join(kept).strip()
    if not normalized:
        normalized = text
    return normalized[:max_chars]


def url_policy_check(uri: str, config: dict[str, Any] | None = None) -> GateDecision:
    cfg = _resolve_gate_config(config)
    parsed = urlparse(str(uri or "").strip())
    domain = str(parsed.netloc or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    if not cfg["enable_strict_gate"]:
        return GateDecision(
            accepted=True,
            blocked=False,
            reason="disabled",
            quality_score=100.0,
            diagnostics={"domain": domain, "path": path},
        )

    domain_hit = next((d for d in cfg["low_value_domains"] if domain == d or domain.endswith(f".{d}")), None)
    if domain_hit:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="url_policy_low_value_domain",
            quality_score=0.0,
            diagnostics={"domain": domain, "path": path, "matched_domain": domain_hit},
        )

    path_hit = next((kw for kw in cfg["low_value_path_keywords"] if kw and kw in path), None)
    if path_hit:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="url_policy_low_value_endpoint",
            quality_score=0.0,
            diagnostics={"domain": domain, "path": path, "matched_path_keyword": path_hit},
        )

    return GateDecision(
        accepted=True,
        blocked=False,
        reason="ok",
        quality_score=100.0,
        diagnostics={"domain": domain, "path": path},
    )


def content_quality_check(
    uri: str,
    content: str,
    doc_type: str | None,
    extraction_status: dict[str, Any] | str | None = None,
    config: dict[str, Any] | None = None,
) -> GateDecision:
    cfg = _resolve_gate_config(config)
    text = str(content or "")
    stripped = normalize_content_for_ingest(text)
    lower = stripped.lower()
    semantic_len = _semantic_text_len(stripped)
    min_len = max(1, int(cfg["min_semantic_len"]))
    if not cfg["enable_strict_gate"]:
        return GateDecision(
            accepted=True,
            blocked=False,
            reason="disabled",
            quality_score=100.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "min_semantic_len": min_len},
        )

    if not stripped:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_empty",
            quality_score=0.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len},
        )

    if _is_api_status_wrapper(stripped):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_api_status_wrapper",
            quality_score=0.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len},
        )

    matched_sig = next((sig for sig in cfg["shell_signatures"] if sig and sig in lower), None)
    if matched_sig:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_shell_signature",
            quality_score=10.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "matched_signature": matched_sig, "semantic_len": semantic_len},
        )

    extraction_ok = False
    if isinstance(extraction_status, dict):
        extraction_ok = bool(extraction_status.get("text_extracted")) or bool(extraction_status.get("extraction_enabled"))
    elif isinstance(extraction_status, str):
        extraction_ok = extraction_status.strip().lower() in {"ok", "success", "extracted"}
    if stripped.startswith("%PDF-1.") and not extraction_ok and semantic_len < min_len:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_pdf_binary_without_text",
            quality_score=0.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len},
        )

    parsed = urlparse(str(uri or "").strip())
    path = str(parsed.path or "").lower()
    is_feed_like_path = bool(
        path.endswith(".xml")
        or "/rss" in path
        or "/feed" in path
        or path.endswith("/rss")
        or path.endswith("/feed")
    )
    feed_marker_hits = sum(lower.count(marker) for marker in _RSS_FEED_SHELL_MARKERS)
    if is_feed_like_path and semantic_len < max(400, min_len * 2) and feed_marker_hits >= 1:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_rss_feed_shell",
            quality_score=5.0,
            diagnostics={
                "uri": uri,
                "doc_type": doc_type,
                "semantic_len": semantic_len,
                "feed_marker_hits": feed_marker_hits,
            },
        )

    js_hits = _js_template_hits(lower)
    if js_hits >= 6 and semantic_len < max(1600, min_len * 3):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_js_template_shell",
            quality_score=12.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "js_template_hits": js_hits},
        )

    mojibake_hits = _mojibake_hits(stripped)
    if mojibake_hits >= 3 and semantic_len < max(2400, min_len * 5):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_mojibake_garbled",
            quality_score=8.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "mojibake_hits": mojibake_hits},
        )

    nav_marker_hits = sum(lower.count(marker) for marker in ("skip to content", "more menu", "accessibility help", "watch live"))
    if path in {"", "/"} and nav_marker_hits >= 2 and semantic_len < max(2200, min_len * 4):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_navigation_or_home_shell",
            quality_score=15.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "nav_marker_hits": nav_marker_hits},
        )
    if nav_marker_hits >= 4 and semantic_len < max(2000, min_len * 4):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_navigation_shell",
            quality_score=15.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "nav_marker_hits": nav_marker_hits},
        )

    link_hits = lower.count("http://") + lower.count("https://")
    if link_hits >= 15 and semantic_len < max(2200, min_len * 4):
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_link_farm_like",
            quality_score=20.0,
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "link_hits": link_hits},
        )

    if semantic_len < min_len:
        return GateDecision(
            accepted=False,
            blocked=True,
            reason="content_semantic_too_short",
            quality_score=max(1.0, round((semantic_len / float(min_len)) * 100.0, 2)),
            diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "min_semantic_len": min_len},
        )

    score = min(100.0, max(0.0, 70.0 + min(30.0, (semantic_len - min_len) / 20.0)))
    return GateDecision(
        accepted=True,
        blocked=False,
        reason="ok",
        quality_score=round(score, 2),
        diagnostics={"uri": uri, "doc_type": doc_type, "semantic_len": semantic_len, "min_semantic_len": min_len},
    )
