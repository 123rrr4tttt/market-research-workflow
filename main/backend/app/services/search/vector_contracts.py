from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse
from typing import Annotated, Any, Iterable, Mapping, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import search_failures


GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION = "global_vector_object.v1"
SEARCH_EVIDENCE_HIT_CONTRACT_VERSION = "search_evidence_hit.v1"
SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION = "search_retrieval_run.v1"
SEARCH_RETRIEVAL_BRANCH_CONTRACT_VERSION = "search_retrieval_branch.v1"
SEARCH_RETRIEVAL_HIT_CONTRACT_VERSION = "search_retrieval_hit.v1"
AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION = "agent_matrix_search_evidence.v1"

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

SEARCH_RETRIEVAL_RUN_REQUIRED_FIELDS = (
    "contract_version",
    "run_id",
    "query_group_id",
    "retrieval_family",
    "query",
    "project_key",
    "rank_mode",
    "branch_records",
    "retrieval_branches",
    "retrieval_hits",
    "evidence_hits",
)

GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS = (
    "provider",
    "backend",
    "retrieval_mode",
    "provider_payload_kind",
    "embedding_model",
    "embedding_model_version",
    "embedding_dim",
    "vector_version",
    "source",
    "source_id",
    "source_reference",
    "reference",
    "score",
    "fallback_reason",
)

_VECTOR_RETRIEVAL_MODES = {"vector", "hybrid"}
_DEFAULT_VECTOR_VERSION = "v1"
_SEARCH_FAILURE_WITNESS = "test:test_w04_graph_search_contract_core"
_SEARCH_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _contract_failure(code: str, message: str, *, operation: str, site: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": search_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": "ValueError",
        "public_message": message,
        "site": site,
        "witness": _SEARCH_FAILURE_WITNESS,
    }
    context.update(details)
    return search_failures.fail(code, message, context)


def _raise_contract_failure(failure: Failure, *, cause: BaseException | None = None) -> NoReturn:
    context = failure.context or {}
    if (
        not search_failures.matches(failure)
        or _SEARCH_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("failure_family") != search_failures.name
        or context.get("public_exception") != "ValueError"
    ):
        # kit:boundary owner=search.vector_contracts.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w04_search_abi_lift_preserves_legacy_value_error_message
        raise TypeError("search contract failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if cause is None:
        # kit:boundary owner=search.vector_contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_w04_search_abi_lift_preserves_legacy_value_error_message
        raise ValueError(message)
    # kit:boundary owner=search.vector_contracts.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=search.failure witness=test:test_w04_search_abi_lift_preserves_legacy_value_error_message
    raise ValueError(message) from cause


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


def _payload_provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for key in ("global_vector_object_provenance", "payload_provenance", "provenance"):
        value = row.get(key)
        if isinstance(value, Mapping):
            provenance.update(dict(value))
    return provenance


def _lookup_with_payload_provenance(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = _lookup(row, key)
        if value is not None:
            return value
    provenance = _payload_provenance(row)
    for key in keys:
        if key in provenance:
            return provenance[key]
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
) -> Annotated[
    str,
    "kit:non-authoritative derived_as=view "
    "fact_source=search_query_parameters "
    "witness=test:test_w04_authority_metadata",
]:
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
        _clean_text(_lookup_with_payload_provenance(row, "source_id", "source", "publisher", "channel_key"))
        or f"document:{document_id}"
    )


def _infer_vector_version(row: Mapping[str, Any], retrieval_mode: str) -> str:
    vector_version = _clean_text(_lookup_with_payload_provenance(row, "vector_version"))
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


def _source_domain_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    try:
        return urlparse(uri).netloc or None
    except Exception:  # noqa: BLE001
        return None


def _infer_fallback_reason(row: Mapping[str, Any]) -> str | None:
    fallback_reason = _clean_optional_text(_lookup_with_payload_provenance(row, "fallback_reason", "fallback"))
    if fallback_reason:
        return fallback_reason
    tags = {str(item).lower() for item in _lookup(row, "tags") or []}
    if "fallback" in tags:
        backend = _infer_backend(row)
        return f"{backend}_fallback"
    return None


