"""Pure URL contract-version and exact readback witnesses."""

from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace
from typing import cast

import pytest
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine

import app.composition.production as production
import app.composition.url_pool_readback as readback
from app.successor_runtime.capabilities.acquisition_url import (
    LegacyUrlSingleUrlOutcome,
    URL_SINGLE_URL_KIND,
    UrlSingleUrlOutcome,
    _canonical_json_value,
    build_url_single_url_contract_version,
    build_url_single_url_contract_versions,
    build_url_single_url_contracts,
)


def _payload_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_contract_projection_and_codecs_come_from_one_version_tuple() -> None:
    versions = build_url_single_url_contract_versions()
    contracts = build_url_single_url_contracts()

    assert tuple(version.contract for version in versions) == contracts
    assert tuple(item.ref.contract_version for item in contracts) == (
        "1.0.0",
        "1.1.0",
        "2.0.0",
    )
    assert [version.request_codec.payload_type_id for version in versions] == [
        "UrlSingleUrlRequest.v1",
        "UrlSingleUrlRequest.v1",
        "UrlSingleUrlRequest.v2",
    ]
    assert [version.outcome_codec.payload_type_id for version in versions] == [
        "UrlSingleUrlOutcome.v1",
        "UrlSingleUrlOutcome.v1",
        "UrlSingleUrlOutcome.v2",
    ]

    for version in versions[:2]:
        request = version.decode_request(
            _payload_bytes(
                {"url": "https://example.test/report", "project_key": "demo"}
            )
        )
        outcome = version.decode_outcome(
            _payload_bytes(
                {
                    "status": "completed",
                    "inserted": 1,
                    "updated": 0,
                    "skipped": 0,
                    "document_id": 41,
                }
            )
        )
        assert isinstance(request.url, str)
        assert isinstance(outcome, LegacyUrlSingleUrlOutcome)
        assert outcome.document_id == 41

    current = versions[2].decode_outcome(
        _payload_bytes(
            {
                "status": "completed",
                "inserted": 1,
                "updated": 0,
                "skipped": 0,
                "material_id": 42,
            }
        )
    )
    assert isinstance(current, UrlSingleUrlOutcome)
    assert current.material_id == 42


def test_unknown_contract_ref_fails_closed_without_legacy_or_current_codec() -> None:
    current = build_url_single_url_contract_versions()[-1]
    drifted = replace(current.contract.ref, contract_digest="0" * 64)

    with pytest.raises(ValueError, match="unknown exact operation contract ref"):
        build_url_single_url_contract_version(drifted)


def test_invalid_payload_roots_preserve_legacy_public_exceptions() -> None:
    current = build_url_single_url_contract_versions()[-1]

    with pytest.raises(
        TypeError,
        match="^URL runtime request root is not an object$",
    ):
        current.decode_request(b"[]")
    with pytest.raises(
        TypeError,
        match="^URL runtime output root is not an object$",
    ):
        current.decode_outcome(b"[]")
    with pytest.raises(
        TypeError,
        match="^runtime output is not canonical JSON$",
    ):
        _canonical_json_value({1: "invalid-key"})


