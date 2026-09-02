from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.catalog import build_first_specimen_registry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.codec import dataclass_to_json, sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import GAP_TYPE
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    HandlerBindingKind,
    MaterializerBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeHandler,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    compose_postgres_first_specimen_runtime,
)
from app.successor_runtime.substrate.postgres.first_specimen_successor import (
    PostgresFirstSpecimenSuccessorHandler,
    SuccessorCompileEnvelope,
    materialize_gap_successor,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    AssignmentEnvelope,
    _assignment_values,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.postgres.work_items import (
    WorkItemClaimRepository,
)

from .p0c_postgres_fixture import (
    DEPLOYMENT_CATALOG_DIGEST,
    NOW,
    PROJECT_KEY,
    QUEUE_ELIGIBILITY_DIGEST,
    RESOURCE_POLICY_DIGEST,
    LiveP0CDatabase,
    live_p0c_database,  # noqa: F401 - registers the module-scoped dependency fixture
    p0c_database,  # noqa: F401 - imported pytest fixture
    submission_command,
)

pytestmark = pytest.mark.integration


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


NODE_PROFILE_DIGEST = _digest("p0d-node-profile")


class _AdvancingClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        self.current += timedelta(seconds=1)
        return self.current


def _seed_predecessor(database: LiveP0CDatabase) -> tuple[object, object, object]:
    command = submission_command(suffix="p0d-gap")
    submitted = database.submission_service().submit(command)
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    registry = build_first_specimen_registry(bundle.operations)
    plan = compile_program(
        submitted.program,
        catalog,
        operation_contracts=registry,
        transform_registry=command.registries.transforms,
        merge_registry=command.registries.merges,
        discriminator_registry=command.registries.discriminators,
    )
    gap = Gap(
        gap_id="gap:p0d:admitted",
        inquiry_ref=command.inquiry.inquiry_id,
        requirement="two supporting qualifications",
        reason="the second source remains insufficient",
        closure_condition="admit two exact supporting qualifications",
        reopen_policy={"mode": "open_gap"},
        missing_evidence_or_decision="second supporting qualification",
    )
    assert gap.content_digest is not None
    gap_content = dataclass_to_json(gap, ("content_digest",))
    assert sha256_hex(gap_content) == gap.content_digest
    provenance = _digest("p0d-gap-provenance")
    gap_incarnation = "gap-inc:p0d:001"
    gap_ref = ResearchObjectRef(
        object_id=gap.gap_id,
        object_type=GAP_TYPE,
        project_key=PROJECT_KEY,
        incarnation=gap_incarnation,
        owner_binding_ref="ResearchLedger",
        content_ref=f"project-value:{gap.gap_id}",
        content_digest=gap.content_digest,
        provenance_closure_digest=provenance,
        lifecycle_state="ADMITTED",
    )
    step_id = "step:p0d:admitted-gap"
    with database.engine.begin() as connection:
        PlanRepository(connection, database.project_tables).put_exact(
            database.scope,
            plan,
            plan.plan_digest,
            operation_catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            catalog_digest=catalog.catalog_digest,
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
                plan_id=plan.plan_id,
                project_key=PROJECT_KEY,
                plan_digest=plan.plan_digest,
                program_id=plan.program_id,
                program_digest=plan.program_digest,
                project_storage_ref=f"project-value:plan:{plan.plan_id}",
                compiler_id=plan.compiler_id,
                compiler_version=plan.compiler_version,
                operation_catalog_id=catalog.catalog_id,
                catalog_version=catalog.catalog_version,
                catalog_digest=catalog.catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
            )
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(PUBLIC_TABLES["runtime_runs"].c.run_id == command.run_id)
            .values(
                plan_id=plan.plan_id,
                plan_digest=plan.plan_digest,
                qualification_digest=_digest("p0d-qualification"),
                state="COMPLETED",
                revision=1,
                execution_epoch=0,
                finished_at=NOW,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                project_key=PROJECT_KEY,
                run_id=command.run_id,
                step_id=step_id,
                operation_id="claim.form_or_open_gap.p0d",
                operation_kind="claim.form_or_open_gap.v1",
                operation_version="1.0.0",
                state="SUCCEEDED",
                revision=1,
                execution_epoch=0,
                input_digest=_digest("p0d-gap-input"),
                output_digest=gap.content_digest,
                effect_class="PURE_TRANSFORM",
                resource_class="cpu",
                capability_id="mrw.first-specimen.claim-or-gap",
                claim_owner="successor",
                claim_authority_epoch=command.claim_authority_epoch,
                claim_policy_digest=command.claim_policy_digest,
                attempt_count=1,
                max_attempts=1,
                finished_at=NOW,
            )
        )
        ValueRepository(connection, database.project_tables).put_exact(
            database.scope,
            value_id=gap.gap_id,
            object_type=GAP_TYPE.type_id,
            codec_id=GAP_TYPE.codec_id,
            content=gap_content,
            expected_digest=gap.content_digest,
            provenance_digest=provenance,
            expected_revision=0,
            expected_incarnation=gap_incarnation,
            provenance={"kind": "admitted-gap", "run_id": command.run_id},
        )
        ResearchLedgerRepository(connection, database.project_tables).put_object(
            database.scope,
            gap_ref,
            expected_revision=0,
            expected_incarnation=gap_incarnation,
        )
    binding = MaterializerBinding.from_content(
        materializer_id="mrw.first_specimen.gap-successor",
        materializer_version="1.0.0",
        predecessor_plan_digest=plan.plan_digest,
        source_value_digest=gap.content_digest,
        target_domain_contract_snapshot_digest=_digest("p0d-domain-contract"),
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:p0d:materialize-gap",
        assignment_kind=AssignmentKind.MATERIALIZE_SUCCESSOR,
        project_key=PROJECT_KEY,
        run_id=command.run_id,
        capability_id="mrw.first-specimen.gap-successor",
        handler_binding_kind=HandlerBindingKind.MATERIALIZER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=submitted.program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=command.run_incarnation,
        input_refs=(gap_ref.content_ref,),
        input_closure_digest=_digest("p0d-gap-input-closure"),
        payload_ref=gap_ref.content_ref,
        payload_digest=gap.content_digest,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        resource_policy_epoch=command.resource_policy_epoch,
        claim_authority_epoch=command.claim_authority_epoch,
        claim_policy_digest=command.claim_policy_digest,
        trace_id="trace:p0d:materialize-gap",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("p0d-materialize-authorization"),
        lease_token="lease:p0d:node-a",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node:a",
        node_profile_digest=NODE_PROFILE_DIGEST,
        authority_digest=_digest("p0d-materialize-authority"),
    )
    with database.engine.begin() as connection:
        values = _assignment_values(
            AssignmentEnvelope(
                assignment=assignment,
                required_node_profile_selector=NODE_PROFILE_DIGEST,
                authority_digest=claim.authority_digest,
                resource_policy_digest=RESOURCE_POLICY_DIGEST,
                fairness_key=PROJECT_KEY,
            ),
            due_at=NOW,
        )
        values.update(
            state="CLAIMED",
            revision=1,
            lease_token=claim.lease_token,
            lease_owner=claim.node_id,
            lease_expires_at=claim.lease_expires_at,
            claim_attempt_id=claim.attempt_id,
            claim_binding_json=claim.model_dump(mode="json"),
            claim_binding_digest=claim.binding_digest,
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(**values)
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                project_key=PROJECT_KEY,
                capability_id=assignment.capability_id,
                mode="canary",
                authority_epoch=assignment.claim_authority_epoch,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=_digest("p0d-materializer-allowlist"),
                config_digest=_digest("p0d-materializer-config"),
                effective_at=NOW,
                updated_by="p0d-gap-fixture",
                approval_ref="approval:p0d-gap-local-only",
                rollback_target_ref="legacy:p0d-gap-read-only",
                revision=0,
            )
        )

    compiler = command.compiler_binding

    def compile_factory(closure: object) -> SuccessorCompileEnvelope:
        return SuccessorCompileEnvelope(
            assignment=RuntimeAssignment(
                runtime_protocol_version="1",
                work_item_id=f"{closure.successor_run_id}:compile",
                assignment_kind=AssignmentKind.COMPILE,
                project_key=PROJECT_KEY,
                run_id=closure.successor_run_id,
                capability_id="mrw.first-specimen.compile",
                handler_binding_kind=HandlerBindingKind.COMPILER,
                handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
                handler_binding_digest=compiler.binding_digest,
                handler_binding=compiler,
                program_digest=closure.materialization.successor_program_digest,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                execution_epoch=0,
                incarnation=closure.successor_run_incarnation,
                input_refs=(closure.inquiry_value_ref.storage_ref,),
                input_closure_digest=_digest("p0d-successor-compile-input"),
                queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
                resource_policy_epoch=command.resource_policy_epoch,
                claim_authority_epoch=command.claim_authority_epoch,
                claim_policy_digest=command.claim_policy_digest,
                trace_id="trace:p0d:successor-compile",
            ),
            required_node_profile_selector=NODE_PROFILE_DIGEST,
            resource_policy_digest=RESOURCE_POLICY_DIGEST,
            fairness_key=PROJECT_KEY,
        )

    return (assignment, claim, (catalog, registry, compile_factory))


