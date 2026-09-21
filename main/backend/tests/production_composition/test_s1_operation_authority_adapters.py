"""Focused fake-SQL tests for operation-bound production authority adapters."""

# ruff: noqa: E402
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.composition.production_runtime import (
    InstalledCanonicalWriterBinding,
    PostgresProductionActorScopes,
    PostgresProductionApprovals,
    ProductionRuntimeAuthorityUnavailable,
    RegisteredCanonicalWriter,
)
from app.successor_runtime.substrate.postgres.c7_canonical_write import (
    PostgresC7CanonicalWritePort,
)
from app.composition.production import load_production_route_bindings
from app.production_contract import (
    APPROVED_DECISION,
    ApprovalGrant,
    EffectAdmission,
    EffectClass,
    RouteEffectContractError,
)
from app.services.request_identity import authenticated_actor_context
from app.successor_runtime.runtime.authority_grants import AuthorityOperationScope
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import compute_scope_digest


pytestmark = pytest.mark.unit
OBSERVED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
ACTOR = authenticated_actor_context(
    actor_id="actor-1",
    source="authenticated_request_state",
    auth_mode="oidc_claims",
)
SCOPE = ProjectScopeRef(
    project_key="demo",
    resolved_schema="mrw_p_demo",
    project_registry_revision=7,
    incarnation="demo-incarnation",
    scope_digest=compute_scope_digest("demo", "mrw_p_demo", 7, "demo-incarnation"),
)
PAYLOAD_DIGEST = "a" * 64


@dataclass
class FakeResult:
    rows: list[dict[str, Any]]

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


@dataclass
class FakeConnection:
    expected_literals: tuple[str, ...]
    rows: list[dict[str, Any]]
    statements: list[str] = field(default_factory=list)

    def execute(self, statement: Any) -> FakeResult:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.statements.append(sql)
        if not all(literal in sql for literal in self.expected_literals):
            return FakeResult([])
        return FakeResult([dict(row) for row in self.rows])


@dataclass
class FakeEngine:
    connection: FakeConnection

    @contextmanager
    def connect(self):
        yield self.connection


def _approval_row() -> dict[str, Any]:
    return {
        "approval_id": "approval-1",
        "actor_id": "actor-1",
        "decision": APPROVED_DECISION,
        "expires_at": OBSERVED_AT + timedelta(minutes=5),
        "operation_kind": "agent-chat.run_agent_chat_turn",
        "capability_id": "agent-chat.run_agent_chat_turn",
        "payload_digest": PAYLOAD_DIGEST,
        "claim_authority_epoch": 7,
    }


def _approval_adapter(connection: FakeConnection) -> PostgresProductionApprovals:
    return PostgresProductionApprovals(FakeEngine(connection))


def test_exact_operation_authorization_is_returned_only_for_exact_sql_join() -> None:
    connection = FakeConnection(
        expected_literals=(
            "approval-1",
            "agent-chat.run_agent_chat_turn",
            PAYLOAD_DIGEST,
            "actor-1",
            "demo",
            "successor",
        ),
        rows=[_approval_row()],
    )
    grants = _approval_adapter(connection).approvals(
        ACTOR,
        "agent-chat.run_agent_chat_turn",
        "agent-chat.run_agent_chat_turn",
        SCOPE,
        OBSERVED_AT,
        "approval-1",
        PAYLOAD_DIGEST,
    )

    assert grants == (
        ApprovalGrant(
            approval_id="approval-1",
            actor_id="actor-1",
            decision=APPROVED_DECISION,
            expires_at=OBSERVED_AT + timedelta(minutes=5),
            project_key="demo",
            operation="agent-chat.run_agent_chat_turn",
            capability_id="agent-chat.run_agent_chat_turn",
            payload_digest=PAYLOAD_DIGEST,
            claim_authority_epoch=7,
        ),
    )
    assert all(
        table in connection.statements[0]
        for table in (
            "runtime_approvals",
            "runtime_step_authorizations",
            "runtime_capability_authority",
        )
    )


@pytest.mark.parametrize(
    ("operation", "capability", "approval_ref", "digest"),
    [
        ("other.operation", "agent-chat.run_agent_chat_turn", "approval-1", PAYLOAD_DIGEST),
        ("agent-chat.run_agent_chat_turn", "other.capability", "approval-1", PAYLOAD_DIGEST),
        ("agent-chat.run_agent_chat_turn", "agent-chat.run_agent_chat_turn", "", PAYLOAD_DIGEST),
        ("agent-chat.run_agent_chat_turn", "agent-chat.run_agent_chat_turn", "approval-1", "b" * 64),
    ],
)
def test_operation_authority_drift_denies(
    operation: str,
    capability: str,
    approval_ref: str,
    digest: str,
) -> None:
    connection = FakeConnection(
        expected_literals=(
            approval_ref or "approval-1",
            operation,
            capability,
            digest,
            approval_ref,
        ),
        rows=[_approval_row()],
    )

    assert (
        _approval_adapter(connection).approvals(
            ACTOR,
            operation,
            capability,
            SCOPE,
            OBSERVED_AT,
            approval_ref,
            digest,
        )
        == ()
    )


