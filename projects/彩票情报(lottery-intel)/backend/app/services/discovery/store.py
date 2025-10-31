from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..http.client import default_http_client
from ..llm.provider import get_chat_model
from ...settings.config import settings
from ..indexer.policy import index_policy_documents
from ...models.base import SessionLocal
from ...models.entities import Source, Document


logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        # drop fragments
        return p._replace(fragment="").geturl()
    except Exception:
        return url


def _fetch_content(url: str) -> str | None:
    try:
        html = default_http_client.get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        # Prefer main article text when possible; fallback to all text
        # Keep it simple to avoid heavy dependencies
        article = soup.find("article") or soup.find("main") or soup.body
        text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)
        if not text:
            return None
        text = text.replace("\x00", "")
        return text[:20000]
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery.store fetch content failed url=%s err=%s", url, exc)
        return None


def _get_or_create_source(session, domain: str) -> int:
    src = session.query(Source).filter(Source.base_url == domain).one_or_none()
    if src:
        return src.id
    src = Source(name=domain, kind="web", base_url=domain)
    session.add(src)
    session.flush()
    return src.id


_POLICY_TOKENS = {
    "regulation", "regulations", "policy", "policies", "bill", "bills", "legislation",
    "statute", "ordinance", "rulemaking", "notice", "committee", "assembly", "senate",
    "法规", "法案", "政策", "立法", "条例", "公告",
}

_MARKET_TOKENS = {
    "market", "sales", "revenue", "jackpot", "draw", "winning", "numbers", "ticket", "prize",
    "trend", "report", "payout", "volume",
    "市场", "销售", "收入", "奖池", "开奖", "中奖", "票价", "走势", "报告",
}


def _classify_kind(title: str, snippet: str, content: str | None) -> str:
    text = " ".join([title or "", snippet or "", (content or "")[:2000]]).lower()
    p_hits = sum(1 for t in _POLICY_TOKENS if t in text)
    m_hits = sum(1 for t in _MARKET_TOKENS if t in text)
    if p_hits >= m_hits + 1:
        return "policy"
    if m_hits >= p_hits + 1:
        return "market"

    # Fallback to LLM when ambiguous
    try:
        model = get_chat_model()
        prompt = (
            "请将以下内容粗分类为'policy'或'market'之一，仅返回这两个词之一。\n"
            f"标题: {title}\n摘要: {snippet}\n正文片段: {(content or '')[:800]}\n分类:"
        )
        resp = model.invoke(prompt)
        txt = getattr(resp, "content", str(resp)).strip().lower()
        if "policy" in txt and "market" not in txt:
            return "policy"
        if "market" in txt and "policy" not in txt:
            return "market"
    except Exception:
        pass
    # Default heuristic
    return "policy" if p_hits >= m_hits else "market"


_DOMAIN_STATE = {
    "www.calottery.com": "CA",
    "calottery.com": "CA",
    "static.www.calottery.com": "CA",
    "data.ny.gov": "NY",
    "ny.gov": "NY",
    "www.texaslottery.com": "TX",
    "texaslottery.com": "TX",
}


def _infer_state(domain: str, title: str, snippet: str) -> str | None:
    if domain in _DOMAIN_STATE:
        return _DOMAIN_STATE[domain]
    lower = (title + " " + snippet).lower()
    if "california" in lower:  # heuristic
        return "CA"
    if "new york" in lower:
        return "NY"
    if "texas" in lower:
        return "TX"
    return None


def store_results(results: List[Dict]) -> Dict[str, int]:
    inserted = 0
    updated = 0
    skipped = 0
    policy_to_index: List[int] = []

    with SessionLocal() as session:
        for item in results:
            try:
                link = _normalize_url((item.get("link") or "").strip())
                if not link:
                    skipped += 1
                    continue
                domain = item.get("domain") or urlparse(link).netloc
                title = (item.get("title") or "").replace("\x00", "").strip() or domain
                snippet = (item.get("snippet") or "").replace("\x00", "").strip()

                source_id = _get_or_create_source(session, domain)

                # Dedup by URI first
                doc = session.query(Document).filter(Document.uri == link).one_or_none()
                if doc:
                    # light update if missing summary/title
                    changed = False
                    if not doc.title and title:
                        doc.title = title
                        changed = True
                    if not doc.summary and snippet:
                        doc.summary = snippet
                        changed = True
                    # 补充 doc_type（若之前为 external）
                    if doc.doc_type in (None, "external"):
                        content_peek = (doc.content or "")[:800]
                        doc.doc_type = _classify_kind(title, snippet, content_peek)
                        changed = True
                    # 补充 state
                    if not doc.state:
                        inferred = _infer_state(domain, title, snippet)
                        if inferred:
                            doc.state = inferred
                            changed = True
                    if changed:
                        updated += 1
                        if doc.doc_type == "policy":
                            policy_to_index.append(doc.id)
                    else:
                        skipped += 1
                    continue

                # Fetch content best-effort（不阻塞失败）
                content = _fetch_content(link)
                text_hash = _sha256((content or title) + "\n" + link)

                # Unique by text_hash as well（DB 层有唯一约束可利用）
                exists = session.query(Document).filter(Document.text_hash == text_hash).one_or_none()
                if exists:
                    skipped += 1
                    continue

                kind = _classify_kind(title, snippet, content)
                state = _infer_state(domain, title, snippet)
                doc = Document(
                    source_id=source_id,
                    state=state,
                    doc_type=kind,
                    title=title,
                    status=None,
                    publish_date=None,
                    content=(content or None),
                    summary=snippet,
                    text_hash=text_hash,
                    uri=link,
                )
                session.add(doc)
                inserted += 1
                if kind == "policy":
                    session.flush()
                    policy_to_index.append(doc.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("discovery.store skipped error err=%s", exc)
                skipped += 1

        session.commit()

    # 触发索引（仅当配置了 OPENAI_API_KEY 且有新增/更新政策文档）
    if settings.openai_api_key and policy_to_index:
        try:
            index_policy_documents(document_ids=policy_to_index)
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery.store index failed ids=%s err=%s", policy_to_index, exc)

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


