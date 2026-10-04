from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ..resource_pool.http_port import make_html_parser


_SHELL_MARKERS = (
    "share",
    "follow",
    "newsletter",
    "subscribe",
    "sign in",
    "log in",
    "register",
    "privacy policy",
    "terms of use",
    "cookie",
    "suggested for you",
    "join the conversation",
    "table of contents",
    "see all",
    "latest tech news",
    "jump to:",
)
_JS_MARKERS = (
    "window.",
    "document.",
    "function(",
    "prototype.",
    "symbol.iterator",
    "sourcemappingurl",
    "addEventListener(",
    "gtag(",
    "navigator.",
    "classlist.",
)
_SUPPORT_HOST_MARKERS = ("support.", "help.")
_SUPPORT_PATH_MARKERS = ("/support", "/help", "/kb/", "/knowledge", "/faq", "/community")
_VIDEO_HOST_MARKERS = ("youtube.com", "youtu.be", "vimeo.com", "bilibili.com")
_INDEX_PATH_MARKERS = ("/category/", "/categories/", "/tag/", "/topics/", "/news/", "/archive", "/archives", "/search")
_ARTICLE_HINTS = (
    "published",
    "updated",
    "review",
    "analysis",
    "report",
    "article",
    "by ",
)
_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def analyze_frontdoor_content(
    *,
    uri: str | None,
    title: str | None,
    content: str | None,
) -> dict[str, Any]:
    raw_title = str(title or "").strip()
    raw_content = str(content or "")
    raw_chars = len(raw_content)
    blocks = _split_blocks(raw_content)
    main_blocks, best_score, prefix_trimmed = _select_main_blocks(blocks)
    main_text = "\n".join(main_blocks).strip() if main_blocks else raw_content.strip()
    main_chars = len(main_text)
    page_family = _classify_page_family(uri=uri, title=raw_title, blocks=blocks, main_text=main_text)
    js_hits = _marker_hits(raw_content, _JS_MARKERS)
    shell_hits = _marker_hits(raw_content, _SHELL_MARKERS)
    duplicate_ratio = _duplicate_ratio(blocks)
    main_ratio = round((main_chars / float(raw_chars)), 4) if raw_chars else 0.0
    shell_heavy = bool(
        (page_family in {"support", "video", "index"})
        or (js_hits >= 4 and main_ratio < 0.75)
        or (page_family != "article" and shell_hits >= 4 and main_ratio < 0.85)
        or duplicate_ratio >= 0.3
    )
    js_heavy = bool(js_hits >= 4 or (js_hits >= 2 and page_family in {"support", "video", "landing"}))
    readerable = bool(
        page_family == "article"
        and main_chars >= 400
        and main_ratio >= 0.35
        and not js_heavy
    )
    extractor_confidence = _extractor_confidence(
        page_family=page_family,
        main_chars=main_chars,
        main_ratio=main_ratio,
        js_hits=js_hits,
        shell_hits=shell_hits,
        duplicate_ratio=duplicate_ratio,
    )
    return {
        "page_family": page_family,
        "readerable": readerable,
        "shell_heavy": shell_heavy,
        "js_heavy": js_heavy,
        "raw_text_chars": raw_chars,
        "main_text_chars": main_chars,
        "main_text_ratio": main_ratio,
        "extractor_name": "heuristic.main_content.v1",
        "extractor_confidence": extractor_confidence,
        "shell_marker_hits": shell_hits,
        "js_template_hits": js_hits,
        "duplicate_line_ratio": round(duplicate_ratio, 4),
        "prefix_trimmed": prefix_trimmed,
        "main_content": main_text,
        "main_title": raw_title,
        "block_count": len(blocks),
        "main_block_count": len(main_blocks),
        "signals": {
            "article_hint_hits": _article_hint_hits(f"{raw_title}\n{raw_content}"),
        },
    }


