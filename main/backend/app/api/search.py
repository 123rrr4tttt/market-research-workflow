from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn, TypeGuard, TypedDict

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import JsonValue
from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.responses import ok
from ..contracts.materials import normalize_material_source_type
from ..services.document_queries import (
    MATERIAL_QUERY_CONTRACT_VERSION,
    MaterialQueryJsonObject,
    MaterialQueryJsonValue,
    build_search_endpoint_material_query_envelope,
    coerce_material_query_result_row,
)
from ..services.search.es_client import get_es_client
from ..services.search.indexes import ensure_indices
from ..services.search.hybrid import observe_hybrid_search, search_failure_payload
from ..services.search.retrieval_runs import (
    SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
    default_search_retrieval_runs_path,
    persist_search_retrieval_run_record,
    read_search_retrieval_run_record,
)
from ..services.search.vector_contracts import (
    GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
    SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
    SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
    build_retrieval_run_record,
    build_search_evidence_hits,
)
import logging

from ._error_responses import error_json_response as _error_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])
SEARCH_RESULTS_CONTRACT_VERSION = "search.results.v2"


class SearchRunIdValidationError(TypedDict):
    message: str
    details: MaterialQueryJsonObject


def _raise_upstream_error(message: str, *, details: MaterialQueryJsonObject | None = None) -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail=error_response(
            ErrorCode.UPSTREAM_ERROR,
            message,
            details=details,
        ),
    )


def _raise_internal_error(message: str, *, details: MaterialQueryJsonObject | None = None) -> NoReturn:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
            details=details,
        ),
    )


SearchEnvelope = ApiEnvelope[dict[str, JsonValue]]


def _search_clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _search_optional_text(value: object) -> str | None:
    cleaned = _search_clean_text(value)
    return cleaned or None


def _is_search_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _search_mapping(value: object) -> Mapping[str, object]:
    return value if _is_search_mapping(value) else {}


def _search_json_object(value: object) -> MaterialQueryJsonObject:
    return coerce_material_query_result_row(value)


def _search_json_value(value: object) -> MaterialQueryJsonValue:
    return _search_json_object({"value": value})["value"]


def _canonical_search_result(row: Mapping[str, object]) -> MaterialQueryJsonObject:
    """Validate the native Material identity before exposing a search result."""
    result = dict(row)
    legacy_fields = [key for key in ("id", "document_id", "doc_id") if key in result]
    if legacy_fields:
        raise ValueError(f"search provider returned retired identity fields: {', '.join(legacy_fields)}")
    if result.get("material_id") is None:
        raise ValueError("search provider result requires material_id")
    source_type = normalize_material_source_type(result.get("source_type"))
    result["source_type"] = "material" if source_type in {"", "document", "documents"} else source_type
    return _search_json_object(result)


def _search_object_list(value: object) -> list[MaterialQueryJsonObject]:
    converted = _search_json_value(value)
    if not isinstance(converted, list):
        return []
    return [_search_json_object(item) for item in converted if _is_search_mapping(item)]


def _search_text_list(value: object) -> list[str]:
    converted = _search_json_value(value)
    if not isinstance(converted, list):
        return []
    return [cleaned for item in converted if (cleaned := _search_clean_text(item))]


def _search_clean_run_id(value: object) -> tuple[str | None, SearchRunIdValidationError | None]:
    cleaned = _search_clean_text(value)
    if not cleaned:
        return None, {
            "message": "retrieval_run_id is required",
            "details": {"field": "retrieval_run_id", "category": "search_retrieval_run_readback"},
        }
    if cleaned != str(value) or any(character.isspace() for character in cleaned):
        return None, {
            "message": "retrieval_run_id must not contain whitespace",
            "details": {"field": "retrieval_run_id", "category": "search_retrieval_run_readback"},
        }
    if len(cleaned) > 256:
        return None, {
            "message": "retrieval_run_id is too long",
            "details": {"field": "retrieval_run_id", "max_length": 256},
        }
    return cleaned, None