def test_gap_successor_is_atomic_idempotent_and_keeps_predecessor(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, claim, dependencies = _seed_predecessor(p0c_database)
    catalog, registry, compile_factory = dependencies
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        first = materialize_gap_successor(
            uow.connection,
            p0c_database.scope,
            assignment=assignment,
            claim=claim,
            observed_at=NOW,
            tables=p0c_database.project_tables,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )
        uow.commit()

    node_b_claim = ClaimBinding.bind(
        assignment,
        authorization_digest=claim.authorization_digest,
        lease_token="lease:p0d:node-b",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node:b",
        node_profile_digest=claim.node_profile_digest,
        authority_digest=claim.authority_digest,
    )
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == assignment.work_item_id
            )
            .values(
                revision=2,
                lease_token=node_b_claim.lease_token,
                lease_owner=node_b_claim.node_id,
                lease_expires_at=node_b_claim.lease_expires_at,
                claim_attempt_id=node_b_claim.attempt_id,
                claim_binding_json=node_b_claim.model_dump(mode="json"),
                claim_binding_digest=node_b_claim.binding_digest,
            )
        )
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        repeated = materialize_gap_successor(
            uow.connection,
            p0c_database.scope,
            assignment=assignment,
            claim=node_b_claim,
            observed_at=NOW,
            tables=p0c_database.project_tables,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )
        uow.commit()
    assert repeated.repeated is True
    assert repeated.closure == first.closure

    with p0c_database.engine.connect() as connection:
        runs = connection.execute(
            sa.select(
                PUBLIC_TABLES["runtime_runs"].c.run_id,
                PUBLIC_TABLES["runtime_runs"].c.state,
            )
        ).all()
        assert (assignment.run_id, "COMPLETED") in runs
        assert (first.closure.successor_run_id, "SUBMITTED") in runs
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_idempotency"]
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(p0c_database.project_tables.research_relations)
                .where(
                    p0c_database.project_tables.research_relations.c.relation_type
                    == "opens"
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(p0c_database.project_tables.research_objects)
                .where(
                    p0c_database.project_tables.research_objects.c.object_id.in_(
                        (
                            first.closure.inquiry.inquiry_id,
                            first.closure.research_plan.plan_id,
                        )
                    )
                )
            )
            == 2
        )


