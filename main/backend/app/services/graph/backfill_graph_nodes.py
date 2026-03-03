from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.entities import Document
from .adapters import normalize_document
from .builder import build_graph
from .persistence import GraphNodeWriter


@dataclass
class BackfillResult:
    scanned_docs: int = 0
    written_nodes: int = 0
    skipped_docs: int = 0
    next_resume_token: Optional[int] = None


def run_graph_node_backfill(
    session: Session,
    *,
    batch_size: int = 200,
    limit: Optional[int] = None,
    resume_token: Optional[int] = None,
    dry_run: bool = True,
) -> BackfillResult:
    query = select(Document).where(Document.extracted_data.isnot(None))
    if resume_token is not None:
        query = query.where(Document.id > int(resume_token))
    query = query.order_by(Document.id.asc()).limit(int(limit or batch_size))

    docs = session.execute(query).scalars().all()
    result = BackfillResult(scanned_docs=len(docs), next_resume_token=(docs[-1].id if docs else resume_token))
    if not docs:
        return result

    normalized_posts = []
    for doc in docs:
        normalized = normalize_document(doc)
        if normalized is None:
            result.skipped_docs += 1
            continue
        normalized_posts.append(normalized)

    if not normalized_posts:
        return result

    graph = build_graph(normalized_posts)
    if dry_run:
        result.written_nodes = len(graph.nodes)
        return result

    writer = GraphNodeWriter(session)
    summary = writer.persist_graph_nodes(graph)
    result.written_nodes = summary.inserted_or_updated
    session.commit()
    return result