def _search_fallback_used(*, used_backends: Sequence[str], retrieval_run: Mapping[str, object]) -> bool:
    if any(backend == "pgvector_fallback" for backend in used_backends):
        return True
    for hit in _search_object_list(retrieval_run.get("retrieval_hits")):
        provenance = hit.get("provenance")
        if _is_search_mapping(provenance) and provenance.get("fallback_reason"):
            return True
    for hit in _search_object_list(retrieval_run.get("evidence_hits")):
        provenance = hit.get("provenance")
        if _is_search_mapping(provenance) and provenance.get("fallback_reason"):
            return True
        if hit.get("fallback_reason"):
            return True
    return False


def _search_index_backend(*, used_backends: Sequence[str], fallback_order: Sequence[str]) -> str:
    for backend in used_backends:
        if backend:
            return backend
    return fallback_order[0] if fallback_order else "unknown"


def _search_hit_count(value: object) -> int:
    converted = _search_json_value(value)
    if isinstance(converted, list):
        return len(converted)
    try:
        return int(converted) if isinstance(converted, (str, int, float)) else 0
    except (TypeError, ValueError):
        return 0


def _search_result_identifier(hit: Mapping[str, object], *, index: int) -> str:
    vector_object = _search_mapping(hit.get("global_vector_object"))
    for value in (
        hit.get("hit_id"),
        hit.get("id"),
        hit.get("material_id"),
        vector_object.get("material_id"),
        vector_object.get("object_id"),
        vector_object.get("chunk_id"),
    ):
        cleaned = _search_clean_text(value)
        if cleaned:
            return cleaned
    return f"result-{index}"


def _search_group_backend(hit: Mapping[str, object]) -> str:
    provenance = _search_mapping(hit.get("provenance"))
    rank_features = _search_mapping(hit.get("rank_features"))
    vector_object = _search_mapping(hit.get("global_vector_object"))
    vector_provenance = _search_mapping(vector_object.get("provenance"))
    return (
        _search_clean_text(hit.get("backend"))
        or _search_clean_text(rank_features.get("backend"))
        or _search_clean_text(provenance.get("backend"))
        or _search_clean_text(vector_provenance.get("backend"))
        or "unknown"
    )


def _search_group_source_type(hit: Mapping[str, object]) -> str:
    provenance = _search_mapping(hit.get("provenance"))
    vector_object = _search_mapping(hit.get("global_vector_object"))
    vector_provenance = _search_mapping(vector_object.get("provenance"))
    return normalize_material_source_type(
        _search_clean_text(hit.get("source_type"))
        or _search_clean_text(hit.get("evidence_class"))
        or _search_clean_text(vector_object.get("object_type"))
        or _search_clean_text(provenance.get("source_type"))
        or _search_clean_text(vector_provenance.get("source_type"))
        or "unknown"
    )


def _search_group_provenance_key(hit: Mapping[str, object]) -> str:
    provenance = _search_mapping(hit.get("provenance"))
    vector_object = _search_mapping(hit.get("global_vector_object"))
    vector_provenance = _search_mapping(vector_object.get("provenance"))
    for value in (
        provenance.get("source_id"),
        provenance.get("source_reference"),
        provenance.get("source"),
        vector_object.get("source_id"),
        vector_provenance.get("source_id"),
        vector_provenance.get("source_reference"),
        vector_provenance.get("source"),
        provenance.get("provider"),
        vector_provenance.get("provider"),
    ):
        cleaned = _search_clean_text(value)
        if cleaned:
            return cleaned
    return "unknown"


def _build_search_result_groups(
    *,
    results: Sequence[Mapping[str, object]],
    evidence_hits: Sequence[Mapping[str, object]],
    default_backend: str,
) -> list[MaterialQueryJsonObject]:
    source_hits = evidence_hits or results
    group_fields: dict[str, tuple[str, str, str]] = {}
    group_result_ids: dict[str, list[str]] = {}
    for index, hit in enumerate(source_hits, start=1):
        backend = _search_group_backend(hit)
        if backend == "unknown" and default_backend:
            backend = default_backend
        source_type = _search_group_source_type(hit)
        provenance_key = _search_group_provenance_key(hit)
        group_key = f"{backend}|{source_type}|{provenance_key}"
        group_fields[group_key] = (backend, source_type, provenance_key)
        result_ids = group_result_ids.setdefault(group_key, [])
        result_id = _search_result_identifier(hit, index=index)
        if result_id not in result_ids:
            result_ids.append(result_id)
    groups: list[MaterialQueryJsonObject] = [
        _search_json_object({
            "group_key": group_key,
            "backend": fields[0],
            "source_type": fields[1],
            "provenance_key": fields[2],
            "count": len(group_result_ids[group_key]),
            "result_ids": group_result_ids[group_key],
        })
        for group_key, fields in group_fields.items()
    ]
    return sorted(
        groups,
        key=lambda item: (
            _search_clean_text(item.get("backend")),
            _search_clean_text(item.get("source_type")),
            _search_clean_text(item.get("provenance_key")),
        ),
    )