def _install_runtime(
    monkeypatch: MonkeyPatch,
    *,
    contract_index: int,
    state: str,
    outcome: object | None = None,
    material: dict[str, object] | None = None,
    grant: bool = True,
) -> SimpleNamespace:
    version = build_url_single_url_contract_versions()[contract_index]
    request = {"url": "https://example.test/report", "project_key": "demo"}
    outcome = (
        outcome
        if outcome is not None
        else UrlSingleUrlOutcome(
            status="completed",
            inserted=1,
            updated=0,
            skipped=0,
            material_id=42,
        )
    )
    calls = SimpleNamespace(
        program=0, inputs=0, outputs=0, failures=0, material=0, grant=0
    )

    def read_program(**_kwargs: object) -> tuple[
        dict[str, object],
        tuple[dict[str, object], ...],
        tuple[()],
    ]:
        calls.program += 1
        return (
            {"run_id": "run-1", "project_key": "demo", "state": state},
            (
                {
                    "step_id": "url-step",
                    "operation_kind": URL_SINGLE_URL_KIND,
                    "operation_contract_ref": version.contract.ref,
                },
            ),
            (),
        )

    def read_inputs(**_kwargs: object) -> tuple[
        tuple[tuple[object, bytes], ...],
        tuple[()],
    ]:
        calls.inputs += 1
        return ((object(), _payload_bytes(request)),), ()

    def read_outputs(**_kwargs: object) -> tuple[tuple[str, object, bytes], ...]:
        calls.outputs += 1
        return (
            (
                "url-step",
                object(),
                _payload_bytes(version.outcome_codec.encode_payload(outcome)),
            ),
        )

    def read_failures(**_kwargs: object) -> tuple[tuple[int, object], ...]:
        calls.failures += 1
        return (
            (
                1,
                SimpleNamespace(
                    domain_failure=None,
                    failure_code="URL_POOL_EXECUTION_FAILED",
                    attempt_id="attempt-1",
                    failure_digest="a" * 64,
                ),
            ),
        )

    def read_material(
        _project_key: str,
        material_id: int,
        _url: str,
    ) -> dict[str, object] | None:
        calls.material += 1
        return material if material is not None else None

    def read_grant(**_kwargs: object) -> bool:
        calls.grant += 1
        return grant

    monkeypatch.setattr(production, "read_installed_program", read_program)
    monkeypatch.setattr(
        production, "read_installed_program_input_bindings", read_inputs
    )
    monkeypatch.setattr(production, "read_installed_program_outputs", read_outputs)
    monkeypatch.setattr(production, "read_installed_program_failures", read_failures)
    monkeypatch.setattr(readback, "read_url_pool_material", read_material)
    monkeypatch.setattr(
        readback, "url_pool_capability_grant_is_current", read_grant
    )
    return calls


def _locator(**overrides: object) -> readback.UrlPoolReadbackLocator:
    values: dict[str, object] = {
        "project_key": "demo",
        "actor_id": "actor-1",
        "run_id": "run-1",
        "submission_project_key": "demo",
        "submission_runtime_run_ref": "runtime-run:run-1",
        "submitted_url": "https://example.test/report",
    }
    values.update(overrides)
    return readback.UrlPoolReadbackLocator(**values)


def _read(
    locator: readback.UrlPoolReadbackLocator | None = None,
) -> readback.UrlPoolRuntimeEvidence:
    return readback.read_url_pool_evidence(
        locator or _locator(),
        engine=cast(Engine, object()),
    )


