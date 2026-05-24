from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text

from ...models.base import SessionLocal, engine
from ...models.entities import Document, Source
from ..projects import bind_project
from ..projects.context import project_schema_name
from .canary_handoff import (
    LIVE_CANARY_EVIDENCE_CONTRACT_VERSION,
    build_single_url_canary_handoff,
)


PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION = "ingest.single_url_canary_handoff.production_like_check.v1"
_API_ENDPOINT = "/api/v1/ingest/url/single"
_REMAINING_EXTERNAL_GAPS = [
    "production 24h rejection-rate readback remains open",
    "production 24h inserted-valid ratio readback remains open",
    "production all-project strict-gate enablement remains operations-owned",
]


def _article_content(run_id: str) -> str:
    return " ".join(
        [
            (
                f"Wave55 robotics operations evidence {idx} for {run_id} covers warehouse safety, "
                "field service adoption, enterprise procurement, and measurable implementation detail."
            )
            for idx in range(36)
        ]
    )


def _search_shell_content(run_id: str) -> str:
    return " ".join(
        [
            (
                f"Wave55 search shell fixture {idx} for {run_id} lists navigational snippets and "
                "should be blocked by the pre-fetch URL gate before any document write."
            )
            for idx in range(10)
        ]
    )


def _prepare_project_schema(project_key: str) -> str:
    schema_name = project_schema_name(project_key)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
    for table in (Source.__table__, Document.__table__):
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}"'))
            table.create(bind=conn, checkfirst=True)
    return schema_name


def _drop_project_schema(schema_name: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))


def _fake_channels() -> list[dict[str, Any]]:
    return [{"channel_key": "url_pool", "enabled": True}]


def _fake_routing(*, run_id: str):
    def _run_item_with_url_routing(**kwargs: Any) -> dict[str, Any]:
        params = kwargs.get("params") if isinstance(kwargs.get("params"), dict) else {}
        urls = params.get("urls") if isinstance(params.get("urls"), list) else []
        url = str(urls[0] if urls else "").strip()
        is_search = "/search" in url
        return {
            "records": [
                {
                    "url": url,
                    "title": "Wave55 search shell" if is_search else "Wave55 production-like guardrail article",
                    "content_text": _search_shell_content(run_id) if is_search else _article_content(run_id),
                    "summary": "Wave55 guardrail canary fixture",
                    "source_label": "url_pool",
                    "record_meta": {"http_status": 200},
                }
            ],
            "errors": [],
            "by_url": [{"url": url, "status": "ok"}],
        }

    return _run_item_with_url_routing


def _fake_structured_extraction(**_kwargs: Any) -> dict[str, Any]:
    return {
        "status": "ok",
        "reason": None,
        "error": None,
        "extractor_version": "unified.structured.v1",
        "model_profile": {"provider": "repo_local_fixture", "model": "deterministic"},
        "prompt_profile": {},
        "structured_output_mode": "fixture",
        "domains": {"market": {"signals": ["guardrail_canary"]}},
        "summary": {"domains_present": ["market"], "extraction_enabled": True},
    }


def _response_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return {"_json_error": str(getattr(response, "text", ""))}
    return payload if isinstance(payload, dict) else {"_json_error": "response JSON was not an object"}


def _response_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return dict(data or {}) if isinstance(data, Mapping) else {}


def _handoff_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    handoff = result.get("canary_handoff")
    return dict(handoff or {}) if isinstance(handoff, Mapping) else {}


def _readback_documents(*, project_key: str, accepted_url: str, rejected_url: str) -> dict[str, Any]:
    with bind_project(project_key):
        with SessionLocal() as session:
            rows = session.query(Document).filter(Document.uri.in_([accepted_url, rejected_url])).all()
            accepted = [row for row in rows if row.uri == accepted_url]
            rejected = [row for row in rows if row.uri == rejected_url]
            return {
                "accepted_doc_count": len(accepted),
                "accepted_doc_ids": [int(row.id) for row in accepted],
                "accepted_titles": [str(row.title or "") for row in accepted],
                "rejected_doc_count": len(rejected),
                "rejected_doc_ids": [int(row.id) for row in rejected],
            }


