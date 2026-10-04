"""Focused tests for the closed production route-effect contract."""

# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from app.composition.production import load_production_route_bindings
from app.production_contract import (
    EffectAdmission,
    EffectClass,
    EndpointEffectContract,
    ProviderClass,
    RouteEffectContractError,
)


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("code", "kwargs"),
    [
        ("route_effect_unclassified", {"effect_class": "not-a-class"}),
        (
            "route_effect_mismatch",
            {"effect_class": "read", "conditional_discriminator": "kind"},
        ),
        ("provider_port_unbound", {"effect_class": "provider_call", "provider_class": "llm"}),
        ("provider_class_mismatch", {"effect_class": "provider_call", "provider_port": "llm-port"}),
        ("canonical_writer_port_unbound", {"effect_class": "canonical_write"}),
        ("legacy_writer_claimed_as_successor", {"effect_class": "legacy_write"}),
        ("conditional_effect_undiscriminated", {"effect_class": "conditional"}),
    ],
)
def test_effect_contract_failure_family_is_closed(code: str, kwargs: dict[str, object]) -> None:
    with pytest.raises(RouteEffectContractError) as exc_info:
        EndpointEffectContract(**kwargs)
    assert exc_info.value.code == code
    assert exc_info.value.failure.code == code


@pytest.mark.parametrize(
    "branches",
    [
        (),
        ("unknown",),
        ("external_or_legacy_effect", "no_effect_or_read"),
        ("no_effect_or_read", "external_or_legacy_effect", "extra"),
        ("no_effect_or_read", "no_effect_or_read", "external_or_legacy_effect"),
    ],
)
def test_conditional_branch_shape_is_closed(branches: tuple[str, ...]) -> None:
    with pytest.raises(RouteEffectContractError) as exc_info:
        EndpointEffectContract(
            effect_class=EffectClass.CONDITIONAL,
            conditional_discriminator="handler_effect_path.v1",
            conditional_branches=branches,
        )
    assert exc_info.value.code == "route_effect_mismatch"


def test_conditional_discriminator_vocabulary_is_closed() -> None:
    with pytest.raises(RouteEffectContractError) as exc_info:
        EndpointEffectContract(
            effect_class=EffectClass.CONDITIONAL,
            conditional_discriminator="unknown.v1",
            conditional_branches=("no_effect_or_read", "external_or_legacy_effect"),
        )
    assert exc_info.value.code == "route_effect_mismatch"


@pytest.mark.parametrize(
    ("kwargs", "port"),
    [
        ({"effect_class": "read", "provider_port": "provider.port.v1"}, "provider_port"),
        (
            {
                "effect_class": "external_auth",
                "external_auth_port": "auth.port.v1",
                "filesystem_port": "fs.port.v1",
            },
            "filesystem_port",
        ),
        (
            {
                "effect_class": "provider_call",
                "provider_class": "llm",
                "canonical_writer_port": "writer.port.v1",
            },
            "canonical_writer_port",
        ),
        (
            {
                "effect_class": "conditional",
                "conditional_discriminator": "handler_effect_path.v1",
                "conditional_branches": ["no_effect_or_read", "external_or_legacy_effect"],
                "filesystem_port": "fs.port.v1",
            },
            "filesystem_port",
        ),
    ],
)
def test_effect_class_rejects_foreign_ports(
    kwargs: dict[str, object], port: str
) -> None:
    with pytest.raises(RouteEffectContractError) as exc_info:
        EndpointEffectContract(**kwargs)
    assert exc_info.value.code == "route_effect_mismatch"
    assert exc_info.value.failure.context["details"]["port"] == port


def test_effect_contract_derives_provider_writer_and_approval_flags() -> None:
    provider = EndpointEffectContract(
        effect_class=EffectClass.PROVIDER_CALL,
        provider_port="provider.port.v1",
        provider_class="llm",
    )
    assert provider.requires_provider is True
    assert provider.requires_canonical_writer is False
    assert provider.approval_required is True

    writer = EndpointEffectContract(
        effect_class=EffectClass.CANONICAL_WRITE,
        canonical_writer_port="writer.port.v1",
    )
    assert writer.requires_provider is False
    assert writer.requires_canonical_writer is True
    assert writer.approval_required is True


def test_conditional_and_filesystem_effects_are_conservative_by_default() -> None:
    conditional = EndpointEffectContract(
        effect_class=EffectClass.CONDITIONAL,
        conditional_discriminator="handler_effect_path.v1",
        conditional_branches=("no_effect_or_read", "external_or_legacy_effect"),
    )
    assert conditional.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    assert conditional.admitted is False

    filesystem = EndpointEffectContract(effect_class=EffectClass.FILESYSTEM_SUBPROCESS)
    assert filesystem.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    assert filesystem.admitted is False


