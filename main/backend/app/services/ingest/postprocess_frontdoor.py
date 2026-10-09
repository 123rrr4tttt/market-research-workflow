from __future__ import annotations

from copy import deepcopy
from typing import TypedDict, TypeGuard
from uuid import uuid4

from ..extraction.application import ExtractionApplicationService
from .canary_handoff import build_single_url_canary_handoff
from .cleanup_executor import execute_frontdoor_cleanup
from .content_cleaner import clean_frontdoor_document_candidate
from .content_extraction import apply_main_content_extraction, is_extracted_pdf_body
from .frontdoor_ingress import CONTRACT_VERSION as INGRESS_CONTRACT_VERSION
from .gate_reason_codes import normalize_reason_code
from .guardrail_rollout import resolve_ingest_guardrail_rollout_decision
from .light_filter import evaluate_light_filter, normalize_light_filter_options
from .meaningful_gate import build_gateplus_snapshot, content_quality_check, url_policy_check
from .retry_policy import build_retry_observability
from .structured_extraction import build_structured_summary, extract_structured_enriched_safe
from .terminal_compat import apply_terminal_compat
from .terminal_normalizer import build_terminal_ingest_payload
from .terminal_writer import persist_terminal_document
from ...settings.config import settings


_EXTRACTION_APP = ExtractionApplicationService()

PostprocessObject = dict[str, object]


class PostprocessDispatchPlan(TypedDict):
    run_extraction: bool
    run_writer: bool


class PostprocessData(TypedDict):
    admission: str
    cleaning: PostprocessObject
    cleanup_execution: PostprocessObject
    content_extraction: PostprocessObject
    quality_assessment: PostprocessObject
    quality_gates: PostprocessObject
    canary_handoff: PostprocessObject
    cleanup_actions: list[str]
    normalized_payload: PostprocessObject
    raw_snapshot_ref: str | None
    rollback_token: str | None
    dispatch_plan: PostprocessDispatchPlan
    writer_result: PostprocessObject | None
    ingress_payload: PostprocessObject


class PostprocessMeta(TypedDict, total=False):
    trace_id: str | None
    ingest_id: str
    attempt: int
    reason_code: str
    retryable: bool
    stages: list[str]
    retry_observability: object


class PostprocessEnvelope(TypedDict):
    status: str
    data: PostprocessData
    error: PostprocessObject | None
    meta: PostprocessMeta


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return bool(default)
    return bool(value)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_view(value: object) -> PostprocessObject:
    if not _is_object_dict(value):
        return {}
    view: PostprocessObject = {}
    for key, item in value.items():
        view[str(key)] = deepcopy(item)
    return view


def _string_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [str(item) for item in value]