def _build_search_index_freshness(
    *,
    index_backend: str,
    fallback_used: bool,
    retrieval_run: Mapping[str, object],
    retrieval_run_readback: Mapping[str, object] | None,
) -> MaterialQueryJsonObject:
    readback = _search_mapping(retrieval_run_readback)
    readback_available = bool(readback.get("readback_available"))
    if readback_available and fallback_used:
        freshness_state = "fallback_available"
    elif readback_available:
        freshness_state = "available"
    elif fallback_used:
        freshness_state = "fallback_unknown"
    elif readback:
        freshness_state = "unavailable"
    else:
        freshness_state = "unknown"

    branch_count = _search_hit_count(readback.get("branch_count"))
    if not branch_count:
        branch_count = _search_hit_count(retrieval_run.get("retrieval_branches"))
    hit_count = _search_hit_count(readback.get("hit_count"))
    if not hit_count:
        hit_count = _search_hit_count(retrieval_run.get("retrieval_hits"))

    return _search_json_object({
        "contract_version": "search.index_freshness.v1",
        "index_backend": index_backend,
        "readback_available": readback_available,
        "freshness_state": freshness_state,
        "fallback_used": fallback_used,
        "retrieval_run_id": retrieval_run.get("retrieval_run_id") or retrieval_run.get("run_id") or readback.get("run_id"),
        "retrieval_run_status": retrieval_run.get("status") or "unknown",
        "readback_status": readback.get("status") or "not_available",
        "branch_count": branch_count,
        "hit_count": hit_count,
        "freshness_basis": "retrieval_run_readback" if readback_available else "retrieval_run",
        "known_limitations": ["no_real_index_timestamp"],
    })


def _build_search_provider_trace(
    *,
    used_backends: Sequence[str],
    fallback_order: Sequence[str],
    retrieval_run: Mapping[str, object],
    index_backend: str,
    fallback_used: bool,
    index_freshness: Mapping[str, object],
) -> MaterialQueryJsonObject:
    branches: list[MaterialQueryJsonObject] = []
    for branch in _search_object_list(retrieval_run.get("retrieval_branches")):
        branches.append(
            {
                "matrix_branch_id": branch.get("matrix_branch_id"),
                "retrieval_mode": branch.get("retrieval_mode"),
                "backend": branch.get("backend"),
                "provider_or_index": branch.get("provider_or_index"),
                "hit_count": branch.get("hit_count"),
                "status": branch.get("status"),
            }
        )
    return _search_json_object({
        "contract_version": "search.provider_trace.compat.v1",
        "status": retrieval_run.get("status") or "completed",
        "retrieval_run_id": retrieval_run.get("retrieval_run_id") or retrieval_run.get("run_id"),
        "query_group_id": retrieval_run.get("query_group_id"),
        "providers_used": list(used_backends),
        "fallback_order": list(fallback_order),
        "index_backend": index_backend,
        "fallback_used": fallback_used,
        "index_freshness": {
            "contract_version": index_freshness.get("contract_version"),
            "freshness_state": index_freshness.get("freshness_state"),
            "readback_available": index_freshness.get("readback_available"),
            "fallback_used": index_freshness.get("fallback_used"),
        },
        "branches": branches,
    })