def apply_main_content_extraction(document_candidate: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = dict(document_candidate or {})
    if is_declared_prepared_text_body(candidate):
        body = str(candidate.get("content") or "").strip()
        analysis = analyze_frontdoor_content(
            uri=str(candidate.get("uri") or "").strip() or None,
            title=str(candidate.get("title") or "").strip() or None,
            content=body,
        )
        analysis.update(
            {
                "main_text_chars": len(body),
                "main_text_ratio": 1.0 if body else 0.0,
                "extractor_name": "ingest.material_text.v1",
                "extractor_confidence": 100.0,
                "prefix_trimmed": False,
                "main_content": body,
                "main_block_count": int(analysis.get("block_count") or 0),
            }
        )
        return candidate, analysis
    if is_extracted_pdf_body(candidate):
        # The URL adapter has already parsed the PDF bytes into text. The
        # HTML main-block heuristic would discard all but one PDF paragraph.
        body = str(candidate["content"]).strip()
        return candidate, {
            "page_family": "article",
            "readerable": len(body) >= 400,
            "shell_heavy": False,
            "js_heavy": False,
            "raw_text_chars": len(body),
            "main_text_chars": len(body),
            "main_text_ratio": 1.0,
            "extractor_name": "source_library.pdf_text.v1",
            "extractor_confidence": 100.0,
            "shell_marker_hits": 0,
            "js_template_hits": 0,
            "duplicate_line_ratio": 0.0,
            "prefix_trimmed": False,
            "main_content": body,
            "main_title": str(candidate.get("title") or "").strip(),
        }
    analysis = analyze_frontdoor_content(
        uri=str(candidate.get("uri") or "").strip() or None,
        title=str(candidate.get("title") or "").strip() or None,
        content=str(candidate.get("content") or ""),
    )
    extracted_content = str(analysis.get("main_content") or "").strip()
    if extracted_content:
        candidate["content"] = extracted_content
    return candidate, analysis


def is_declared_prepared_text_body(candidate: dict[str, Any]) -> bool:
    extracted_data = candidate.get("extracted_data_base")
    raw_input = extracted_data.get("_raw_input") if isinstance(extracted_data, dict) else None
    material_input = raw_input.get("material_input") if isinstance(raw_input, dict) else None
    if not isinstance(material_input, dict):
        return False
    digest = str(material_input.get("raw_content_digest") or "")
    return bool(
        material_input.get("kind") in {"given", "resource"}
        and str(material_input.get("mime_type") or "").split(";", 1)[0].strip().lower()
        in {"text/plain", "text/markdown"}
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest.lower())
        and str(candidate.get("content") or "").strip()
    )


def is_extracted_pdf_body(candidate: dict[str, Any]) -> bool:
    extracted_data = candidate.get("extracted_data_base")
    record_meta = extracted_data.get("record_meta") if isinstance(extracted_data, dict) else None
    content = str(candidate.get("content") or "")
    return bool(
        isinstance(record_meta, dict)
        and record_meta.get("content_format") == "pdf"
        and record_meta.get("text_extraction_status") == "succeeded"
        and content.strip()
        and not content.lstrip().startswith("%PDF")
    )


def extract_main_text_from_html(html: str) -> str:
    raw_html = str(html or "").strip()
    if not raw_html:
        return ""
    try:
        return _locate_main_text_from_html(
            raw_html,
            selectors=("article", "main article", "[role='main'] article", "main", "[role='main']"),
        )
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _locate_main_text_from_html(
    html: Any,
    *,
    selectors: tuple[str, ...],
    transform: Callable[[str], str] | None = None,
) -> str:
    parser = make_html_parser(html)
    for selector in selectors:
        node = parser.css_first(selector)
        if node is None:
            continue
        text = str(node.text(separator="\n", strip=True) or "").strip()
        if len(text) >= 120:
            return transform(text) if transform else text
    body = parser.body
    if body is not None:
        text = str(body.text(separator="\n", strip=True) or "").strip()
        return transform(text) if transform else text
    return ""


def _split_blocks(text: str) -> list[str]:
    raw = str(text or "").replace("\x00", "").strip()
    if not raw:
        return []
    blocks = [line.strip() for line in re.split(r"[\r\n]+", raw) if line and line.strip()]
    if len(blocks) <= 1:
        blocks = [line.strip() for line in re.split(r"(?<=[.!?])\s+|(?<=:)\s+(?=[A-Z])", raw) if line and line.strip()]
    return blocks or [raw]