def build_global_vector_object(
    row: Mapping[str, Any],
    *,
    project_key: str | None = None,
    retrieval_mode: str | None = None,
    matrix_branch_id: str | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=search_row+projection_parameters "
    "witness=test:test_w04_authority_metadata",
]:
    document_id = _infer_document_id(row)
    object_type = _infer_object_type(row, retrieval_mode or _infer_retrieval_mode(row, None))
    object_id = _infer_object_id(row, document_id)
    chunk_id = _infer_chunk_id(row, document_id)
    source_id = _infer_source_id(row, document_id)
    vector_version = _infer_vector_version(row, retrieval_mode or _infer_retrieval_mode(row, None))
    source_uri = _clean_optional_text(_lookup_with_payload_provenance(row, "source_uri", "url", "uri"))
    normalized_backend = _infer_backend(row)
    effective_retrieval_mode = retrieval_mode or _infer_retrieval_mode(row, None)
    provider = (
        _clean_optional_text(
            _lookup_with_payload_provenance(row, "embedding_provider", "provider", "provider_id")
        )
        or normalized_backend
    )
    embedding_model = (
        _clean_optional_text(_lookup_with_payload_provenance(row, "embedding_model", "model"))
        or "unknown_embedding_model"
    )
    embedding_model_version = (
        _clean_optional_text(
            _lookup_with_payload_provenance(
                row,
                "embedding_model_version",
                "embedding_version",
                "model_version",
            )
        )
        or vector_version
        or "unknown_embedding_version"
    )
    embedding_dim = _coerce_int_or_none(_lookup_with_payload_provenance(row, "embedding_dim", "dim"))
    source_reference = (
        _clean_optional_text(
            _lookup_with_payload_provenance(
                row,
                "source_reference",
                "reference",
                "reference_id",
                "url",
                "uri",
                "source_uri",
            )
        )
        or source_uri
        or source_id
        or document_id
    )
    source = (
        _clean_optional_text(_lookup_with_payload_provenance(row, "source", "publisher", "channel_key"))
        or source_id
    )
    provenance = {
        **_payload_provenance(row),
        "source_uri": source_uri,
        "source_domain": _clean_optional_text(_lookup_with_payload_provenance(row, "source_domain"))
        or _source_domain_from_uri(source_uri),
        "effective_time": _clean_optional_text(
            _lookup_with_payload_provenance(row, "effective_time", "publish_date", "published_at")
        ),
        "language": _clean_optional_text(_lookup_with_payload_provenance(row, "language")),
        "provider": provider,
        "backend": normalized_backend,
        "retrieval_mode": effective_retrieval_mode,
        "provider_payload_kind": _clean_optional_text(
            _lookup_with_payload_provenance(row, "provider_payload_kind")
        )
        or normalized_backend,
        "embedding_model": embedding_model,
        "embedding_model_version": embedding_model_version,
        "embedding_dim": embedding_dim,
        "vector_version": vector_version,
        "source": source,
        "source_id": source_id,
        "source_reference": source_reference,
        "reference": source_reference,
        "score": _coerce_float(_lookup_with_payload_provenance(row, "score", "_score", "rank_score")),
        "fallback_reason": _infer_fallback_reason(row),
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
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
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
    retrieval_family: str = "main_search",
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=search_row+query_group+rank_parameters "
    "witness=test:test_w04_authority_metadata",
]:
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
        "retrieval_family": _clean_text(retrieval_family) or "main_search",
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
    retrieval_family: str = "main_search",
) -> Annotated[
    tuple[str, list[dict[str, Any]]],
    "kit:non-authoritative derived_as=view "
    "fact_source=search_rows+query_parameters "
    "witness=test:test_w04_authority_metadata",
]:
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
            retrieval_family=retrieval_family,
        )
        for index, row in enumerate(rows, start=1)
        if isinstance(row, Mapping)
    ]
    for hit in hits:
        failure = validate_search_evidence_hit(hit)
        if failure is not None:
            _raise_contract_failure(failure)
    return query_group_id, hits


