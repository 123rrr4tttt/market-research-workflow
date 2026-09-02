"""Focused production-root tests; no test-private runtime handler is used."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    derive_material_ref,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.research.codec import sha256_hex as research_sha256_hex
from app.successor_runtime.research.materials import CapturedMaterialSnapshot
from app.successor_runtime.research.object_types import MATERIAL_REF_TYPE
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.captured_values import (
    MATERIAL_READ_OPERATION_KIND,
    MaterialReadReplay,
    PostgresCapturedValueReplayAdapter,
    canonical_read_payload_from_source,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    InstalledMaterialReadHandler,
    PostgresMaterialReadHandler,
    compose_postgres_first_specimen_runtime,
)
from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory

from .p0c_postgres_fixture import (  # noqa: F401 - imported fixtures are collected
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _assignment() -> RuntimeAssignment:
    operation_digest = _digest("material-read-operation")
    profile_digest = _digest("material-read-profile")
    deployment_digest = _digest("deployment")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=profile_digest,
        deployment_catalog_digest=deployment_digest,
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=1,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:material-read",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="project-unicode",
        run_id="run:material-read",
        step_id="step:material-read",
        step_role=CompiledStepRole.EFFECT,
        capability_id="material.first_specimen.v1",
        operation_contract_ref=OperationContractRef(
            kind=MATERIAL_READ_OPERATION_KIND,
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.return.material-ref.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=deployment_digest,
        execution_epoch=0,
        incarnation="run-incarnation",
        input_refs=("project-value:captured",),
        input_closure_digest=canonical_digest(("project-value:captured",)),
        queue_eligibility_digest=_digest("queue"),
        resource_policy_epoch=1,
        claim_authority_epoch=2,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace:material-read",
    )


class _ReplayOnlyProjectStore:
    def __init__(self, replay: MaterialReadReplay) -> None:
        self.replay = replay
        self.calls: list[tuple[str, str]] = []

    def load_material_read(
        self, assignment: RuntimeAssignment, *, actor_id: str
    ) -> MaterialReadReplay:
        self.calls.append((assignment.assignment_digest, actor_id))
        return self.replay

    def publish_material_result(
        self,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
        replay: MaterialReadReplay,
    ) -> None:
        assert replay is self.replay
        self.calls.append((assignment.assignment_digest, actor_id))


def test_unicode_payload_uses_capability_checksum_authority() -> None:
    source = SourceRef(
        source_ref_id="source:文档:一",
        owner_id="研究资料库",
        locator="document://项目/文档/一",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
    )
    payload = canonical_read_payload_from_source(source)
    values = {
        "source_ref": source.source_ref_id,
        "locator": source.locator,
        "owner_id": source.owner_id,
        "observed_at": source.observed_at.isoformat(),
    }

    assert payload.payload_digest == content_digest(values)
    assert payload.payload_digest != research_sha256_hex(values)


def test_production_handler_replays_project_value_without_document_port() -> None:
    assignment = _assignment()
    source = SourceRef(
        source_ref_id="source:文档:一",
        owner_id="研究资料库",
        locator="document://项目/文档/一",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
    )
    exact = "submission-captured 文档内容".encode()
    snapshot = CapturedMaterialSnapshot(
        value_ref=assignment.input_refs[0],
        document_id=101,
        observed_text_hash=hashlib.sha256(exact).hexdigest(),
        observed_updated_at=NOW,
        byte_size=len(exact),
    )
    captured = CapturedDocumentValue(
        exact_bytes=exact,
        snapshot=snapshot,
        exact_bytes_digest=hashlib.sha256(exact).hexdigest(),
    )
    expected = derive_material_ref(
        source_ref=source.source_ref_id,
        snapshot=snapshot,
        owner_id=source.owner_id,
        locator=source.locator,
        observed_at=source.observed_at.isoformat(),
    )
    replay = _ReplayOnlyProjectStore(
        MaterialReadReplay(
            payload=canonical_read_payload_from_source(source),
            captured=captured,
            expected_material=expected,
            expected_material_value_ref=ValueRef(
                value_id=expected.material_ref_id,
                project_key=assignment.project_key,
                object_type=MATERIAL_REF_TYPE,
                codec_id=MATERIAL_REF_TYPE.codec_id,
                content_digest=expected.content_digest or "",
                storage_kind="project_value_ref",
                store_id="successor_values",
                store_version="1",
                storage_ref=f"project-value:{expected.material_ref_id}",
                byte_size=1,
                provenance_digest=expected.provenance_digest or "",
            ),
        )
    )
    profile_digest = assignment.handler_binding.interpreter_profile_digest
    assert profile_digest is not None
    handler = PostgresMaterialReadHandler(
        InstalledMaterialReadHandler(
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=profile_digest,
            operation_contract_digest=assignment.operation_contract_digest or "",
        ),
        replay,  # type: ignore[arg-type] - deterministic exact project-store port
    )
    authority = _digest("authority")
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=authority,
        lease_token="lease:material-read",
        lease_expires_at=NOW + timedelta(minutes=1),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=profile_digest,
        authority_digest=authority,
        execution_reservation_ref="reservation:material-read",
        execution_reservation_digest=_digest("reservation"),
    )

    outcome = handler.execute(
        assignment,
        claim,
        RuntimeExecutionContext(
            node=NodeIdentity(
                node_id="runtime-node-a",
                incarnation="node-incarnation",
                started_at=NOW,
            ),
            observed_at=NOW,
        ),
    )

    assert isinstance(outcome, InterpreterOutcome)
    assert outcome.disposition is EffectDisposition.SUCCEEDED
    assert (
        outcome.result_digest
        == replay.replay.expected_material_value_ref.content_digest
    )
    assert replay.calls == [
        (assignment.assignment_digest, "runtime-node-a"),
        (assignment.assignment_digest, "runtime-node-a"),
    ]


class _AdvancingClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def now(self) -> datetime:
        current = self._current
        self._current += timedelta(milliseconds=10)
        return current


@pytest.mark.integration
def test_real_postgres_production_root_runs_two_isomorphic_nodes(
    request: pytest.FixtureRequest,
) -> None:
    """Opt-in dedicated DB proof for Store -> Node -> lifecycle wiring."""

    # This helper creates only the frozen Program/Plan/qualification/work rows.
    # The executable node, resolver, handler, guard, and store replay are all
    # production classes from this packet.
    from .test_p0c_two_nodes_postgres import (
        AUTHORITY_EPOCH,
        DEPLOYMENT_CATALOG_DIGEST,
        NODE_PROFILE_DIGEST,
        _prepare_execution,
    )
    from .test_p0c_two_nodes_postgres import (
        NOW as POSTGRES_NOW,
    )

    database = request.getfixturevalue("p0c_database")
    assert isinstance(database, LiveP0CDatabase)
    prepared = _prepare_execution(database)
    first_assignment = prepared.assignments[0]
    profile_digest = first_assignment.handler_binding.interpreter_profile_digest
    assert profile_digest is not None
    installation = InstalledMaterialReadHandler(
        handler_binding_digest=first_assignment.handler_binding_digest,
        interpreter_profile_digest=profile_digest,
        operation_contract_digest=first_assignment.operation_contract_digest or "",
    )

    replay_probe = PostgresCapturedValueReplayAdapter(
        runtime_uow_factory(database.engine)
    )
    for assignment in prepared.assignments:
        replay_probe.load_material_read(assignment, actor_id="p0c-node-probe")

    reports = []
    for node_id in ("p0c-node-a", "p0c-node-b"):
        composition = compose_postgres_first_specimen_runtime(
            engine=database.engine,
            identity=NodeIdentity(
                node_id=node_id,
                incarnation=f"{node_id}:incarnation:1",
                started_at=POSTGRES_NOW - timedelta(minutes=1),
            ),
            profile=RuntimeNodeProfile(
                profile_digest=NODE_PROFILE_DIGEST,
                supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
                interpreter_profile_digests=frozenset({profile_digest}),
            ),
            deployment=DeploymentBinding(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                node_profile_digest=NODE_PROFILE_DIGEST,
                runtime_protocol_version="1",
            ),
            protocol=RuntimeNodeProtocol(version="1", claim_batch_size=1),
            control_scope=ControlPlaneScope(
                system_actor_id=node_id,
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=AUTHORITY_EPOCH,
            ),
            installations=(installation,),
            clock=_AdvancingClock(POSTGRES_NOW),
        )
        reports.append(composition.node.run_once())

    assert [report.claimed for report in reports] == [1, 1]
    assert all(report.results[0].committed for report in reports), reports
    assert all(
        report.results[0].disposition is EffectDisposition.SUCCEEDED
        for report in reports
    )
