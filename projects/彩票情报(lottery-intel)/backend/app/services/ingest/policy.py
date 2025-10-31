from __future__ import annotations

import hashlib
from typing import Callable, Dict

from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..job_logger import start_job, complete_job, fail_job
from .adapters import (
    CaliforniaLegislatureAdapter,
    LegiScanApiAdapter,
    PolicyAdapter,
    PolicyDocument,
)

AdapterFactory = Callable[[str], PolicyAdapter]

ADAPTERS: Dict[str, AdapterFactory] = {
    "CA": CaliforniaLegislatureAdapter,
}


def get_policy_adapter(state: str, source_hint: str | None = None) -> PolicyAdapter:
    state_key = state.upper()
    if source_hint and source_hint.lower() == "legiscan":
        return LegiScanApiAdapter(state_key)

    factory = ADAPTERS.get(state_key)
    if not factory:
        raise ValueError(f"暂无州 {state_key} 的政策适配器；可尝试设置 source_hint=legiscan")
    return factory(state_key)


def _get_or_create_source(session: Session, doc: PolicyDocument) -> Source:
    name = doc.source_name or "Unknown Source"
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == "state_site")
        .one_or_none()
    )
    if source:
        return source

    source = Source(name=name, kind="state_site", base_url=doc.uri)
    session.add(source)
    session.flush()
    return source


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_policy_documents(state: str, source_hint: str | None = None) -> dict:
    adapter = get_policy_adapter(state, source_hint)
    inserted = 0
    skipped = 0
    documents = list(adapter.fetch_documents())
    inserted_ids: list[int] = []

    job_id = start_job("ingest_policy", {"state": state})

    with SessionLocal() as session:
        try:
            for doc in documents:
                content = doc.content or doc.summary or ""
                if not content:
                    skipped += 1
                    continue

                text_hash = _hash_text(content)
                existed = session.query(Document).filter(Document.text_hash == text_hash).first()
                if existed:
                    skipped += 1
                    continue

                source = _get_or_create_source(session, doc)

                db_doc = Document(
                    source_id=source.id,
                    state=doc.state,
                    doc_type="policy",
                    title=doc.title,
                    status=doc.status,
                    publish_date=doc.publish_date,
                    summary=doc.summary,
                    content=doc.content,
                    text_hash=text_hash,
                    uri=doc.uri,
                )
                session.add(db_doc)
                session.flush()
                inserted_ids.append(db_doc.id)
                inserted += 1

            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            fail_job(job_id, str(exc))
            raise

    try:
        if inserted_ids:
            from ..indexer import index_policy_documents

            index_policy_documents(document_ids=inserted_ids)

        result = {
            "inserted": inserted,
            "skipped": skipped,
            "state": state.upper(),
            "document_ids": inserted_ids,
        }
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise


