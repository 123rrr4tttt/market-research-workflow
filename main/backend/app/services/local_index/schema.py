from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LOCAL_INDEX_QUERY_MODES = {"keyword", "vector", "hybrid"}


def normalize_local_index_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    return normalized if normalized in LOCAL_INDEX_QUERY_MODES else "keyword"


@dataclass(frozen=True)
class LocalIndexChunk:
    chunk_id: str
    document_id: str
    project_id: str
    source_id: str
    title: str
    content: str
    url: str | None = None
    source_type: str = "material"
    language: str = "mixed"
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "project_id": self.project_id,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "title": self.title,
            "url": self.url or "",
            "content": self.content,
            "language": self.language,
            "created_at": self.created_at or "",
            "metadata": dict(self.metadata or {}),
            "vector": list(self.vector or []),
        }


@dataclass(frozen=True)
class LocalIndexQuery:
    query: str
    project_id: str
    source_id: str | None = None
    top_k: int = 10
    mode: str = "keyword"


@dataclass(frozen=True)
class LocalIndexSearchResult:
    chunk_id: str
    document_id: str
    project_id: str
    source_id: str
    title: str
    content: str
    score: float | None = None
    url: str | None = None
    source_type: str = "material"
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_mode: str = "keyword"
    retrieval_family: str = "local_index"
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "project_id": self.project_id,
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "url": self.url,
            "source_type": self.source_type,
            "metadata": dict(self.metadata or {}),
            "retrieval_mode": self.retrieval_mode,
            "retrieval_family": self.retrieval_family,
            "trace": dict(self.trace or {}),
        }