def _search_backends_from_retrieval_run(retrieval_run: Mapping[str, object]) -> list[str]:
    backends: list[str] = []
    for branch in _search_object_list(retrieval_run.get("retrieval_branches")):
        backend = _search_clean_text(branch.get("provider_or_index")) or _search_clean_text(branch.get("backend"))
        if backend and backend not in backends:
            backends.append(backend)
    for hit in _search_object_list(retrieval_run.get("retrieval_hits")):
        backend = _search_group_backend(hit)
        if backend and backend != "unknown" and backend not in backends:
            backends.append(backend)
    return backends


def _build_search_source_query(retrieval_run: Mapping[str, object]) -> MaterialQueryJsonObject:
    return _search_json_object({
        "contract_version": "search.source_query.v1",
        "scope": "search.retrieval_run",
        "entrypoint": "search.runs.readback",
        "retrieval_run_id": retrieval_run.get("retrieval_run_id") or retrieval_run.get("run_id"),
        "run_id": retrieval_run.get("run_id"),
        "query_group_id": retrieval_run.get("query_group_id"),
        "query": retrieval_run.get("query") or retrieval_run.get("query_text"),
        "query_text": retrieval_run.get("query_text") or retrieval_run.get("query"),
        "project_key": retrieval_run.get("project_key"),
        "rank_mode": retrieval_run.get("rank_mode"),
        "retrieval_family": retrieval_run.get("retrieval_family"),
        "filters": dict(_search_mapping(retrieval_run.get("filters"))),
        "state": retrieval_run.get("state"),
        "modality": retrieval_run.get("modality"),
        "top_k": retrieval_run.get("top_k"),
    })


def _build_search_source_refs(retrieval_run: Mapping[str, object]) -> list[MaterialQueryJsonObject]:
    retrieval_run_id = retrieval_run.get("retrieval_run_id") or retrieval_run.get("run_id")
    query_group_id = retrieval_run.get("query_group_id")
    run_ref_id = f"search.retrieval_run:{retrieval_run_id}"
    refs: list[MaterialQueryJsonObject] = [
        _search_json_object({
            "id": run_ref_id,
            "type": "search_retrieval_run",
            "table": "search_retrieval_runs",
            "retrieval_run_id": retrieval_run_id,
            "run_id": retrieval_run.get("run_id"),
            "query_group_id": query_group_id,
        })
    ]
    seen = {run_ref_id}
    raw_hits = retrieval_run.get("retrieval_hits") or retrieval_run.get("evidence_hits")
    for index, hit in enumerate(_search_object_list(raw_hits), start=1):
        provenance = _search_mapping(hit.get("provenance"))
        vector_object = _search_mapping(hit.get("global_vector_object"))
        vector_provenance = _search_mapping(vector_object.get("provenance"))
        hit_id = _search_clean_text(hit.get("hit_id")) or f"hit-{index}"
        source_reference = (
            _search_clean_text(provenance.get("source_reference"))
            or _search_clean_text(vector_provenance.get("source_reference"))
            or _search_clean_text(provenance.get("reference"))
            or _search_clean_text(vector_provenance.get("reference"))
            or None
        )
        source_id = (
            _search_clean_text(hit.get("source_id"))
            or _search_clean_text(vector_object.get("source_id"))
            or _search_clean_text(provenance.get("source_id"))
            or _search_clean_text(vector_provenance.get("source_id"))
            or None
        )
        ref_id = f"search.evidence_hit:{retrieval_run_id}:{hit_id}"
        if ref_id in seen:
            continue
        seen.add(ref_id)
        refs.append(
            _search_json_object({
                "id": ref_id,
                "type": "search_evidence_hit",
                "table": "search_retrieval_hits",
                "retrieval_run_id": retrieval_run_id,
                "run_id": retrieval_run.get("run_id"),
                "query_group_id": query_group_id,
                "hit_id": hit_id,
                "backend": _search_group_backend(hit),
                "material_id": (
                    _search_clean_text(hit.get("material_id"))
                    or _search_clean_text(vector_object.get("material_id"))
                    or None
                ),
                "chunk_id": _search_clean_text(hit.get("chunk_id")) or _search_clean_text(vector_object.get("chunk_id")) or None,
                "source_id": source_id,
                "source_reference": source_reference,
            })
        )
    return refs