def _object_list(value: object) -> list[object]:
    if not _is_object_list(value):
        return []
    return list(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _frontdoor_gate_config(*, terminal_context: dict[str, object] | None = None) -> dict[str, object]:
    context = _object_view(terminal_context)
    request_gate_config = _object_view(context.get("meaningful_gate_config"))

    settings_enabled = bool(getattr(settings, "ingest_enable_strict_gate", False))
    request_enabled = _coerce_bool(request_gate_config.get("enable_strict_gate"), False)
    # Source token retained for the Wave9 checker: terminal_context.strict_mode.
    strict_mode_enabled = _coerce_bool(context.get("strict_mode"), False)
    project_key = str(context.get("project_key") or "").strip() or None
    source_mode = str(context.get("source_mode") or "").strip().lower()
    entrypoint = str(context.get("ingestion_entrypoint") or "").strip().lower()
    capability_profile = _object_view(context.get("capability_profile"))
    rollout_eligible = bool(
        source_mode == "url_execution"
        or entrypoint in {"ingest.url_pool", "ingest.source_library.run"}
        or capability_profile.get("source_library_collect_only")
    )
    rollout_decision = resolve_ingest_guardrail_rollout_decision(
        project_key=project_key,
        settings_enabled=settings_enabled,
        request_enabled=request_enabled,
        strict_mode_enabled=strict_mode_enabled,
        rollout_eligible=rollout_eligible,
    )

    raw_min_len = request_gate_config.get(
        "min_semantic_len",
        getattr(settings, "ingest_min_semantic_len", 500),
    )
    return {
        "enable_strict_gate": bool(rollout_decision.enable_strict_gate),
        "strict_gate_source": str(rollout_decision.strict_gate_source),
        "min_semantic_len": _safe_int(raw_min_len) or 500,
        "guardrail_rollout": rollout_decision.to_dict(),
    }


def run_postprocess_frontdoor(
    *,
    ingress_envelope: object,
    run_writer: bool | None = None,
) -> PostprocessEnvelope:
    envelope: PostprocessEnvelope = {
        "status": "ok",
        "data": {
            "admission": "reject",
            "cleaning": {},
            "cleanup_execution": {},
            "content_extraction": {},
            "quality_assessment": {},
            "quality_gates": {},
            "canary_handoff": {},
            "cleanup_actions": [],
            "normalized_payload": {},
            "raw_snapshot_ref": None,
            "rollback_token": None,
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
            },
            "writer_result": None,
            "ingress_payload": _object_view(ingress_envelope),
        },
        "error": None,
        "meta": {
            "trace_id": None,
            "ingest_id": f"fd-{uuid4().hex[:16]}",
            "attempt": 1,
            "reason_code": "ok",
            "retryable": False,
            "stages": [],
        },
    }
    _stage(envelope, "received")
    error = _validate_ingress(ingress_envelope)
    if error is not None:
        return _fail(envelope, reason_code="invalid_ingress", error=error, retryable=False)

    ingress = _object_view(ingress_envelope)
    ingress_meta = _object_view(ingress.get("meta"))
    envelope["meta"]["trace_id"] = _optional_str(ingress_meta.get("trace_id"))
    envelope["meta"]["reason_code"] = str(ingress_meta.get("reason_code") or "ok")
    envelope["meta"]["retryable"] = bool(ingress_meta.get("retryable"))
    _stage(envelope, "contract_validated")

    collection_payload = _object_view(ingress.get("collection_payload"))
    document_candidate = _object_view(collection_payload.get("document_candidate"))
    dispatch_plan = _object_view(collection_payload.get("dispatch_plan"))
    records = collection_payload.get("records")
    extraction_plan = _object_view(collection_payload.get("extraction_plan"))
    effective_run_writer = bool(dispatch_plan.get("run_writer", True if run_writer is None else run_writer))
    effective_run_extraction = bool(dispatch_plan.get("run_extraction", True))
    admission = "accept"
    if document_candidate:
        if not str(document_candidate.get("uri") or "").strip() and not str(document_candidate.get("content") or "").strip():
            admission = "reject"
    elif isinstance(records, list) and records:
        admission = "defer"
        effective_run_writer = False
        effective_run_extraction = False
    else:
        admission = "reject"
        effective_run_writer = False
        effective_run_extraction = False

    envelope["data"]["admission"] = admission
    envelope["data"]["dispatch_plan"] = {
        "run_extraction": effective_run_extraction,
        "run_writer": effective_run_writer,
    }
    envelope["data"]["raw_snapshot_ref"] = str(ingress_meta.get("payload_hash") or "") or None
    _stage(envelope, "admission_decided")

    if admission != "accept":
        envelope["meta"]["reason_code"] = "deferred" if admission == "defer" else "rejected"
        return envelope

    terminal_context = _object_view(collection_payload.get("terminal_context"))
    if ingress.get("project_key") and not terminal_context.get("project_key"):
        terminal_context["project_key"] = ingress.get("project_key")
    document_candidate, extraction_profile = apply_main_content_extraction(document_candidate)
    terminal_context["content_extraction"] = _object_view(extraction_profile)
    envelope["data"]["content_extraction"] = deepcopy(extraction_profile)
    _stage(envelope, "content_extracted")
    document_candidate, cleaning_result = clean_frontdoor_document_candidate(document_candidate)
    terminal_context["frontdoor_cleaning"] = _object_view(cleaning_result)
    envelope["data"]["cleaning"] = deepcopy(cleaning_result)
    _stage(envelope, "cleaned")
    quality_result = _evaluate_quality_frontdoor(
        document_candidate=document_candidate,
        terminal_context=terminal_context,
    )
    envelope["data"]["quality_assessment"] = _object_view(quality_result["quality_assessment"])
    envelope["data"]["quality_gates"] = _object_view(quality_result["quality_gates"])
    envelope["data"]["cleanup_actions"] = _string_list(quality_result["cleanup_actions"])
    _stage(envelope, "quality_evaluated")

    admission = str(quality_result["admission"] or admission)
    envelope["data"]["admission"] = admission
    if admission != "accept":
        cleanup_execution = _maybe_execute_cleanup(
            document_candidate=document_candidate,
            terminal_context=terminal_context,
            quality_result=quality_result,
        )
        envelope["data"]["cleanup_execution"] = deepcopy(cleanup_execution)
        if cleanup_execution.get("recovered") and cleanup_execution.get("quality_result"):
            document_candidate = _object_view(cleanup_execution.get("document_candidate")) or document_candidate
            terminal_context = _object_view(cleanup_execution.get("terminal_context")) or terminal_context
            quality_result = _object_view(cleanup_execution.get("quality_result")) or quality_result
            envelope["data"]["content_extraction"] = _object_view(terminal_context.get("content_extraction"))
            envelope["data"]["cleaning"] = _object_view(terminal_context.get("frontdoor_cleaning"))
            envelope["data"]["quality_assessment"] = _object_view(quality_result["quality_assessment"])
            envelope["data"]["quality_gates"] = _object_view(quality_result["quality_gates"])
            envelope["data"]["cleanup_actions"] = _string_list(quality_result["cleanup_actions"])
            admission = str(quality_result["admission"] or admission)
            envelope["data"]["admission"] = admission
        if admission == "accept":
            terminal_context = _merge_terminal_context(
                terminal_context=terminal_context,
                quality_result=quality_result,
            )
            document_candidate = _merge_document_candidate(
                document_candidate=document_candidate,
                quality_result=quality_result,
            )
        else:
            envelope["data"]["dispatch_plan"] = {
                "run_extraction": False,
                "run_writer": False,
            }
            envelope["meta"]["reason_code"] = str(quality_result["reason_code"] or "rejected")
            envelope["meta"]["retryable"] = bool(quality_result["retryable"])
            envelope["meta"]["retry_observability"] = deepcopy(quality_result["retry_observability"])
            if admission == "return_for_cleanup":
                envelope["data"]["rollback_token"] = envelope["data"]["raw_snapshot_ref"]
                _stage(envelope, "returned_for_cleanup")
            _attach_canary_handoff(envelope=envelope, ingress=ingress)
            return envelope

    terminal_context = _merge_terminal_context(
        terminal_context=terminal_context,
        quality_result=quality_result,
    )
    document_candidate = _merge_document_candidate(
        document_candidate=document_candidate,
        quality_result=quality_result,
    )

    extraction_outcome: PostprocessObject = _object_view(collection_payload.get("extraction_outcome"))
    if effective_run_extraction and bool(extraction_plan.get("enabled", True)):
        if extraction_outcome:
            extraction_outcome = _normalize_existing_extraction_outcome(extraction_outcome)
        else:
            extraction_outcome = _run_extraction_plan(
                document_candidate=document_candidate,
                extraction_plan=extraction_plan,
            )
    elif extraction_outcome:
        extraction_outcome = _normalize_existing_extraction_outcome(extraction_outcome)
    else:
        extraction_outcome = {
            "status": "skipped",
            "reason": "extraction_not_requested",
            "error": None,
            "extractor_version": "unified.structured.v1",
            "model_profile": {},
            "prompt_profile": {},
            "structured_output_mode": "unknown",
            "domains": {},
            "summary": {},
        }
    _stage(envelope, "extraction_completed")

    if not document_candidate.get("publish_date"):
        derived_publish_date = _derive_publish_date_from_domains(extraction_outcome.get("domains"))
        if derived_publish_date:
            document_candidate["publish_date"] = derived_publish_date

    normalized_payload = build_terminal_ingest_payload(
        document_candidate=document_candidate,
        ingress_envelope=ingress,
        extraction_outcome=extraction_outcome,
        terminal_context=terminal_context,
    )
    normalized_payload["extracted_data"] = apply_terminal_compat(
        _object_view(normalized_payload.get("extracted_data"))
    )
    envelope["data"]["normalized_payload"] = normalized_payload
    _stage(envelope, "normalized")

    if effective_run_writer:
        writer_result = persist_terminal_document(normalized_payload)
        envelope["data"]["writer_result"] = writer_result
        _stage(envelope, "writer_completed")
    _attach_canary_handoff(envelope=envelope, ingress=ingress)
    return envelope


