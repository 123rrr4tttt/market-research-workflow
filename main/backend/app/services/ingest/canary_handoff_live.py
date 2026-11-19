from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Annotated, Iterable, Protocol, TypeGuard, TypedDict, runtime_checkable
from typing import Mapping as TypingMapping
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text

from ...models.base import SessionLocal, engine, require_model_table
from ...models.entities import Material, Source
from ...models.ingest_registry import IngestSubmissionRegistry
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


class _MaterialReadback(TypedDict):
    accepted_material_count: int
    accepted_material_ids: list[int]
    accepted_titles: list[str]
    rejected_material_count: int
    rejected_material_ids: list[int]


class _JsonResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> object: ...


@runtime_checkable
class _HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        json: TypingMapping[str, object],
        headers: TypingMapping[str, str],
    ) -> _JsonResponse: ...

    def close(self) -> None: ...


def _require_http_client(value: object) -> _HttpClient:
    if not isinstance(value, _HttpClient):
        raise TypeError("TestClient does not expose the required JSON client interface")
    return value


def _is_string_key(value: object) -> bool:
    return isinstance(value, str)


@runtime_checkable
class _StringKeyInspectable(Protocol):
    def keys(self) -> Iterable[object]: ...


def _has_only_string_keys(value: object) -> bool:
    if not isinstance(value, _StringKeyInspectable):
        return False
    return all(map(_is_string_key, value.keys()))


def _is_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not _has_only_string_keys(value):
        return False
    return isinstance(value, Mapping)


def _object_mapping(value: object) -> Mapping[str, object]:
    return value if _is_object_mapping(value) else {}


def _object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_object_mapping(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _coerce_int(value: object) -> int:
    if not isinstance(value, (str, bytes, int, float)):
        return 0
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return 0


def _model_value(row: object, field: str) -> object:
    return getattr(row, field, None)


def _article_content(run_id: str) -> str:
    return " ".join(
        [
            (
                f"Robotics operations evidence {idx} for {run_id} covers warehouse safety, "
                "field service adoption, enterprise procurement, and measurable implementation detail."
            )
            for idx in range(36)
        ]
    )


def _search_shell_content(run_id: str) -> str:
    return " ".join(
        [
            (
                f"Search shell fixture {idx} for {run_id} lists navigational snippets and "
                "should be blocked by the pre-fetch URL gate before any document write."
            )
            for idx in range(10)
        ]
    )


def _prepare_project_schema(project_key: str) -> str:
    schema_name = project_schema_name(project_key)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
    for table in (
        require_model_table(Source.__table__),
        require_model_table(Material.__table__),
        require_model_table(IngestSubmissionRegistry.__table__),
    ):
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}"'))
            table.create(bind=conn, checkfirst=True)
    return schema_name


def _drop_project_schema(schema_name: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))


def _fake_channels() -> list[dict[str, object]]:
    return [{"channel_key": "url_pool", "enabled": True}]


def _fake_list_channels(**_kwargs: object) -> list[dict[str, object]]:
    return _fake_channels()


def _fake_routing(*, run_id: str):
    def _run_item_with_url_routing(**kwargs: object) -> dict[str, object]:
        params = _object_mapping(kwargs.get("params"))
        urls_value = params.get("urls")
        urls = list(urls_value) if _is_object_list(urls_value) else []
        url = str(urls[0] if urls else "").strip()
        is_search = "/search" in url
        return {
            "records": [
                {
                    "url": url,
                    "title": "Search shell" if is_search else "Production-like guardrail article",
                    "content_text": _search_shell_content(run_id) if is_search else _article_content(run_id),
                    "summary": "Guardrail canary fixture",
                    "source_label": "url_pool",
                    "record_meta": {"http_status": 200},
                }
            ],
            "errors": [],
            "by_url": [{"url": url, "status": "ok"}],
        }

    return _run_item_with_url_routing


def _fake_structured_extraction(**_kwargs: object) -> dict[str, object]:
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


def _response_payload(response: _JsonResponse) -> dict[str, object]:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return {"_json_error": str(getattr(response, "text", ""))}
    return _object_dict(payload) if _is_object_mapping(payload) else {"_json_error": "response JSON was not an object"}


def _response_data(payload: Mapping[str, object]) -> dict[str, object]:
    return _object_dict(payload.get("data"))