def test_ambiguous_operation_authority_fails_closed() -> None:
    connection = FakeConnection(expected_literals=(), rows=[_approval_row(), _approval_row()])

    with pytest.raises(ProductionRuntimeAuthorityUnavailable, match="ambiguous"):
        _approval_adapter(connection).approvals(
            ACTOR,
            "agent-chat.run_agent_chat_turn",
            "agent-chat.run_agent_chat_turn",
            SCOPE,
            OBSERVED_AT,
            "approval-1",
            PAYLOAD_DIGEST,
        )


def test_actor_scope_requires_exact_operation_kind() -> None:
    scope = AuthorityOperationScope.from_content(
        operation_kinds=("agent-chat.run_agent_chat_turn",),
        project_scope_digest=SCOPE.scope_digest,
    )
    row = {"operation_scope_json": scope.model_dump(mode="python")}
    connection = FakeConnection(
        expected_literals=("agent-chat.run_agent_chat_turn",),
        rows=[row],
    )

    adapter = PostgresProductionActorScopes(FakeEngine(connection))
    assert adapter.scopes(
        ACTOR,
        "agent-chat.run_agent_chat_turn",
        "agent-chat.run_agent_chat_turn",
        SCOPE,
    ) == ("api:invoke",)
    assert (
        adapter.scopes(
            ACTOR,
            "agent-chat.run_agent_chat_turn",
            "other.capability",
            SCOPE,
        )
        == ()
    )
    assert adapter.scopes(ACTOR, "discovery.discovery_search", "discovery.discovery_search", SCOPE) == ()


def test_writer_owner_requires_exact_claim_and_registered_port() -> None:
    writer = RegisteredCanonicalWriter(
        bindings=(("document.write", "successor-runtime", "runtime_step_authorization.v1"),),
        installed=(
            InstalledCanonicalWriterBinding(
                operation="document.write",
                canonical_owner_ref="successor-runtime",
                writer_port_kind="runtime_step_authorization.v1",
                port=SimpleNamespace(admit=lambda *args, **kwargs: None),
            ),
            InstalledCanonicalWriterBinding(
                operation="ingest_index.c7.v2.canonical_commit_write",
                canonical_owner_ref="document.canonical.v1",
                writer_port_kind="postgres.c7_canonical_write.v1",
                port=PostgresC7CanonicalWritePort(),
            ),
        ),
    )
    grant = ApprovalGrant(
        approval_id="approval-1",
        actor_id="actor-1",
        decision=APPROVED_DECISION,
        project_key="demo",
        operation="document.write",
        capability_id="document.write",
        payload_digest=PAYLOAD_DIGEST,
        claim_authority_epoch=7,
    )

    assert (
        writer.owner(
            "document.write",
            "demo",
            "successor-runtime",
            "runtime_step_authorization.v1",
            (grant,),
        )
        == "successor-runtime"
    )
    assert (
        writer.owner(
            "other.write",
            "demo",
            "successor-runtime",
            "runtime_step_authorization.v1",
            (grant,),
        )
        is None
    )


def test_route_declaration_without_installed_writer_port_denies() -> None:
    grant = ApprovalGrant(
        approval_id="approval-1",
        actor_id="actor-1",
        decision=APPROVED_DECISION,
        project_key="demo",
        operation="ingest.ingest_source_library_run",
        capability_id="ingest.ingest_source_library_run",
        payload_digest=PAYLOAD_DIGEST,
        claim_authority_epoch=7,
    )
    route_only = RegisteredCanonicalWriter(
        bindings=(("ingest.ingest_source_library_run", "successor-runtime", "runtime_step_authorization.v1"),),
        installed=(
            InstalledCanonicalWriterBinding(
                operation="ingest_index.c7.v2.canonical_commit_write",
                canonical_owner_ref="document.canonical.v1",
                writer_port_kind="postgres.c7_canonical_write.v1",
                port=PostgresC7CanonicalWritePort(),
            ),
        ),
    )

    assert (
        route_only.owner(
            "ingest.ingest_source_library_run",
            "demo",
            "successor-runtime",
            "runtime_step_authorization.v1",
            (grant,),
        )
        is None
    )