def run_frontdoor_extraction(
    *,
    title: str | None,
    content: str | None,
    extraction_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    return _run_extraction_plan(
        document_candidate={
            "title": title,
            "content": str(content or ""),
        },
        extraction_plan=dict(extraction_plan or {}),
    )


def run_unified_structured_extraction(
    *,
    content: str,
    title: str | None = None,
    include_policy: bool = True,
    include_market: bool = True,
    include_sentiment: bool = True,
    include_company: bool = True,
    include_product: bool = True,
    include_operation: bool = True,
) -> dict[str, object]:
    payload = "\n\n".join([segment for segment in [str(title or "").strip(), str(content or "").strip()] if segment]).strip()
    result = extract_structured_enriched_safe(
        extraction_app=_EXTRACTION_APP,
        payload=payload,
        include_market=include_market,
        include_policy=include_policy,
        include_sentiment=include_sentiment,
        include_company=include_company,
        include_product=include_product,
        include_operation=include_operation,
    )
    domains = dict(result.data or {})
    summary = build_structured_summary(
        domains,
        extraction_enabled=str(result.status or "").strip().lower() == "ok",
        chunks_used=1,
        extraction_mode="frontdoor",
    )
    return {
        "status": str(result.status or "failed").strip().lower() or "failed",
        "reason": result.reason,
        "error": result.error,
        "extractor_version": "unified.structured.v1",
        "model_profile": {
            "provider": None,
            "model": None,
        },
        "prompt_profile": {},
        "structured_output_mode": "unknown",
        "domains": domains,
        "summary": summary,
    }


def _validate_ingress(ingress_envelope: object) -> str | None:
    if not _is_object_dict(ingress_envelope):
        return "ingress_envelope must be dict"
    if str(ingress_envelope.get("contract_version") or "").strip() != INGRESS_CONTRACT_VERSION:
        return "invalid contract_version"
    if not str(ingress_envelope.get("entrypoint") or "").strip():
        return "entrypoint is required"
    if not isinstance(ingress_envelope.get("collection_payload"), dict):
        return "collection_payload must be dict"
    return None


def _attach_canary_handoff(
    *,
    envelope: PostprocessEnvelope,
    ingress: PostprocessObject,
) -> None:
    envelope["data"]["canary_handoff"] = build_single_url_canary_handoff(
        ingress_envelope=ingress,
        postprocess_frontdoor=envelope,
        writer_result=_object_view(envelope["data"]["writer_result"]),
    )


def _normalize_existing_extraction_outcome(extraction_outcome: dict[str, object]) -> dict[str, object]:
    normalized = dict(extraction_outcome or {})
    if "domains" not in normalized:
        normalized["domains"] = _object_view(normalized.get("data"))
    normalized.setdefault("extractor_version", "unified.structured.v1")
    normalized.setdefault("model_profile", {})
    normalized.setdefault("prompt_profile", {})
    normalized.setdefault("structured_output_mode", "unknown")
    normalized.setdefault("summary", {})
    normalized["status"] = str(normalized.get("status") or "failed").strip().lower() or "failed"
    return normalized


def _normalize_extraction_plan(extraction_plan: dict[str, object]) -> dict[str, bool]:
    plan = dict(extraction_plan or {})
    return {
        "include_policy": bool(plan.get("include_policy", True)),
        "include_market": bool(plan.get("include_market", True)),
        "include_sentiment": bool(plan.get("include_sentiment", True)),
        "include_company": bool(plan.get("include_company", True)),
        "include_product": bool(plan.get("include_product", True)),
        "include_operation": bool(plan.get("include_operation", True)),
    }


def _run_extraction_plan(
    *,
    document_candidate: dict[str, object],
    extraction_plan: dict[str, object],
) -> dict[str, object]:
    resolved_plan = _normalize_extraction_plan(extraction_plan)
    chunks = _string_list(extraction_plan.get("chunks"))
    title = _optional_str(document_candidate.get("title"))
    if chunks:
        outcomes: list[dict[str, object]] = []
        for chunk in chunks:
            text = str(chunk or "").strip()
            if not text:
                continue
            outcomes.append(
                run_unified_structured_extraction(
                    title=title,
                    content=text,
                    include_policy=resolved_plan["include_policy"],
                    include_market=resolved_plan["include_market"],
                    include_sentiment=resolved_plan["include_sentiment"],
                    include_company=resolved_plan["include_company"],
                    include_product=resolved_plan["include_product"],
                    include_operation=resolved_plan["include_operation"],
                )
            )
        return _merge_extraction_outcomes(
            outcomes=outcomes,
            extraction_mode=str(extraction_plan.get("mode") or "frontdoor"),
            chunks_used=len(chunks),
        )
    return run_unified_structured_extraction(
        title=title,
        content=str(document_candidate.get("content") or ""),
        include_policy=resolved_plan["include_policy"],
        include_market=resolved_plan["include_market"],
        include_sentiment=resolved_plan["include_sentiment"],
        include_company=resolved_plan["include_company"],
        include_product=resolved_plan["include_product"],
        include_operation=resolved_plan["include_operation"],
    )


def _merge_extraction_outcomes(
    *,
    outcomes: list[dict[str, object]],
    extraction_mode: str,
    chunks_used: int,
) -> dict[str, object]:
    merged_domains: dict[str, object] = {}
    statuses: list[str] = []
    reasons: list[str] = []
    errors: list[str] = []
    for outcome in outcomes:
        statuses.append(str(outcome.get("status") or "failed").strip().lower())
        reason = str(outcome.get("reason") or "").strip()
        error = str(outcome.get("error") or "").strip()
        if reason:
            reasons.append(reason)
        if error:
            errors.append(error)
        merged_domains = _merge_domain_payloads(merged_domains, outcome.get("domains"))
    if not outcomes:
        status = "failed"
        reason = "empty_structured_output"
    elif any(status == "ok" for status in statuses):
        status = "ok"
        reason = None
    else:
        status = "failed"
        reason = reasons[0] if reasons else "empty_structured_output"
    summary = build_structured_summary(
        merged_domains,
        extraction_enabled=bool(outcomes),
        chunks_used=chunks_used,
        extraction_mode=extraction_mode,
    )
    return {
        "status": status,
        "reason": reason,
        "error": errors[0] if errors else None,
        "extractor_version": "unified.structured.v1",
        "model_profile": {},
        "prompt_profile": {},
        "structured_output_mode": "unknown",
        "domains": merged_domains,
        "summary": summary,
    }


def _merge_domain_payloads(base: dict[str, object], incoming: object) -> dict[str, object]:
    out = _object_view(base)
    incoming_view = _object_view(incoming)
    if not incoming_view:
        return out
    for key, value in incoming_view.items():
        if key == "entities_relations":
            current = _object_view(out.get("entities_relations"))
            relation_payload = _object_view(value)
            entities = _object_list(current.get("entities"))
            relations = _object_list(current.get("relations"))
            _merge_unique_list_of_dicts(entities, _object_list(relation_payload.get("entities")), ("text", "type"))
            _merge_unique_list_of_dicts(relations, _object_list(relation_payload.get("relations")), ("subject", "predicate", "object"))
            out["entities_relations"] = {"entities": entities[:50], "relations": relations[:50]}
            continue
        if key == "entities":
            entities = _object_list(out.get("entities"))
            _merge_unique_list_of_dicts(entities, _object_list(value), ("text", "type"))
            out["entities"] = entities[:50]
            continue
        value_view = _object_view(value)
        current_view = _object_view(out.get(key))
        if value_view and current_view:
            merged = current_view
            merged.update(value_view)
            out[key] = merged
            continue
        out[key] = deepcopy(value)
    return out


def _merge_unique_list_of_dicts(target: list[object], incoming: list[object], keys: tuple[str, ...]) -> None:
    seen = {
        tuple(str((item or {}).get(key) or "").strip().lower() for key in keys)
        for item in target
        if _is_object_dict(item)
    }
    for item in incoming:
        if not _is_object_dict(item):
            continue
        signature = tuple(str(item.get(key) or "").strip().lower() for key in keys)
        if not any(signature):
            continue
        if signature in seen:
            continue
        seen.add(signature)
        target.append(item)


def _evaluate_quality_frontdoor(
    *,
    document_candidate: dict[str, object],
    terminal_context: dict[str, object],
) -> dict[str, object]:
    candidate = _object_view(document_candidate)
    context = _object_view(terminal_context)
    uri = str(candidate.get("uri") or "").strip()
    title = str(candidate.get("title") or "").strip()
    summary = str(candidate.get("summary") or "").strip()
    content = str(candidate.get("content") or "")
    source_base_url = str(candidate.get("source_base_url") or "").strip().lower()
    capability_profile = _object_view(context.get("capability_profile"))
    content_profile = _object_view(context.get("content_extraction"))
    entry_type = str(capability_profile.get("entry_type") or "").strip().lower()
    http_status = _safe_int(context.get("http_status")) or 0
    existing_quality_score = _safe_float(context.get("quality_score"))

    existing_light_filter = _object_view(context.get("light_filter"))
    if "filter_decision" in existing_light_filter:
        light_filter = existing_light_filter
    else:
        light_filter_options = normalize_light_filter_options(existing_light_filter)
        if is_extracted_pdf_body(candidate):
            light_filter_options["light_filter_reject_static_assets"] = False
        light_filter = evaluate_light_filter(
            url=uri,
            title=title,
            snippet=summary or content[:240],
            source_domain=source_base_url,
            http_status=http_status,
            entry_type=entry_type,
            options=light_filter_options,
        )

    light_reason = normalize_reason_code(light_filter.get("filter_reason_code"), default="ok")
    light_score = _safe_float(light_filter.get("filter_score")) or 0.0
    if str(light_filter.get("filter_decision") or "").strip().lower() == "reject":
        retry_observability = build_retry_observability({"reason_code": "light_filter_rejected"})
        return {
            "admission": "reject",
            "reason_code": "light_filter_rejected",
            "retryable": bool(retry_observability.get("retryable")),
            "retry_observability": retry_observability,
            "cleanup_actions": [],
            "cleaning": _object_view(context.get("frontdoor_cleaning")),
            "quality_assessment": {
                "quality_score": light_score,
                "meaningful": False,
                "provenance_ok": False,
                "content_ok": False,
            },
            "quality_gates": {
                "light_filter": light_filter,
                "gate_plus": {"checks": [], "blocked": True, "blocked_stage": "light_filter", "blocked_reason": light_reason},
            },
            "degradation_flags": ["light_filter_rejected", f"light_filter_rejected:{light_reason}"],
            "light_filter": light_filter,
            "gate_plus": {"checks": [], "blocked": True, "blocked_stage": "light_filter", "blocked_reason": light_reason},
        }

    gate_cfg = _frontdoor_gate_config(terminal_context=context)
    url_gate = url_policy_check(uri, config=gate_cfg) if uri else None
    content_gate = content_quality_check(
        uri=uri,
        content=content,
        doc_type=str(candidate.get("doc_type") or "unknown"),
        extraction_status="pending",
        config=gate_cfg,
        content_profile=content_profile,
    )
    gate_plus = build_gateplus_snapshot(
        url_gate=url_gate,
        content_gate=content_gate,
    )
    provenance_ok = bool(url_gate is None or not url_gate.blocked)
    content_ok = bool(not content_gate.blocked)
    cleanup_actions: list[str] = []
    degradation_flags: list[str] = []
    admission = "accept"
    reason_code = "ok"

    if url_gate is not None and url_gate.blocked:
        reason_code = normalize_reason_code(url_gate.reason, default="provenance_gate_rejected")
        admission = "reject"
        degradation_flags.extend([reason_code, f"provenance_gate_rejected:{reason_code}"])
    elif str(content_profile.get("page_family") or "") == "video":
        reason_code = "content_video_shell"
        cleanup_actions = ["specialized_extractor_required"]
        admission = "return_for_cleanup"
        degradation_flags.extend([reason_code, f"cleanup_required:{reason_code}"])
    elif content_gate.blocked:
        reason_code = normalize_reason_code(content_gate.reason, default="content_gate_rejected")
        cleanup_actions = _cleanup_actions_for_reason(reason_code)
        if cleanup_actions:
            admission = "return_for_cleanup"
            degradation_flags.extend([reason_code, f"cleanup_required:{reason_code}"])
        else:
            admission = "reject"
            degradation_flags.extend([reason_code, f"content_gate_rejected:{reason_code}"])

    retry_observability = build_retry_observability({"reason_code": reason_code})
    computed_quality_score = min(
        100.0,
        max(
            0.0,
            float(
                min(
                    light_score if light_score else 100.0,
                    (url_gate.quality_score if url_gate is not None else 100.0),
                    content_gate.quality_score,
                )
            ),
        ),
    )
    quality_score = max(existing_quality_score if existing_quality_score is not None else 0.0, computed_quality_score)
    guardrail_rollout = _object_view(gate_cfg.get("guardrail_rollout"))
    return {
        "admission": admission,
        "reason_code": reason_code,
        "retryable": bool(retry_observability.get("retryable")),
        "retry_observability": retry_observability,
        "cleanup_actions": cleanup_actions,
        "cleaning": _object_view(context.get("frontdoor_cleaning")),
        "quality_assessment": {
            "quality_score": quality_score,
            "meaningful": bool(provenance_ok and content_ok),
            "provenance_ok": provenance_ok,
            "content_ok": content_ok,
            "readerable": bool(content_profile.get("readerable")),
            "page_family": str(content_profile.get("page_family") or "unknown"),
            "strict_gate_enabled": bool(gate_cfg.get("enable_strict_gate")),
            "strict_gate_source": str(gate_cfg.get("strict_gate_source") or "disabled"),
            "guardrail_rollout_mode": str(guardrail_rollout.get("rollout_mode") or "canary"),
            "guardrail_canary_matched": bool(guardrail_rollout.get("canary_matched")),
            "guardrail_closure_claim": bool(guardrail_rollout.get("closure_claim")),
        },
        "quality_gates": {
            "light_filter": light_filter,
            "url_gate": (url_gate.to_dict() if url_gate is not None else None),
            "content_gate": content_gate.to_dict(),
            "gate_plus": gate_plus,
            "content_profile": deepcopy(content_profile),
            "gate_config": {
                "enable_strict_gate": bool(gate_cfg.get("enable_strict_gate")),
                "strict_gate_source": str(gate_cfg.get("strict_gate_source") or "disabled"),
                "min_semantic_len": _safe_int(gate_cfg.get("min_semantic_len")) or 500,
                "guardrail_rollout": guardrail_rollout,
            },
        },
        "degradation_flags": degradation_flags,
        "light_filter": light_filter,
        "gate_plus": gate_plus,
    }


def _merge_terminal_context(
    *,
    terminal_context: dict[str, object],
    quality_result: dict[str, object],
) -> dict[str, object]:
    context = _object_view(terminal_context)
    quality_assessment = _object_view(quality_result.get("quality_assessment"))
    context["quality_score"] = _safe_float(quality_assessment.get("quality_score")) or 0.0
    context["degradation_flags"] = _string_list(quality_result.get("degradation_flags"))
    context["light_filter"] = _object_view(quality_result.get("light_filter"))
    context["gate_plus"] = _object_view(quality_result.get("gate_plus"))
    context["frontdoor_cleaning"] = _object_view(quality_result.get("cleaning"))
    quality_gates = _object_view(quality_result.get("quality_gates"))
    context["content_extraction"] = _object_view(quality_gates.get("content_profile"))
    return context


def _merge_document_candidate(
    *,
    document_candidate: dict[str, object],
    quality_result: dict[str, object],
) -> dict[str, object]:
    candidate = _object_view(document_candidate)
    extracted_data_base = _object_view(candidate.get("extracted_data_base"))
    extracted_data_base.setdefault("_quality_frontdoor", {})
    extracted_data_base["_quality_frontdoor"] = {
        "cleaning": _object_view(quality_result.get("cleaning")),
        "quality_assessment": _object_view(quality_result.get("quality_assessment")),
        "cleanup_actions": _string_list(quality_result.get("cleanup_actions")),
        "gate_plus": _object_view(quality_result.get("gate_plus")),
        "content_extraction": _object_view(
            _object_view(quality_result.get("quality_gates")).get("content_profile")
        ),
    }
    candidate["extracted_data_base"] = extracted_data_base
    return candidate


def _cleanup_actions_for_reason(reason_code: str) -> list[str]:
    code = normalize_reason_code(reason_code, default="unknown_rejection_reason")
    if code in {
        "content_shell_signature",
        "content_js_template_shell",
        "content_shell_heavy_after_extraction",
        "content_navigation_shell",
        "content_navigation_or_home_shell",
        "content_rss_feed_shell",
        "content_support_shell",
        "content_video_shell",
    }:
        return ["strip_boilerplate", "refetch_suggested"]
    if code in {"content_mojibake_garbled"}:
        return ["refetch_suggested"]
    return []


def _maybe_execute_cleanup(
    *,
    document_candidate: dict[str, object],
    terminal_context: dict[str, object],
    quality_result: dict[str, object],
) -> dict[str, object]:
    if str(quality_result.get("admission") or "") != "return_for_cleanup":
        return {"executed": False, "recovered": False}
    cleanup_actions = _string_list(quality_result.get("cleanup_actions"))
    if not cleanup_actions:
        return {"executed": False, "recovered": False}
    if "specialized_extractor_required" in cleanup_actions:
        return {"executed": False, "recovered": False, "skipped_reason": "specialized_extractor_required"}
    cleanup_execution = execute_frontdoor_cleanup(
        document_candidate=document_candidate,
        terminal_context=terminal_context,
        cleanup_actions=cleanup_actions,
    )
    if not cleanup_execution.get("recovered"):
        return cleanup_execution
    rerun_quality = _evaluate_quality_frontdoor(
        document_candidate=_object_view(cleanup_execution.get("document_candidate")) or document_candidate,
        terminal_context=_object_view(cleanup_execution.get("terminal_context")) or terminal_context,
    )
    cleanup_execution["quality_result"] = rerun_quality
    cleanup_execution["recovered"] = str(rerun_quality.get("admission") or "") == "accept"
    return cleanup_execution


def _derive_publish_date_from_domains(domains: object) -> str | None:
    domain_view = _object_view(domains)
    if not domain_view:
        return None
    policy = _object_view(domain_view.get("policy"))
    effective_date = str(policy.get("effective_date") or "").strip()
    if effective_date:
        return effective_date
    market = _object_view(domain_view.get("market"))
    report_date = str(market.get("report_date") or "").strip()
    if report_date:
        return report_date
    return None


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _fail(
    envelope: PostprocessEnvelope,
    *,
    reason_code: str,
    error: str,
    retryable: bool,
) -> PostprocessEnvelope:
    envelope["status"] = "error"
    envelope["error"] = {"message": error}
    envelope["meta"]["reason_code"] = reason_code
    envelope["meta"]["retryable"] = retryable
    return envelope


def _stage(envelope: PostprocessEnvelope, stage: str) -> None:
    envelope["meta"].setdefault("stages", []).append(stage)


__all__ = ["run_postprocess_frontdoor"]