def build_retrieval_run_record(
    *,
    query: str,
    query_group_id: str,
    evidence_hits: Iterable[Mapping[str, Any]],
    project_key: str | None = None,
    rank_mode: str = "hybrid",
    state: str | None = None,
    modality: str = "any",
    top_k: int | None = None,
    retrieval_family: str = "main_search",
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=query+evidence_hits+rank_parameters "
    "witness=test:test_w04_authority_metadata",
]:
    hits = [dict(hit) for hit in evidence_hits if isinstance(hit, Mapping)]
    branch_map: dict[str, dict[str, Any]] = {}
    for hit in hits:
        branch_id = _clean_text(hit.get("matrix_branch_id")) or "branch_unknown"
        branch = branch_map.setdefault(
            branch_id,
            {
                "matrix_branch_id": branch_id,
                "retrieval_mode": _clean_text(hit.get("retrieval_mode")),
                "backend": _clean_text(hit.get("backend")),
                "retrieval_family": _clean_text(hit.get("retrieval_family")) or retrieval_family,
                "hit_ids": [],
                "hit_count": 0,
                "top_score": 0.0,
                "global_vector_object_refs": [],
                "verification_states": [],
            },
        )
        hit_id = _clean_text(hit.get("hit_id"))
        if hit_id and hit_id not in branch["hit_ids"]:
            branch["hit_ids"].append(hit_id)
        branch["hit_count"] = len(branch["hit_ids"])
        branch["top_score"] = max(float(branch.get("top_score") or 0.0), _coerce_float(hit.get("score")))
        verification_state = _clean_text(hit.get("verification_state"))
        if verification_state and verification_state not in branch["verification_states"]:
            branch["verification_states"].append(verification_state)
        vector_object = _mapping(hit.get("global_vector_object"))
        vector_ref = {
            "document_id": _clean_text(vector_object.get("document_id")),
            "chunk_id": _clean_text(vector_object.get("chunk_id")),
            "source_id": _clean_text(vector_object.get("source_id")),
            "vector_version": _clean_text(vector_object.get("vector_version")),
        }
        if vector_ref not in branch["global_vector_object_refs"]:
            branch["global_vector_object_refs"].append(vector_ref)
    branch_records = sorted(branch_map.values(), key=lambda item: item["matrix_branch_id"])
    run_id = _stable_id(
        "retrieval_run",
        {
            "branch_records": branch_records,
            "project_key": _clean_optional_text(project_key),
            "query": _clean_text(query),
            "query_group_id": query_group_id,
            "rank_mode": rank_mode,
            "retrieval_family": retrieval_family,
            "top_k": top_k,
        },
    )
    filters = {
        "state": _clean_optional_text(state),
        "modality": _clean_text(modality) or "any",
        "top_k": top_k,
    }
    retrieval_branches: list[dict[str, Any]] = []
    for branch in branch_records:
        enriched_branch = {
            **branch,
            "contract_version": SEARCH_RETRIEVAL_BRANCH_CONTRACT_VERSION,
            "run_id": run_id,
            "retrieval_run_id": run_id,
            "query_group_id": query_group_id,
            "query_text": _clean_text(query),
            "rank_mode": _clean_text(rank_mode) or "hybrid",
            "provider_or_index": _clean_text(branch.get("backend")) or "unknown",
            "status": "completed",
            "filters": dict(filters),
        }
        retrieval_branches.append(enriched_branch)
    retrieval_hits = []
    for hit in hits:
        vector_object = _mapping(hit.get("global_vector_object"))
        retrieval_hits.append(
            {
                "contract_version": SEARCH_RETRIEVAL_HIT_CONTRACT_VERSION,
                "run_id": run_id,
                "retrieval_run_id": run_id,
                "query_group_id": query_group_id,
                "matrix_branch_id": _clean_text(hit.get("matrix_branch_id")),
                "hit_id": _clean_text(hit.get("hit_id")),
                "rank": hit.get("rank"),
                "score": _coerce_float(hit.get("score")),
                "retrieval_mode": _clean_text(hit.get("retrieval_mode")),
                "retrieval_family": _clean_text(hit.get("retrieval_family")) or retrieval_family,
                "backend": _clean_text(hit.get("backend")),
                "object_type": _clean_text(vector_object.get("object_type")),
                "object_id": _clean_text(vector_object.get("object_id")),
                "chunk_id": _clean_text(vector_object.get("chunk_id")),
                "document_id": _clean_text(vector_object.get("document_id")),
                "source_id": _clean_text(vector_object.get("source_id")),
                "evidence_class": _clean_text(hit.get("evidence_class")),
                "verification_state": _clean_text(hit.get("verification_state")),
                "provenance": dict(_mapping(hit.get("provenance"))),
                "global_vector_object": dict(vector_object),
            }
        )
    record = {
        "contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
        "run_id": run_id,
        "retrieval_run_id": run_id,
        "query_group_id": query_group_id,
        "retrieval_family": _clean_text(retrieval_family) or "main_search",
        "query": _clean_text(query),
        "query_text": _clean_text(query),
        "project_key": _clean_optional_text(project_key),
        "rank_mode": _clean_text(rank_mode) or "hybrid",
        "state": _clean_optional_text(state),
        "modality": _clean_text(modality) or "any",
        "top_k": top_k,
        "filters": filters,
        "branch_records": branch_records,
        "retrieval_branches": retrieval_branches,
        "retrieval_hits": retrieval_hits,
        "evidence_hits": hits,
        "branch_count": len(retrieval_branches),
        "hit_count": len(retrieval_hits),
        "status": "completed",
    }
    failure = validate_retrieval_run_record(record)
    if failure is not None:
        _raise_contract_failure(failure)
    return record


