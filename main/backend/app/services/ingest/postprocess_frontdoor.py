from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from ..extraction.application import ExtractionApplicationService
from .cleanup_executor import execute_frontdoor_cleanup
from .content_cleaner import clean_frontdoor_document_candidate
from .content_extraction import apply_main_content_extraction
from .frontdoor_ingress import CONTRACT_VERSION as INGRESS_CONTRACT_VERSION
from .gate_reason_codes import normalize_reason_code
from .light_filter import evaluate_light_filter, normalize_light_filter_options
from .meaningful_gate import build_gateplus_snapshot, content_quality_check, url_policy_check
from .retry_policy import build_retry_observability
from .structured_extraction import build_structured_summary, extract_structured_enriched_safe
from .terminal_compat import apply_terminal_compat
from .terminal_normalizer import build_terminal_ingest_payload
from .terminal_writer import persist_terminal_document
from ...settings.config import settings


_EXTRACTION_APP = ExtractionApplicationService()


def _frontdoor_gate_config() -> dict[str, Any]:
    return {
        "enable_strict_gate": bool(getattr(settings, "ingest_enable_strict_gate", False)),
        "min_semantic_len": int(getattr(settings, "ingest_min_semantic_len", 500) or 500),
    }


def run_postprocess_frontdoor(
    *,
    ingress_envelope: dict[str, Any],
    run_writer: bool | None = None,
) -> dict[str, Any]:
    envelope = {
        "status": "ok",
        "data": {
            "admission": "reject",
            "cleaning": {},
            "cleanup_execution": {},
            "content_extraction": {},
            "quality_assessment": {},
            "quality_gates": {},
            "cleanup_actions": [],
            "normalized_payload": {},
            "raw_snapshot_ref": None,
            "rollback_token": None,
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
            },
            "writer_result": None,
            "ingress_payload": deepcopy(ingress_envelope if isinstance(ingress_envelope, dict) else {}),
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

    ingress = dict(ingress_envelope or {})
    envelope["meta"]["trace_id"] = ((ingress.get("meta") or {}).get("trace_id") if isinstance(ingress.get("meta"), dict) else None)
    envelope["meta"]["reason_code"] = str(((ingress.get("meta") or {}).get("reason_code") if isinstance(ingress.get("meta"), dict) else "ok") or "ok")
    envelope["meta"]["retryable"] = bool(((ingress.get("meta") or {}).get("retryable")) if isinstance(ingress.get("meta"), dict) else False)
    _stage(envelope, "contract_validated")

    collection_payload = ingress.get("collection_payload") if isinstance(ingress.get("collection_payload"), dict) else {}
    document_candidate = collection_payload.get("document_candidate") if isinstance(collection_payload.get("document_candidate"), dict) else {}
    dispatch_plan = collection_payload.get("dispatch_plan") if isinstance(collection_payload.get("dispatch_plan"), dict) else {}
    records = collection_payload.get("records") if isinstance(collection_payload.get("records"), list) else []
    extraction_plan = collection_payload.get("extraction_plan") if isinstance(collection_payload.get("extraction_plan"), dict) else {}
    effective_run_writer = bool(dispatch_plan.get("run_writer", True if run_writer is None else run_writer))
    effective_run_extraction = bool(dispatch_plan.get("run_extraction", True))
    admission = "accept"
    if document_candidate:
        if not str(document_candidate.get("uri") or "").strip() and not str(document_candidate.get("content") or "").strip():
            admission = "reject"
    elif records:
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
    envelope["data"]["raw_snapshot_ref"] = str(((ingress.get("meta") or {}).get("payload_hash")) if isinstance(ingress.get("meta"), dict) else "") or None
    _stage(envelope, "admission_decided")

    if admission != "accept":
        envelope["meta"]["reason_code"] = "deferred" if admission == "defer" else "rejected"
        return envelope

    terminal_context = collection_payload.get("terminal_context") if isinstance(collection_payload.get("terminal_context"), dict) else {}
    document_candidate, extraction_profile = apply_main_content_extraction(document_candidate)
    terminal_context = dict(terminal_context or {})
    terminal_context["content_extraction"] = dict(extraction_profile)
    envelope["data"]["content_extraction"] = deepcopy(extraction_profile)
    _stage(envelope, "content_extracted")
    document_candidate, cleaning_result = clean_frontdoor_document_candidate(document_candidate)
    terminal_context["frontdoor_cleaning"] = dict(cleaning_result)
    envelope["data"]["cleaning"] = deepcopy(cleaning_result)
    _stage(envelope, "cleaned")
    quality_result = _evaluate_quality_frontdoor(
        document_candidate=document_candidate,
        terminal_context=terminal_context,
    )
    envelope["data"]["quality_assessment"] = deepcopy(quality_result["quality_assessment"])
    envelope["data"]["quality_gates"] = deepcopy(quality_result["quality_gates"])
    envelope["data"]["cleanup_actions"] = list(quality_result["cleanup_actions"])
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
            document_candidate = dict(cleanup_execution.get("document_candidate") or document_candidate)
            terminal_context = dict(cleanup_execution.get("terminal_context") or terminal_context)
            quality_result = dict(cleanup_execution.get("quality_result") or quality_result)
            envelope["data"]["content_extraction"] = deepcopy((terminal_context.get("content_extraction") or {}))
            envelope["data"]["cleaning"] = deepcopy((terminal_context.get("frontdoor_cleaning") or {}))
            envelope["data"]["quality_assessment"] = deepcopy(quality_result["quality_assessment"])
            envelope["data"]["quality_gates"] = deepcopy(quality_result["quality_gates"])
            envelope["data"]["cleanup_actions"] = list(quality_result["cleanup_actions"])
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
            return envelope

    terminal_context = _merge_terminal_context(
        terminal_context=terminal_context,
        quality_result=quality_result,
    )
    document_candidate = _merge_document_candidate(
        document_candidate=document_candidate,
        quality_result=quality_result,
    )

    extraction_outcome = collection_payload.get("extraction_outcome") if isinstance(collection_payload.get("extraction_outcome"), dict) else {}
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
    normalized_payload["extracted_data"] = apply_terminal_compat(normalized_payload.get("extracted_data") if isinstance(normalized_payload.get("extracted_data"), dict) else {})
    envelope["data"]["normalized_payload"] = normalized_payload
    _stage(envelope, "normalized")

    if effective_run_writer:
        writer_result = persist_terminal_document(normalized_payload)
        envelope["data"]["writer_result"] = writer_result
        _stage(envelope, "writer_completed")
    return envelope


def run_frontdoor_extraction(
    *,
    title: str | None,
    content: str | None,
    extraction_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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


def _validate_ingress(ingress_envelope: Any) -> str | None:
    if not isinstance(ingress_envelope, dict):
        return "ingress_envelope must be dict"
    if str(ingress_envelope.get("contract_version") or "").strip() != INGRESS_CONTRACT_VERSION:
        return "invalid contract_version"
    if not str(ingress_envelope.get("entrypoint") or "").strip():
        return "entrypoint is required"
    if not isinstance(ingress_envelope.get("collection_payload"), dict):
        return "collection_payload must be dict"
    return None


def _normalize_existing_extraction_outcome(extraction_outcome: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(extraction_outcome or {})
    if "domains" not in normalized:
        normalized["domains"] = dict(normalized.get("data") or {})
    normalized.setdefault("extractor_version", "unified.structured.v1")
    normalized.setdefault("model_profile", {})
    normalized.setdefault("prompt_profile", {})
    normalized.setdefault("structured_output_mode", "unknown")
    normalized.setdefault("summary", {})
    normalized["status"] = str(normalized.get("status") or "failed").strip().lower() or "failed"
    return normalized


def _normalize_extraction_plan(extraction_plan: dict[str, Any]) -> dict[str, bool]:
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
    document_candidate: dict[str, Any],
    extraction_plan: dict[str, Any],
) -> dict[str, Any]:
    resolved_plan = _normalize_extraction_plan(extraction_plan)
    chunks = extraction_plan.get("chunks") if isinstance(extraction_plan.get("chunks"), list) else None
    title = document_candidate.get("title")
    if chunks:
        outcomes: list[dict[str, Any]] = []
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
    outcomes: list[dict[str, Any]],
    extraction_mode: str,
    chunks_used: int,
) -> dict[str, Any]:
    merged_domains: dict[str, Any] = {}
    statuses: list[str] = []
    reasons: list[str] = []
    errors: list[str] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
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


def _merge_domain_payloads(base: dict[str, Any], incoming: Any) -> dict[str, Any]:
    out = dict(base or {})
    if not isinstance(incoming, dict):
        return out
    for key, value in incoming.items():
        if key == "entities_relations" and isinstance(value, dict):
            current = out.get("entities_relations") if isinstance(out.get("entities_relations"), dict) else {}
            entities = list(current.get("entities") or [])
            relations = list(current.get("relations") or [])
            _merge_unique_list_of_dicts(entities, value.get("entities") or [], ("text", "type"))
            _merge_unique_list_of_dicts(relations, value.get("relations") or [], ("subject", "predicate", "object"))
            out["entities_relations"] = {"entities": entities[:50], "relations": relations[:50]}
            continue
        if key == "entities" and isinstance(value, list):
            entities = list(out.get("entities") or [])
            _merge_unique_list_of_dicts(entities, value, ("text", "type"))
            out["entities"] = entities[:50]
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            merged = dict(out.get(key) or {})
            merged.update(value)
            out[key] = merged
            continue
        out[key] = deepcopy(value)
    return out


def _merge_unique_list_of_dicts(target: list[Any], incoming: list[Any], keys: tuple[str, ...]) -> None:
    seen = {
        tuple(str((item or {}).get(key) or "").strip().lower() for key in keys)
        for item in target
        if isinstance(item, dict)
    }
    for item in incoming:
        if not isinstance(item, dict):
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
    document_candidate: dict[str, Any],
    terminal_context: dict[str, Any],
) -> dict[str, Any]:
    candidate = dict(document_candidate or {})
    context = dict(terminal_context or {})
    uri = str(candidate.get("uri") or "").strip()
    title = str(candidate.get("title") or "").strip()
    summary = str(candidate.get("summary") or "").strip()
    content = str(candidate.get("content") or "")
    source_base_url = str(candidate.get("source_base_url") or "").strip().lower()
    capability_profile = context.get("capability_profile") if isinstance(context.get("capability_profile"), dict) else {}
    content_profile = context.get("content_extraction") if isinstance(context.get("content_extraction"), dict) else {}
    entry_type = str(capability_profile.get("entry_type") or "").strip().lower()
    http_status = _safe_int(context.get("http_status")) or 0
    existing_quality_score = _safe_float(context.get("quality_score"))

    existing_light_filter = context.get("light_filter") if isinstance(context.get("light_filter"), dict) else {}
    if "filter_decision" in existing_light_filter:
        light_filter = dict(existing_light_filter)
    else:
        light_filter = evaluate_light_filter(
            url=uri,
            title=title,
            snippet=summary or content[:240],
            source_domain=source_base_url,
            http_status=http_status,
            entry_type=entry_type,
            options=normalize_light_filter_options(existing_light_filter),
        )

    light_reason = normalize_reason_code(light_filter.get("filter_reason_code"), default="ok")
    light_score = float(light_filter.get("filter_score") or 0)
    if str(light_filter.get("filter_decision") or "").strip().lower() == "reject":
        retry_observability = build_retry_observability({"reason_code": "light_filter_rejected"})
        return {
            "admission": "reject",
            "reason_code": "light_filter_rejected",
            "retryable": bool(retry_observability.get("retryable")),
            "retry_observability": retry_observability,
            "cleanup_actions": [],
            "cleaning": dict(context.get("frontdoor_cleaning") or {}),
            "quality_assessment": {
                "quality_score": light_score,
                "meaningful": False,
                "provenance_ok": False,
                "content_ok": False,
            },
            "quality_gates": {
                "light_filter": dict(light_filter),
                "gate_plus": {"checks": [], "blocked": True, "blocked_stage": "light_filter", "blocked_reason": light_reason},
            },
            "degradation_flags": ["light_filter_rejected", f"light_filter_rejected:{light_reason}"],
            "light_filter": dict(light_filter),
            "gate_plus": {"checks": [], "blocked": True, "blocked_stage": "light_filter", "blocked_reason": light_reason},
        }

    gate_cfg = _frontdoor_gate_config()
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
                    light_score or 100.0,
                    (url_gate.quality_score if url_gate is not None else 100.0),
                    content_gate.quality_score,
                )
            ),
        ),
    )
    quality_score = max(existing_quality_score if existing_quality_score is not None else 0.0, computed_quality_score)
    return {
        "admission": admission,
        "reason_code": reason_code,
        "retryable": bool(retry_observability.get("retryable")),
        "retry_observability": retry_observability,
        "cleanup_actions": cleanup_actions,
        "cleaning": dict(context.get("frontdoor_cleaning") or {}),
        "quality_assessment": {
            "quality_score": quality_score,
            "meaningful": bool(not content_gate.blocked),
            "provenance_ok": bool(url_gate is None or not url_gate.blocked),
            "content_ok": bool(not content_gate.blocked),
            "readerable": bool(content_profile.get("readerable")),
            "page_family": str(content_profile.get("page_family") or "unknown"),
        },
        "quality_gates": {
            "light_filter": dict(light_filter),
            "url_gate": (url_gate.to_dict() if url_gate is not None else None),
            "content_gate": content_gate.to_dict(),
            "gate_plus": gate_plus,
            "content_profile": deepcopy(content_profile),
        },
        "degradation_flags": degradation_flags,
        "light_filter": dict(light_filter),
        "gate_plus": gate_plus,
    }