def _build_search_retrieval_run_readback_payload(
    *,
    retrieval_run: Mapping[str, object],
    store_path: Path,
) -> MaterialQueryJsonObject:
    retrieval_run_id = retrieval_run.get("retrieval_run_id") or retrieval_run.get("run_id")
    readback = {
        "contract_version": SEARCH_RETRIEVAL_RUN_READBACK_CONTRACT_VERSION,
        "status": "passed",
        "readback_performed": True,
        "readback_available": True,
        "storage_kind": "local_jsonl",
        "path": str(store_path),
        "run_id": retrieval_run.get("run_id"),
        "retrieval_run_id": retrieval_run_id,
        "branch_count": len(_search_object_list(retrieval_run.get("retrieval_branches"))),
        "hit_count": len(_search_object_list(retrieval_run.get("retrieval_hits"))),
    }
    used_backends = _search_backends_from_retrieval_run(retrieval_run)
    fallback_order = [
        "opensearch_lexical",
        "qdrant_vector",
        "pgvector_fallback",
    ]
    index_backend = _search_index_backend(used_backends=used_backends, fallback_order=fallback_order)
    fallback_used = _search_fallback_used(used_backends=used_backends, retrieval_run=retrieval_run)
    index_freshness = _build_search_index_freshness(
        index_backend=index_backend,
        fallback_used=fallback_used,
        retrieval_run=retrieval_run,
        retrieval_run_readback=readback,
    )
    provider_trace = _build_search_provider_trace(
        used_backends=used_backends,
        fallback_order=fallback_order,
        retrieval_run=retrieval_run,
        index_backend=index_backend,
        fallback_used=fallback_used,
        index_freshness=index_freshness,
    )
    return _search_json_object({
        "retrieval_run_id": retrieval_run_id,
        "run_id": retrieval_run.get("run_id"),
        "query_group_id": retrieval_run.get("query_group_id"),
        "retrieval_run": _search_json_object(retrieval_run),
        "source_query": _build_search_source_query(retrieval_run),
        "source_refs": _build_search_source_refs(retrieval_run),
        "provider_trace": provider_trace,
        "index_backend": index_backend,
        "fallback_used": fallback_used,
        "index_freshness": index_freshness,
        "retrieval_run_readback": readback,
        "readback": readback,
    })


def _build_search_trace_chain(
    *,
    request: Request,
    query: str,
    project_key: str | None,
    used_backends: Sequence[str],
    fallback_order: Sequence[str],
    retrieval_run: Mapping[str, object],
    retrieval_run_readback: Mapping[str, object] | None,
    provider_trace: Mapping[str, object],
    index_backend: str,
    fallback_used: bool,
    index_freshness: Mapping[str, object],
) -> MaterialQueryJsonObject:
    readback = _search_mapping(retrieval_run_readback)
    retrieval_run_id = (
        _search_clean_text(retrieval_run.get("retrieval_run_id"))
        or _search_clean_text(retrieval_run.get("run_id"))
        or _search_clean_text(readback.get("retrieval_run_id"))
        or _search_clean_text(readback.get("run_id"))
        or None
    )
    trace_id = (
        _search_clean_text(request.headers.get("x-request-id"))
        or _search_clean_text(request.headers.get("x-correlation-id"))
        or retrieval_run_id
        or _search_clean_text(provider_trace.get("query_group_id"))
        or "search.trace.unavailable"
    )
    limitations = list(
        dict.fromkeys(
            [
                *_search_text_list(index_freshness.get("known_limitations")),
                "no_real_index_timestamp",
            ]
        )
    )
    return _search_json_object({
        "contract_version": "ingest_search.trace_chain.v1",
        "trace_id": trace_id,
        "project_key": project_key,
        "entrypoint": "search.query",
        "run_order": [
            {
                "order": 1,
                "stage": "search_request",
                "query": query,
                "query_group_id": retrieval_run.get("query_group_id"),
                "status": "accepted",
            },
            {
                "order": 2,
                "stage": "provider_trace",
                "providers_used": list(used_backends),
                "fallback_order": list(fallback_order),
                "status": provider_trace.get("status") or "completed",
            },
            {
                "order": 3,
                "stage": "retrieval_run",
                "retrieval_run_id": retrieval_run_id,
                "readback_available": bool(readback.get("readback_available")),
                "status": retrieval_run.get("status") or "unknown",
            },
            {
                "order": 4,
                "stage": "index_freshness",
                "index_backend": index_backend,
                "freshness_state": index_freshness.get("freshness_state"),
                "real_timestamp_available": False,
                "timestamp_status": "not_available",
            },
        ],
        "ids": {
            "submission_id": None,
            "task_id": None,
            "retrieval_run_id": retrieval_run_id,
        },
        "provider": used_backends[0] if used_backends else "unknown",
        "fallback": {
            "used": bool(fallback_used),
            "fallback_order": list(fallback_order),
            "reason": "fallback_backend_or_hit_provenance_detected" if fallback_used else "no_fallback_detected",
        },
        "index": {
            "index_backend": index_backend,
            "freshness_state": index_freshness.get("freshness_state"),
            "readback_available": bool(index_freshness.get("readback_available")),
            "freshness_basis": index_freshness.get("freshness_basis"),
            "real_timestamp_available": False,
            "timestamp_status": "not_available",
        },
        "replay": {
            "retrieval_run_readback_status": readback.get("status") or "not_available",
            "storage_kind": readback.get("storage_kind"),
            "path": readback.get("path"),
        },
        "known_limitations": limitations,
    })


