from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION = "global_vector_object.v1"
SEARCH_EVIDENCE_HIT_CONTRACT_VERSION = "search_evidence_hit.v1"

GLOBAL_VECTOR_OBJECT_REQUIRED_FIELDS = (
    "contract_version",
    "project_key",
    "object_type",
    "object_id",
    "chunk_id",
    "source_id",
    "document_id",
    "vector_version",
    "embedding_model",
    "embedding_dim",
    "matrix_branch_id",
    "provenance",
)

SEARCH_EVIDENCE_HIT_REQUIRED_FIELDS = (
    "contract_version",
    "hit_id",
    "rank",
    "query_group_id",
    "matrix_branch_id",
    "retrieval_mode",
    "retrieval_family",
    "backend",
    "evidence_class",
    "verification_state",
    "score",
    "rank_features",
    "provenance",
    "global_vector_object",
)

_VECTOR_RETRIEVAL_MODES = {"vector", "hybrid"}
_DEFAULT_VECTOR_VERSION = "v1"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _lookup(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(
        encoded.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:16]
    return f"{prefix}_{digest}"


def build_query_group_id(
    *,
    query: str,
    project_key: str | None = None,
    rank_mode: str = "hybrid",
    state: str | None = None,
    modality: str = "any",
    top_k: int | None = None,
) -> str:
    return _stable_id(
        "qg",
        {
            "modality": _clean_text(modality) or "any",
            "project_key": _clean_optional_text(project_key),
            "query": _clean_text(query),
            "rank_mode": _clean_text(rank_mode) or "hybrid",
            "state": _clean_optional_text(state),
            "top_k": top_k,
        },
    )


def _infer_retrieval_mode(row: Mapping[str, Any], rank_mode: str | None) -> str:
    mode = _clean_text(_lookup(row, "retrieval_mode", "mode")).lower()
    if mode == "bm25":
        return "keyword"
    if mode:
        return mode
    fallback = _clean_text(rank_mode).lower()
    return fallback or "hybrid"


def _infer_backend(row: Mapping[str, Any]) -> str:
    backend = _clean_text(_lookup(row, "backend", "provider"))
    if backend == "opensearch":
        return "opensearch_lexical"
    if backend == "qdrant":
        return "qdrant_vector"
    if backend == "pgvector":
        return "pgvector_fallback"
    return backend or "unknown"


def _infer_object_type(row: Mapping[str, Any], retrieval_mode: str) -> str:
    object_type = _clean_text(_lookup(row, "object_type"))
    if object_type:
        return object_type
    has_chunk_identity = _lookup(row, "chunk_index", "chunk_id") is not None
    if has_chunk_identity or retrieval_mode in _VECTOR_RETRIEVAL_MODES:
        return "policy_chunk"
    return _clean_text(_lookup(row, "source_type")) or "document"


def _infer_document_id(row: Mapping[str, Any]) -> str:
    return _clean_text(_lookup(row, "document_id", "doc_id", "id")) or "unknown_document"


def _infer_object_id(row: Mapping[str, Any], document_id: str) -> str:
    return _clean_text(_lookup(row, "object_id", "item_key")) or document_id


def _infer_chunk_id(row: Mapping[str, Any], document_id: str) -> str:
    chunk_id = _clean_text(_lookup(row, "chunk_id"))
    if chunk_id:
        return chunk_id
    chunk_index = _lookup(row, "chunk_index")
    if chunk_index is not None:
        return f"{document_id}:chunk:{chunk_index}"
    return f"{document_id}:document"


def _infer_source_id(row: Mapping[str, Any], document_id: str) -> str:
    return (
        _clean_text(_lookup(row, "source_id", "source", "publisher", "channel_key"))
        or f"document:{document_id}"
    )


def _infer_vector_version(row: Mapping[str, Any], retrieval_mode: str) -> str:
    vector_version = _clean_text(_lookup(row, "vector_version"))
    if vector_version:
        return vector_version
    if retrieval_mode in _VECTOR_RETRIEVAL_MODES:
        return _DEFAULT_VECTOR_VERSION
    return "not_vector_ranked"


def _infer_evidence_class(row: Mapping[str, Any], object_type: str) -> str:
    return _clean_text(_lookup(row, "evidence_class", "source_type")) or object_type


def _infer_verification_state(row: Mapping[str, Any]) -> str:
    verification_state = _clean_text(_lookup(row, "verification_state")).lower()
    if verification_state:
        return verification_state
    tags = {str(item).lower() for item in _lookup(row, "tags") or []}
    if "fallback" in tags:
        return "fallback"
    return "unverified"


def build_global_vector_object(
    row: Mapping[str, Any],
    *,
    project_key: str | None = None,
    retrieval_mode: str | None = None,
    matrix_branch_id: str | None = None,
) -> dict[str, Any]:
    document_id = _infer_document_id(row)
    object_type = _infer_object_type(row, retrieval_mode or _infer_retrieval_mode(row, None))
    object_id = _infer_object_id(row, document_id)
    chunk_id = _infer_chunk_id(row, document_id)
    source_id = _infer_source_id(row, document_id)
    vector_version = _infer_vector_version(row, retrieval_mode or _infer_retrieval_mode(row, None))
    source_uri = _clean_optional_text(_lookup(row, "source_uri", "url", "uri"))
    provenance = {
        "source_uri": source_uri,
        "source_domain": _clean_optional_text(_lookup(row, "source_domain")),
        "effective_time": _clean_optional_text(
            _lookup(row, "effective_time", "publish_date", "published_at")
        ),
        "language": _clean_optional_text(_lookup(row, "language")),
        "backend": _infer_backend(row),
    }
    return {
        "contract_version": GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
        "project_key": _clean_optional_text(_lookup(row, "project_key")) or _clean_optional_text(project_key),
        "object_type": object_type,
        "object_id": object_id,
        "chunk_id": chunk_id,
        "source_id": source_id,
        "document_id": document_id,
        "vector_version": vector_version,
        "embedding_model": _clean_optional_text(_lookup(row, "embedding_model", "model")),
        "embedding_dim": _coerce_int_or_none(_lookup(row, "embedding_dim", "dim")),
        "matrix_branch_id": _clean_optional_text(_lookup(row, "matrix_branch_id")) or matrix_branch_id,
        "provenance": provenance,
    }


def build_search_evidence_hit(
    row: Mapping[str, Any],
    *,
    rank: int,
    query_group_id: str,
    project_key: str | None = None,
    rank_mode: str = "hybrid",
) -> dict[str, Any]:
    raw = dict(row)
    retrieval_mode = _infer_retrieval_mode(raw, rank_mode)
    backend = _infer_backend(raw)
    matrix_branch_id = _clean_optional_text(_lookup(raw, "matrix_branch_id")) or _stable_id(
        "branch",
        {
            "backend": backend,
            "query_group_id": query_group_id,
            "retrieval_mode": retrieval_mode,
        },
    )
    vector_object = build_global_vector_object(
        raw,
        project_key=project_key,
        retrieval_mode=retrieval_mode,
        matrix_branch_id=matrix_branch_id,
    )
    score = _coerce_float(_lookup(raw, "score", "_score", "rank_score"))
    rank_features = {
        "rank": max(1, int(rank)),
        "score": score,
        "fusion_score": _coerce_float(_lookup(raw, "fusion_score"), default=0.0),
        "lexical_score": _coerce_float(_lookup(raw, "lexical_score"), default=0.0),
        "vector_score": _coerce_float(_lookup(raw, "vector_score"), default=0.0),
        "backend": backend,
        "retrieval_mode": retrieval_mode,
        "tags": list(_lookup(raw, "tags") or []),
    }
    provenance = {
        **dict(vector_object["provenance"]),
        "project_key": vector_object["project_key"],
        "document_id": vector_object["document_id"],
        "source_id": vector_object["source_id"],
        "chunk_id": vector_object["chunk_id"],
        "vector_version": vector_object["vector_version"],
        "matrix_branch_id": matrix_branch_id,
    }
    hit_id = _stable_id(
        "eh",
        {
            "backend": backend,
            "chunk_id": vector_object["chunk_id"],
            "document_id": vector_object["document_id"],
            "matrix_branch_id": matrix_branch_id,
            "object_id": vector_object["object_id"],
            "query_group_id": query_group_id,
            "rank": rank,
        },
    )
    return {
        "contract_version": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
        "hit_id": hit_id,
        "rank": max(1, int(rank)),
        "query_group_id": query_group_id,
        "matrix_branch_id": matrix_branch_id,
        "retrieval_mode": retrieval_mode,
        "retrieval_family": "main_search",
        "backend": backend,
        "evidence_class": _infer_evidence_class(raw, vector_object["object_type"]),
        "verification_state": _infer_verification_state(raw),
        "score": score,
        "rank_features": rank_features,
        "provenance": provenance,
        "global_vector_object": vector_object,
    }


def build_search_evidence_hits(
    rows: Iterable[Mapping[str, Any]],
    *,
    query: str,
    project_key: str | None = None,
    rank_mode: str = "hybrid",
    state: str | None = None,
    modality: str = "any",
    top_k: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    query_group_id = build_query_group_id(
        query=query,
        project_key=project_key,
        rank_mode=rank_mode,
        state=state,
        modality=modality,
        top_k=top_k,
    )
    hits = [
        build_search_evidence_hit(
            _mapping(row),
            rank=index,
            query_group_id=query_group_id,
            project_key=project_key,
            rank_mode=rank_mode,
        )
        for index, row in enumerate(rows, start=1)
        if isinstance(row, Mapping)
    ]
    for hit in hits:
        validate_search_evidence_hit(hit)
    return query_group_id, hits


def validate_global_vector_object(vector_object: Mapping[str, Any]) -> None:
    if vector_object.get("contract_version") != GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION:
        raise ValueError("unsupported global vector object contract_version")
    missing = [field for field in GLOBAL_VECTOR_OBJECT_REQUIRED_FIELDS if field not in vector_object]
    if missing:
        raise ValueError(f"global_vector_object_missing_fields:{','.join(missing)}")
    for field in ("object_type", "object_id", "chunk_id", "source_id", "document_id", "vector_version"):
        if not _clean_text(vector_object.get(field)):
            raise ValueError(f"global_vector_object_empty_field:{field}")
    if not isinstance(vector_object.get("provenance"), Mapping):
        raise ValueError("global_vector_object provenance must be an object")


def validate_search_evidence_hit(hit: Mapping[str, Any]) -> None:
    if hit.get("contract_version") != SEARCH_EVIDENCE_HIT_CONTRACT_VERSION:
        raise ValueError("unsupported search evidence hit contract_version")
    missing = [field for field in SEARCH_EVIDENCE_HIT_REQUIRED_FIELDS if field not in hit]
    if missing:
        raise ValueError(f"search_evidence_hit_missing_fields:{','.join(missing)}")
    for field in ("hit_id", "query_group_id", "matrix_branch_id", "retrieval_mode", "backend", "evidence_class"):
        if not _clean_text(hit.get(field)):
            raise ValueError(f"search_evidence_hit_empty_field:{field}")
    if _coerce_int_or_none(hit.get("rank")) is None or int(hit["rank"]) < 1:
        raise ValueError("search_evidence_hit rank must be a positive integer")
    if not isinstance(hit.get("rank_features"), Mapping):
        raise ValueError("search_evidence_hit rank_features must be an object")
    if not isinstance(hit.get("provenance"), Mapping):
        raise ValueError("search_evidence_hit provenance must be an object")
    validate_global_vector_object(_mapping(hit.get("global_vector_object")))
