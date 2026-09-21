from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn, Optional, Protocol

from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import graph_backfill_failures
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.entities import Document
from .builder import build_graph
from .persistence import GraphNodeWriter
from .ports import GraphDocumentNormalizer


@dataclass
class BackfillResult:
    scanned_docs: int = 0
    written_nodes: int = 0
    skipped_docs: int = 0
    next_resume_token: Optional[int] = None


class GraphNodePersistencePort(Protocol):
    """Effect boundary for the graph-node projection writer."""

    def persist_graph_nodes(self, graph: Any) -> Any:
        ...


def _default_graph_node_persistence(session: Session) -> GraphNodePersistencePort:
    return GraphNodeWriter(session)


def _transaction_failure(exc: BaseException) -> Failure:
    message = str(exc)
    return graph_backfill_failures.fail(
        "transaction_failed",
        message,
        {
            "boundary_class": "EFFECT_SHELL_FAILURE",
            "failure_family": graph_backfill_failures.name,
            "operation": "run_graph_node_backfill",
            "owner": "graph.backfill.persistence_port",
            "exception_type": type(exc).__name__,
            "public_exception": type(exc).__name__,
            "public_message": message,
            "site": "graph.backfill.persistence_port",
            "cause": exc,
        },
    )


def _raise_transaction_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not graph_backfill_failures.matches(failure)
        or failure.code != "transaction_failed"
        or not isinstance(context.get("cause"), BaseException)
    ):
        # kit:boundary owner=graph.backfill.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w04_graph_backfill_failure_rolls_back_and_keeps_cause
        raise TypeError("graph backfill failure context is incomplete or inconsistent")
    cause = context["cause"]
    # kit:boundary owner=graph.backfill.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=graph.backfill.failure witness=test:test_w04_graph_backfill_failure_rolls_back_and_keeps_cause
    raise cause from cause


def run_graph_node_backfill_or_raise(
    session: Session,
    *,
    normalizer: GraphDocumentNormalizer,
    batch_size: int = 200,
    limit: Optional[int] = None,
    resume_token: Optional[int] = None,
    dry_run: bool = True,
    persistence_port: GraphNodePersistencePort | None = None,
) -> BackfillResult:
    """Compatibility shell that lifts the no-throw backfill result."""
    result = try_run_graph_node_backfill(
        session,
        normalizer=normalizer,
        batch_size=batch_size,
        limit=limit,
        resume_token=resume_token,
        dry_run=dry_run,
        persistence_port=persistence_port,
    )
    if isinstance(result, Failure):
        _raise_transaction_failure(result)
    return result


def _rollback_quietly(session: Session) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass


def try_run_graph_node_backfill(
    session: Session,
    *,
    normalizer: GraphDocumentNormalizer,
    batch_size: int = 200,
    limit: Optional[int] = None,
    resume_token: Optional[int] = None,
    dry_run: bool = True,
    persistence_port: GraphNodePersistencePort | None = None,
) -> BackfillResult | Failure:
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
        normalized = normalizer(doc)
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

    try:
        writer = persistence_port or _default_graph_node_persistence(session)
        summary = writer.persist_graph_nodes(graph)
        result.written_nodes = summary.inserted_or_updated
        session.commit()
    except Exception as exc:  # noqa: BLE001
        _rollback_quietly(session)
        return _transaction_failure(exc)
    return result


def run_graph_node_backfill(
    session: Session,
    *,
    normalizer: GraphDocumentNormalizer,
    batch_size: int = 200,
    limit: Optional[int] = None,
    resume_token: Optional[int] = None,
    dry_run: bool = True,
    persistence_port: GraphNodePersistencePort | None = None,
) -> BackfillResult:
    """Legacy shell preserving the established exception ABI."""
    result = try_run_graph_node_backfill(
        session,
        normalizer=normalizer,
        batch_size=batch_size,
        limit=limit,
        resume_token=resume_token,
        dry_run=dry_run,
        persistence_port=persistence_port,
    )
    if isinstance(result, Failure):
        _raise_transaction_failure(result)
    return result
