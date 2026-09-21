"""Focused witnesses for the W05-N4 C6.3 typed-total failure repair."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from mrw_functorial_kit.core import (
    successor_capability_contract_failures,
)

from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities.agent_core_c6_3 import (
    _apply_classification,
    _contract_failure,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    RedactionBindingMismatch,
    _require_exact_redaction_binding,
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
from app.successor_runtime.runtime.assignments import InterpreterBinding

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
C6_3_FILES = {
    "agent_core_c6_3.py",
    "agent_core_c6_3_interpreters.py",
    "agent_core_c6_3_program.py",
}


def test_w05_n4_c63_typed_contract_failures() -> None:
    failure = _contract_failure(
        "digest_contract_invalid",
        "digest drift",
        field="fixture",
    )

    assert successor_capability_contract_failures.matches(failure)
    assert failure.family == "successor.capability.contract_failure"
    assert failure.code == "digest_contract_invalid"
    assert failure.context is not None
    assert failure.context["owner"] == "agent_core.c6_3.v1"
    assert failure.context["effect_boundary"] == ("agent_core.c6_3.contract_core")
    assert failure.context["boundary_class"] == "PURE_CONTRACT_FAILURE"
    assert failure.context["failure_family"] == failure.family
    assert failure.context["witness"] == "test:test_w05_n4_c63_typed_contract_failures"
    assert failure.context["field"] == "fixture"


def test_w05_n4_c63_sensitive_classification_returns_closed_value() -> None:
    outcome = _apply_classification(
        {"api_key": "raw-secret"},
        path="",
        classifications={},
        redacted_paths=[],
        omitted_paths=[],
        fingerprints=[],
        suppressed_values=[],
    )

    assert isinstance(outcome, c6_3.RedactionFailure)
    assert outcome.code == "SensitiveFieldUnclassified"
    assert outcome.message == ("sensitive field is not classified by the bound policy: api_key")
    assert outcome.retryable is False
    assert outcome.disposition == "FAILED"


def test_w05_n4_c63_redaction_propagates_closed_sensitive_value() -> None:
    scope = ProjectScope("demo_proj", 1, "demo_schema", "inc-1", "")
    raw = {"api_key": "raw-secret"}
    policy = c6_3.RedactionPolicyRef(
        policy_id="policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest("policy", "1", {}),
    )
    payload = c6_3.RedactionEvidencePayload(
        schema_version=c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
        operation_kind=c6_3.AGENT_CORE_C6_3_KIND,
        project_scope=scope,
        source_observation_ref="project-value:source",
        source_observation_digest=c6_3.source_observation_digest(raw),
        source_kind="agent_core.tool_event",
        trace_id="trace",
        request_id="request",
        call_id="call",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications={},
        max_input_bytes=1024,
        max_event_batch=1,
    )

    outcome = c6_3.redact_observation(payload, raw)

    assert isinstance(outcome, c6_3.RedactionFailure)
    assert outcome.code == "SensitiveFieldUnclassified"
    assert outcome.message == ("sensitive field is not classified by the bound policy: api_key")


def test_w05_n4_c63_public_binding_lift_preserves_type_message_and_metadata() -> None:
    scope = ProjectScope("demo_proj", 1, "demo_schema", "inc-1", "")
    raw = {"visible": "value"}
    policy = c6_3.RedactionPolicyRef(
        policy_id="policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest("policy", "1", {}),
    )
    payload = c6_3.RedactionEvidencePayload(
        schema_version=c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
        operation_kind=c6_3.AGENT_CORE_C6_3_KIND,
        project_scope=scope,
        source_observation_ref="project-value:source",
        source_observation_digest=c6_3.source_observation_digest(raw),
        source_kind="agent_core.tool_event",
        trace_id="trace",
        request_id="request",
        call_id="call",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications={},
        max_input_bytes=1024,
        max_event_batch=1,
    )
    bundle = c6_3.build_agent_core_c6_3_bundle()
    catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
    registry = c6_3.build_agent_core_c6_3_registry(bundle)
    built = build_agent_core_c6_3_program(
        payload=payload,
        catalog=catalog,
        program_id="w05-n4",
        project_key=scope.project_key,
        project_registry_revision=scope.registry_revision,
        project_scope_digest=scope.scope_digest,
    )
    plan = compile_agent_core_c6_3_program(
        built,
        catalog,
        operation_contracts=registry,
    )
    contract_ref = registry.resolve_required(built.root.operation.contract_ref).ref
    payload_ref = payload_value_ref(
        payload,
        program_id=built.program_id,
        project_key=scope.project_key,
    )
    binding = InterpreterBinding.from_content(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=scope.scope_digest,
        resource_policy_epoch=1,
        authority_requirement_digest=authority_requirement_digest(),
    )
    drifted_binding = binding.model_copy(update={"binding_digest": "not-hex64"})
    arguments = {
        "program": built,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": payload_ref,
        "payload": payload,
        "project_scope": scope,
        "catalog": catalog,
        "deployment_catalog_digest": c6_deployment_catalog_digest(),
        "binding": drifted_binding,
    }

    internal = _require_exact_redaction_binding(**arguments)
    message = "C6.3 redaction binding drift: binding digest"

    assert successor_capability_contract_failures.matches(internal)
    assert internal.message == message
    assert internal.context is not None
    assert internal.context["drifts"] == ["binding digest"]
    assert internal.context["public_exception"] == "RedactionBindingMismatch"
    assert internal.context["boundary_class"] == "PURE_CONTRACT_FAILURE"
    assert internal.context["witness"] == ("test:test_w05_n4_c63_typed_contract_failures")
    with pytest.raises(RedactionBindingMismatch, match="^C6\\.3.*binding digest$"):
        require_exact_redaction_binding(**arguments)


def test_w05_n4_c63_retained_boundary_metadata_is_complete() -> None:
    checked = 0
    root = REPO_ROOT / "main/backend/app/successor_runtime/capabilities"
    for filename in C6_3_FILES:
        path = root / filename
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            checked += 1
            metadata = lines[node.lineno - 2].strip()
            assert metadata.startswith("# kit:boundary owner=agent_core_c6_3.py ")
            assert "class=LEGACY_COMPATIBILITY_EXCEPTION" in metadata
            assert "failure_family=successor.capability.contract_failure" in metadata
            assert "witness=test:test_w05_n4_c63_typed_contract_failures" in metadata
    assert checked == 1
