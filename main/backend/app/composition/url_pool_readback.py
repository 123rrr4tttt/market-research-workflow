"""Exact URL-pool runtime and material readback composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeGuard, cast

from sqlalchemy.engine import Engine

from app.contracts.json import JSONObject, JSONValue
from app.successor_runtime.capabilities.acquisition_url import (
    LegacyUrlSingleUrlRequest,
    LegacyUrlSingleUrlOutcome,
    URL_SINGLE_URL_KIND,
    URL_SINGLE_URL_OWNER,
    UrlSingleUrlContractVersion,
    UrlSingleUrlRequest,
    UrlSingleUrlOutcome,
    build_url_single_url_contract_version,
)
from app.successor_runtime.language.object_contracts import OperationContractRef

UrlSingleUrlContractVersionBinding = (
    UrlSingleUrlContractVersion[LegacyUrlSingleUrlRequest, LegacyUrlSingleUrlOutcome]
    | UrlSingleUrlContractVersion[UrlSingleUrlRequest, UrlSingleUrlOutcome]
)


@dataclass(frozen=True, slots=True)
class UrlPoolRuntimeEvidence:
    run: JSONObject
    outcome: JSONObject | None = None
    material: JSONObject | None = None
    failure_rows: tuple[JSONObject, ...] = ()
    error: JSONObject | None = None
    pending: bool = False
    verified: bool = False
    historical: bool = False


@dataclass(frozen=True, slots=True)
class UrlPoolReadbackLocator:
    project_key: str
    actor_id: str
    run_id: str
    submission_project_key: str
    submission_runtime_run_ref: str
    submitted_url: str


def _json_value(value: object) -> JSONValue:
    if _is_string_key_mapping(value):
        return {str(key): _json_value(item) for key, item in value.items()}
    if _is_object_sequence(value):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(value)


def _json_object(value: object) -> JSONObject:
    normalized = _json_value(value)
    if not _is_json_object(normalized):
        return {}
    return {key: item for key, item in normalized.items()}


def _is_string_key_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    if not isinstance(value, Mapping):
        return False
    mapping = cast(Mapping[object, object], value)
    return all(isinstance(key, str) for key in mapping)


def _is_object_sequence(
    value: object,
) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, list | tuple)


def _is_json_object(value: JSONValue) -> TypeGuard[dict[str, JSONValue]]:
    return isinstance(value, dict)


def _error(code: str, message: str, **details: JSONValue) -> UrlPoolRuntimeEvidence:
    return UrlPoolRuntimeEvidence(
        run={},
        error={"code": code, "message": message, **details},
    )


def _run_error(
    run_view: JSONObject,
    code: str,
    message: str,
    **details: JSONValue,
) -> UrlPoolRuntimeEvidence:
    return UrlPoolRuntimeEvidence(
        run=run_view,
        error={"code": code, "message": message, **details},
    )


def _read_url_pool_runtime_url(
    *,
    engine: Engine,
    locator: UrlPoolReadbackLocator,
    contract_version: UrlSingleUrlContractVersionBinding,
) -> str:
    from app.composition.production import read_installed_program_input_bindings

    static_inputs, _started_inputs = read_installed_program_input_bindings(
        engine=engine,
        project_key=locator.project_key,
        actor_id=locator.actor_id,
        run_id=locator.run_id,
        static_input_type=contract_version.request_type,
    )
    if len(static_inputs) != 1:
        raise ValueError("URL runtime run does not have one exact request input")
    _request_ref, exact = static_inputs[0]
    request = contract_version.decode_request(exact)
    request_url = request.url.strip()
    if request.project_key != locator.project_key or not request_url:
        raise ValueError("URL runtime request identity does not match the project")
    return request_url


def read_url_pool_evidence(
    locator: UrlPoolReadbackLocator,
    *,
    engine: Engine,
) -> UrlPoolRuntimeEvidence:
    """Read one exact URL submission without deriving evidence from neighbors."""

    submission_project = locator.submission_project_key.strip()
    if submission_project and submission_project != locator.project_key:
        return _error(
            "url_pool_submission_project_mismatch",
            "URL-pool submission belongs to another project",
            submission_project=submission_project,
            project_key=locator.project_key,
        )

    runtime_ref = locator.submission_runtime_run_ref.strip()
    if (
        not runtime_ref.startswith("runtime-run:")
        or len(runtime_ref) <= len("runtime-run:")
    ):
        return _error(
            "url_pool_runtime_run_ref_missing",
            "async URL-pool submission has no exact runtime run reference",
            runtime_run_ref=runtime_ref,
        )
    run_id = runtime_ref.removeprefix("runtime-run:")
    if run_id != locator.run_id:
        return _error(
            "url_pool_runtime_identity_mismatch",
            "canonical URL runtime run identity does not match the submission",
        )

    try:
        from app.composition.production import (
            read_installed_program,
            read_installed_program_failures,
            read_installed_program_outputs,
        )

        if not url_pool_capability_grant_is_current(
            runtime_engine=engine,
            project_key=locator.project_key,
            actor_id=locator.actor_id,
            capability_id=URL_SINGLE_URL_OWNER,
        ):
            return _error(
                "url_pool_runtime_capability_grant_required",
                "URL-pool canonical runtime readback requires a current capability grant",
                capability_id=URL_SINGLE_URL_OWNER,
            )

        run, steps, _events = read_installed_program(
            engine=engine,
            project_key=locator.project_key,
            actor_id=locator.actor_id,
            run_id=run_id,
        )
        run_view = _json_object(run)
        if (
            str(run_view.get("run_id") or "") != run_id
            or str(run_view.get("project_key") or "") != locator.project_key
        ):
            return _run_error(
                run_view,
                "url_pool_runtime_identity_mismatch",
                "canonical URL runtime run identity does not match the submission",
            )

        url_steps = tuple(
            step
            for step in steps
            if str(step.get("operation_kind") or "") == URL_SINGLE_URL_KIND
        )
        if len(url_steps) != 1:
            return _run_error(
                run_view,
                "url_pool_runtime_contract_identity_invalid",
                "canonical URL runtime run does not have one exact URL contract ref",
                url_step_count=len(url_steps),
            )
        contract_ref_value = url_steps[0].get("operation_contract_ref")
        if not isinstance(contract_ref_value, OperationContractRef):
            return _run_error(
                run_view,
                "url_pool_runtime_contract_identity_invalid",
                "canonical URL runtime step lacks its exact operation contract ref",
            )
        contract_ref = contract_ref_value
        contract_version = build_url_single_url_contract_version(contract_ref)
        runtime_url = _read_url_pool_runtime_url(
            engine=engine,
            locator=locator,
            contract_version=contract_version,
        )
        if runtime_url != locator.submitted_url:
            return _run_error(
                run_view,
                "url_pool_runtime_request_mismatch",
                "canonical URL runtime request does not match the selected submission",
                submission_url=locator.submitted_url,
                runtime_url=runtime_url,
            )

        state = str(run_view.get("state") or "").strip().upper()
        if state in {"READY", "RUNNING", "WAITING", "RECONCILING", "CANCELLING"}:
            return UrlPoolRuntimeEvidence(run=run_view, pending=True)
        if state in {"FAILED", "CANCELLED", "SUPERSEDED"}:
            failure_rows = tuple(
                _json_object(
                    {
                        "sequence": sequence,
                        "failure_family": (
                            row.domain_failure.family
                            if row.domain_failure is not None
                            else None
                        ),
                        "failure_code": row.failure_code,
                        "reason": (
                            row.domain_failure.message
                            if row.domain_failure is not None
                            else row.failure_code
                        ),
                        "attempt_id": row.attempt_id,
                        "failure_digest": row.failure_digest,
                    }
                )
                for sequence, row in read_installed_program_failures(
                    engine=engine,
                    project_key=locator.project_key,
                    actor_id=locator.actor_id,
                    run_id=run_id,
                )
            )
            if state == "FAILED" and not failure_rows:
                return UrlPoolRuntimeEvidence(
                    run=run_view,
                    failure_rows=failure_rows,
                    error={
                        "code": "url_pool_runtime_failure_rows_missing",
                        "message": "failed canonical URL runtime run has no exact EffectFailed rows",
                        "state": state,
                    },
                )
            return UrlPoolRuntimeEvidence(
                run=run_view,
                failure_rows=failure_rows,
                error={
                    "code": {
                        "FAILED": "url_pool_runtime_failed",
                        "CANCELLED": "url_pool_runtime_cancelled",
                        "SUPERSEDED": "url_pool_runtime_superseded",
                    }[state],
                    "message": f"canonical URL runtime run is {state}",
                    "state": state,
                    "failure_count": len(failure_rows),
                },
            )
        if state != "COMPLETED":
            return _run_error(
                run_view,
                "url_pool_runtime_state_unknown",
                f"canonical URL runtime run has unverified state {state or 'UNKNOWN'}",
                state=state or "UNKNOWN",
            )

        outputs = read_installed_program_outputs(
            engine=engine,
            project_key=locator.project_key,
            actor_id=locator.actor_id,
            run_id=run_id,
        )
        url_step_ids = {str(url_steps[0].get("step_id") or "")}
        exact_outputs = [item for item in outputs if item[0] in url_step_ids]
        if len(url_step_ids) != 1 or len(exact_outputs) != 1:
            return _run_error(
                run_view,
                "url_pool_runtime_output_identity_invalid",
                "completed URL runtime run does not have one exact URL outcome",
                url_step_count=len(url_step_ids),
                output_count=len(exact_outputs),
            )

        _step_id, _value_ref, exact = exact_outputs[0]
        outcome = contract_version.decode_outcome(exact)
        contract_identity = _json_object(
            {
                "kind": contract_ref.kind,
                "contract_version": contract_ref.contract_version,
                "contract_digest": contract_ref.contract_digest,
            }
        )
        if isinstance(outcome, LegacyUrlSingleUrlOutcome):
            return UrlPoolRuntimeEvidence(
                run=run_view,
                outcome={
                    "status": outcome.status,
                    "inserted": outcome.inserted,
                    "updated": outcome.updated,
                    "skipped": outcome.skipped,
                    "error": outcome.error,
                    "task_id": outcome.task_id,
                    "operation_contract_ref": contract_identity,
                    "historical": True,
                },
                historical=True,
            )
        outcome_view: JSONObject = {
            "status": outcome.status,
            "inserted": outcome.inserted,
            "updated": outcome.updated,
            "skipped": outcome.skipped,
            "material_id": outcome.material_id,
            "error": outcome.error,
            "task_id": outcome.task_id,
            "operation_contract_ref": contract_identity,
        }
        material_id = outcome_view.get("material_id")
        if (
            str(outcome_view.get("status") or "") != "completed"
            or not isinstance(material_id, int)
            or material_id <= 0
        ):
            return UrlPoolRuntimeEvidence(
                run=run_view,
                outcome=outcome_view,
                error={
                    "code": "url_pool_runtime_output_incomplete",
                    "message": "completed URL runtime run did not decode to a completed material outcome",
                },
            )
        material = read_url_pool_material(
            locator.project_key,
            material_id,
            locator.submitted_url,
        )
        if material is None:
            return UrlPoolRuntimeEvidence(
                run=run_view,
                outcome=outcome_view,
                error={
                    "code": "url_pool_material_readback_mismatch",
                    "message": "decoded URL material is absent or does not match the submitted project URL",
                    "material_id": material_id,
                },
            )
        return UrlPoolRuntimeEvidence(
            run=run_view,
            outcome=outcome_view,
            material=material,
            verified=True,
        )
    except Exception as exc:  # noqa: BLE001
        return _error(
            "url_pool_runtime_readback_failed",
            f"URL-pool canonical runtime readback failed: {exc}",
            exception=exc.__class__.__name__,
        )


def read_url_pool_material(
    project_key: str,
    material_id: int,
    url: str,
) -> JSONObject | None:
    """Read and exact-match one Material in the submitted project scope."""

    from sqlalchemy import select

    from app.models.base import SessionLocal
    from app.models.entities import Material, Source
    from app.services.projects import bind_project

    with bind_project(project_key), SessionLocal() as session:
        row = session.execute(
            select(Material.id, Material.uri, Material.extracted_data, Source.base_url)
            .join(Source, Material.source_id == Source.id, isouter=True)
            .where(Material.id == material_id)
        ).first()
    if row is None:
        return None
    material_url = str(row.uri or "").strip()
    source_url = str(row.base_url or "").strip()
    extracted_data: Mapping[str, object] = (
        row.extracted_data
        if _is_string_key_mapping(row.extracted_data)
        else {}
    )
    source_ref_value: object = extracted_data.get("source_ref")
    source_ref: Mapping[str, object] = (
        source_ref_value
        if _is_string_key_mapping(source_ref_value)
        else {}
    )
    persisted_request_urls = {
        str(source_ref.get(key) or "").strip()
        for key in ("url", "locator")
        if str(source_ref.get(key) or "").strip()
    }
    if url != material_url and url not in persisted_request_urls:
        return None
    match_kind = "material_uri" if url == material_url else "persisted_source_ref"
    return {
        "project_key": project_key,
        "material_id": int(row.id),
        "uri": material_url,
        "source_base_url": source_url,
        "matched_url": url,
        "match_kind": match_kind,
    }


def url_pool_capability_grant_is_current(
    *,
    runtime_engine: Engine,
    project_key: str,
    actor_id: str,
    capability_id: str,
) -> bool:
    """Check the current capability grant in the existing authority repository."""

    from app.successor_runtime.runtime.ports import RuntimeScope
    from app.successor_runtime.substrate.postgres.authority import (
        AuthorityGrantRepository,
    )
    from app.successor_runtime.substrate.postgres.session import (
        ServerProjectScopeResolver,
    )

    with runtime_engine.connect() as connection:
        project_scope = ServerProjectScopeResolver(connection=connection).resolve(
            project_key
        )
        scope = RuntimeScope(project_scope=project_scope, actor_id=actor_id)
        return bool(
            AuthorityGrantRepository(connection, scope).current_for(
                actor_id=actor_id,
                capability_id=capability_id,
                at=datetime.now(UTC),
            )
        )
