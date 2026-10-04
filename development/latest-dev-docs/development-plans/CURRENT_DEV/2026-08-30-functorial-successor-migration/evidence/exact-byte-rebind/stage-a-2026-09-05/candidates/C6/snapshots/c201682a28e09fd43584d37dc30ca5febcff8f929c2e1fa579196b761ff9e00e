"""P3 C6.3 pre-persistence redaction/receipt contracts and replay."""

from __future__ import annotations

import json

import pytest

from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    RedactionBindingMismatch,
    VersionedRedactionEvidenceInterpreter,
    authority_requirement_digest,
    require_exact_redaction_binding,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_3_program import (
    build_agent_core_c6_3_program,
    compile_agent_core_c6_3_program,
    payload_value_ref,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    ProjectScope,
    c6_deployment_catalog_digest,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.program import decode_program_spec
from app.successor_runtime.runtime.assignments import InterpreterBinding

pytestmark = pytest.mark.unit

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = ProjectScope(
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_INCARNATION,
    "",
).scope_digest
SENTINEL = "mrw-c6-3-raw-secret::api_key=fixture-key;cookie=session-cookie"
FIELD_CLASSIFICATIONS = {
    "provider.request": "REDACT",
    "provider.headers": "OMIT",
    "customer.id": "FINGERPRINT",
}


def _scope() -> ProjectScope:
    return ProjectScope(
        PROJECT_KEY,
        REGISTRY_REVISION,
        RESOLVED_SCHEMA,
        SCOPE_INCARNATION,
        "",
    )


def _policy() -> c6_3.RedactionPolicyRef:
    return c6_3.RedactionPolicyRef(
        policy_id="c6-3-redaction-policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest(
            "c6-3-redaction-policy", "1", FIELD_CLASSIFICATIONS
        ),
    )


def _raw_observation() -> dict[str, object]:
    return {
        "provider": {
            "request": {"body": SENTINEL, "url": "https://provider.example"},
            "headers": {"authorization": "Bearer fixture-token"},
        },
        "customer": {"id": "customer-42"},
        "notes": "visible observation text",
    }


def _payload(**overrides) -> c6_3.RedactionEvidencePayload:
    raw = _raw_observation()
    values = {
        "schema_version": c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
        "operation_kind": c6_3.AGENT_CORE_C6_3_KIND,
        "project_scope": _scope(),
        "source_observation_ref": "project-value:source:c6-3",
        "source_observation_digest": c6_3.source_observation_digest(raw),
        "source_kind": "agent_core.tool_event",
        "trace_id": "trace-c6-3",
        "request_id": "req-c6-3",
        "call_id": "call-c6-3",
        "interpreter_profile_ref": "successor.agent_core.c6_3.redaction.v1",
        "policy": _policy(),
        "field_classifications": FIELD_CLASSIFICATIONS,
        "max_input_bytes": c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
        "max_event_batch": c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
    }
    values.update(overrides)
    return c6_3.RedactionEvidencePayload(**values)


def _catalog_and_registry():
    bundle = c6_3.build_agent_core_c6_3_bundle()
    catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
    registry = c6_3.build_agent_core_c6_3_registry(bundle)
    return bundle, catalog, registry


def _program(payload):
    _bundle, catalog, _registry = _catalog_and_registry()
    return build_agent_core_c6_3_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-3.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )


def _plan(program):
    _bundle, catalog, registry = _catalog_and_registry()
    return compile_agent_core_c6_3_program(
        program, catalog, operation_contracts=registry
    )


def _binding(contract_ref):
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=authority_requirement_digest(),
    )


def test_redaction_receipt_omits_raw_values_and_binds_policy() -> None:
    payload = _payload()
    receipt = c6_3.redact_observation(payload, _raw_observation())
    assert isinstance(receipt, c6_3.RedactionReceipt)
    plain = json.dumps(receipt.to_plain(), sort_keys=True)
    assert SENTINEL not in plain
    assert "fixture-token" not in plain
    evidence = receipt.evidence
    assert evidence.raw_value_persisted is False
    assert "provider.request" in evidence.redacted_field_paths
    assert "provider.headers" in evidence.omitted_field_paths
    fingerprints = dict(evidence.fingerprint_entries)
    assert "customer.id" in fingerprints
    assert "visible observation text" in plain
    assert (
        dict(receipt.policy_application_receipt)["applied_before_persistence"] is True
    )
    plain_body = {
        key: value
        for key, value in receipt.to_plain().items()
        if key != "receipt_digest"
    }
    assert receipt.receipt_digest == content_digest(plain_body)