def _merge_terminal_context(
    *,
    terminal_context: dict[str, Any],
    quality_result: dict[str, Any],
) -> dict[str, Any]:
    context = dict(terminal_context or {})
    context["quality_score"] = float((quality_result.get("quality_assessment") or {}).get("quality_score") or 0.0)
    context["degradation_flags"] = list(quality_result.get("degradation_flags") or [])
    context["light_filter"] = dict(quality_result.get("light_filter") or {})
    context["gate_plus"] = deepcopy(quality_result.get("gate_plus") or {})
    context["frontdoor_cleaning"] = deepcopy(quality_result.get("cleaning") or {})
    context["content_extraction"] = deepcopy((quality_result.get("quality_gates") or {}).get("content_profile") or {})
    return context


def _merge_document_candidate(
    *,
    document_candidate: dict[str, Any],
    quality_result: dict[str, Any],
) -> dict[str, Any]:
    candidate = dict(document_candidate or {})
    extracted_data_base = dict(candidate.get("extracted_data_base") or {})
    extracted_data_base.setdefault("_quality_frontdoor", {})
    extracted_data_base["_quality_frontdoor"] = {
        "cleaning": deepcopy(quality_result.get("cleaning") or {}),
        "quality_assessment": deepcopy(quality_result.get("quality_assessment") or {}),
        "cleanup_actions": list(quality_result.get("cleanup_actions") or []),
        "gate_plus": deepcopy(quality_result.get("gate_plus") or {}),
        "content_extraction": deepcopy((quality_result.get("quality_gates") or {}).get("content_profile") or {}),
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
    document_candidate: dict[str, Any],
    terminal_context: dict[str, Any],
    quality_result: dict[str, Any],
) -> dict[str, Any]:
    if str(quality_result.get("admission") or "") != "return_for_cleanup":
        return {"executed": False, "recovered": False}
    cleanup_actions = list(quality_result.get("cleanup_actions") or [])
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
        document_candidate=dict(cleanup_execution.get("document_candidate") or document_candidate),
        terminal_context=dict(cleanup_execution.get("terminal_context") or terminal_context),
    )
    cleanup_execution["quality_result"] = rerun_quality
    cleanup_execution["recovered"] = str(rerun_quality.get("admission") or "") == "accept"
    return cleanup_execution


def _derive_publish_date_from_domains(domains: Any) -> str | None:
    if not isinstance(domains, dict):
        return None
    policy = domains.get("policy")
    if isinstance(policy, dict):
        effective_date = str(policy.get("effective_date") or "").strip()
        if effective_date:
            return effective_date
    market = domains.get("market")
    if isinstance(market, dict):
        report_date = str(market.get("report_date") or "").strip()
        if report_date:
            return report_date
    return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _fail(envelope: dict[str, Any], *, reason_code: str, error: str, retryable: bool) -> dict[str, Any]:
    envelope["status"] = "error"
    envelope["error"] = {"message": error}
    envelope["meta"]["reason_code"] = reason_code
    envelope["meta"]["retryable"] = retryable
    return envelope


def _stage(envelope: dict[str, Any], stage: str) -> None:
    stages = envelope["meta"].setdefault("stages", [])
    if isinstance(stages, list):
        stages.append(str(stage))


__all__ = ["run_postprocess_frontdoor"]