def test_gap_successor_stale_authority_and_crash_rollback_fail_closed(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, claim, dependencies = _seed_predecessor(p0c_database)
    catalog, registry, compile_factory = dependencies
    stale = ClaimBinding.bind(
        assignment,
        authorization_digest=claim.authorization_digest,
        lease_token=claim.lease_token,
        lease_expires_at=claim.lease_expires_at,
        node_id=claim.node_id,
        node_profile_digest=claim.node_profile_digest,
        authority_digest=_digest("stale-authority"),
    )
    with (
        pytest.raises(Exception, match="claim/lease/authority"),
        RuntimeUnitOfWork(engine=p0c_database.engine) as uow,
    ):
        materialize_gap_successor(
            uow.connection,
            p0c_database.scope,
            assignment=assignment,
            claim=stale,
            observed_at=NOW,
            tables=p0c_database.project_tables,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )

    with (
        pytest.raises(RuntimeError, match="injected crash"),
        RuntimeUnitOfWork(engine=p0c_database.engine) as uow,
    ):
        materialize_gap_successor(
            uow.connection,
            p0c_database.scope,
            assignment=assignment,
            claim=claim,
            observed_at=NOW,
            tables=p0c_database.project_tables,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )
        raise RuntimeError("injected crash")
    with p0c_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_idempotency"]
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.event_type
                    == "SuccessorMaterialized"
                )
            )
            == 0
        )