def build_production_like_handoff_evidence(
    *,
    project_key: str,
    accepted_url: str,
    rejected_url: str,
    accepted_status_code: int,
    rejected_status_code: int,
    accepted_result: Mapping[str, Any],
    rejected_result: Mapping[str, Any],
    db_readback: Mapping[str, Any],
) -> dict[str, Any]:
    accepted_handoff = _handoff_from_result(accepted_result)
    rejected_handoff = _handoff_from_result(rejected_result)
    accepted_gate = accepted_handoff.get("strict_gate_state") if isinstance(accepted_handoff.get("strict_gate_state"), Mapping) else {}
    rejected_gate = rejected_handoff.get("strict_gate_state") if isinstance(rejected_handoff.get("strict_gate_state"), Mapping) else {}
    accepted_rollout = accepted_handoff.get("rollout") if isinstance(accepted_handoff.get("rollout"), Mapping) else {}
    rejected_rollout = rejected_handoff.get("rollout") if isinstance(rejected_handoff.get("rollout"), Mapping) else {}

    checks = {
        "api_runtime_validated": accepted_status_code == 200
        and rejected_status_code == 200
        and str(accepted_result.get("status") or "") == "success"
        and str(rejected_result.get("status") or "") in {"failed", "degraded_success"},
        "db_readback_validated": int(db_readback.get("accepted_doc_count") or 0) == 1
        and int(db_readback.get("rejected_doc_count") or 0) == 0,
        "guardrail_pass_observed": accepted_gate.get("state") == "strict_passed"
        and accepted_gate.get("strict_gate_enabled") is True
        and accepted_rollout.get("channel") == "canary",
        "guardrail_block_observed": rejected_gate.get("state") == "strict_blocked"
        and rejected_gate.get("strict_gate_enabled") is True
        and rejected_rollout.get("channel") == "canary",
        "handoff_readback_present": bool(accepted_handoff) and bool(rejected_handoff),
    }
    live_canary_validated = all(checks.values())
    return {
        "contract_version": LIVE_CANARY_EVIDENCE_CONTRACT_VERSION,
        "validation_scope": "repo_local_api_db_runtime",
        "api_endpoint": _API_ENDPOINT,
        "project_key": project_key,
        "accepted_url": accepted_url,
        "rejected_url": rejected_url,
        "api_runtime": {
            "accepted_status_code": int(accepted_status_code),
            "rejected_status_code": int(rejected_status_code),
            "accepted_status": accepted_result.get("status"),
            "rejected_status": rejected_result.get("status"),
        },
        "db_readback": deepcopy(dict(db_readback or {})),
        "guardrail_readback": {
            "accepted_handoff_state": accepted_handoff.get("handoff_state"),
            "accepted_strict_gate_state": accepted_gate.get("state"),
            "accepted_rollout_channel": accepted_rollout.get("channel"),
            "rejected_handoff_state": rejected_handoff.get("handoff_state"),
            "rejected_strict_gate_state": rejected_gate.get("state"),
            "rejected_reason_code": rejected_gate.get("reason_code"),
            "rejected_rollout_channel": rejected_rollout.get("channel"),
        },
        "validation_checks": checks,
        "live_canary_validated": live_canary_validated,
        "closure_claim": False,
        "remaining_external_gaps": list(_REMAINING_EXTERNAL_GAPS),
    }


def validate_production_like_handoff_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    checks = evidence.get("validation_checks") if isinstance(evidence.get("validation_checks"), Mapping) else {}
    required = {
        "api_runtime_validated",
        "db_readback_validated",
        "guardrail_pass_observed",
        "guardrail_block_observed",
        "handoff_readback_present",
    }
    validation_checks = {
        "contract_version": evidence.get("contract_version") == LIVE_CANARY_EVIDENCE_CONTRACT_VERSION,
        "validation_scope": evidence.get("validation_scope") == "repo_local_api_db_runtime",
        **{name: checks.get(name) is True for name in sorted(required)},
        "live_canary_validated": evidence.get("live_canary_validated") is True,
        "no_closure_claim": evidence.get("closure_claim") is False,
    }
    failed = [name for name, passed in validation_checks.items() if not passed]
    return {
        "contract_version": PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION,
        "status": "passed" if not failed else "failed",
        "passed": not failed,
        "validation_checks": validation_checks,
        "failed_checks": failed,
    }


