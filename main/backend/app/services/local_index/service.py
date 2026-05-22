from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .schema import LocalIndexChunk, LocalIndexQuery, LocalIndexSearchResult, normalize_local_index_mode


class LocalIndexAdapter(Protocol):
    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        ...

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        ...


class LocalIndexService:
    """Thin retrieval-layer service for fetched document/material chunks.

    This service deliberately does not know about source_library source
    configuration records. It only indexes content chunks that upstream ingest
    or writing-material storage has already produced.
    """

    def __init__(self, adapter: LocalIndexAdapter) -> None:
        self._adapter = adapter

    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        valid_chunks = [chunk for chunk in chunks if chunk.chunk_id and chunk.document_id and chunk.project_id and chunk.source_id]
        return self._adapter.upsert_chunks(valid_chunks)

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        if not query.query.strip() or not query.project_id.strip():
            return []
        normalized_query = replace(query, mode=normalize_local_index_mode(query.mode))
        return self._adapter.search(normalized_query)