def test_two_runtime_nodes_atomically_materialize_one_gap_successor(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, _claim, dependencies = _seed_predecessor(p0c_database)
    assert isinstance(assignment, RuntimeAssignment)
    catalog, registry, compile_factory = dependencies
    binding = assignment.handler_binding
    assert isinstance(binding, MaterializerBinding)
    node_ids = ("p0d-materializer-node-a", "p0d-materializer-node-b")
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == assignment.work_item_id
            )
            .values(
                state="READY",
                revision=2,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                due_at=NOW,
            )
        )
        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="p0d-materializer-v1",
                catalog_ref="artifact:p0d-materializer-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("p0d-materializer-security"),
                resource_profile_digest=_digest("p0d-materializer-resource"),
            )
        )
        nodes = RuntimeNodeRepository(connection)
        for node_id in node_ids:
            nodes.register(
                node_id=node_id,
                node_profile_digest=NODE_PROFILE_DIGEST,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                runtime_protocol_version="1",
                started_at=NOW - timedelta(minutes=1),
            )

    handler = PostgresFirstSpecimenSuccessorHandler(
        engine=p0c_database.engine,
        tables=p0c_database.project_tables,
        scope=p0c_database.scope,
        binding=binding,
        catalog=catalog,
        operation_contracts=registry,
        compile_assignment_factory=compile_factory,
    )
    profile = RuntimeNodeProfile(
        profile_digest=NODE_PROFILE_DIGEST,
        supported_assignment_kinds=frozenset({AssignmentKind.MATERIALIZE_SUCCESSOR}),
    )
    deployment = DeploymentBinding(
        catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        node_profile_digest=NODE_PROFILE_DIGEST,
        runtime_protocol_version="1",
    )
    protocol = RuntimeNodeProtocol(version="1", claim_batch_size=1)
    clock = _AdvancingClock(NOW)
    nodes = tuple(
        compose_postgres_first_specimen_runtime(
            engine=p0c_database.engine,
            identity=NodeIdentity(
                node_id=node_id,
                incarnation=f"{node_id}:incarnation:1",
                started_at=NOW - timedelta(minutes=1),
            ),
            profile=profile,
            deployment=deployment,
            protocol=protocol,
            control_scope=ControlPlaneScope(
                system_actor_id=node_id,
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=assignment.claim_authority_epoch,
            ),
            installations=(),
            additional_handlers=(handler,),
            clock=clock,
        ).node
        for node_id in node_ids
    )

    first = nodes[0].run_once()
    second = nodes[1].run_once()
    assert first.claimed == 1
    assert first.results[0].committed is True
    assert first.results[0].executed is True
    assert second.claimed == 0

    with p0c_database.engine.connect() as connection:
        work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == assignment.work_item_id
                )
            )
            .mappings()
            .one()
        )
        source_step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == assignment.run_id,
                    PUBLIC_TABLES["runtime_steps"].c.output_digest
                    == assignment.payload_digest,
                )
            )
            .mappings()
            .one()
        )
        predecessor = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id
                )
            )
            .mappings()
            .one()
        )
        materialized = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_events"]).where(
                    PUBLIC_TABLES["runtime_events"].c.run_id == assignment.run_id,
                    PUBLIC_TABLES["runtime_events"].c.event_type
                    == "SuccessorMaterialized",
                )
            )
            .mappings()
            .one()
        )
        assert work["state"] == "COMPLETED"
        assert work["lease_token"] is None
        assert predecessor["state"] == "COMPLETED"
        assert source_step["state"] == "SUCCEEDED"
        assert int(source_step["revision"]) == 1
        assert materialized["step_id"] is None
        assert materialized["attempt_id"] is None
        assert (
            materialized["payload_digest"]
            == materialized["event_metadata_json"]["result_digest"]
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_effect_attempts"]
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_resource_reservations"]
                )
            )
            == 0
        )
        idempotency = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"]).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.capability_id
                    == assignment.capability_id
                )
            )
            .mappings()
            .one()
        )
        assert idempotency["state"] == "TERMINAL"
        assert idempotency["terminal_observation_ref"] == materialized["payload_ref"]
        forbidden = connection.scalar(
            sa.select(sa.func.count())
            .select_from(PUBLIC_TABLES["runtime_events"])
            .where(
                PUBLIC_TABLES["runtime_events"].c.run_id == assignment.run_id,
                PUBLIC_TABLES["runtime_events"].c.event_type.in_(
                    (
                        "EffectStarted",
                        "RuntimeValueProduced",
                        "EffectFailed",
                        "SuccessorRunAdopted",
                    )
                ),
            )
        )
        assert forbidden == 0