def _select_main_blocks(blocks: list[str]) -> tuple[list[str], float, bool]:
    if not blocks:
        return [], 0.0, False
    scores = [_block_score(block) for block in blocks]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    threshold = max(2.0, scores[best_idx] * 0.35)
    start = best_idx
    end = best_idx
    while start > 0 and scores[start - 1] >= threshold:
        start -= 1
    while end + 1 < len(scores) and scores[end + 1] >= threshold:
        end += 1
    prefix_trimmed = start > 0
    selected = [block for block in blocks[start : end + 1] if _block_score(block) > 0]
    if not selected:
        selected = [blocks[best_idx]]
    return selected, float(scores[best_idx]), prefix_trimmed


def _block_score(block: str) -> float:
    lower = str(block or "").lower()
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", lower)
    if not tokens:
        return -20.0
    score = min(len(tokens), 40) * 1.2
    score += min(str(block).count(".") + str(block).count(",") + str(block).count(":"), 6) * 1.5
    score += _article_hint_hits(block) * 4.0
    score -= _marker_hits(block, _SHELL_MARKERS) * 6.0
    score -= _marker_hits(block, _JS_MARKERS) * 8.0
    if str(block).count("|") + str(block).count(">") + str(block).count("/") >= 4:
        score -= 10.0
    if str(block).count("{") + str(block).count("}") >= 3:
        score -= 10.0
    return score


def _classify_page_family(
    *,
    uri: str | None,
    title: str,
    blocks: list[str],
    main_text: str,
) -> str:
    parsed = urlparse(str(uri or "").strip())
    host = str(parsed.netloc or "").lower()
    path = str(parsed.path or "").lower()
    if any(marker in host for marker in _VIDEO_HOST_MARKERS):
        return "video"
    if any(marker in host for marker in _SUPPORT_HOST_MARKERS) or any(marker in path for marker in _SUPPORT_PATH_MARKERS):
        return "support"
    if any(marker in path for marker in _INDEX_PATH_MARKERS):
        return "index"
    lower_text = f"{title}\n{main_text}".lower()
    if _marker_hits(lower_text, _JS_MARKERS) >= 4 and len(main_text) < 2500:
        return "landing"
    if _article_hint_hits(lower_text) >= 1 and len(main_text) >= 70:
        return "article"
    if len(blocks) >= 3 and len(main_text) >= 240:
        return "article"
    return "unknown"


def _article_hint_hits(text: str) -> int:
    lower = str(text or "").lower()
    hits = sum(lower.count(marker) for marker in _ARTICLE_HINTS)
    hits += sum(lower.count(month) for month in _MONTHS)
    if re.search(r"\b(20\d{2}|19\d{2})\b", lower):
        hits += 1
    return hits


def _marker_hits(text: str, markers: tuple[str, ...]) -> int:
    lower = str(text or "").lower()
    return sum(lower.count(marker.lower()) for marker in markers)


def _duplicate_ratio(blocks: list[str]) -> float:
    normalized = [re.sub(r"\s+", " ", str(block).strip().lower()) for block in blocks if str(block).strip()]
    if not normalized:
        return 0.0
    unique = len(set(normalized))
    return max(0.0, 1.0 - (unique / float(len(normalized))))


def _extractor_confidence(
    *,
    page_family: str,
    main_chars: int,
    main_ratio: float,
    js_hits: int,
    shell_hits: int,
    duplicate_ratio: float,
) -> float:
    score = 45.0
    if page_family == "article":
        score += 20.0
    elif page_family in {"support", "video", "landing", "index"}:
        score -= 10.0
    score += min(20.0, main_chars / 100.0)
    score += min(10.0, main_ratio * 20.0)
    score -= min(20.0, js_hits * 4.0)
    score -= min(15.0, shell_hits * 2.5)
    score -= min(15.0, duplicate_ratio * 30.0)
    return round(min(100.0, max(0.0, score)), 2)