def serialize_retrieval_run_record(record: Mapping[str, Any]) -> str:
    failure = validate_retrieval_run_record(record)
    if failure is not None:
        _raise_contract_failure(failure)
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_retrieval_run_record(raw: str) -> dict[str, Any]:
    try:
        record = json.loads(raw)
    except (TypeError, ValueError) as exc:
        failure = _contract_failure(
            "retrieval_run_invalid",
            str(exc),
            operation="load_retrieval_run_record",
            site="search.vector_contracts.load_retrieval_run_record",
            cause=exc,
        )
        _raise_contract_failure(failure, cause=exc)
    if not isinstance(record, dict):
        failure = _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run must be a JSON object",
            operation="load_retrieval_run_record",
            site="search.vector_contracts.load_retrieval_run_record",
        )
        _raise_contract_failure(failure)
    failure = validate_retrieval_run_record(record)
    if failure is not None:
        _raise_contract_failure(failure)
    return record


def build_agent_matrix_evidence_hits(
    candidates: Iterable[Mapping[str, Any]],
    *,
    query: str,
    project_key: str | None = None,
    rank_mode: str = "matrix",
    top_k: int | None = None,
) -> Annotated[
    tuple[str, list[dict[str, Any]]],
    "kit:non-authoritative derived_as=view "
    "fact_source=agent_matrix_candidates+query_parameters "
    "witness=test:test_w04_authority_metadata",
]:
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        url = _clean_optional_text(_lookup(candidate, "url", "link", "canonical_link"))
        trust = _mapping(candidate.get("trust"))
        branches = list(candidate.get("matrix_branches") or [])
        first_branch = _mapping(branches[0]) if branches else {}
        provider = (
            _clean_optional_text(first_branch.get("provider"))
            or _clean_optional_text(_lookup(candidate, "source_provider", "provider", "source"))
            or "agent_matrix"
        )
        branch_id = _clean_optional_text(first_branch.get("branch_id")) or _stable_id(
            "agent_branch",
            {"provider": provider, "query": first_branch.get("query") or query, "rank": index},
        )
        trust_score = _coerce_float(trust.get("trust_score"), default=_coerce_float(candidate.get("score")))
        rows.append(
            {
                "document_id": _clean_optional_text(candidate.get("url_checksum"))
                or _clean_optional_text(trust.get("url_checksum"))
                or url
                or f"agent-candidate-{index}",
                "object_type": "source_candidate",
                "object_id": _clean_optional_text(candidate.get("url_checksum"))
                or _clean_optional_text(trust.get("url_checksum"))
                or url
                or f"agent-candidate-{index}",
                "chunk_id": f"source-candidate-{index}",
                "source_id": provider,
                "source_uri": url,
                "source_domain": _source_domain_from_uri(url),
                "score": trust_score,
                "backend": provider,
                "mode": "agent_matrix",
                "matrix_branch_id": branch_id,
                "evidence_class": "source_candidate",
                "verification_state": _clean_optional_text(trust.get("status")) or "candidate",
                "provider_payload_kind": "agent_matrix_candidate",
                "title": candidate.get("title"),
                "summary": candidate.get("snippet"),
                "tags": ["agent_matrix", "source_candidate"],
            }
        )
    return build_search_evidence_hits(
        rows,
        query=query,
        project_key=project_key,
        rank_mode=rank_mode,
        top_k=top_k,
        retrieval_family="agent_matrix",
    )