@router.get("/runs/{retrieval_run_id}", response_model=SearchEnvelope)
def get_search_retrieval_run(retrieval_run_id: str):
    """Read back a persisted search retrieval run by id."""
    cleaned_run_id, validation_error = _search_clean_run_id(retrieval_run_id)
    if validation_error is not None:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            validation_error["message"],
            details=validation_error["details"],
        )
    assert cleaned_run_id is not None
    store_path = default_search_retrieval_runs_path()
    try:
        retrieval_run = _search_json_object(read_search_retrieval_run_record(store_path, cleaned_run_id))
    except FileNotFoundError:
        return _error_json(
            404,
            ErrorCode.NOT_FOUND,
            "search retrieval run store is missing",
            details={
                "category": "search_retrieval_run_readback",
                "retrieval_run_id": cleaned_run_id,
                "store_kind": "local_jsonl",
            },
        )
    except KeyError:
        return _error_json(
            404,
            ErrorCode.NOT_FOUND,
            f"search retrieval run not found: {cleaned_run_id}",
            details={
                "category": "search_retrieval_run_readback",
                "retrieval_run_id": cleaned_run_id,
                "store_kind": "local_jsonl",
            },
        )
    except ValueError as exc:
        _raise_internal_error(
            "search retrieval run store is invalid",
            details={
                "category": "search_retrieval_run_readback",
                "retrieval_run_id": cleaned_run_id,
                "exception_type": exc.__class__.__name__,
            },
        )

    return ok(_build_search_retrieval_run_readback_payload(retrieval_run=retrieval_run, store_path=store_path))


