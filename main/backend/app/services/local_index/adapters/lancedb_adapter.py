from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from ..embedding_provider import LocalEmbeddingProvider, RepoLocalHashingEmbeddingProvider
from ..schema import LocalIndexChunk, LocalIndexQuery, LocalIndexSearchResult, normalize_local_index_mode


def is_lancedb_available() -> bool:
    return importlib.util.find_spec("lancedb") is not None


def _deterministic_vector(text: str, dims: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    values = [((digest[i] / 255.0) * 2.0) - 1.0 for i in range(dims)]
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return [round(value / norm, 6) for value in values]


class LanceDBLocalIndexAdapter:
    """Optional LanceDB prototype adapter for local material retrieval.

    The dependency is intentionally optional. Importing this module must not
    force the project to install LanceDB; construction fails with a clear error
    when the package is not available.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        table_name: str = "chunks",
        embedding_provider: LocalEmbeddingProvider | None = None,
    ) -> None:
        if not is_lancedb_available():
            raise RuntimeError("lancedb is not installed; use an isolated PYTHONPATH or install the optional dependency")
        import lancedb  # type: ignore

        self.db_path = str(db_path or tempfile.mkdtemp(prefix="mrw-local-index-lancedb-"))
        self.table_name = table_name
        self._embedding_provider = embedding_provider or RepoLocalHashingEmbeddingProvider()
        self._db = lancedb.connect(self.db_path)
        self._table: Any | None = None

    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        rows: list[dict[str, Any]] = []
        embedding_provider = _adapter_embedding_provider(self)
        provider_meta = embedding_provider.metadata()
        for chunk in chunks:
            record = chunk.to_record()
            metadata = dict(record.pop("metadata", {}) or {})
            if not record.get("vector"):
                record["vector"] = embedding_provider.embed_text(_embedding_text(record))
            record["embedding_provider"] = metadata.get("embedding_provider") or provider_meta["provider_id"]
            record["embedding_model"] = metadata.get("embedding_model") or provider_meta["model"]
            record["embedding_model_version"] = metadata.get("embedding_model_version") or provider_meta["model_version"]
            record["embedding_dim"] = metadata.get("embedding_dim") or len(record["vector"])
            record["vector_version"] = metadata.get("vector_version") or provider_meta["vector_version"]
            record["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            rows.append(record)
        if not rows:
            return {"ok": True, "chunk_count": 0, "created_table": False, "adapter": "lancedb"}
        self._table = self._db.create_table(self.table_name, data=rows, mode="overwrite")
        self._table.create_fts_index("content", replace=True)
        return {
            "ok": True,
            "chunk_count": len(rows),
            "created_table": True,
            "adapter": "lancedb",
            "embedding_provider": str(provider_meta["provider_id"]),
            "embedding_model": str(provider_meta["model"]),
            "embedding_dim": int(provider_meta["embedding_dim"]),
            "vector_version": str(provider_meta["vector_version"]),
        }

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        if self._table is None:
            return []
        mode = normalize_local_index_mode(query.mode)
        embedding_provider = _adapter_embedding_provider(self)
        provider_readback = embedding_provider.readback([query.query])
        predicate = f"project_id = '{_escape_lancedb_literal(query.project_id)}'"
        if query.source_id:
            predicate += f" AND source_id = '{_escape_lancedb_literal(query.source_id)}'"
        limit = max(1, min(50, int(query.top_k or 10)))
        executed_mode = mode
        trace: dict[str, Any] = {
            "adapter": "lancedb",
            "requested_mode": mode,
            "executed_mode": mode,
            "query_family": "local_material",
            "project_id": query.project_id,
            "source_id": query.source_id,
            "top_k": limit,
            "embedding_provider": embedding_provider.metadata(),
            "embedding_provider_readback": provider_readback,
            "provider_live_verified": provider_readback.get("live_provider_verified") is True,
        }
        try:
            rows = _search_rows(
                self._table,
                query=query,
                predicate=predicate,
                limit=limit,
                mode=mode,
                embedding_provider=embedding_provider,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            if mode == "keyword":
                raise
            executed_mode = "keyword"
            trace["executed_mode"] = executed_mode
            trace["fallback_from"] = mode
            trace["fallback_reason"] = exc.__class__.__name__
            rows = _search_rows(
                self._table,
                query=query,
                predicate=predicate,
                limit=limit,
                mode=executed_mode,
                embedding_provider=embedding_provider,
            )
        return [_result_from_record(row, retrieval_mode=executed_mode, trace=trace) for row in rows]


def _escape_lancedb_literal(value: str) -> str:
    return str(value or "").replace("'", "''")


def _search_rows(
    table: Any,
    *,
    query: LocalIndexQuery,
    predicate: str,
    limit: int,
    mode: str,
    embedding_provider: LocalEmbeddingProvider,
) -> list[dict[str, Any]]:
    if mode == "keyword":
        builder = table.search(query.query, query_type="fts")
    elif mode == "vector":
        builder = _vector_search(table, query.query, embedding_provider=embedding_provider)
    elif mode == "hybrid":
        builder = _hybrid_search(table, query.query, embedding_provider=embedding_provider)
    else:
        builder = table.search(query.query, query_type="fts")
    return builder.where(predicate).limit(limit).to_list()


def _vector_search(table: Any, text: str, *, embedding_provider: LocalEmbeddingProvider) -> Any:
    vector = embedding_provider.embed_query(text)
    try:
        return table.search(vector, vector_column_name="vector")
    except TypeError:
        return table.search(vector)


def _hybrid_search(table: Any, text: str, *, embedding_provider: LocalEmbeddingProvider) -> Any:
    vector = embedding_provider.embed_query(text)
    try:
        return table.search(None, query_type="hybrid", vector_column_name="vector").text(text).vector(vector)
    except (AttributeError, TypeError):
        pass
    try:
        return table.search(text, query_type="hybrid", vector_column_name="vector")
    except TypeError:
        try:
            return table.search(text, query_type="hybrid")
        except TypeError:
            return _vector_search(table, text)


def _result_from_record(row: dict[str, Any], *, retrieval_mode: str, trace: dict[str, Any]) -> LocalIndexSearchResult:
    score = row.get("_score")
    if score is None:
        score = row.get("_relevance_score")
    if score is None:
        score = row.get("_distance")
    return LocalIndexSearchResult(
        chunk_id=str(row.get("chunk_id") or ""),
        document_id=str(row.get("document_id") or ""),
        project_id=str(row.get("project_id") or ""),
        source_id=str(row.get("source_id") or ""),
        title=str(row.get("title") or ""),
        content=str(row.get("content") or ""),
        score=float(score) if score is not None else None,
        url=str(row.get("url") or "") or None,
        source_type=str(row.get("source_type") or "material"),
        metadata={
            "adapter": "lancedb",
            "embedding_provider": row.get("embedding_provider"),
            "embedding_model": row.get("embedding_model"),
            "embedding_model_version": row.get("embedding_model_version"),
            "embedding_dim": row.get("embedding_dim"),
            "vector_version": row.get("vector_version"),
        },
        retrieval_mode=retrieval_mode,
        retrieval_family="local_index",
        trace=dict(trace or {}),
    )


def _adapter_embedding_provider(adapter: LanceDBLocalIndexAdapter) -> LocalEmbeddingProvider:
    provider = getattr(adapter, "_embedding_provider", None)
    return provider if provider is not None else RepoLocalHashingEmbeddingProvider()


def _embedding_text(record: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            str(record.get("title") or "").strip(),
            str(record.get("content") or "").strip(),
        ]
        if part
    )
