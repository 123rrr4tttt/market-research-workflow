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

from app.composition.production import (
    ProductionEndpointBinding,
    ProviderSelection,
    load_production_route_bindings,
)
from app.production_contract import (
    EffectAdmission,
    EffectClass,
    EndpointEffectContract,
    RouteEffectContractError,
)


pytestmark = pytest.mark.unit


def test_runtime_validators_preserve_supported_subclass_inputs() -> None:
    class ReadEffectContract(EndpointEffectContract):
        pass

    class PayloadSize(int):
        pass

    contract = ReadEffectContract(effect_class=EffectClass.READ)
    binding = ProductionEndpointBinding(
        route_template="/subclass",
        domain="test",
        operation="test.read",
        metrics_label="test:subclass",
        methods=("GET",),
        effect_contract=contract,
    )
    selection = ProviderSelection(
        provider_id="provider-1",
        request_payload_bytes=PayloadSize(7),
    )

    assert binding.effect_contract is contract
    assert selection.request_payload_bytes == 7
    with pytest.raises(ValueError, match="non-negative integer"):
        ProviderSelection(provider_id="provider-1", request_payload_bytes=True)


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


def test_expanded_declaration_delegates_complete_kwargs_to_constructor() -> None:
    read = EndpointEffectContract.from_expanded_declaration(
        {"effect_class": "read"}
    )
    filesystem = EndpointEffectContract.from_expanded_declaration(
        {"effect_class": "filesystem_subprocess"}
    )

    assert read == EndpointEffectContract(effect_class="read")
    assert filesystem == EndpointEffectContract(effect_class="filesystem_subprocess")
    with pytest.raises(TypeError, match="unexpected"):
        EndpointEffectContract.from_expanded_declaration(
            {"effect_class": "read", "unexpected": None}
        )