def try_validate_global_vector_object(vector_object: Mapping[str, Any]) -> Failure | None:
    operation = "validate_global_vector_object"
    site = "search.vector_contracts.validate_global_vector_object"
    vector_object = _mapping(vector_object)
    if vector_object.get("contract_version") != GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION:
        return _contract_failure(
            "global_vector_object_invalid",
            "unsupported global vector object contract_version",
            operation=operation,
            site=site,
            field="contract_version",
        )
    missing = [field for field in GLOBAL_VECTOR_OBJECT_REQUIRED_FIELDS if field not in vector_object]
    if missing:
        return _contract_failure(
            "global_vector_object_invalid",
            f"global_vector_object_missing_fields:{','.join(missing)}",
            operation=operation,
            site=site,
            fields=tuple(missing),
        )
    for field in ("object_type", "object_id", "chunk_id", "source_id", "document_id", "vector_version"):
        if not _clean_text(vector_object.get(field)):
            return _contract_failure(
                "global_vector_object_invalid",
                f"global_vector_object_empty_field:{field}",
                operation=operation,
                site=site,
                field=field,
            )
    if not isinstance(vector_object.get("provenance"), Mapping):
        return _contract_failure(
            "global_vector_object_invalid",
            "global_vector_object provenance must be an object",
            operation=operation,
            site=site,
            field="provenance",
        )
    provenance = _mapping(vector_object.get("provenance"))
    missing_provenance = [
        field for field in GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS if field not in provenance
    ]
    if missing_provenance:
        return _contract_failure(
            "global_vector_object_invalid",
            f"global_vector_object_provenance_missing_fields:{','.join(missing_provenance)}",
            operation=operation,
            site=site,
            fields=tuple(missing_provenance),
        )
    for field in (
        "provider",
        "backend",
        "retrieval_mode",
        "provider_payload_kind",
        "embedding_model",
        "embedding_model_version",
        "vector_version",
        "source",
        "source_id",
        "source_reference",
        "reference",
    ):
        if not _clean_text(provenance.get(field)):
            return _contract_failure(
                "global_vector_object_invalid",
                f"global_vector_object_provenance_empty_field:{field}",
                operation=operation,
                site=site,
                field=field,
            )
    if "score" not in provenance and not _clean_text(provenance.get("fallback_reason")):
        return _contract_failure(
            "global_vector_object_invalid",
            "global_vector_object_provenance_requires_score_or_fallback_reason",
            operation=operation,
            site=site,
            field="provenance.score",
        )
    return None