class _CrashAfterMaterializerCommit:
    interpreter_profile_digest = None
    operation_contract_digest = None

    def __init__(self, delegate: RuntimeHandler) -> None:
        self.delegate = delegate
        self.handler_binding_digest = delegate.handler_binding_digest

    def execute(self, assignment: object, claim: object, context: object) -> object:
        self.delegate.execute(assignment, claim, context)  # type: ignore[arg-type]
        raise RuntimeError("injected crash after materializer commit")


class _RevokeBeforeMaterializerCommit:
    interpreter_profile_digest = None
    operation_contract_digest = None

    def __init__(self, database: LiveP0CDatabase, delegate: RuntimeHandler) -> None:
        self.database = database
        self.delegate = delegate
        self.handler_binding_digest = delegate.handler_binding_digest

    def execute(self, assignment: object, claim: object, context: object) -> object:
        with self.database.engine.begin() as connection:
            connection.execute(
                sa.update(PUBLIC_TABLES["runtime_capability_authority"])
                .where(
                    PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                    == "mrw.first-specimen.gap-successor",
                )
                .values(successor_claim_enabled=False, revision=1)
            )
        return self.delegate.execute(assignment, claim, context)  # type: ignore[arg-type]


class _CrashOnceBeforeMaterializerCommit:
    interpreter_profile_digest = None
    operation_contract_digest = None

    def __init__(self, delegate: RuntimeHandler) -> None:
        self.delegate = delegate
        self.handler_binding_digest = delegate.handler_binding_digest
        self.crashed = False

    def execute(self, assignment: object, claim: object, context: object) -> object:
        if not self.crashed:
            self.crashed = True
            raise RuntimeError("injected crash before materializer commit")
        return self.delegate.execute(assignment, claim, context)  # type: ignore[arg-type]


def _runtime_materializer_nodes(
    database: LiveP0CDatabase,
    assignment: RuntimeAssignment,
    dependencies: tuple[object, object, object],
    *,
    wrap: Callable[[RuntimeHandler], RuntimeHandler] = lambda handler: handler,
) -> tuple[object, object]:
    catalog, registry, compile_factory = dependencies
    binding = assignment.handler_binding
    assert isinstance(binding, MaterializerBinding)
    node_ids = ("p0d-materializer-node-a", "p0d-materializer-node-b")
    with database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == assignment.work_item_id
            )
            .values(
                state="READY",
                revision=2,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                due_at=NOW,
            )
        )
        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="p0d-materializer-v1",
                catalog_ref="artifact:p0d-materializer-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("p0d-materializer-security"),
                resource_profile_digest=_digest("p0d-materializer-resource"),
            )
        )
        repository = RuntimeNodeRepository(connection)
        for node_id in node_ids:
            repository.register(
                node_id=node_id,
                node_profile_digest=NODE_PROFILE_DIGEST,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                runtime_protocol_version="1",
                started_at=NOW - timedelta(minutes=1),
            )
    handler = wrap(
        PostgresFirstSpecimenSuccessorHandler(
            engine=database.engine,
            tables=database.project_tables,
            scope=database.scope,
            binding=binding,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )
    )
    profile = RuntimeNodeProfile(
        profile_digest=NODE_PROFILE_DIGEST,
        supported_assignment_kinds=frozenset({AssignmentKind.MATERIALIZE_SUCCESSOR}),
    )
    deployment = DeploymentBinding(
        catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        node_profile_digest=NODE_PROFILE_DIGEST,
        runtime_protocol_version="1",
    )
    clock = _AdvancingClock(NOW)
    return tuple(
        compose_postgres_first_specimen_runtime(
            engine=database.engine,
            identity=NodeIdentity(
                node_id=node_id,
                incarnation=f"{node_id}:incarnation:1",
                started_at=NOW - timedelta(minutes=1),
            ),
            profile=profile,
            deployment=deployment,
            protocol=RuntimeNodeProtocol(version="1", claim_batch_size=1),
            control_scope=ControlPlaneScope(
                system_actor_id=node_id,
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=assignment.claim_authority_epoch,
            ),
            installations=(),
            additional_handlers=(handler,),
            clock=clock,
        ).node
        for node_id in node_ids
    )  # type: ignore[return-value]