def test_v3_registry_rejects_missing_or_extra_effect_fields(tmp_path: Path) -> None:
    entry = {
        "route_template": "/example",
        "domain": "example",
        "operation": "example.read",
        "metrics_label": "legacy-custom-label",
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
    valid = tmp_path / "valid-v3.json"
    valid.write_text(json.dumps(payload), encoding="utf-8")
    legacy, = load_production_route_bindings(valid)
    assert legacy.effect_contract == EndpointEffectContract(effect_class="read")
    assert legacy.metrics_label == "legacy-custom-label"

    default_admission = tmp_path / "default-admission-v3.json"
    default_payload = json.loads(json.dumps(payload))
    default_payload["bindings"][0]["effect_contract"]["admission"] = None
    default_admission.write_text(json.dumps(default_payload), encoding="utf-8")
    default_binding, = load_production_route_bindings(default_admission)
    assert default_binding.effect_contract.admission is EffectAdmission.ADMITTED

    filesystem_default = tmp_path / "filesystem-default-admission-v3.json"
    filesystem_payload = json.loads(json.dumps(default_payload))
    filesystem_payload["bindings"][0]["effect_contract"][
        "effect_class"
    ] = "filesystem_subprocess"
    filesystem_default.write_text(json.dumps(filesystem_payload), encoding="utf-8")
    filesystem_binding, = load_production_route_bindings(filesystem_default)
    assert (
        filesystem_binding.effect_contract.admission
        is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    )

    invalid_provider_class = tmp_path / "invalid-provider-class-v3.json"
    invalid_provider_payload = json.loads(json.dumps(payload))
    invalid_provider_payload["bindings"][0]["effect_contract"][
        "provider_class"
    ] = "not-a-provider-class"
    invalid_provider_class.write_text(
        json.dumps(invalid_provider_payload),
        encoding="utf-8",
    )
    with pytest.raises(RouteEffectContractError) as provider_exc:
        load_production_route_bindings(invalid_provider_class)
    assert provider_exc.value.code == "provider_class_mismatch"

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


def test_registry_shape_and_route_effect_invariants() -> None:
    bindings = load_production_route_bindings()
    contracts = [binding.effect_contract for binding in bindings]
    conditional = [contract for contract in contracts if contract.effect_class is EffectClass.CONDITIONAL]

    # Completeness against the installed router is checked independently by
    # test_checked_in_route_registry_exactly_covers_installed_routes.  Preserve
    # identity and effect consistency when an endpoint gains a URL alias.
    route_methods = [(binding.route_template, method) for binding in bindings for method in binding.methods]
    assert bindings and len(route_methods) == len(set(route_methods))
    by_operation: dict[str, EndpointEffectContract] = {}
    for binding in bindings:
        previous = by_operation.setdefault(binding.operation, binding.effect_contract)
        assert previous == binding.effect_contract
    canonical_writes = [
        contract for contract in contracts if contract.effect_class is EffectClass.CANONICAL_WRITE
    ]
    assert canonical_writes == []
    assert conditional
    assert all(
        contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        for contract in conditional
    )
    operations = {binding.operation for binding in bindings}
    assert not {
        "agent-batch.run_agent_batch_nl_command",
        "agent-batch.run_agent_batch_nl_command_direct",
        "agent-sessions.run_agent_session_coordinator_pass",
    } & operations
    for operation in (
        "agent-batch.reject_agent_batch_nl_command",
        "agent-batch.reject_agent_batch_nl_command_direct",
        "discovery.generate_keywords_api",
        "discovery.generate_subreddit_keywords_api",
    ):
        contract = next(binding.effect_contract for binding in bindings if binding.operation == operation)
        assert contract.effect_class is EffectClass.PURE_COMPUTE
        assert contract.admission is EffectAdmission.ADMITTED
    new_routes = {
        "agent-cell.read_agent_cell": EffectClass.READ,
        "agent-macro-host.read_macro_environment": EffectClass.READ,
        "agent-macro-host.prepare_macro_host": EffectClass.LEGACY_WRITE,
        "agent-macro-host.bind_macro_host": EffectClass.LEGACY_WRITE,
        "agent-macro-host.record_macro_input": EffectClass.LEGACY_WRITE,
        "agent-macro-host.confirm_macro_action": EffectClass.LEGACY_WRITE,
        "agent-macro-host.dispatch_macro_tool": EffectClass.CONDITIONAL,
        "agent-macro-host.end_macro_turn": EffectClass.LEGACY_WRITE,
        "crawler.list_crawler_agent_modules_api": EffectClass.READ,
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


@pytest.mark.parametrize(
    "effect",
    [
        {"effect_class": "read"},
        {"effect_class": "read", "admission": None},
        {"effect_class": "read", "admission": "admitted", "provider_port": None},
        {"effect_class": "read", "admission": "admitted", "unknown": None},
        {"effect_class": "provider_call", "admission": "blocked_until_effect_binding", "provider_port": None},
        {"effect_class": "provider_call", "admission": "blocked_until_effect_binding", "provider_class": "llm"},
        {"effect_class": "provider_call", "admission": "admitted", "provider_port": None, "provider_class": "llm"},
        {"effect_class": "conditional", "admission": "blocked_until_effect_binding"},
        {"effect_class": "conditional", "admission": "blocked_until_effect_binding", "conditional_discriminator": "unknown.v1"},
        {"effect_class": "external_auth", "admission": "admitted", "external_auth_port": None},
        {"effect_class": "external_auth", "admission": "blocked_until_effect_binding"},
        {"effect_class": "canonical_write", "admission": "blocked_until_effect_binding"},
        {"effect_class": "filesystem_subprocess", "admission": "blocked_until_effect_binding"},
        {"effect_class": "unknown", "admission": "admitted"},
    ],
)
def test_compact_effect_declaration_rejects_missing_foreign_or_unbound_fields(effect: dict) -> None:
    with pytest.raises(RouteEffectContractError):
        EndpointEffectContract.from_declaration(effect)


@pytest.mark.parametrize("admission,port", [("admitted", "auth.port.v1"), ("blocked_until_effect_binding", None)])
def test_compact_effect_preserves_explicit_admission_and_owned_port(admission: str, port: str | None) -> None:
    compact = EndpointEffectContract.from_declaration({
        "effect_class": "external_auth", "admission": admission, "external_auth_port": port,
    })
    assert compact == EndpointEffectContract(effect_class="external_auth", admission=admission, external_auth_port=port)


def test_compact_conditional_uses_original_closed_branches_and_stays_blocked() -> None:
    effect = EndpointEffectContract.from_declaration({
        "effect_class": "conditional", "admission": "admitted",
        "conditional_discriminator": "handler_effect_path.v1",
    })
    assert effect.conditional_branches == ("no_effect_or_read", "external_or_legacy_effect")
    assert effect.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING


@pytest.mark.parametrize("mutation", ["missing_scope", "missing_effect", "extra_metrics", "unknown_schema"])
def test_v4_route_loader_keeps_explicit_identity_authority_and_version(tmp_path: Path, mutation: str) -> None:
    payload = json.loads((BACKEND_ROOT / "app/composition/production_route_bindings.json").read_text())
    payload["bindings"] = [payload["bindings"][0]]
    row = payload["bindings"][0]
    if mutation == "missing_scope":
        del row["required_scope"]
    elif mutation == "missing_effect":
        del row["effect_contract"]
    elif mutation == "extra_metrics":
        row["metrics_label"] = "injected"
    else:
        payload["schema"] = "mrw.production.route-bindings.v5"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(RouteEffectContractError):
        load_production_route_bindings(path)


def test_v4_metrics_uses_normalized_binding_identity(tmp_path: Path) -> None:
    payload = json.loads((BACKEND_ROOT / "app/composition/production_route_bindings.json").read_text())
    payload["bindings"] = [payload["bindings"][0]]
    row = payload["bindings"][0]
    row["domain"] = "  example  "
    row["route_template"] = "  /example  "
    path = tmp_path / "normalized.json"
    path.write_text(json.dumps(payload))
    binding, = load_production_route_bindings(path)
    assert binding.metrics_label == f"{binding.domain}:{binding.route_template}" == "example:/example"