def _handoff_from_result(result: Mapping[str, object]) -> dict[str, object]:
    return _object_dict(result.get("canary_handoff"))


def _readback_materials(*, project_key: str, accepted_url: str, rejected_url: str) -> _MaterialReadback:
    with bind_project(project_key):
        with SessionLocal() as session:
            rows = session.query(Material).filter(Material.uri.in_([accepted_url, rejected_url])).all()
            accepted = [row for row in rows if _model_value(row, "uri") == accepted_url]
            rejected = [row for row in rows if _model_value(row, "uri") == rejected_url]
            return {
                "accepted_material_count": len(accepted),
                "accepted_material_ids": [_coerce_int(_model_value(row, "id")) for row in accepted],
                "accepted_titles": [str(_model_value(row, "title") or "") for row in accepted],
                "rejected_material_count": len(rejected),
                "rejected_material_ids": [_coerce_int(_model_value(row, "id")) for row in rejected],
            }


def build_production_like_handoff_evidence(
    *,
    project_key: str,
    accepted_url: str,
    rejected_url: str,
    accepted_status_code: int,
    rejected_status_code: int,
    accepted_result: Mapping[str, object],
    rejected_result: Mapping[str, object],
    db_readback: _MaterialReadback,
) -> Annotated[
    dict[str, object],
    "kit:non-authoritative derived_as=generated_evidence fact_source=repo_local_api_responses+db_readback witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    accepted_handoff = _handoff_from_result(accepted_result)
    rejected_handoff = _handoff_from_result(rejected_result)
    accepted_gate = _object_mapping(accepted_handoff.get("strict_gate_state"))
    rejected_gate = _object_mapping(rejected_handoff.get("strict_gate_state"))
    accepted_rollout = _object_mapping(accepted_handoff.get("rollout"))
    rejected_rollout = _object_mapping(rejected_handoff.get("rollout"))

    checks = {
        "api_runtime_validated": accepted_status_code == 200
        and rejected_status_code == 200
        and str(accepted_result.get("status") or "") == "success"
        and str(rejected_result.get("status") or "") in {"failed", "degraded_success"},
        "db_readback_validated": db_readback["accepted_material_count"] == 1
        and db_readback["rejected_material_count"] == 0,
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


def validate_production_like_handoff_evidence(evidence: Mapping[str, object]) -> dict[str, object]:
    checks = _object_mapping(evidence.get("validation_checks"))
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


def run_repo_local_production_like_handoff_canary(*, project_key: str | None = None) -> dict[str, object]:
    run_id = uuid4().hex[:10]
    resolved_project_key = str(project_key or f"ingest_canary_{run_id}").strip().lower()
    accepted_url = f"https://example.com/production-like-{run_id}"
    rejected_url = f"https://example.com/search?q=search-shell-{run_id}"
    schema_name = _prepare_project_schema(resolved_project_key)
    cleanup: dict[str, object] = {"schema_name": schema_name, "performed": False, "error": None}
    result: dict[str, object] | None = None
    try:
        from app.main import app
        from fastapi.testclient import TestClient

        with (
            patch("app.services.source_library.resolver.list_effective_channels", side_effect=_fake_list_channels),
            patch("app.services.source_library.resolver.run_item_with_url_routing", side_effect=_fake_routing(run_id=run_id)),
            patch("app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction", side_effect=_fake_structured_extraction),
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", resolved_project_key),
        ):
            client = _require_http_client(TestClient(app, raise_server_exceptions=False))
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
        db_readback = _readback_materials(
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

        accepted_postprocess = _object_mapping(accepted_result.get("postprocess_frontdoor"))
        accepted_ingress = _object_mapping(accepted_result.get("frontdoor_ingress"))
        accepted_data = _object_mapping(accepted_postprocess.get("data"))
        writer_result = _object_mapping(accepted_data.get("writer_result"))
        validated_handoff = build_single_url_canary_handoff(
            ingress_envelope=accepted_ingress,
            postprocess_frontdoor=accepted_postprocess,
            writer_result=writer_result,
            live_canary_evidence=evidence,
            live_canary_validated=validation.get("passed") is True,
            closure_claim=False,
        )
        result = {
            "contract_version": PRODUCTION_LIKE_HANDOFF_CHECK_CONTRACT_VERSION,
            "status": "passed" if validation.get("passed") is True else "failed",
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