def test_v3_registry_rejects_missing_or_extra_effect_fields(tmp_path: Path) -> None:
    entry = {
        "route_template": "/example",
        "domain": "example",
        "operation": "example.read",
        "metrics_label": "example:/example",
        "methods": ["GET"],
        "required_scope": "api:invoke",
        "required_approval_ids": [],
        "capability_id": None,
        "effect_contract": {
            "effect_class": "read",
            "admission": "admitted",
            "provider_port": None,
            "provider_class": "null",
            "canonical_writer_port": None,
            "external_auth_port": None,
            "filesystem_port": None,
            "conditional_discriminator": None,
            "conditional_branches": [],
        },
    }
    payload = {"schema": "mrw.production.route-bindings.v3", "bindings": [entry], "exemptions": []}
    missing = tmp_path / "missing.json"
    missing_payload = json.loads(json.dumps(payload))
    del missing_payload["bindings"][0]["effect_contract"]["provider_port"]
    missing.write_text(json.dumps(missing_payload), encoding="utf-8")
    with pytest.raises(RouteEffectContractError) as missing_exc:
        load_production_route_bindings(missing)
    assert missing_exc.value.code == "route_effect_unclassified"

    extra = tmp_path / "extra.json"
    extra_payload = json.loads(json.dumps(payload))
    extra_payload["bindings"][0]["effect_contract"]["unexpected"] = None
    extra.write_text(json.dumps(extra_payload), encoding="utf-8")
    with pytest.raises(RouteEffectContractError) as extra_exc:
        load_production_route_bindings(extra)
    assert extra_exc.value.code == "route_effect_unclassified"


def test_v3_registry_shape_and_route_effect_invariants() -> None:
    bindings = load_production_route_bindings()
    contracts = [binding.effect_contract for binding in bindings]
    conditional = [contract for contract in contracts if contract.effect_class is EffectClass.CONDITIONAL]
    provider_calls = [contract for contract in contracts if contract.effect_class is EffectClass.PROVIDER_CALL]

    assert len(bindings) == 310
    canonical_writes = [
        contract for contract in contracts if contract.effect_class is EffectClass.CANONICAL_WRITE
    ]
    # Stage 4 admits exactly one task-scoped C9 canonical writer.  The route
    # remains local/non-authoritative; all other effectful routes stay blocked.
    assert len(canonical_writes) == 1
    assert canonical_writes[0].admission is EffectAdmission.ADMITTED
    assert canonical_writes[0].canonical_writer_port == "postgres.projection_rebuild.v2"
    assert len(conditional) == 76
    assert len(provider_calls) == 2
    assert all(
        contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        for contract in conditional
    )
    operations = {binding.operation for binding in bindings}
    assert not {
        "agent-batch.run_agent_batch_nl_command",
        "agent-batch.run_agent_batch_nl_command_direct",
    } & operations
    for operation in (
        "agent-batch.reject_agent_batch_nl_command",
        "agent-batch.reject_agent_batch_nl_command_direct",
    ):
        contract = next(binding.effect_contract for binding in bindings if binding.operation == operation)
        assert contract.effect_class is EffectClass.PURE_COMPUTE
        assert contract.admission is EffectAdmission.ADMITTED
    new_routes = {
        "information-topology.describe_profiles": EffectClass.READ,
        "information-topology.list_topologies": EffectClass.READ,
        "information-topology.resolve_refs": EffectClass.READ,
        "information-topology.read_topology": EffectClass.READ,
        "information-topology.find_relations": EffectClass.READ,
        "information-topology.preview_mapping": EffectClass.READ,
        "information-topology.apply_patch": EffectClass.LEGACY_WRITE,
        "information-topology.import_structure": EffectClass.LEGACY_WRITE,
        "information-topology.export_structure": EffectClass.FILESYSTEM_SUBPROCESS,
        "project-retrieval.current_mode": EffectClass.LEGACY_WRITE,
        "project-retrieval.refresh_mode": EffectClass.LEGACY_WRITE,
        "project-retrieval.preview": EffectClass.LEGACY_WRITE,
        "project-retrieval.start": EffectClass.CONDITIONAL,
        "project-retrieval.read_run": EffectClass.READ,
        "project-retrieval.continue_saved_frontier": EffectClass.CONDITIONAL,
    }
    for operation, expected_class in new_routes.items():
        contract = next(binding.effect_contract for binding in bindings if binding.operation == operation)
        assert contract.effect_class is expected_class
        expected_admission = (
            EffectAdmission.ADMITTED
            if expected_class is EffectClass.READ
            else EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        )
        assert contract.admission is expected_admission
    assert all(
        contract.conditional_discriminator == "handler_effect_path.v1"
        and contract.conditional_branches
        == ("no_effect_or_read", "external_or_legacy_effect")
        and contract.provider_port is None
        and contract.canonical_writer_port is None
        and contract.external_auth_port is None
        and contract.filesystem_port is None
        for contract in conditional
    )
    # The checked-in provider shape is blocked and portless; the provider class
    # remains explicit until its provider port is bound.
    assert all(
        contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        and contract.provider_port is None
        and contract.provider_class is ProviderClass.LLM
        for contract in provider_calls
    )
