from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path
from typing import Any

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

    def __init__(self, db_path: str | Path | None = None, table_name: str = "chunks") -> None:
        if not is_lancedb_available():
            raise RuntimeError("lancedb is not installed; use an isolated PYTHONPATH or install the optional dependency")
        import lancedb  # type: ignore

        self.db_path = str(db_path or tempfile.mkdtemp(prefix="mrw-local-index-lancedb-"))
        self.table_name = table_name
        self._db = lancedb.connect(self.db_path)
        self._table: Any | None = None

    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            record = chunk.to_record()
            if not record.get("vector"):
                record["vector"] = _deterministic_vector(str(record.get("content") or ""))
            record["metadata_json"] = str(record.pop("metadata", {}) or {})
            rows.append(record)
        if not rows:
            return {"ok": True, "chunk_count": 0, "created_table": False, "adapter": "lancedb"}
        self._table = self._db.create_table(self.table_name, data=rows, mode="overwrite")
        self._table.create_fts_index("content", replace=True)
        return {"ok": True, "chunk_count": len(rows), "created_table": True, "adapter": "lancedb"}

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        if self._table is None:
            return []
        mode = normalize_local_index_mode(query.mode)
        predicate = f"project_id = '{_escape_lancedb_literal(query.project_id)}'"
        if query.source_id:
            predicate += f" AND source_id = '{_escape_lancedb_literal(query.source_id)}'"
        rows = self._search_rows(query=query, mode=mode, predicate=predicate)
        return [_result_from_record(row, mode=mode) for row in rows]

    def _search_rows(self, *, query: LocalIndexQuery, mode: str, predicate: str) -> list[dict[str, Any]]:
        limit = max(1, min(50, int(query.top_k or 10)))
        if mode == "vector":
            search = self._vector_search(query.query)
        elif mode == "hybrid":
            search = self._hybrid_search(query.query)
        else:
            search = self._table.search(query.query, query_type="fts")
        try:
            return search.where(predicate).limit(limit).to_list()
        except Exception:
            if mode == "keyword":
                raise
            return self._table.search(query.query, query_type="fts").where(predicate).limit(limit).to_list()

    def _vector_search(self, text: str) -> Any:
        vector = _deterministic_vector(text)
        try:
            return self._table.search(vector, vector_column_name="vector")
        except TypeError:
            return self._table.search(vector)

    def _hybrid_search(self, text: str) -> Any:
        try:
            return self._table.search(text, query_type="hybrid", vector_column_name="vector")
        except TypeError:
            try:
                return self._table.search(text, query_type="hybrid")
            except TypeError:
                return self._vector_search(text)


def _escape_lancedb_literal(value: str) -> str:
    return str(value or "").replace("'", "''")


def _result_from_record(row: dict[str, Any], *, mode: str = "keyword") -> LocalIndexSearchResult:
    return LocalIndexSearchResult(
        chunk_id=str(row.get("chunk_id") or ""),
        document_id=str(row.get("document_id") or ""),
        project_id=str(row.get("project_id") or ""),
        source_id=str(row.get("source_id") or ""),
        title=str(row.get("title") or ""),
        content=str(row.get("content") or ""),
        score=float(row["_score"]) if row.get("_score") is not None else None,
        url=str(row.get("url") or "") or None,
        source_type=str(row.get("source_type") or "material"),
        metadata={"adapter": "lancedb"},
        retrieval_mode=mode,
        retrieval_family="local_index",
        trace={
            "adapter": "lancedb",
            "mode": mode,
            "supports_vector": True,
            "fallback_family": "keyword",
        },
    )