@router.get("", response_model=SearchEnvelope)
def search(
    request: Request,
    q: str = Query("market trend"),
    state: str | None = None,
    modality: str = Query("any"),
    rank: str = Query("hybrid"),
    top_k: int = Query(10, ge=1, le=100),
):
    """Search the project using the requested lexical and/or vector channels."""
    try:
        project_key = _search_optional_text(getattr(request.state, "project_key_resolved", None))
        hybrid_observation = observe_hybrid_search(
            q,
            state,
            top_k,
            rank,
            project_key=project_key,
        )
        results = [_canonical_search_result(row) for row in hybrid_observation.hits]
        search_failures: list[MaterialQueryJsonValue] = [
            search_failure_payload(failure) for failure in hybrid_observation.failures
        ]
        if not hybrid_observation.used_backends and search_failures:
            _raise_upstream_error(
                "Search backends are unavailable",
                details={
                    "category": "search_backend",
                    "search_failures": search_failures,
                },
            )
        # Diagnostics about fallback/backends (contract-safe: added under data)
        fallback_order = [
            "opensearch_lexical",
            "qdrant_vector",
            "pgvector_fallback",
        ]
        used_backends: list[str] = []
        for b in hybrid_observation.used_backends:
            if b == "opensearch":
                used_backends.append("opensearch_lexical")
            elif b == "qdrant":
                used_backends.append("qdrant_vector")
            elif b == "pgvector":
                used_backends.append("pgvector_fallback")
            else:
                used_backends.append(b)

        query_group_id, raw_evidence_hits = build_search_evidence_hits(
            results,
            query=q,
            project_key=project_key,
            rank_mode=rank,
            state=state,
            modality=modality,
            top_k=top_k,
        )
        evidence_hits = [_search_json_object(hit) for hit in raw_evidence_hits]
        retrieval_run = _search_json_object(build_retrieval_run_record(
            query=q,
            query_group_id=query_group_id,
            evidence_hits=evidence_hits,
            project_key=project_key,
            rank_mode=rank,
            state=state,
            modality=modality,
            top_k=top_k,
            retrieval_family="main_search",
        ))
        retrieval_run_readback = _search_json_object(persist_search_retrieval_run_record(retrieval_run))
        index_backend = _search_index_backend(used_backends=used_backends, fallback_order=fallback_order)
        fallback_used = _search_fallback_used(used_backends=used_backends, retrieval_run=retrieval_run)
        result_groups = _build_search_result_groups(
            results=results,
            evidence_hits=evidence_hits,
            default_backend=index_backend,
        )
        index_freshness = _build_search_index_freshness(
            index_backend=index_backend,
            fallback_used=fallback_used,
            retrieval_run=retrieval_run,
            retrieval_run_readback=retrieval_run_readback,
        )
        provider_trace = _build_search_provider_trace(
            used_backends=used_backends,
            fallback_order=fallback_order,
            retrieval_run=retrieval_run,
            index_backend=index_backend,
            fallback_used=fallback_used,
            index_freshness=index_freshness,
        )
        trace_chain = _build_search_trace_chain(
            request=request,
            query=q,
            project_key=project_key,
            used_backends=used_backends,
            fallback_order=fallback_order,
            retrieval_run=retrieval_run,
            retrieval_run_readback=retrieval_run_readback,
            provider_trace=provider_trace,
            index_backend=index_backend,
            fallback_used=fallback_used,
            index_freshness=index_freshness,
        )
        material_query_envelope = build_search_endpoint_material_query_envelope(
            query=q,
            state=state,
            modality=modality,
            rank=rank,
            top_k=top_k,
            results=results,
            project_key=project_key,
            used_backends=used_backends,
        )
        material_query_data = material_query_envelope["data"]

        response_data = _search_json_object({
            "query": q,
            "state": state,
            "modality": modality,
            "rank": rank,
            "top_k": top_k,
            "search_result_contract_version": SEARCH_RESULTS_CONTRACT_VERSION,
            "results": results,
            "material_query_contract_version": MATERIAL_QUERY_CONTRACT_VERSION,
            "material_query": material_query_data["query"],
            "material_query_results": material_query_data["results"],
            "material_query_pagination": material_query_data["pagination"],
            "material_query_meta": material_query_envelope["meta"],
            "global_vector_object_contract_version": GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
            "evidence_hit_contract_version": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
            "query_group_id": query_group_id,
            "evidence_hits": evidence_hits,
            "retrieval_run_contract_version": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "retrieval_run_id": retrieval_run["run_id"],
            "search_branches": retrieval_run["retrieval_branches"],
            "branch_hit_details": retrieval_run["retrieval_hits"],
            "retrieval_run": retrieval_run,
            "retrieval_run_readback": retrieval_run_readback,
            "search_fallback_order": fallback_order,
            "search_backends_used": used_backends,
            "search_failures": search_failures,
            "provider_trace": provider_trace,
            "index_backend": index_backend,
            "fallback_used": fallback_used,
            "result_groups": result_groups,
            "index_freshness": index_freshness,
            "trace_chain": trace_chain,
        })
        return ok(response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("搜索失败")
        _raise_internal_error(
            f"搜索失败: {e}",
            details={"exception_type": e.__class__.__name__},
        )


@router.post("/_init", response_model=SearchEnvelope)
def init_search_indices():
    """Create ES indices if not present (idempotent)."""
    es = get_es_client()
    return ok(_search_json_object(ensure_indices(es)))