def test_completed_current_outcome_requires_exact_material_readback(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _install_runtime(
        monkeypatch,
        contract_index=2,
        state="COMPLETED",
        material={
            "project_key": "demo",
            "material_id": 42,
            "matched_url": "https://example.test/report",
        },
    )

    evidence = _read()

    assert evidence.verified is True
    assert evidence.historical is False
    assert evidence.material is not None
    assert evidence.material["material_id"] == 42
    assert calls.material == 1


def test_completed_current_outcome_without_material_stays_unverified(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, contract_index=2, state="COMPLETED")

    evidence = _read()

    assert evidence.verified is False
    assert evidence.pending is False
    assert evidence.error is not None
    assert evidence.error["code"] == "url_pool_material_readback_mismatch"


def test_completed_historical_outcome_is_observable_without_material_claim(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _install_runtime(
        monkeypatch,
        contract_index=0,
        state="COMPLETED",
        outcome=LegacyUrlSingleUrlOutcome(
            status="completed",
            inserted=1,
            updated=0,
            skipped=0,
            document_id=41,
        ),
    )

    evidence = _read()

    assert evidence.historical is True
    assert evidence.verified is False
    assert evidence.outcome is not None
    assert evidence.outcome["historical"] is True
    assert calls.material == 0


@pytest.mark.parametrize(
    ("state", "expected_code", "expected_pending"),
    [
        ("RUNNING", None, True),
        ("FAILED", "url_pool_runtime_failed", False),
        ("CANCELLED", "url_pool_runtime_cancelled", False),
        ("SUPERSEDED", "url_pool_runtime_superseded", False),
        ("UNKNOWN", "url_pool_runtime_state_unknown", False),
    ],
)
def test_runtime_states_remain_distinct(
    monkeypatch: MonkeyPatch,
    state: str,
    expected_code: str | None,
    expected_pending: bool,
) -> None:
    calls = _install_runtime(monkeypatch, contract_index=2, state=state)

    evidence = _read()

    assert evidence.verified is False
    assert evidence.pending is expected_pending
    if expected_code is None:
        assert evidence.error is None
        assert calls.outputs == 0
        assert calls.failures == 0
    else:
        assert evidence.error is not None
        assert evidence.error["code"] == expected_code
        assert calls.outputs == 0


def test_runtime_run_identity_and_request_mismatch_stay_exact(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, contract_index=2, state="COMPLETED")

    original_program = production.read_installed_program

    def wrong_run(**_kwargs: object) -> tuple[
        dict[str, object],
        tuple[dict[str, object], ...],
        tuple[()],
    ]:
        run, steps, events = original_program()
        return {**run, "run_id": "other-run"}, steps, events

    monkeypatch.setattr(production, "read_installed_program", wrong_run)
    wrong_run_evidence = _read()
    monkeypatch.setattr(production, "read_installed_program", original_program)

    original_inputs = production.read_installed_program_input_bindings

    def wrong_request(**_kwargs: object) -> tuple[
        tuple[tuple[object, bytes], ...],
        tuple[()],
    ]:
        static_inputs, started_inputs = original_inputs()
        wrong_bytes = _payload_bytes(
            {"url": "https://example.test/other", "project_key": "demo"}
        )
        return ((static_inputs[0][0], wrong_bytes),), started_inputs

    monkeypatch.setattr(
        production, "read_installed_program_input_bindings", wrong_request
    )
    wrong_request_evidence = _read()

    assert wrong_run_evidence.error is not None
    assert wrong_run_evidence.error["code"] == "url_pool_runtime_identity_mismatch"
    assert wrong_request_evidence.error is not None
    assert (
        wrong_request_evidence.error["code"] == "url_pool_runtime_request_mismatch"
    ), wrong_request_evidence.error


def test_readback_preserves_invalid_runtime_payload_root_exceptions(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, contract_index=2, state="COMPLETED")
    original_inputs = production.read_installed_program_input_bindings

    def invalid_request(**_kwargs: object) -> tuple[
        tuple[tuple[object, bytes], ...],
        tuple[()],
    ]:
        return ((object(), b"[]"),), ()

    monkeypatch.setattr(
        production, "read_installed_program_input_bindings", invalid_request
    )
    request_evidence = _read()
    monkeypatch.setattr(
        production, "read_installed_program_input_bindings", original_inputs
    )

    original_outputs = production.read_installed_program_outputs

    def invalid_output(**_kwargs: object) -> tuple[tuple[str, object, bytes], ...]:
        return (("url-step", object(), b"[]"),)

    monkeypatch.setattr(production, "read_installed_program_outputs", invalid_output)
    outcome_evidence = _read()

    assert request_evidence.error is not None
    assert request_evidence.error["exception"] == "TypeError"
    assert request_evidence.error["message"] == (
        "URL-pool canonical runtime readback failed: "
        "URL runtime request root is not an object"
    )
    assert outcome_evidence.error is not None
    assert outcome_evidence.error["exception"] == "TypeError"
    assert outcome_evidence.error["message"] == (
        "URL-pool canonical runtime readback failed: "
        "URL runtime output root is not an object"
    )


def test_completed_current_outcome_must_be_a_completed_material_outcome(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_runtime(
        monkeypatch,
        contract_index=2,
        state="COMPLETED",
        outcome=UrlSingleUrlOutcome(
            status="accepted",
            inserted=0,
            updated=0,
            skipped=0,
            material_id=None,
        ),
    )

    evidence = _read()

    assert evidence.verified is False
    assert evidence.error is not None
    assert evidence.error["code"] == "url_pool_runtime_output_incomplete"


def test_failed_without_effect_rows_is_not_downgraded_to_cancelled(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _install_runtime(monkeypatch, contract_index=2, state="FAILED")

    def no_failures(**_kwargs: object) -> tuple[()]:
        calls.failures += 1
        return ()

    monkeypatch.setattr(production, "read_installed_program_failures", no_failures)
    evidence = _read()

    assert evidence.error is not None
    assert evidence.error["code"] == "url_pool_runtime_failure_rows_missing"
    assert evidence.failure_rows == ()


def test_submission_and_grant_checks_precede_runtime_reads(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _install_runtime(monkeypatch, contract_index=2, state="COMPLETED", grant=False)

    missing_project = _read(_locator(submission_project_key="other"))
    missing_ref = _read(_locator(submission_runtime_run_ref=""))
    no_grant = _read()

    assert missing_project.error is not None
    assert missing_project.error["code"] == "url_pool_submission_project_mismatch"
    assert missing_ref.error is not None
    assert missing_ref.error["code"] == "url_pool_runtime_run_ref_missing"
    assert no_grant.error is not None
    assert no_grant.error["code"] == "url_pool_runtime_capability_grant_required"
    assert calls.program == 0