def test_commit_ack_crash_does_not_repeat_materialization(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, _claim, dependencies = _seed_predecessor(p0c_database)
    assert isinstance(assignment, RuntimeAssignment)
    nodes = _runtime_materializer_nodes(
        p0c_database,
        assignment,
        dependencies,
        wrap=_CrashAfterMaterializerCommit,
    )

    first = nodes[0].run_once()
    second = nodes[1].run_once()

    assert first.results[0].state.value == "RECOVERY_REQUIRED"
    assert first.results[0].disposition.value == "OUTCOME_UNKNOWN"
    assert second.claimed == 0
    with p0c_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.event_type
                    == "SuccessorMaterialized"
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_work_items"])
                .where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == assignment.work_item_id,
                    PUBLIC_TABLES["runtime_work_items"].c.state == "COMPLETED",
                )
            )
            == 1
        )


def test_precommit_crash_requeues_after_lease_and_second_node_converges(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, _claim, dependencies = _seed_predecessor(p0c_database)
    assert isinstance(assignment, RuntimeAssignment)
    nodes = _runtime_materializer_nodes(
        p0c_database,
        assignment,
        dependencies,
        wrap=_CrashOnceBeforeMaterializerCommit,
    )

    first = nodes[0].run_once()
    assert first.results[0].state.value == "RECOVERY_REQUIRED"
    with p0c_database.engine.connect() as connection:
        lease_expires_at = connection.scalar(
            sa.select(PUBLIC_TABLES["runtime_work_items"].c.lease_expires_at).where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == assignment.work_item_id
            )
        )
    assert lease_expires_at is not None
    with RuntimeUnitOfWork(engine=p0c_database.engine) as uow:
        reaped = WorkItemClaimRepository(uow.connection).reap_expired(
            ControlPlaneScope(
                system_actor_id="p0d-materializer-node-a",
                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                authority_epoch=assignment.claim_authority_epoch,
            ),
            now=lease_expires_at + timedelta(seconds=1),
        )
        uow.commit()
    assert reaped == (assignment.work_item_id,)

    second = nodes[1].run_once()

    assert second.claimed == 1
    assert second.results[0].committed is True
    with p0c_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.event_type
                    == "SuccessorMaterialized"
                )
            )
            == 1
        )


def test_final_materializer_uow_revalidates_revoked_authority(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
) -> None:
    assignment, _claim, dependencies = _seed_predecessor(p0c_database)
    assert isinstance(assignment, RuntimeAssignment)
    nodes = _runtime_materializer_nodes(
        p0c_database,
        assignment,
        dependencies,
        wrap=lambda handler: _RevokeBeforeMaterializerCommit(
            p0c_database,
            handler,
        ),
    )

    report = nodes[0].run_once()

    assert report.results[0].state.value == "REJECTED"
    assert report.results[0].disposition.value == "NOT_STARTED"
    with p0c_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_idempotency"]
                )
            )
            == 0
        )


@pytest.mark.parametrize("mode", ["missing", "ambiguous"])
def test_materializer_source_step_resolution_fails_closed(
    p0c_database: LiveP0CDatabase,  # noqa: F811 - pytest fixture injection
    mode: str,
) -> None:
    assignment, claim, dependencies = _seed_predecessor(p0c_database)
    assert isinstance(assignment, RuntimeAssignment)
    catalog, registry, compile_factory = dependencies
    with p0c_database.engine.begin() as connection:
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == assignment.run_id
                )
            )
            .mappings()
            .one()
        )
        if mode == "missing":
            connection.execute(
                sa.update(PUBLIC_TABLES["runtime_steps"])
                .where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == assignment.run_id,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == step["step_id"],
                )
                .values(output_digest=_digest("different-gap-output"))
            )
        else:
            copy = dict(step)
            copy.pop("created_at", None)
            copy.pop("updated_at", None)
            copy["step_id"] = "step:p0d:admitted-gap:duplicate"
            connection.execute(sa.insert(PUBLIC_TABLES["runtime_steps"]).values(**copy))

    with (
        pytest.raises(Exception, match="absent or ambiguous"),
        RuntimeUnitOfWork(engine=p0c_database.engine) as uow,
    ):
        materialize_gap_successor(
            uow.connection,
            p0c_database.scope,
            assignment=assignment,
            claim=claim,
            observed_at=NOW,
            tables=p0c_database.project_tables,
            catalog=catalog,
            operation_contracts=registry,
            compile_assignment_factory=compile_factory,
        )
    with p0c_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_idempotency"]
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.event_type
                    == "SuccessorMaterialized"
                )
            )
            == 0
        )