def test_redaction_replay_is_deterministic() -> None:
    first = c6_3.redact_observation(_payload(), _raw_observation())
    second = c6_3.redact_observation(_payload(), _raw_observation())
    assert isinstance(first, c6_3.RedactionReceipt)
    assert isinstance(second, c6_3.RedactionReceipt)
    assert first.receipt_digest == second.receipt_digest
    assert first.evidence.evidence_digest == second.evidence.evidence_digest


def test_redaction_failures_are_fail_closed() -> None:
    assert isinstance(
        c6_3.redact_observation(
            _payload(source_observation_digest="0" * 64), _raw_observation()
        ),
        c6_3.RedactionFailure,
    )
    raw = {"api_key": "raw-secret"}
    unclassified_payload = _payload(
        source_observation_digest=c6_3.source_observation_digest(raw),
        field_classifications={},
        policy=c6_3.RedactionPolicyRef(
            policy_id="c6-3-redaction-policy",
            policy_version="1",
            policy_digest=c6_3.redaction_policy_digest(
                "c6-3-redaction-policy", "1", {}
            ),
        ),
    )
    failure = c6_3.redact_observation(unclassified_payload, raw)
    assert isinstance(failure, c6_3.RedactionFailure)
    assert failure.code == "SensitiveFieldUnclassified"

    wrong_policy = _payload(
        policy=c6_3.RedactionPolicyRef(
            policy_id="c6-3-redaction-policy",
            policy_version="1",
            policy_digest=c6_3.redaction_policy_digest(
                "c6-3-redaction-policy", "1", {"other.path": "REDACT"}
            ),
        )
    )
    assert isinstance(
        c6_3.redact_observation(wrong_policy, _raw_observation()),
        c6_3.RedactionFailure,
    )
    small = _payload(max_input_bytes=16)
    assert isinstance(
        c6_3.redact_observation(small, _raw_observation()),
        c6_3.RedactionFailure,
    )


def test_payload_codec_round_trip_and_drift_rejection() -> None:
    bundle, _catalog, _registry = _catalog_and_registry()
    payload = _payload()
    codec = bundle.payload_codec()
    encoded = codec.encode_payload(payload)
    assert codec.decode_payload(encoded) == payload
    with_extra = dict(encoded)
    with_extra["unexpected"] = "x"
    with pytest.raises(ValueError, match="extra"):
        codec.decode_payload(with_extra)
    with_missing = {key: value for key, value in encoded.items() if key != "policy"}
    with pytest.raises(ValueError, match="missing"):
        codec.decode_payload(with_missing)


def test_program_plan_compile_and_binding_mismatch() -> None:
    payload = _payload()
    program = _program(payload)
    plan = _plan(program)
    _bundle, catalog, registry = _catalog_and_registry()
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    decoded = decode_program_spec(
        {
            "program": json.loads(program.canonical_json()),
            "program_digest": program.digest(),
        }
    )
    assert decoded.program_digest == program.program_digest
    assert plan.program_digest == program.program_digest
    assert c6_deployment_catalog_digest() != catalog.catalog_digest
    value_ref = payload_value_ref(
        payload,
        program_id=program.program_id,
        project_key=PROJECT_KEY,
    )
    binding = _binding(contract_ref)
    require_exact_redaction_binding(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=value_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=binding,
    )

    tampered = _program(_payload(trace_id="tampered"))
    with pytest.raises(RedactionBindingMismatch):
        require_exact_redaction_binding(
            program=tampered,
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=value_ref,
            payload=payload,
            project_scope=_scope(),
            catalog=catalog,
            deployment_catalog_digest=c6_deployment_catalog_digest(),
            binding=binding,
        )

    outcome = VersionedRedactionEvidenceInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=value_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=binding,
        raw_observation=_raw_observation(),
    )
    assert outcome.disposition == "SUCCEEDED"
    assert isinstance(outcome.value, c6_3.RedactionReceipt)
