"""Resource pool extraction API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..contracts import ApiEnvelope, ApiMetaModel, fail, ok, ok_page, task_result_response
from ..contracts.errors import ErrorCode, map_exception_to_error
from ..settings.config import get_effective_project_key_enforcement_mode
from ..services.projects import current_project_key
from ..services.ingest_config import get_config as get_ingest_config
from ..services.resource_pool import (
    classify_site_entry,
    classify_site_entries_batch,
    discover_search_contract,
    discover_site_entries_from_urls,
    extract_from_documents,
    extract_from_tasks,
    get_site_entry_by_url,
    import_open_source_preset_pack,
    list_urls,
    list_open_source_preset_packs,
    list_site_entries,
    simplify_site_entries,
    unified_search_by_item,
    upsert_site_entry,
    upsert_capture_config,
    write_discovered_site_entries,
)
from ..services.source_library.item_plan import build_item_execution_plan

ScopeType = Literal["shared", "project", "effective"]

router = APIRouter(prefix="/resource_pool", tags=["resource_pool"])
ResourcePoolAnyEnvelope = ApiEnvelope[Any]

SITE_ENTRIES_DASH_ALIAS_DEPRECATION = "resource_pool.site_entries_dash_alias.v1"
SITE_ENTRY_LIFECYCLE_STATES = {"active", "candidate", "accepted", "rejected", "needs_review", "disabled"}
SITE_ENTRY_REVIEW_STATES = {"accepted", "rejected", "needs_review", "disabled"}
SITE_ENTRY_LIFECYCLE_TRANSITION_CONTRACT = "resource_pool.site_entry.lifecycle_transition.v1"


def _error_status_code(code: ErrorCode) -> int:
    if code in {ErrorCode.INVALID_INPUT, ErrorCode.PROJECT_KEY_REQUIRED, ErrorCode.CONFIG_ERROR}:
        return 400
    if code == ErrorCode.NOT_FOUND:
        return 404
    if code == ErrorCode.RATE_LIMITED:
        return 429
    if code == ErrorCode.UPSTREAM_ERROR:
        return 503
    if code == ErrorCode.PARSE_ERROR:
        return 502
    return 500


def _error_json(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = fail(code, message, details=details)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


def _json_from_exception(exc: Exception) -> JSONResponse:
    if isinstance(exc, ValueError):
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            str(exc) or "Invalid resource pool request.",
            details={"exception_type": exc.__class__.__name__},
        )
    code, message, details = map_exception_to_error(exc)
    return _error_json(_error_status_code(code), code, message, details=details)


def _site_entry_lifecycle_state(item: dict[str, Any]) -> tuple[str, str]:
    raw = str(item.get("lifecycle_state") or "").strip().lower()
    if raw:
        return raw, "field"
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    for key in ("lifecycle_state", "lifecycle", "status", "review_state"):
        raw = str(extra.get(key) or "").strip().lower()
        if raw:
            return raw, f"extra.{key}"
    if item.get("enabled") is False:
        return "disabled", "enabled"
    return "active", "compat_default"


def _attach_site_entry_lifecycle(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item or {})
    state, state_source = _site_entry_lifecycle_state(enriched)
    enriched["lifecycle_state"] = state
    review_closure = _site_entry_review_closure(enriched, state=state)
    execution_plan = _site_entry_execution_plan_preview(enriched)
    lifecycle_transition = _site_entry_lifecycle_transition_readback(
        enriched,
        state=state,
        review_closure=review_closure,
    )
    review_closure["lifecycle_transition"] = lifecycle_transition
    execution_fact = _site_entry_execution_fact(
        item=enriched,
        review_closure=review_closure,
        execution_plan=execution_plan,
    )
    execution_fact["lifecycle_transition"] = lifecycle_transition
    extra = dict(enriched.get("extra") or {}) if isinstance(enriched.get("extra"), dict) else {}
    extra["lifecycle_transition"] = lifecycle_transition
    extra["review_closure"] = review_closure
    extra["evidence_binding"] = review_closure["evidence_binding"]
    extra["execution_fact"] = execution_fact
    enriched["extra"] = extra
    lifecycle_summary = enriched.get("lifecycle_summary") if isinstance(enriched.get("lifecycle_summary"), dict) else {}
    enriched["lifecycle_summary"] = {
        **lifecycle_summary,
        "state": state,
        "enabled": bool(enriched.get("enabled", True)),
        "scope": enriched.get("scope"),
        "entry_type": enriched.get("entry_type"),
        "source": enriched.get("source"),
        "state_source": state_source,
        "review_closure_status": review_closure["status"],
        "report_source_ref": review_closure["report_source_ref"],
        "execution_fact_ref": execution_fact["fact_ref"],
        "execution_reason_code": execution_fact["reason_code"],
        "lifecycle_transition_ref": lifecycle_transition["event_ref"],
        "lifecycle_transition_contract_version": lifecycle_transition["contract_version"],
    }
    enriched["lifecycle_transition"] = lifecycle_transition
    enriched["execution_plan_preview"] = execution_plan
    enriched["review_closure"] = review_closure
    enriched["next_actions"] = review_closure["next_actions"]
    enriched["evidence_binding"] = review_closure["evidence_binding"]
    enriched["execution_fact"] = execution_fact
    return enriched


def _attach_site_entries_lifecycle(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_attach_site_entry_lifecycle(item) for item in items]


def _site_entry_execution_plan_preview(item: dict[str, Any]) -> dict[str, Any]:
    site_url = str(item.get("site_url") or item.get("template") or "").strip()
    entry_type = str(item.get("entry_type") or "domain_root").strip().lower() or "domain_root"
    source_item = {
        "item_key": f"resource_pool.site_entry.{item.get('id') or site_url}",
        "name": item.get("name") or item.get("domain") or site_url,
        "params": {
            "site_entries": [site_url] if site_url else [],
            "expected_entry_type": entry_type,
        },
        "extra": {
            "expected_entry_type": entry_type,
            "source_pool_scope": item.get("scope"),
        },
    }
    plan = build_item_execution_plan(source_item)
    plan_meta = plan.get("plan_meta") if isinstance(plan.get("plan_meta"), dict) else {}
    plan["plan_meta"] = {
        **plan_meta,
        "preview_source": "resource_pool.site_entry",
        "site_entry_scope": item.get("scope"),
        "site_entry_type": entry_type,
    }
    return plan


def _site_entry_domain_from_url(site_url: str) -> str:
    try:
        parsed = urlparse(site_url)
        domain = parsed.netloc or parsed.path.split("/", 1)[0]
        return domain.lower().removeprefix("www.")
    except Exception:
        return ""


def _site_entry_trace_source_ref(item: dict[str, Any], *, project_key: str | None = None) -> dict[str, Any]:
    site_url = str(item.get("site_url") or item.get("template") or "").strip()
    domain = str(item.get("domain") or "").strip().lower() or _site_entry_domain_from_url(site_url)
    source_ref = dict(item.get("source_ref") or {}) if isinstance(item.get("source_ref"), dict) else {}
    source_ref.setdefault("tool", "resource_pool.site_entry_review")
    if site_url:
        source_ref.setdefault("site_entry_url", site_url)
        source_ref.setdefault("url", site_url)
        source_ref.setdefault("locator", site_url)
    if domain:
        source_ref.setdefault("domain", domain)
        source_ref.setdefault("entry_domain", domain)
    if item.get("entry_type"):
        source_ref.setdefault("entry_type", item.get("entry_type"))
    if item.get("scope"):
        source_ref.setdefault("scope", item.get("scope"))
    if project_key:
        source_ref.setdefault("project_key", project_key)
    if item.get("id") is not None:
        source_ref.setdefault("site_entry_id", item.get("id"))
    return {str(key): value for key, value in source_ref.items() if value is not None and value != ""}


def _site_entry_report_source_ref(item: dict[str, Any]) -> str:
    scope = str(item.get("scope") or "effective").strip().lower() or "effective"
    entry_id = str(item.get("id") or "").strip()
    site_url = str(item.get("site_url") or item.get("template") or "").strip()
    if entry_id:
        return f"resource_pool.site_entry:{scope}:{entry_id}"
    return f"resource_pool.site_entry:{scope}:{site_url}"


def _site_entry_single_source_guard(
    *,
    site_url: str,
    source_ref: dict[str, Any],
    report_source_ref: str,
    executable_state: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    allowed_urls = [site_url] if site_url else []
    missing_reason = None if allowed_urls else "missing_site_entry_url"
    guard_reason = block_reason or missing_reason
    guarantee = bool(executable_state and len(allowed_urls) == 1 and not guard_reason)
    reason_code = None if guarantee else guard_reason or "single_source_guard_not_executable"
    return {
        "contract_version": "resource_pool.site_entry.single_source_guard.v1",
        "strict_source": True,
        "guarantee": guarantee,
        "status": "passed" if guarantee else "blocked",
        "reason_code": reason_code,
        "source_ref": source_ref,
        "report_source_ref": report_source_ref,
        "allowed_urls": allowed_urls,
        "allowed_count": len(allowed_urls),
        "blocked_reason": reason_code,
        "runner_contract": {
            "entrypoint": "ingest.source_library.run",
            "guard_field": "override_params.site_entries",
            "guarantee_basis": "ResourcePool collect action constructs exactly one site_entries URL and does not send top-level urls.",
        },
    }


def _site_entry_review_closure(
    item: dict[str, Any],
    *,
    state: str | None = None,
    project_key: str | None = None,
) -> dict[str, Any]:
    resolved_state = str(state or _site_entry_lifecycle_state(item)[0] or "active").strip().lower()
    enabled = bool(item.get("enabled", True))
    site_url = str(item.get("site_url") or item.get("template") or "").strip()
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    if extra.get("site_entry_url_missing") is True:
        site_url = ""
    entry_type = str(item.get("entry_type") or "domain_root").strip().lower() or "domain_root"
    report_source_ref = _site_entry_report_source_ref(item)
    source_ref = _site_entry_trace_source_ref(item, project_key=project_key)
    executable_state = resolved_state == "accepted" and enabled
    block_reason = None
    if not executable_state:
        if resolved_state == "disabled" or not enabled:
            block_reason = "review_disabled"
        elif resolved_state == "rejected":
            block_reason = "review_rejected"
        elif resolved_state == "needs_review":
            block_reason = "review_needs_review"
        elif resolved_state == "candidate":
            block_reason = "review_candidate"
        else:
            block_reason = "review_not_accepted"
    single_source_guard = _site_entry_single_source_guard(
        site_url=site_url,
        source_ref=source_ref,
        report_source_ref=report_source_ref,
        executable_state=executable_state,
        block_reason=block_reason,
    )
    executable = bool(executable_state and single_source_guard["guarantee"])
    if executable_state and not executable:
        block_reason = single_source_guard["blocked_reason"]

    evidence_binding = {
        "contract_version": "resource_pool.site_entry.evidence_binding.v1",
        "target": f"evidence.resource_pool.site_entry:{item.get('id') or site_url}",
        "site_entry_url": site_url,
        "source_ref": source_ref,
        "report_source_ref": report_source_ref,
        "report_refs": [report_source_ref, site_url] if site_url else [report_source_ref],
    }
    collect_payload = {
        "project_key": project_key,
        "handler_key": entry_type,
        "async_mode": True,
        "override_params": {
            "site_entries": [site_url] if site_url else [],
            "source_ref": source_ref,
            "report_source_ref": report_source_ref,
            "review_state": resolved_state,
            "single_source_guard": single_source_guard,
        },
    }
    if not project_key:
        collect_payload.pop("project_key", None)
    next_actions = [
        {
            "action": "collect_source_library_run",
            "enabled": executable,
            "blocked": not executable,
            "block_reason": block_reason,
            "method": "POST",
            "endpoint": "/api/v1/ingest/source-library/run",
            "handler_key": entry_type,
            "strict_source": single_source_guard,
            "single_source_guard": single_source_guard,
            "payload": collect_payload,
        },
        {
            "action": "copy_report_source_ref",
            "enabled": bool(report_source_ref),
            "blocked": False,
            "report_source_ref": report_source_ref,
            "source_ref": source_ref,
        },
    ]
    return {
        "contract_version": "resource_pool.site_entry.review_closure.v1",
        "status": "ready_to_collect" if executable else "blocked",
        "reason_code": "ready_to_collect" if executable else block_reason,
        "state": resolved_state,
        "enabled": enabled,
        "executable": executable,
        "blocked": not executable,
        "block_reason": block_reason,
        "site_entry_url": site_url,
        "entry_type": entry_type,
        "report_source_ref": report_source_ref,
        "source_ref": source_ref,
        "strict_source": single_source_guard,
        "single_source_guard": single_source_guard,
        "evidence_binding": evidence_binding,
        "next_actions": next_actions,
    }


def _site_entry_execution_fact(
    *,
    item: dict[str, Any],
    review_closure: dict[str, Any],
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    site_url = str(review_closure.get("site_entry_url") or item.get("site_url") or item.get("template") or "").strip()
    report_source_ref = str(review_closure.get("report_source_ref") or _site_entry_report_source_ref(item)).strip()
    source_ref = review_closure.get("source_ref") if isinstance(review_closure.get("source_ref"), dict) else {}
    guard = review_closure.get("single_source_guard") if isinstance(review_closure.get("single_source_guard"), dict) else {}
    reason_code = str(review_closure.get("reason_code") or review_closure.get("block_reason") or "").strip()
    if not reason_code:
        reason_code = "ready_to_collect" if review_closure.get("status") == "ready_to_collect" else "execution_state_unknown"
    guard_status = str(guard.get("status") or "").strip()
    if not guard_status:
        guard_status = "passed" if guard.get("guarantee") is True else "blocked"
    fact_ref = f"resource.execution_fact:{report_source_ref}" if report_source_ref else f"resource.execution_fact:{site_url}"
    return {
        "contract_version": "resource.execution_fact.v1",
        "fact_ref": fact_ref,
        "reason_code": reason_code,
        "review_state": review_closure.get("state"),
        "review_status": review_closure.get("status"),
        "guard_status": guard_status,
        "guard_reason_code": guard.get("reason_code") or guard.get("blocked_reason"),
        "blocked": bool(review_closure.get("blocked")),
        "executable": bool(review_closure.get("executable")),
        "source_refs": [
            {
                "kind": "resource_pool.site_entry",
                "report_source_ref": report_source_ref,
                "site_entry_url": site_url,
                "source_ref": source_ref,
            }
        ],
        "source_ref": source_ref,
        "report_source_ref": report_source_ref,
        "execution_plan_ref": {
            "contract_version": execution_plan.get("contract_version"),
            "item_key": execution_plan.get("item_key"),
            "site_entry_urls": execution_plan.get("site_entry_urls") if isinstance(execution_plan.get("site_entry_urls"), list) else [],
            "route_bucket_counts": execution_plan.get("route_bucket_counts") if isinstance(execution_plan.get("route_bucket_counts"), dict) else {},
        },
        "next_actions": review_closure.get("next_actions") if isinstance(review_closure.get("next_actions"), list) else [],
        "single_source_guard": guard,
        "lifecycle_transition": review_closure.get("lifecycle_transition")
        if isinstance(review_closure.get("lifecycle_transition"), dict)
        else None,
    }


def _site_entry_lifecycle_transition_readback(
    item: dict[str, Any],
    *,
    state: str,
    review_closure: dict[str, Any],
) -> dict[str, Any]:
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    existing = item.get("lifecycle_transition") if isinstance(item.get("lifecycle_transition"), dict) else {}
    if not existing and isinstance(extra.get("lifecycle_transition"), dict):
        existing = extra.get("lifecycle_transition") or {}
    lifecycle_review = extra.get("lifecycle_review") if isinstance(extra.get("lifecycle_review"), dict) else {}
    report_source_ref = str(review_closure.get("report_source_ref") or _site_entry_report_source_ref(item))
    updated_at = str(existing.get("updated_at") or lifecycle_review.get("updated_at") or "").strip() or None
    event_ref = str(existing.get("event_ref") or "").strip()
    if not event_ref:
        event_ref = _site_entry_lifecycle_transition_event_ref(
            item=item,
            to_state=state,
            updated_at=updated_at,
            report_source_ref=report_source_ref,
        )
    executable_after = bool(review_closure.get("executable"))
    transition = {
        **existing,
        "contract_version": str(existing.get("contract_version") or SITE_ENTRY_LIFECYCLE_TRANSITION_CONTRACT),
        "from_state": existing.get("from_state"),
        "to_state": str(existing.get("to_state") or state),
        "reviewer": existing.get("reviewer", lifecycle_review.get("reviewer")),
        "reason": existing.get("reason", lifecycle_review.get("reason") or lifecycle_review.get("note")),
        "updated_at": updated_at,
        "event_ref": event_ref,
        "source_ref": existing.get("source_ref")
        if isinstance(existing.get("source_ref"), dict)
        else review_closure.get("source_ref"),
        "report_source_ref": str(existing.get("report_source_ref") or report_source_ref),
        "executable_after": bool(existing.get("executable_after", executable_after)),
        "to_state_executable": bool(existing.get("to_state_executable", executable_after)),
        "executable": bool(existing.get("executable", executable_after)),
    }
    if "executable_before" in existing:
        transition["executable_before"] = bool(existing.get("executable_before"))
    return transition


def _site_entry_lifecycle_transition_event_ref(
    *,
    item: dict[str, Any],
    to_state: str,
    updated_at: str | None,
    report_source_ref: str,
) -> str:
    scope = str(item.get("scope") or "effective").strip().lower() or "effective"
    entry_id = str(item.get("id") or "").strip()
    site_url = str(item.get("site_url") or item.get("template") or "").strip()
    target = entry_id or _site_entry_domain_from_url(site_url) or "unknown"
    timestamp = str(updated_at or "").strip() or "readback"
    return f"resource_pool.site_entry.lifecycle_transition:{scope}:{target}:{to_state}:{timestamp}"


def _build_site_entry_lifecycle_transition(
    *,
    item: dict[str, Any],
    from_state: str | None,
    to_state: str,
    reviewer: str | None,
    reason: str | None,
    updated_at: str,
    review_closure: dict[str, Any],
    executable_before: bool | None,
) -> dict[str, Any]:
    report_source_ref = str(review_closure.get("report_source_ref") or _site_entry_report_source_ref(item))
    executable_after = bool(review_closure.get("executable"))
    return {
        "contract_version": SITE_ENTRY_LIFECYCLE_TRANSITION_CONTRACT,
        "from_state": from_state,
        "to_state": to_state,
        "reviewer": reviewer,
        "reason": reason,
        "updated_at": updated_at,
        "event_ref": _site_entry_lifecycle_transition_event_ref(
            item=item,
            to_state=to_state,
            updated_at=updated_at,
            report_source_ref=report_source_ref,
        ),
        "source_ref": review_closure.get("source_ref"),
        "report_source_ref": report_source_ref,
        "executable_before": bool(executable_before),
        "executable_after": executable_after,
        "to_state_executable": executable_after,
        "executable": executable_after,
    }


def _prepare_site_entry_lifecycle_extra_for_write(
    *,
    item: dict[str, Any],
    extra: dict[str, Any],
    state: str,
    from_state: str | None = None,
    reviewer: str | None = None,
    note: str | None = None,
    reason: str | None = None,
    updated_at: str | None = None,
    project_key: str | None = None,
    executable_before: bool | None = None,
) -> dict[str, Any]:
    prepared = dict(extra)
    prepared["lifecycle_state"] = state
    if state in SITE_ENTRY_REVIEW_STATES:
        prepared["review_state"] = state
    timestamp = updated_at or datetime.now(timezone.utc).isoformat()
    prepared["lifecycle_review"] = {
        **(prepared.get("lifecycle_review") if isinstance(prepared.get("lifecycle_review"), dict) else {}),
        "state": state,
        "review_state": state if state in SITE_ENTRY_REVIEW_STATES else None,
        "reviewer": reviewer,
        "note": note,
        "reason": reason,
        "updated_at": timestamp,
    }
    seed = {**item, "extra": prepared}
    review_closure = _site_entry_review_closure(seed, state=state, project_key=project_key)
    lifecycle_transition = _build_site_entry_lifecycle_transition(
        item=seed,
        from_state=from_state,
        to_state=state,
        reviewer=reviewer,
        reason=reason or note,
        updated_at=timestamp,
        review_closure=review_closure,
        executable_before=executable_before,
    )
    review_closure["lifecycle_transition"] = lifecycle_transition
    execution_fact = _site_entry_execution_fact(
        item=seed,
        review_closure=review_closure,
        execution_plan=_site_entry_execution_plan_preview(seed),
    )
    execution_fact["lifecycle_transition"] = lifecycle_transition
    prepared["lifecycle_transition"] = lifecycle_transition
    prepared["review_closure"] = review_closure
    prepared["next_actions"] = review_closure["next_actions"]
    prepared["evidence_binding"] = review_closure["evidence_binding"]
    prepared["execution_fact"] = execution_fact
    return prepared


def _normalize_site_entry_lifecycle_write_state(value: str) -> str:
    state = str(value or "").strip().lower()
    if state not in SITE_ENTRY_LIFECYCLE_STATES:
        raise ValueError(
            "lifecycle_state must be one of: "
            + ", ".join(sorted(SITE_ENTRY_LIFECYCLE_STATES))
        )
    return state


def _is_site_entries_dash_alias(request: Request) -> bool:
    return "/resource_pool/site-entries" in str(request.url.path)


def _site_entries_alias_headers(request: Request) -> dict[str, str]:
    if not _is_site_entries_dash_alias(request):
        return {}
    deprecated_path = str(request.url.path)
    replacement_path = deprecated_path.replace("/site-entries", "/site_entries", 1)
    return {
        "Deprecation": "true",
        "X-Deprecated-Endpoint": deprecated_path,
        "X-Replacement-Endpoint": replacement_path,
        "Link": f"<{replacement_path}>; rel=\"successor-version\"",
    }


def _site_entries_alias_meta(request: Request) -> ApiMetaModel | None:
    if not _is_site_entries_dash_alias(request):
        return None
    return ApiMetaModel(deprecated=SITE_ENTRIES_DASH_ALIAS_DEPRECATION)


def _get_project_key_or_error(project_key: str | None, *, request: Request | None = None) -> tuple[str | None, JSONResponse | None]:
    key = (project_key or "").strip()
    blocked_by_require_fallback = False
    if not key and request is not None:
        source = str(getattr(getattr(request, "state", None), "project_key_source", "") or "").strip().lower()
        resolved = str(getattr(getattr(request, "state", None), "project_key_resolved", "") or "").strip()
        if source in {"header", "query"} and resolved:
            key = resolved
        elif source == "fallback" and get_effective_project_key_enforcement_mode() == "require":
            blocked_by_require_fallback = True
    if not key and not blocked_by_require_fallback:
        try:
            key = (current_project_key() or "").strip()
        except RuntimeError:
            key = ""
    if not key:
        return (
            None,
            _error_json(400, ErrorCode.PROJECT_KEY_REQUIRED, "project_key is required. Please select a project first."),
        )
    return key, None


def _resolve_request_project_key(project_key: str | None, request: Request | None = None) -> str | None:
    explicit = (project_key or "").strip()
    if explicit:
        return explicit
    if request is not None:
        source = str(getattr(getattr(request, "state", None), "project_key_source", "") or "").strip().lower()
        resolved = str(getattr(getattr(request, "state", None), "project_key_resolved", "") or "").strip()
        if source in {"header", "query"} and resolved:
            return resolved
    return None


def _get_project_key_for_scope_or_error(
    scope: ScopeType | str,
    project_key: str | None,
    *,
    request: Request | None = None,
) -> tuple[str | None, JSONResponse | None]:
    resolved_scope = str(scope or "effective").strip().lower()
    if resolved_scope == "shared":
        return None, None
    explicit = _resolve_request_project_key(project_key, request=request)
    if explicit:
        return explicit, None
    return _get_project_key_or_error(None, request=request)


def _get_project_key_for_project_route_or_error(
    project_key: str | None,
    *,
    request: Request | None = None,
) -> tuple[str | None, JSONResponse | None]:
    return _get_project_key_or_error(_resolve_request_project_key(project_key, request=request), request=request)


class ExtractFromDocumentsPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project", description="Write to project or shared pool")
    filters: dict[str, Any] = Field(default_factory=dict)
    async_mode: bool = Field(default=False, description="Run via Celery")


@router.post("/extract/from-documents", response_model=ResourcePoolAnyEnvelope)
def extract_from_documents_api(payload: ExtractFromDocumentsPayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    filters = payload.filters or {}
    doc_type = filters.get("doc_type")
    state = filters.get("state")
    document_ids = filters.get("document_ids")
    limit = filters.get("limit", 500)
    limit = min(max(1, int(limit)), 5000)

    if payload.async_mode:
        task = _get_tasks_module().task_extract_resource_pool_from_documents.delay(
            project_key=project_key,
            scope=payload.scope,
            doc_type=doc_type,
            state=state,
            document_ids=document_ids,
            limit=limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=task.id,
                    async_mode=True,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    try:
        result = extract_from_documents(
            project_key=project_key,
            scope=payload.scope,
            doc_type=doc_type,
            state=state,
            document_ids=document_ids,
            limit=limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=None,
                    async_mode=False,
                    result=result,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.get("/urls", response_model=ResourcePoolAnyEnvelope)
def list_urls_api(
    request: Request,
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: str | None = Query(default=None),
    domain: str | None = Query(default=None),
):
    project_key, error = _get_project_key_for_scope_or_error(scope, project_key, request=request)
    if error:
        return error
    try:
        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source,
            domain=domain,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return JSONResponse(
            status_code=200,
            content=ok_page(
                {"items": items},
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


class CaptureEnablePayload(BaseModel):
    project_key: str | None = Field(default=None)
    scope: Literal["project", "shared"] = Field(default="project")
    job_types: list[str] = Field(..., min_length=1)
    enabled: bool = Field(default=True)


class CaptureFromTasksPayload(BaseModel):
    project_key: str | None = Field(default=None)
    scope: Literal["project", "shared"] = Field(default="project")
    task_ids: list[int] | None = Field(default=None)
    job_type: str | None = Field(default=None)
    since: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)
    async_mode: bool = Field(default=False)


class ImportOpenSourcePresetPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project")
    pack_key: str = Field(..., description="Preset pack key")
    enabled: bool = Field(default=True)
    extra_tags: list[str] = Field(default_factory=list)


@router.get(
    "/open-source-presets",
    operation_id="resource_pool_list_open_source_presets",
    response_model=ResourcePoolAnyEnvelope,
)
def list_open_source_presets_api():
    return JSONResponse(status_code=200, content=ok({"items": list_open_source_preset_packs()}))


@router.post(
    "/import/open-source-presets",
    operation_id="resource_pool_import_open_source_presets",
    response_model=ResourcePoolAnyEnvelope,
)
def import_open_source_presets_api(payload: ImportOpenSourcePresetPayload, request: Request):
    project_key, error = _get_project_key_for_scope_or_error(payload.scope, payload.project_key, request=request)
    if error and payload.scope == "project":
        return error
    try:
        result = import_open_source_preset_pack(
            pack_key=payload.pack_key,
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            enabled=payload.enabled,
            extra_tags=payload.extra_tags,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "pack_key": result.pack_key,
                    "title": result.title,
                    "scope": result.scope,
                    "project_key": result.project_key,
                    "inserted_or_updated": result.inserted_or_updated,
                    "count": len(result.inserted_or_updated),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return _json_from_exception(exc)


@router.post("/capture/enable", response_model=ResourcePoolAnyEnvelope)
def capture_enable_api(payload: CaptureEnablePayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    try:
        result = upsert_capture_config(
            project_key=project_key,
            job_types=payload.job_types,
            scope=payload.scope,
            enabled=payload.enabled,
        )
        return JSONResponse(status_code=200, content=ok(result))
    except Exception as exc:
        return _json_from_exception(exc)


@router.post("/capture/from-tasks", response_model=ResourcePoolAnyEnvelope)
def capture_from_tasks_api(payload: CaptureFromTasksPayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    if payload.async_mode:
        task = _get_tasks_module().task_extract_resource_pool_from_tasks.delay(
            project_key=project_key,
            scope=payload.scope,
            task_ids=payload.task_ids,
            job_type=payload.job_type,
            since=payload.since,
            limit=payload.limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=task.id,
                    async_mode=True,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    try:
        result = extract_from_tasks(
            project_key=project_key,
            scope=payload.scope,
            task_ids=payload.task_ids,
            job_type=payload.job_type,
            since=payload.since,
            limit=payload.limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                task_result_response(
                    task_id=None,
                    async_mode=False,
                    result=result,
                    params={"project_key": project_key, "scope": payload.scope},
                )
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


class UpsertSiteEntryPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier (required for project scope)")
    scope: Literal["project", "shared"] = Field(default="project", description="Write to project or shared pool")
    site_url: str = Field(..., min_length=1, description="Site entry URL (domain_root/rss/sitemap/search template root)")
    entry_type: str = Field(default="domain_root", description="domain_root|rss|sitemap|search_template|official_api")
    template: str | None = Field(default=None, description="Optional template for search_template etc.")
    name: str | None = Field(default=None)
    domain: str | None = Field(default=None)
    capabilities: dict[str, Any] | None = Field(default=None)
    source: str = Field(default="manual")
    source_ref: dict[str, Any] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    enabled: bool = Field(default=True)
    extra: dict[str, Any] | None = Field(default=None)


class SiteEntryLifecyclePatchPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier (required for project scope)")
    scope: Literal["project", "shared"] = Field(default="project", description="Write target scope")
    site_url: str = Field(..., min_length=1, description="Site entry URL to update")
    lifecycle_state: str = Field(..., min_length=1, description="accepted|rejected|needs_review|disabled|candidate|active")
    reviewer: str | None = Field(default=None)
    review_note: str | None = Field(default=None)
    review_reason: str | None = Field(default=None)
    enabled: bool | None = Field(default=None, description="Optional explicit enabled override")
    extra_patch: dict[str, Any] | None = Field(default=None, description="Optional extra metadata merge")


@router.get(
    "/site_entries",
    operation_id="resource_pool_list_site_entries",
    response_model=ResourcePoolAnyEnvelope,
)
@router.get(
    "/site-entries",
    operation_id="resource_pool_list_site_entries_dash",
    response_model=ResourcePoolAnyEnvelope,
)
def list_site_entries_api(
    request: Request,
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    domain: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
):
    project_key, error = _get_project_key_for_scope_or_error(scope, project_key, request=request)
    if error:
        return error
    try:
        items, total = list_site_entries(
            scope=scope,
            project_key=project_key,
            domain=domain,
            entry_type=entry_type,
            enabled=enabled,
            page=page,
            page_size=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return JSONResponse(
            status_code=200,
            content=ok_page(
                {"items": _attach_site_entries_lifecycle(items)},
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                meta=_site_entries_alias_meta(request),
            ),
            headers=_site_entries_alias_headers(request),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.get(
    "/site_entries/grouped",
    operation_id="resource_pool_group_site_entries",
    response_model=ResourcePoolAnyEnvelope,
)
@router.get(
    "/site-entries/grouped",
    operation_id="resource_pool_group_site_entries_dash",
    response_model=ResourcePoolAnyEnvelope,
)
def group_site_entries_api(
    request: Request,
    project_key: str | None = Query(default=None),
    scope: ScopeType = Query(default="effective"),
    enabled: bool | None = Query(default=True),
):
    project_key, error = _get_project_key_for_scope_or_error(scope, project_key, request=request)
    if error:
        return error
    try:
        page = 1
        page_size = 100
        by_entry_type: dict[str, dict[str, Any]] = {}
        while True:
            items, total = list_site_entries(
                scope=scope,
                project_key=project_key,
                enabled=enabled,
                page=page,
                page_size=page_size,
            )
            for row in _attach_site_entries_lifecycle(items):
                et = str(row.get("entry_type") or "domain_root").strip().lower() or "domain_root"
                bucket = by_entry_type.setdefault(et, {"count": 0, "sample_urls": [], "lifecycle_summary": {}})
                bucket["count"] += 1
                state = str(row.get("lifecycle_state") or "active").strip().lower() or "active"
                lifecycle_summary = bucket["lifecycle_summary"]
                lifecycle_summary[state] = int(lifecycle_summary.get(state) or 0) + 1
                su = str(row.get("site_url") or "").strip()
                if su and len(bucket["sample_urls"]) < 5:
                    bucket["sample_urls"].append(su)
            if not items or page * page_size >= int(total or 0):
                break
            page += 1
        return JSONResponse(
            status_code=200,
            content=ok(
                {"by_entry_type": by_entry_type, "scope": scope, "project_key": project_key},
                meta=_site_entries_alias_meta(request),
            ),
            headers=_site_entries_alias_headers(request),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.post(
    "/site_entries",
    operation_id="resource_pool_upsert_site_entry",
    response_model=ResourcePoolAnyEnvelope,
)
@router.post(
    "/site-entries",
    operation_id="resource_pool_upsert_site_entry_dash",
    response_model=ResourcePoolAnyEnvelope,
)
def upsert_site_entry_api(payload: UpsertSiteEntryPayload, request: Request):
    project_key, error = _get_project_key_for_scope_or_error(payload.scope, payload.project_key, request=request)
    if error and payload.scope == "project":
        return error
    try:
        extra = dict(payload.extra or {})
        lifecycle_state = _site_entry_lifecycle_state({"enabled": payload.enabled, "extra": extra})[0]
        should_persist_lifecycle_evidence = bool(
            extra.get("lifecycle_state")
            or extra.get("review_state")
            or extra.get("lifecycle_transition")
            or extra.get("lifecycle_review")
            or lifecycle_state in SITE_ENTRY_REVIEW_STATES
        )
        if should_persist_lifecycle_evidence:
            seed = {
                "site_url": payload.site_url,
                "entry_type": payload.entry_type,
                "template": payload.template,
                "name": payload.name,
                "domain": payload.domain,
                "capabilities": payload.capabilities if isinstance(payload.capabilities, dict) else {},
                "source": payload.source,
                "source_ref": payload.source_ref if isinstance(payload.source_ref, dict) else {},
                "tags": payload.tags if isinstance(payload.tags, list) else [],
                "enabled": payload.enabled,
                "scope": payload.scope,
            }
            extra = _prepare_site_entry_lifecycle_extra_for_write(
                item=seed,
                extra=extra,
                state=lifecycle_state,
                from_state=None,
                project_key=project_key if payload.scope == "project" else None,
                executable_before=None,
            )
        item = upsert_site_entry(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            site_url=payload.site_url,
            entry_type=payload.entry_type,
            template=payload.template,
            name=payload.name,
            domain=payload.domain,
            capabilities=payload.capabilities,
            source=payload.source,
            source_ref=payload.source_ref,
            tags=payload.tags,
            enabled=payload.enabled,
            extra=extra or payload.extra,
        )
        return JSONResponse(
            status_code=200,
            content=ok(_attach_site_entry_lifecycle(item), meta=_site_entries_alias_meta(request)),
            headers=_site_entries_alias_headers(request),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.patch(
    "/site_entries/lifecycle",
    operation_id="resource_pool_patch_site_entry_lifecycle",
    response_model=ResourcePoolAnyEnvelope,
)
@router.patch(
    "/site-entries/lifecycle",
    operation_id="resource_pool_patch_site_entry_lifecycle_dash",
    response_model=ResourcePoolAnyEnvelope,
)
def patch_site_entry_lifecycle_api(payload: SiteEntryLifecyclePatchPayload, request: Request):
    project_key, error = _get_project_key_for_scope_or_error(payload.scope, payload.project_key, request=request)
    if error and payload.scope == "project":
        return error
    try:
        lifecycle_state = _normalize_site_entry_lifecycle_write_state(payload.lifecycle_state)
        existing = get_site_entry_by_url(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            site_url=payload.site_url,
        )
        if not existing:
            return _error_json(
                404,
                ErrorCode.NOT_FOUND,
                "site entry not found",
                details={"site_url": payload.site_url, "scope": payload.scope},
            )

        previous_state = _site_entry_lifecycle_state(existing)[0]
        existing_site_url = str(existing.get("site_url") or "").strip()
        before_seed = {
            **existing,
            "site_url": existing_site_url,
            "entry_type": str(existing.get("entry_type") or "domain_root"),
            "source_ref": existing.get("source_ref") if isinstance(existing.get("source_ref"), dict) else {},
            "scope": payload.scope,
        }
        before_closure = _site_entry_review_closure(
            before_seed,
            state=previous_state,
            project_key=project_key if payload.scope == "project" else None,
        )
        extra = dict(existing.get("extra") or {})
        if isinstance(payload.extra_patch, dict):
            extra.update(payload.extra_patch)
        if existing_site_url:
            extra.pop("site_entry_url_missing", None)
        else:
            extra["site_entry_url_missing"] = True

        enabled = bool(existing.get("enabled", True)) if payload.enabled is None else bool(payload.enabled)
        if lifecycle_state == "disabled":
            enabled = False
        elif lifecycle_state == "accepted" and payload.enabled is None:
            enabled = True

        closure_seed = {
            **existing,
            "site_url": existing_site_url or payload.site_url,
            "entry_type": str(existing.get("entry_type") or "domain_root"),
            "source_ref": existing.get("source_ref") if isinstance(existing.get("source_ref"), dict) else {},
            "enabled": enabled,
            "scope": payload.scope,
            "extra": extra,
        }
        extra = _prepare_site_entry_lifecycle_extra_for_write(
            item=closure_seed,
            extra=extra,
            state=lifecycle_state,
            from_state=previous_state,
            reviewer=payload.reviewer,
            note=payload.review_note,
            reason=payload.review_reason,
            project_key=project_key if payload.scope == "project" else None,
            executable_before=bool(before_closure.get("executable")),
        )

        item = upsert_site_entry(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            site_url=existing_site_url or payload.site_url,
            entry_type=str(existing.get("entry_type") or "domain_root"),
            template=existing.get("template"),
            name=existing.get("name"),
            domain=existing.get("domain"),
            capabilities=existing.get("capabilities") if isinstance(existing.get("capabilities"), dict) else {},
            source=str(existing.get("source") or "manual"),
            source_ref=existing.get("source_ref") if isinstance(existing.get("source_ref"), dict) else {},
            tags=existing.get("tags") if isinstance(existing.get("tags"), list) else [],
            enabled=enabled,
            extra=extra,
        )
        return JSONResponse(
            status_code=200,
            content=ok(_attach_site_entry_lifecycle(item), meta=_site_entries_alias_meta(request)),
            headers=_site_entries_alias_headers(request),
        )
    except Exception as exc:
        return _json_from_exception(exc)


class DiscoverSiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    url_scope: ScopeType = Field(default="effective", description="shared|project|effective, read urls from")
    target_scope: Literal["shared", "project"] = Field(default="project", description="write target scope for site entries")
    domain: str | None = Field(default=None)
    limit_domains: int = Field(default=50, ge=1, le=500)
    probe_timeout: float = Field(default=8.0, ge=1.0, le=60.0)
    include_link_alternate: bool = Field(default=True)
    sitemap_paths: list[str] | None = Field(default=None, description="Optional override paths for sitemap probing")
    rss_paths: list[str] | None = Field(default=None, description="Optional override paths for rss probing")
    allow_domains: list[str] | None = Field(default=None, description="Optional allowlist of domains")
    deny_domains: list[str] | None = Field(default=None, description="Optional denylist of domains")
    dry_run: bool = Field(default=True, description="If true, do not write")
    write: bool = Field(default=False, description="If true, persist discovered candidates")
    run_auto_classify: bool = Field(default=False, description="If true, run classify on domain_root without sitemap/rss")
    use_llm: bool = Field(default=False, description="If true and run_auto_classify, use LLM for classification")
    async_mode: bool = Field(default=False, description="Run discovery in background (Celery)")
    batch_size: int = Field(default=20, ge=1, le=100, description="Domains per batch when async_mode=true")
    simplify_pool_first: bool = Field(default=True, description="Simplify duplicate site entries before async batched discovery")


class SimplifySiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project")
    domain: str | None = Field(default=None, description="Optional domain filter")
    dry_run: bool = Field(default=True, description="Preview only; do not delete duplicates")


class DiscoverSearchContractPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    scope: Literal["project", "shared"] = Field(default="project", description="write target scope for site entry")
    site_url: str = Field(..., min_length=1)
    query_terms: list[str] | str = Field(..., description="Probe query terms")
    suffixes: list[str] | None = Field(default=None, description="Optional controlled suffix variants")
    max_pages: int = Field(default=1, ge=1, le=10)
    probe_timeout: float = Field(default=6.0, ge=1.0, le=30.0)
    persist: bool = Field(default=True)


@router.post(
    "/discover/search-contract",
    operation_id="resource_pool_discover_search_contract",
    response_model=ResourcePoolAnyEnvelope,
)
def discover_search_contract_api(payload: DiscoverSearchContractPayload, request: Request):
    project_key, error = _get_project_key_for_scope_or_error(payload.scope, payload.project_key, request=request)
    if error and payload.scope == "project":
        return error
    try:
        result = discover_search_contract(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            site_url=payload.site_url,
            query_terms=payload.query_terms,
            suffixes=payload.suffixes,
            max_pages=payload.max_pages,
            probe_timeout=payload.probe_timeout,
            persist=payload.persist,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "site_url": result.site_url,
                    "domain": result.domain,
                    "entry_type": result.entry_type,
                    "templates_tried": result.templates_tried,
                    "suffixes_tried": result.suffixes_tried,
                    "best_template": result.best_template,
                    "best_suffix": result.best_suffix,
                    "best_score": result.best_score,
                    "probe_rows": [
                        {
                            "template": row.template,
                            "query_text": row.query_text,
                            "candidate_count": row.candidate_count,
                            "selected_count": row.selected_count,
                            "search_service": row.search_service,
                            "score": row.score,
                        }
                        for row in result.probe_rows
                    ],
                    "persisted_entry": result.persisted_entry,
                }
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.post(
    "/discover/site-entries",
    operation_id="resource_pool_discover_site_entries",
    response_model=ResourcePoolAnyEnvelope,
)
def discover_site_entries_api(payload: DiscoverSiteEntriesPayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    try:
        # Optional: merge ingest_config policy (payload wins)
        policy = (get_ingest_config(project_key, "site_entry_discovery_policy") or {}).get("payload") or {}
        url_scope = payload.url_scope or policy.get("url_scope") or "effective"
        target_scope = payload.target_scope or policy.get("target_scope") or "project"
        limit_domains = payload.limit_domains if payload.limit_domains is not None else int(policy.get("limit_domains") or 50)
        probe_timeout = payload.probe_timeout if payload.probe_timeout is not None else float(policy.get("probe_timeout") or 8.0)
        include_link_alternate = (
            payload.include_link_alternate
            if payload.include_link_alternate is not None
            else bool(policy.get("include_link_alternate", True))
        )
        sitemap_paths = payload.sitemap_paths if payload.sitemap_paths is not None else policy.get("sitemap_paths")
        rss_paths = payload.rss_paths if payload.rss_paths is not None else policy.get("rss_paths")
        allow_domains = payload.allow_domains if payload.allow_domains is not None else policy.get("allow_domains")
        deny_domains = payload.deny_domains if payload.deny_domains is not None else policy.get("deny_domains")
        run_auto_classify = payload.run_auto_classify if payload.run_auto_classify is not None else bool(policy.get("run_auto_classify", False))
        use_llm = payload.use_llm if payload.use_llm is not None else bool(policy.get("use_llm", False))

        if payload.async_mode:
            task = _get_tasks_module().task_discover_site_entries_batched.delay(
                project_key=project_key,
                url_scope=url_scope,
                target_scope=target_scope,
                domain=payload.domain,
                limit_domains=limit_domains,
                probe_timeout=probe_timeout,
                include_link_alternate=include_link_alternate,
                sitemap_paths=sitemap_paths,
                rss_paths=rss_paths,
                allow_domains=allow_domains,
                deny_domains=deny_domains,
                run_auto_classify=run_auto_classify,
                use_llm=use_llm,
                write=bool(payload.write) and not bool(payload.dry_run),
                batch_size=payload.batch_size,
                simplify_pool_first=bool(payload.simplify_pool_first),
            )
            return JSONResponse(
                status_code=200,
                content=ok(
                    task_result_response(
                        task_id=task.id,
                        async_mode=True,
                        params={
                            "project_key": project_key,
                            "url_scope": url_scope,
                            "target_scope": target_scope,
                            "limit_domains": limit_domains,
                            "run_auto_classify": run_auto_classify,
                            "use_llm": use_llm,
                            "batch_size": payload.batch_size,
                            "simplify_pool_first": bool(payload.simplify_pool_first),
                        },
                    )
                ),
            )

        result = discover_site_entries_from_urls(
            project_key=project_key,
            url_scope=url_scope,
            target_scope=target_scope,
            domain=payload.domain,
            limit_domains=limit_domains,
            probe_timeout=probe_timeout,
            include_link_alternate=include_link_alternate,
            sitemap_paths=sitemap_paths,
            rss_paths=rss_paths,
            allow_domains=allow_domains,
            deny_domains=deny_domains,
            run_auto_classify=run_auto_classify,
            use_llm=use_llm,
        )
        write_result = None
        do_write = bool(payload.write) and not bool(payload.dry_run)
        if do_write:
            wr = write_discovered_site_entries(
                project_key=project_key,
                candidates=result.candidates,
                target_scope=target_scope,
                dry_run=False,
            )
            write_result = {
                "upserted": wr.upserted,
                "skipped": wr.skipped,
                "errors": wr.errors,
            }
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "domains_scanned": result.domains_scanned,
                    "candidates_count": len(result.candidates),
                    "probe_stats": result.probe_stats,
                    "errors": result.errors,
                    "write_result": write_result,
                    "candidates": result.candidates,
                }
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.post(
    "/site_entries/simplify",
    operation_id="resource_pool_simplify_site_entries",
    response_model=ResourcePoolAnyEnvelope,
)
def simplify_site_entries_api(payload: SimplifySiteEntriesPayload, request: Request):
    project_key, error = _get_project_key_for_scope_or_error(payload.scope, payload.project_key, request=request)
    if error and payload.scope == "project":
        return error
    try:
        result = simplify_site_entries(
            scope=payload.scope,
            project_key=project_key if payload.scope == "project" else None,
            domain=payload.domain,
            dry_run=payload.dry_run,
        )
        return JSONResponse(status_code=200, content=ok(result))
    except Exception as exc:
        return _json_from_exception(exc)


class RecommendSiteEntryPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    site_url: str = Field(..., min_length=1, description="Site entry URL to classify")
    entry_type: str | None = Field(default=None, description="Optional known entry_type")
    template: str | None = Field(default=None, description="Optional template for search_template")
    use_llm: bool = Field(default=False, description="Whether to call LLM when rules cannot determine")


class BatchRecommendSiteEntriesPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    entries: list[dict[str, Any]] = Field(default_factory=list, description="Rows: {site_url, entry_type?, template?}")
    use_llm: bool = Field(default=True, description="Whether to use LLM for unresolved rows")
    llm_batch_size: int = Field(default=20, ge=1, le=100, description="Batch size for one LLM request")


@router.post(
    "/site_entries/recommend",
    operation_id="resource_pool_recommend_site_entry",
    response_model=ResourcePoolAnyEnvelope,
)
def recommend_site_entry_api(payload: RecommendSiteEntryPayload):
    """Recommend channel_key and entry_type for a site entry. Rule-first, LLM fallback when use_llm=True."""
    try:
        rec = classify_site_entry(
            site_url=payload.site_url,
            entry_type=payload.entry_type,
            template=payload.template,
            use_llm=payload.use_llm,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "channel_key": rec.channel_key,
                    "entry_type": rec.entry_type,
                    "template": rec.template,
                    "validated": rec.validated,
                    "source": rec.source,
                    "capabilities": rec.capabilities or {},
                }
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.post(
    "/site_entries/recommend-batch",
    operation_id="resource_pool_recommend_site_entries_batch",
    response_model=ResourcePoolAnyEnvelope,
)
def recommend_site_entries_batch_api(payload: BatchRecommendSiteEntriesPayload):
    """Batch recommend channel/entry_type/template (+ capability/symbol-ready hints) for site entries."""
    try:
        rows = []
        for i, row in enumerate(payload.entries or []):
            if not isinstance(row, dict):
                continue
            site_url = str(row.get("site_url") or "").strip()
            if not site_url:
                continue
            rows.append(
                {
                    "index": i,
                    "site_url": site_url,
                    "entry_type": row.get("entry_type"),
                    "template": row.get("template"),
                }
            )
        result = classify_site_entries_batch(rows, use_llm=payload.use_llm, llm_batch_size=payload.llm_batch_size)
        normalized = [
            {
                "index": item.get("index"),
                "site_url": item.get("site_url"),
                "entry_type": item.get("entry_type"),
                "channel_key": item.get("channel_key"),
                "template": item.get("template"),
                "validated": item.get("validated"),
                "source": item.get("source"),
                "capabilities": item.get("capabilities") or {},
                "symbol_suggestion": item.get("symbol_suggestion"),
            }
            for item in result
        ]
        return JSONResponse(status_code=200, content=ok({"items": normalized, "count": len(normalized)}))
    except Exception as exc:
        return _json_from_exception(exc)


class UnifiedSearchPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    item_key: str = Field(..., min_length=1, max_length=128)
    query_terms: list[str] = Field(default_factory=list, description="Search terms (merged into {{q}})")
    max_candidates: int = Field(default=200, ge=1, le=2000)
    probe_timeout: float = Field(default=10.0, ge=1.0, le=60.0)
    write_to_pool: bool = Field(default=False)
    pool_scope: Literal["project", "shared"] = Field(default="project")
    auto_ingest: bool = Field(default=False, description="After write_to_pool, fetch URLs and store as Documents")
    ingest_limit: int = Field(default=10, ge=1, le=50)


class SourceLibraryCollectPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project identifier")
    item_key: str = Field(..., min_length=1, max_length=128)
    query_terms: list[str] = Field(default_factory=list, description="User keywords or normalized base information")
    max_candidates: int = Field(default=500, ge=1, le=2000)
    pool_scope: Literal["project", "shared"] = Field(default="project")
    probe_timeout: float = Field(default=10.0, ge=1.0, le=60.0)
    ingest_limit: int = Field(default=100, ge=1, le=500)
    allow_term_fallback: bool = Field(default=True)


def _source_library_collect_response(result) -> dict[str, Any]:
    ingest_result = result.ingest_result if isinstance(result.ingest_result, dict) else {}
    written = result.written if isinstance(result.written, dict) else {}
    inserted = int(ingest_result.get("inserted") or 0)
    inserted_valid = int(ingest_result.get("inserted_valid") or inserted or 0)
    queued = int(ingest_result.get("queued") or 0)
    rejected_count = int(ingest_result.get("rejected_count") or 0)
    skipped = int(ingest_result.get("skipped") or 0)
    candidates = list(result.candidates or [])
    site_entries_used = list(result.site_entries_used or [])
    return {
        "contract_version": "source_library.keyword_collect.v1",
        "lifecycle_summary": {
            "state": "ready" if (inserted_valid + queued) > 0 else "not_ready",
            "candidates_found": len(candidates),
            "materialized_urls": int(written.get("urls_new") or written.get("new") or 0),
            "documents_inserted_valid": inserted_valid,
            "documents_queued": queued,
            "errors": len(result.errors or []),
        },
        "item_key": result.item_key,
        "query_terms": result.query_terms,
        "site_entries_used": site_entries_used,
        "candidates": candidates,
        "written": written or None,
        "ingest_result": result.ingest_result,
        "errors": result.errors,
        "summary": {
            "site_entries_used": len(site_entries_used),
            "candidates_found": len(candidates),
            "urls_written_new": int(written.get("urls_new") or written.get("new") or 0),
            "urls_written_skipped": int(written.get("urls_skipped") or written.get("duplicate") or 0),
            "documents_inserted": inserted,
            "documents_inserted_valid": inserted_valid,
            "documents_queued": queued,
            "documents_skipped": skipped,
            "documents_rejected": rejected_count,
            "ready_for_project_flows": (inserted_valid + queued) > 0,
        },
        "pipeline": {
            "entrypoint": "resource_pool.source_library.collect",
            "source_search": "resource_pool.unified_search_by_item",
            "candidate_materialization": "resource_pool.urls",
            "document_ingest": "ingest.url_pool.source_library_frontdoor",
            "structured_extraction": "frontdoor.unified.structured.v1",
            "project_downstream": ["documents", "writing_materials", "graph_projection", "llm_report_sources"],
        },
    }


@router.post(
    "/unified-search",
    operation_id="resource_pool_unified_search",
    response_model=ResourcePoolAnyEnvelope,
)
def unified_search_api(payload: UnifiedSearchPayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    try:
        result = unified_search_by_item(
            project_key=project_key,
            item_key=payload.item_key,
            query_terms=payload.query_terms or [],
            max_candidates=payload.max_candidates,
            write_to_pool=bool(payload.write_to_pool),
            pool_scope=payload.pool_scope,
            probe_timeout=payload.probe_timeout,
            auto_ingest=bool(payload.auto_ingest),
            ingest_limit=payload.ingest_limit,
        )
        return JSONResponse(
            status_code=200,
            content=ok(
                {
                    "item_key": result.item_key,
                    "query_terms": result.query_terms,
                    "site_entries_used": result.site_entries_used,
                    "candidates": result.candidates,
                    "written": result.written,
                    "ingest_result": result.ingest_result,
                    "errors": result.errors,
                }
            ),
        )
    except Exception as exc:
        return _json_from_exception(exc)


@router.post(
    "/source-library/collect",
    operation_id="resource_pool_source_library_collect",
    response_model=ResourcePoolAnyEnvelope,
)
def source_library_collect_api(payload: SourceLibraryCollectPayload, request: Request):
    project_key, error = _get_project_key_for_project_route_or_error(payload.project_key, request=request)
    if error:
        return error
    try:
        result = unified_search_by_item(
            project_key=project_key,
            item_key=payload.item_key,
            query_terms=payload.query_terms or [],
            max_candidates=payload.max_candidates,
            write_to_pool=True,
            pool_scope=payload.pool_scope,
            probe_timeout=payload.probe_timeout,
            auto_ingest=True,
            ingest_limit=payload.ingest_limit,
            enable_extraction=True,
            allow_term_fallback=payload.allow_term_fallback,
        )
        return JSONResponse(status_code=200, content=ok(_source_library_collect_response(result)))
    except Exception as exc:
        return _json_from_exception(exc)


def _get_tasks_module():
    from ..services import tasks as m
    return m
