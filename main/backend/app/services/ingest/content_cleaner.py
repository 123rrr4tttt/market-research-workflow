from __future__ import annotations

import re
from typing import Any


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
    "follow us on",
    "suggested for you",
    "join the conversation",
    "share on facebook",
    "share on twitter",
    "share on linkedin",
    "share copy link",
    "newsletter",
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
    "gtag(",
    "addEventListener(",
    "appendchild(",
    "navigator.",
    "classlist.",
    "prototype.",
    "symbol.iterator",
    "spdx-license-identifier",
)
_CSS_PROPERTY_MARKERS = (
    "display:",
    "margin:",
    "padding:",
    "border-radius:",
    "box-shadow:",
    "font-size:",
    "max-width:",
    "object-fit:",
    "list-style:",
    "transition:",
    "background:",
    "color:",
)
_JSON_NOISE_MARKERS = (
    '"@context"',
    '"@type"',
    '"itemlistelement"',
    '"position"',
    "schema.org",
    "breadcrumblist",
)
_HTML_TAG_RE = re.compile(r"<[^>]{1,200}>")
_SCRIPT_ASSIGNMENT_RE = re.compile(
    r"\b(window|document|navigator|gtag|dataLayer|analytics|cookieMessage|browserNotSupportedMessage)\b"
    r"|(?:function\s+[A-Za-z_]\w*\s*\()"
    r"|(?:\b(?:var|const|let)\s+[A-Za-z_$][\w$]*\s*=)"
    r"|(?:=>\s*\{?)"
    r"|(?:appendChild\s*\()"
    r"|(?:classList\.)",
    re.IGNORECASE,
)
_EMBEDDED_HTML_FRAGMENT_RE = re.compile(r"['\"]\s*<[^>]{1,300}>[\s\S]{0,2000}")


def normalize_content_for_ingest(content: str, *, max_chars: int = 50000) -> str:
    text = str(content or "").replace("\x00", "").strip()
    text = _EMBEDDED_HTML_FRAGMENT_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    if not text:
        return ""
    raw_lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line and line.strip()]
    if len(raw_lines) <= 1:
        raw_lines = [line.strip() for line in re.split(r"(?<=[.!?])\s+", text) if line and line.strip()]
    if len(raw_lines) <= 3:
        lowered = text.lower()
        script_density = sum(lowered.count(marker) for marker in _JS_TEMPLATE_MARKERS)
        if script_density >= 2 or text.count(";") >= 8 or (text.count("{") + text.count("}")) >= 8:
            split_lines = [
                line.strip()
                for line in re.split(r";\s+|(?<=\})\s+|(?<=\))\s+(?=[A-Za-z_$])", text)
                if line and line.strip()
            ]
            if len(split_lines) > len(raw_lines):
                raw_lines = split_lines
    if len(raw_lines) <= 3 and text.count("|") >= 5:
        split_lines = [line.strip() for line in re.split(r"\s+\|\s+|\s+/\s+|\s+>\s+|\s+·\s+|\s+-\s+", text) if line and line.strip()]
        if len(split_lines) > len(raw_lines):
            raw_lines = split_lines
    kept: list[str] = []
    seen_kept: set[str] = set()

    def _is_noise_line(line: str) -> bool:
        lower = line.lower()
        if any(marker in lower for marker in _JSON_NOISE_MARKERS):
            return True
        if '"item": "http' in lower or ('"name":' in lower and ('"item":' in lower or '"position"' in lower)):
            return True
        if any(marker in lower for marker in _LINE_NOISE_MARKERS):
            return True
        if any(p.search(line) for p in _NOISE_LINE_PATTERNS):
            return True
        script_hits = sum(1 for marker in _JS_TEMPLATE_MARKERS if marker in lower)
        if script_hits >= 3:
            return True
        if script_hits >= 2 and len(line) < 240:
            return True
        if _SCRIPT_ASSIGNMENT_RE.search(line) and (
            len(line) >= 120
            or ";" in line
            or line.count("(") >= 2
            or line.count("{") + line.count("}") >= 2
        ):
            return True
        if (
            line.count("{") >= 1
            and line.count("}") >= 1
            and line.count(":") >= 2
            and len(line) < 500
        ):
            return True
        css_hits = sum(1 for marker in _CSS_PROPERTY_MARKERS if marker in lower)
        if css_hits >= 3 and line.count("{") >= 1:
            return True
        tokens = re.findall(r"[a-zA-Z\u4e00-\u9fff]+", lower)
        if len(tokens) >= 4:
            nav_hits = sum(1 for t in tokens if t in _NAV_NOISE_WORDS)
            if nav_hits / float(len(tokens)) >= 0.6 and len(tokens) <= 24:
                return True
            if nav_hits >= 8 and line.count("|") + line.count("/") + line.count(">") + line.count("·") + line.count("-") >= 4:
                return True
            if nav_hits >= 5 and len(tokens) <= 18 and line.count("|") + line.count("/") + line.count(">") >= 2:
                return True
        sep_hits = line.count("|") + line.count("›") + line.count("»") + line.count("•")
        if sep_hits >= 3 and len(tokens) <= 24:
            return True
        if lower.startswith(("home ", "news ", "tech ", "business ", "sports ")) and len(tokens) <= 16:
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


def clean_frontdoor_document_candidate(document_candidate: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = dict(document_candidate or {})
    original_title = str(candidate.get("title") or "")
    original_summary = str(candidate.get("summary") or "")
    original_content = str(candidate.get("content") or "")

    cleaned_title = original_title.replace("\x00", "").strip()
    cleaned_summary = normalize_content_for_ingest(original_summary, max_chars=2000) if original_summary else ""
    cleaned_content = normalize_content_for_ingest(original_content, max_chars=50000) if original_content else ""

    candidate["title"] = cleaned_title
    candidate["summary"] = cleaned_summary
    candidate["content"] = cleaned_content

    return candidate, {
        "title_changed": cleaned_title != original_title,
        "summary_changed": cleaned_summary != original_summary,
        "content_changed": cleaned_content != original_content,
        "summary_chars_before": len(original_summary),
        "summary_chars_after": len(cleaned_summary),
        "content_chars_before": len(original_content),
        "content_chars_after": len(cleaned_content),
    }