def run_repo_local_production_like_handoff_canary(*, project_key: str | None = None) -> dict[str, Any]:
    run_id = uuid4().hex[:10]
    resolved_project_key = str(project_key or f"wave55_ingest_canary_{run_id}").strip().lower()
    accepted_url = f"https://example.com/wave55-production-like-{run_id}"
    rejected_url = f"https://example.com/search?q=wave55-{run_id}"
    schema_name = _prepare_project_schema(resolved_project_key)
    cleanup: dict[str, Any] = {"schema_name": schema_name, "performed": False, "error": None}
    result: dict[str, Any] | None = None
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        with (
            patch("app.services.source_library.resolver.list_effective_channels", side_effect=lambda **_kwargs: _fake_channels()),
            patch("app.services.source_library.resolver.run_item_with_url_routing", side_effect=_fake_routing(run_id=run_id)),
            patch("app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction", side_effect=_fake_structured_extraction),
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", resolved_project_key),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            headers = {"X-Project-Key": resolved_project_key}
            try:
                accepted_response = client.post(
                    _API_ENDPOINT,
                    json={
                        "url": accepted_url,
                        "query_terms": ["robotics guardrail canary"],
                        "project_key": resolved_project_key,
                        "strict_mode": False,
                        "async_mode": False,
                    },
                    headers=headers,
                )
                rejected_response = client.post(
                    _API_ENDPOINT,
                    json={
                        "url": rejected_url,
                        "query_terms": ["robotics guardrail canary"],
                        "project_key": resolved_project_key,
                        "strict_mode": False,
                        "async_mode": False,
                    },
                    headers=headers,
                )
            finally:
                client.close()

        accepted_payload = _response_payload(accepted_response)
        rejected_payload = _response_payload(rejected_response)
        accepted_result = _response_data(accepted_payload)
        rejected_result = _response_data(rejected_payload)
        db_readback = _readback_documents(
            project_key=resolved_project_key,
            accepted_url=accepted_url,
            rejected_url=rejected_url,
        )
        evidence = build_production_like_handoff_evidence(
            project_key=resolved_project_key,
            accepted_url=accepted_url,
            rejected_url=rejected_url,
            accepted_status_code=int(accepted_response.status_code),
            rejected_status_code=int(rejected_response.status_code),
            accepted_result=accepted_result,
            rejected_result=rejected_result,
            db_readback=db_readback,
        )
        validation = validate_production_like_handoff_evidence(evidence)

        accepted_postprocess = (
            accepted_result.get("postprocess_frontdoor")
            if isinstance(accepted_result.get("postprocess_frontdoor"), Mapping)
            else {}
        )
        accepted_ingress = (
            accepted_result.get("frontdoor_ingress") if isinstance(accepted_result.get("frontdoor_ingress"), Mapping) else {}
        )
        accepted_data = (
            accepted_postprocess.get("data") if isinstance(accepted_postprocess.get("data"), Mapping) else {}
        )
        writer_result = (
            accepted_data.get("writer_result") if isinstance(accepted_data.get("writer_result"), Mapping) else {}
        )
        validated_handoff = build_single_url_canary_handoff(
            ingress_envelope=accepted_ingress,
            postprocess_frontdoor=accepted_postprocess,
            writer_result=writer_result,
            live_canary_evidence=evidence,
            live_canary_validated=validation["passed"],
            closure_claim=False,
        )
        result = {
            "contract_version": PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION,
            "status": "passed" if validation["passed"] else "failed",
            "project_key": resolved_project_key,
            "schema_name": schema_name,
            "accepted_response_status_code": int(accepted_response.status_code),
            "rejected_response_status_code": int(rejected_response.status_code),
            "evidence": evidence,
            "validation": validation,
            "validated_handoff": validated_handoff,
            "accepted_result": {
                "status": accepted_result.get("status"),
                "inserted_valid": accepted_result.get("inserted_valid"),
                "rejected_count": accepted_result.get("rejected_count"),
            },
            "rejected_result": {
                "status": rejected_result.get("status"),
                "inserted_valid": rejected_result.get("inserted_valid"),
                "rejected_count": rejected_result.get("rejected_count"),
            },
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "contract_version": PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION,
            "status": "failed",
            "project_key": resolved_project_key,
            "schema_name": schema_name,
            "error": str(exc),
            "exception_type": exc.__class__.__name__,
        }
    finally:
        try:
            _drop_project_schema(schema_name)
            cleanup["performed"] = True
        except Exception as exc:  # noqa: BLE001
            cleanup["error"] = str(exc)
        if result is not None:
            result["cleanup"] = dict(cleanup)
    return result if result is not None else {
        "contract_version": PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION,
        "status": "failed",
        "project_key": resolved_project_key,
        "schema_name": schema_name,
        "error": "production-like handoff canary returned no result",
        "cleanup": dict(cleanup),
    }


__all__ = [
    "LIVE_CANARY_EVIDENCE_CONTRACT_VERSION",
    "PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION",
    "build_production_like_handoff_evidence",
    "run_repo_local_production_like_handoff_canary",
    "validate_production_like_handoff_evidence",
]