def try_validate_search_evidence_hit(hit: Mapping[str, Any]) -> Failure | None:
    operation = "validate_search_evidence_hit"
    site = "search.vector_contracts.validate_search_evidence_hit"
    hit = _mapping(hit)
    if hit.get("contract_version") != SEARCH_EVIDENCE_HIT_CONTRACT_VERSION:
        return _contract_failure(
            "evidence_hit_invalid",
            "unsupported search evidence hit contract_version",
            operation=operation,
            site=site,
            field="contract_version",
        )
    missing = [field for field in SEARCH_EVIDENCE_HIT_REQUIRED_FIELDS if field not in hit]
    if missing:
        return _contract_failure(
            "evidence_hit_invalid",
            f"search_evidence_hit_missing_fields:{','.join(missing)}",
            operation=operation,
            site=site,
            fields=tuple(missing),
        )
    for field in ("hit_id", "query_group_id", "matrix_branch_id", "retrieval_mode", "backend", "evidence_class"):
        if not _clean_text(hit.get(field)):
            return _contract_failure(
                "evidence_hit_invalid",
                f"search_evidence_hit_empty_field:{field}",
                operation=operation,
                site=site,
                field=field,
            )
    if _coerce_int_or_none(hit.get("rank")) is None or int(hit["rank"]) < 1:
        return _contract_failure(
            "evidence_hit_invalid",
            "search_evidence_hit rank must be a positive integer",
            operation=operation,
            site=site,
            field="rank",
        )
    if not isinstance(hit.get("rank_features"), Mapping):
        return _contract_failure(
            "evidence_hit_invalid",
            "search_evidence_hit rank_features must be an object",
            operation=operation,
            site=site,
            field="rank_features",
        )
    if not isinstance(hit.get("provenance"), Mapping):
        return _contract_failure(
            "evidence_hit_invalid",
            "search_evidence_hit provenance must be an object",
            operation=operation,
            site=site,
            field="provenance",
        )
    vector_failure = try_validate_global_vector_object(_mapping(hit.get("global_vector_object")))
    if vector_failure is not None:
        return _contract_failure(
            "evidence_hit_invalid",
            vector_failure.message,
            operation=operation,
            site=site,
            cause_failure_code=vector_failure.code,
            cause_failure_context=dict(vector_failure.context or {}),
        )
    return None