def test_c7_writer_owner_requires_route_and_installed_port_exact_match() -> None:
    operation = "ingest_index.c7.v2.canonical_commit_write"
    owner = "document.canonical.v1"
    port_kind = "postgres.c7_canonical_write.v1"
    writer = RegisteredCanonicalWriter(
        bindings=((operation, owner, port_kind),),
        installed=(
            InstalledCanonicalWriterBinding(
                operation=operation,
                canonical_owner_ref=owner,
                writer_port_kind=port_kind,
                port=PostgresC7CanonicalWritePort(),
            ),
        ),
    )
    grant = ApprovalGrant(
        approval_id="approval-1",
        actor_id="actor-1",
        decision=APPROVED_DECISION,
        project_key="demo",
        operation=operation,
        capability_id=operation,
        payload_digest=PAYLOAD_DIGEST,
        claim_authority_epoch=7,
    )

    assert writer.owner(operation, "demo", owner, port_kind, (grant,)) == owner
    assert (
        writer.owner(
            "document.write",
            "demo",
            "legacy-runtime",
            "runtime_step_authorization.v1",
            (grant,),
        )
        is None
    )
    assert (
        writer.owner(
            "document.write",
            "demo",
            "successor-runtime",
            "legacy.writer.v1",
            (grant,),
        )
        is None
    )


def test_route_registry_loader_fails_closed_on_new_authority_fields(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "app/composition/production_route_bindings.json"
    registry = json.loads(source.read_text(encoding="utf-8"))
    registry["bindings"] = [registry["bindings"][0]]

    assert registry["schema"] == "mrw.production.route-bindings.v3"
    first = registry["bindings"][0]
    assert "effect_contract" in first
    assert not {"provider_class", "requires_provider", "requires_canonical_writer"} & first.keys()
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(registry), encoding="utf-8")
    assert load_production_route_bindings(valid)

    missing = tmp_path / "missing.json"
    del registry["bindings"][0]["effect_contract"]
    missing.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(RouteEffectContractError, match="fields are not explicit"):
        load_production_route_bindings(missing)

    registry = json.loads(source.read_text(encoding="utf-8"))
    registry["bindings"] = [registry["bindings"][0]]
    invalid = tmp_path / "invalid.json"
    registry["bindings"][0]["effect_contract"]["provider_class"] = "database"
    invalid.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(RouteEffectContractError, match="closed provider vocabulary"):
        load_production_route_bindings(invalid)

    inconsistent = tmp_path / "inconsistent.json"
    effect = registry["bindings"][0]["effect_contract"]
    effect["effect_class"] = "provider_call"
    effect["admission"] = "admitted"
    effect["provider_port"] = "example.provider.v1"
    effect["provider_class"] = "null"
    effect["conditional_discriminator"] = None
    effect["conditional_branches"] = []
    inconsistent.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(RouteEffectContractError, match="non-null provider class"):
        load_production_route_bindings(inconsistent)


def test_checked_in_effect_contracts_match_public_route_design() -> None:
    bindings = {
        binding.operation: binding.effect_contract
        for binding in load_production_route_bindings()
    }

    for operation in (
        "codex-auth.codex_auth_login",
        "codex-auth.codex_auth_callback",
        "codex-auth.codex_auth_status",
    ):
        contract = bindings[operation]
        assert contract.effect_class is EffectClass.EXTERNAL_AUTH
        assert contract.admission is EffectAdmission.ADMITTED
        assert contract.external_auth_port == "codex_oauth.bootstrap.v1"

    for operation in (
        "codex-auth.codex_auth_logout",
        "codex-auth.codex_auth_revoke_token_sink_profile",
        "codex-auth.codex_cli_bootstrap",
    ):
        contract = bindings[operation]
        assert contract.effect_class is EffectClass.EXTERNAL_AUTH
        assert contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING

    for operation in ("discovery.discovery_search", "agent-chat.run_agent_chat_turn"):
        contract = bindings[operation]
        assert contract.effect_class is EffectClass.CONDITIONAL
        assert contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
        assert contract.conditional_discriminator == "handler_effect_path.v1"
        assert contract.conditional_branches == ("no_effect_or_read", "external_or_legacy_effect")

    config_contract = bindings["config.update_env"]
    assert config_contract.effect_class is EffectClass.FILESYSTEM_SUBPROCESS
    assert config_contract.admission is EffectAdmission.BLOCKED_UNTIL_EFFECT_BINDING
    assert not any(contract.requires_canonical_writer for contract in bindings.values())
