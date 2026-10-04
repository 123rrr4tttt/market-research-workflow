"""P3 C2.3 typed contract, profile, codec, port and redaction tests."""

from __future__ import annotations

import re
from typing import Any

import dataclasses
import pytest

from app.successor_runtime.capabilities import source_resolution as c21
from app.successor_runtime.capabilities import source_planning as c22
from app.successor_runtime.capabilities import source_planning_interpreters as c22i
from app.successor_runtime.capabilities import source_provider_acquisition as c23
from app.successor_runtime.capabilities import source_contracts as c2_shared
from app.successor_runtime.capabilities import (
    source_provider_ports as c23_ports,
)
from app.successor_runtime.capabilities import (
    source_provider_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_resolution import (
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    resolve_source_execution_request,
)

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = c21.project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)
ORCHESTRATION_POLICY_REF = "mrw.source.plan-source-mode.policy.v2"


def _effect_request() -> c23.ProviderEffectRequest:
    channels = [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
            "extra": {"credential_refs": ["credential:/secret-ref/hc-api-key"]},
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
    ]
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {
            "stable_handler_cluster": True,
            "expected_entry_type": "search_template",
        },
        "revision": 3,
        "incarnation": "item-inc-3",
    }
    item["content_digest"] = source_item_definition_content_digest(item)
    payload = c21.payload_from_dicts(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        channels=channels,
        item=item,
        params={
            "query_terms": ["robotics"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    )
    resolved = resolve_source_execution_request(payload)
    assert isinstance(resolved, c21.ResolvedResolution)
    request = resolved.request
    planning = c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22i.kind_for_mode(request.source_mode.mode),
        project_scope=request.project_scope,
        execution_request=request,
        execution_request_digest=content_digest(request.to_plain()),
        catalog=payload.catalog,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        orchestration_policy_ref=ORCHESTRATION_POLICY_REF,
        resource_ceiling_digest=c21.resource_ceiling_digest(),
    )
    plan = c22i.plan_source_mode(planning)
    assert isinstance(plan, c22.PlannedPlanning)
    return plan.plan.ordered_tasks[0].effect_request


def _bundle() -> c23.SourceProviderAcquisitionCapabilityBundle:
    return c23.build_source_provider_acquisition_bundle()


def test_c2_3_bundle_contract_profiles_and_registry() -> None:
    bundle = _bundle()
    catalog = c23.build_source_provider_acquisition_catalog(bundle)
    registry = c23.build_source_provider_acquisition_registry(bundle)
    contract = bundle.operation
    assert contract.ref.kind == "source_library.execute_provider_effect.v1"
    assert contract.owner_capability_id == c23.SOURCE_PROVIDER_ACQUISITION_OWNER
    assert catalog.lookup(contract.ref.kind) == contract.ref
    assert registry.resolve_required(contract.ref).ref == contract.ref
    assert bundle.profiles["effect"].execution_class == "EFFECTFUL"
    assert bundle.profiles["effect"].network_required is False
    assert bundle.profiles["failure"].unknown_outcome_supported is True
    assert "OUTCOME_UNKNOWN" in bundle.profiles["failure"].typed_failures
    assert bundle.profiles["failure"].readback_or_compensation == (
        "authoritative_readback_or_reconcile"
    )
    assert bundle.profiles["authority"].canonical_owner == c23.SOURCE_PROVIDER_ACQUISITION_OWNER


def test_payload_codec_roundtrip_is_exact() -> None:
    bundle = _bundle()
    request = _effect_request()
    codec = bundle.payload_codec()
    encoded = codec.encode_payload(request)
    decoded = codec.decode_payload(encoded)
    # C2.1 and shared mirror the scope DTO as distinct frozen classes; the
    # canonical plain projection is the exact cross-class equality contract.
    assert decoded.to_plain() == request.to_plain()
    assert decoded.request_digest == request.request_digest
    assert "SECRET" not in str(encoded)


def test_historical_provider_payload_is_explicit_and_keeps_digest() -> None:
    current = _effect_request()
    historical_refs = tuple(
        dataclasses.replace(
            ref,
            schema_version=c2_shared.CREDENTIAL_REF_HISTORICAL_SCHEMA,
        )
        for ref in current.credential_refs
    )
    historical_policy = dataclasses.replace(
        current.policy,
        schema_version=c2_shared.RESOURCE_POLICY_HISTORICAL_SCHEMA,
    )
    historical = dataclasses.replace(
        current,
        schema_version=c23.SOURCE_PROVIDER_ACQUISITION_HISTORICAL_PAYLOAD_SCHEMA,
        credential_refs=historical_refs,
        policy=historical_policy,
        request_digest="",
    )
    encoded = historical.to_plain()
    with pytest.raises(ValueError, match="historical provider acquisition payload"):
        _bundle().payload_codec().decode_payload(encoded)
    decoded = c23.provider_effect_request_from_historical_plain(encoded)
    assert decoded.to_plain() == encoded
    assert decoded.request_digest == historical.request_digest

    wrong_version = dict(encoded)
    wrong_version["schema_version"] = "mrw.source.unknown.v9"
    with pytest.raises(ValueError, match="exact C2 schema"):
        c23.provider_effect_request_from_historical_plain(wrong_version)


def test_historical_provider_receipt_keeps_original_digest_preimage() -> None:
    values = {
        "receipt_id": "receipt:historical-provider",
        "provider": "fixture",
        "provider_job_id": "job:historical-provider",
        "provider_status": "COMPLETED",
        "attempt_ref": "provider-attempt:historical-provider",
        "observed_at": "2026-09-02T00:00:00.000Z",
        "provider_job_uri": None,
    }
    historical_digest = c23.provider_receipt_digest(
        **values,
        schema_version=c2_shared.PROVIDER_RECEIPT_HISTORICAL_SCHEMA,
    )
    receipt = c23.ProviderReceipt(
        **values,
        schema_version=c2_shared.PROVIDER_RECEIPT_HISTORICAL_SCHEMA,
        receipt_digest=historical_digest,
    )
    assert receipt.receipt_digest == historical_digest
    assert historical_digest != c23.provider_receipt_digest(**values)
    encoded = receipt.to_plain()
    with pytest.raises(ValueError, match="historical provider receipt"):
        c23.provider_receipt_from_plain(encoded)
    decoded = c23.provider_receipt_from_historical_plain(encoded)
    assert decoded.to_plain() == encoded

    wrong_version = dict(encoded)
    wrong_version["schema_version"] = "mrw.source.unknown.v9"
    with pytest.raises(ValueError, match="exact C2 schema"):
        c23.provider_receipt_from_historical_plain(wrong_version)


def _no_secret_scan(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _no_secret_scan(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _no_secret_scan(item, f"{path}[{index}]")
    elif isinstance(value, str):
        assert value == value.strip(), f"whitespace string at {path}: {value!r}"
        if re.fullmatch(r"[0-9a-fA-F]{32,}", value):
            raise AssertionError(f"high-entropy bare hex at {path}")
        if re.fullmatch(r"[A-Za-z0-9+/]{40,}={0,2}", value):
            raise AssertionError(f"high-entropy base64-like token at {path}")
        if "SECRET" in value.upper() and not value.startswith("credential:/"):
            raise AssertionError(f"secret-like raw value at {path}: {value!r}")


def test_request_never_contains_secret_bytes() -> None:
    request = _effect_request()
    plain = request.to_plain()
    _no_secret_scan(plain["credential_refs"])
    for ref in request.credential_refs:
        assert ref.ref.startswith("credential:/")
        assert ref.ref == ref.ref.strip()


def test_ports_are_runtime_checkable_protocols() -> None:
    assert isinstance(c23_ports.CredentialResolverPort, type)
    assert isinstance(c23_ports.ProviderEffectPort, type)
    assert isinstance(c23_ports.ProviderReadbackPort, type)
    assert isinstance(c23_ports.ProviderEffectGateway, type)


def test_fixture_credential_resolver_redacts_and_rejects_missing() -> None:
    request = _effect_request()
    resolver = c23_fixtures.FixtureCredentialResolverPort(
        resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"},
    )
    ref = request.credential_refs[0]
    resolved = resolver.resolve(ref, {"authority": "fixture"})
    assert isinstance(resolved, c23_ports.EphemeralCredentialLease)
    assert resolved.credential_decision_receipt.decision == "RESOLVED"
    assert "value" not in str(resolved.to_plain()).lower()

    missing_resolver = c23_fixtures.FixtureCredentialResolverPort(
        resolved_refs={},
    )
    rejected = missing_resolver.resolve(ref, {"authority": "fixture"})
    assert isinstance(rejected, c23_ports.RedactedCredentialRejection)
    assert rejected.code == "MISSING_CREDENTIAL"
    assert rejected.credential_decision_receipt is not None
    assert rejected.credential_decision_receipt.decision == "MISSING"


def test_gateway_rejects_missing_credential_with_zero_provider_calls() -> None:
    request = _effect_request()
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(resolved_refs={}),
        effect=c23_fixtures.FixtureProviderEffectPort(),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    outcome = gateway.execute(request, {"authority": "fixture"})
    assert isinstance(outcome, c23.RejectedProviderEffect)
    assert outcome.code == "MISSING_CREDENTIAL"
    assert gateway.provider_calls == []


def test_scripted_outcomes_are_deterministic_and_traced() -> None:
    request = _effect_request()
    attempt = c23_fixtures.build_fixture_attempt_ref(request)
    completed = c23_fixtures.build_deterministic_completed_outcome(
        request, attempt_ref=attempt
    )
    again = c23_fixtures.build_deterministic_completed_outcome(
        request, attempt_ref=attempt
    )
    assert completed.outcome_digest == again.outcome_digest
    assert completed.receipt.receipt_digest == again.receipt.receipt_digest
    assert c23.provider_effect_outcomes_equal(completed, again)

    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(
            outcomes={request.request_id: completed}
        ),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    outcome = gateway.execute(request, {"authority": "fixture"})
    assert isinstance(outcome, c23.CompletedProviderEffect)
    assert gateway.provider_calls == [request.request_id]