def try_validate_retrieval_run_record(record: Mapping[str, Any]) -> Failure | None:
    operation = "validate_retrieval_run_record"
    site = "search.vector_contracts.validate_retrieval_run_record"
    record = _mapping(record)
    if record.get("contract_version") != SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION:
        return _contract_failure(
            "retrieval_run_invalid",
            "unsupported search retrieval run contract_version",
            operation=operation,
            site=site,
            field="contract_version",
        )
    missing = [field for field in SEARCH_RETRIEVAL_RUN_REQUIRED_FIELDS if field not in record]
    if missing:
        return _contract_failure(
            "retrieval_run_invalid",
            f"search_retrieval_run_missing_fields:{','.join(missing)}",
            operation=operation,
            site=site,
            fields=tuple(missing),
        )
    if not isinstance(record.get("branch_records"), list):
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run branch_records must be a list",
            operation=operation,
            site=site,
            field="branch_records",
        )
    if not isinstance(record.get("retrieval_branches"), list):
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run retrieval_branches must be a list",
            operation=operation,
            site=site,
            field="retrieval_branches",
        )
    if not isinstance(record.get("retrieval_hits"), list):
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run retrieval_hits must be a list",
            operation=operation,
            site=site,
            field="retrieval_hits",
        )
    if not isinstance(record.get("evidence_hits"), list):
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run evidence_hits must be a list",
            operation=operation,
            site=site,
            field="evidence_hits",
        )
    run_id = _clean_text(record.get("run_id"))
    hits = list(record.get("evidence_hits") or [])
    branch_records = list(record.get("branch_records") or [])
    retrieval_branches = list(record.get("retrieval_branches") or [])
    retrieval_hits = list(record.get("retrieval_hits") or [])
    hit_ids = {_clean_text(hit.get("hit_id")) for hit in hits if isinstance(hit, Mapping)}
    hit_branch_ids = {_clean_text(hit.get("matrix_branch_id")) for hit in hits if isinstance(hit, Mapping)}
    record_branch_ids = {
        _clean_text(branch.get("matrix_branch_id")) for branch in branch_records if isinstance(branch, Mapping)
    }
    persisted_branch_ids = {
        _clean_text(branch.get("matrix_branch_id")) for branch in retrieval_branches if isinstance(branch, Mapping)
    }
    persisted_hit_ids = {_clean_text(hit.get("hit_id")) for hit in retrieval_hits if isinstance(hit, Mapping)}
    if hit_branch_ids != record_branch_ids:
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run branch_records do not match evidence hit branches",
            operation=operation,
            site=site,
            field="branch_records",
        )
    if hit_branch_ids != persisted_branch_ids:
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run retrieval_branches do not match evidence hit branches",
            operation=operation,
            site=site,
            field="retrieval_branches",
        )
    if hit_ids != persisted_hit_ids:
        return _contract_failure(
            "retrieval_run_invalid",
            "search_retrieval_run retrieval_hits do not match evidence hits",
            operation=operation,
            site=site,
            field="retrieval_hits",
        )
    for hit in hits:
        failure = try_validate_search_evidence_hit(_mapping(hit))
        if failure is not None:
            return _contract_failure(
                "retrieval_run_invalid",
                failure.message,
                operation=operation,
                site=site,
                cause_failure_code=failure.code,
                cause_failure_context=dict(failure.context or {}),
            )
    for branch in branch_records:
        branch_hit_ids = {_clean_text(item) for item in list(_mapping(branch).get("hit_ids") or [])}
        if not branch_hit_ids.issubset(hit_ids):
            return _contract_failure(
                "retrieval_run_invalid",
                "search_retrieval_run branch references unknown hit_id",
                operation=operation,
                site=site,
                field="branch_records.hit_ids",
            )
    for branch in retrieval_branches:
        branch_map = _mapping(branch)
        if branch_map.get("contract_version") != SEARCH_RETRIEVAL_BRANCH_CONTRACT_VERSION:
            return _contract_failure(
                "retrieval_run_invalid",
                "unsupported search retrieval branch contract_version",
                operation=operation,
                site=site,
                field="retrieval_branches.contract_version",
            )
        if _clean_text(branch_map.get("run_id")) != run_id:
            return _contract_failure(
                "retrieval_run_invalid",
                "search_retrieval_branch run_id mismatch",
                operation=operation,
                site=site,
                field="retrieval_branches.run_id",
            )
        branch_hit_ids = {_clean_text(item) for item in list(branch_map.get("hit_ids") or [])}
        if not branch_hit_ids.issubset(hit_ids):
            return _contract_failure(
                "retrieval_run_invalid",
                "search_retrieval_branch references unknown hit_id",
                operation=operation,
                site=site,
                field="retrieval_branches.hit_ids",
            )
    for hit in retrieval_hits:
        hit_map = _mapping(hit)
        if hit_map.get("contract_version") != SEARCH_RETRIEVAL_HIT_CONTRACT_VERSION:
            return _contract_failure(
                "retrieval_run_invalid",
                "unsupported search retrieval hit contract_version",
                operation=operation,
                site=site,
                field="retrieval_hits.contract_version",
            )
        if _clean_text(hit_map.get("run_id")) != run_id:
            return _contract_failure(
                "retrieval_run_invalid",
                "search_retrieval_hit run_id mismatch",
                operation=operation,
                site=site,
                field="retrieval_hits.run_id",
            )
        if _clean_text(hit_map.get("matrix_branch_id")) not in hit_branch_ids:
            return _contract_failure(
                "retrieval_run_invalid",
                "search_retrieval_hit references unknown branch",
                operation=operation,
                site=site,
                field="retrieval_hits.matrix_branch_id",
            )
    return None


def validate_global_vector_object(vector_object: Mapping[str, Any]) -> None:
    failure = try_validate_global_vector_object(vector_object)
    if failure is not None:
        _raise_contract_failure(failure)


def validate_search_evidence_hit(hit: Mapping[str, Any]) -> None:
    failure = try_validate_search_evidence_hit(hit)
    if failure is not None:
        _raise_contract_failure(failure)


def validate_retrieval_run_record(record: Mapping[str, Any]) -> None:
    failure = try_validate_retrieval_run_record(record)
    if failure is not None:
        _raise_contract_failure(failure)
