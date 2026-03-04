from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.entities import Document
from .adapters import normalize_document
from .adapters.market import MarketAdapter
from .adapters.policy import PolicyAdapter
from .builder import build_graph, build_market_graph, build_policy_graph
from .persistence import GraphNodeWriter


@dataclass
class BackfillResult:
    scanned_docs: int = 0
    written_nodes: int = 0
    skipped_docs: int = 0
    social_written_nodes: int = 0
    market_written_nodes: int = 0
    policy_written_nodes: int = 0
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
    normalized_market = []
    normalized_policy = []
    market_adapter = MarketAdapter()
    policy_adapter = PolicyAdapter()
    for doc in docs:
        normalized = normalize_document(doc)
        if normalized is None:
            result.skipped_docs += 1
        else:
            normalized_posts.append(normalized)

        try:
            market_item = market_adapter.to_normalized(doc)
            if market_item is not None:
                normalized_market.append(market_item)
        except Exception:
            pass

        try:
            policy_item = policy_adapter.to_normalized(doc)
            if policy_item is not None:
                normalized_policy.append(policy_item)
        except Exception:
            pass

    if not normalized_posts and not normalized_market and not normalized_policy:
        return result

    social_graph = build_graph(normalized_posts) if normalized_posts else None
    market_graph = build_market_graph(normalized_market) if normalized_market else None
    policy_graph = build_policy_graph(normalized_policy) if normalized_policy else None

    if dry_run:
        result.social_written_nodes = len(social_graph.nodes) if social_graph else 0
        result.market_written_nodes = len(market_graph.nodes) if market_graph else 0
        result.policy_written_nodes = len(policy_graph.nodes) if policy_graph else 0
        result.written_nodes = (
            result.social_written_nodes
            + result.market_written_nodes
            + result.policy_written_nodes
        )
        return result

    writer = GraphNodeWriter(session)
    if social_graph is not None:
        social_summary = writer.persist_graph_nodes(social_graph)
        result.social_written_nodes = social_summary.inserted_or_updated
        result.written_nodes += social_summary.inserted_or_updated
    if market_graph is not None:
        market_summary = writer.persist_graph_nodes(market_graph)
        result.market_written_nodes = market_summary.inserted_or_updated
        result.written_nodes += market_summary.inserted_or_updated
    if policy_graph is not None:
        policy_summary = writer.persist_graph_nodes(policy_graph)
        result.policy_written_nodes = policy_summary.inserted_or_updated
        result.written_nodes += policy_summary.inserted_or_updated
    session.commit()
    return result
