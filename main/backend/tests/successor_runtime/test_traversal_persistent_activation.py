"""Fixed-N ordered single-dispatch traversal persistence witness.

Proves that one ordered ``ZipOrdered`` batch Program compiles and activates into
N typed dispatch effects in one run with ordered failfast, unknown-outcome
non-duplication, and cancellation.  The pure compile/activation tests need no
PostgreSQL; the integration tests reuse the P0-B ``live_database`` fixture.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
import traceback
from collections import Counter, deque
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from .single_dispatch_program_fixture import ordered_dispatch_program
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.composition.production import (
    build_program_activation,
    execute_successor_work_item,
    read_installed_program,
    read_installed_program_input_bindings,
    read_installed_program_outputs,
)
from app.composition.production_runtime import install_runtime_authority
from app.services.request_identity import RequestActorContext
from app.services.project_retrieval.execution import (
    _control_literal_node,
    _retrieval_operation_environment,
    build_initial_retrieval_program,
    build_retrieval_runtime_journal_reader,
)
from app.services.project_retrieval.service import ProjectRetrievalService
from app.services import tasks as tasks_module
from app.services.project_retrieval import topology as retrieval_topology
from app.models import base as models_base
from app.models.base import Base
from app.models.entities import Material, Source
from app.models.information_topology_entities import (
    InformationTopologyLink,
    InformationTopologyState,
)
from app.models.project_retrieval import ProjectRetrievalPlan
from app.successor_runtime.capabilities import batch_task as c4
from app.successor_runtime.capabilities.acquisition_url import (
    URL_SINGLE_URL_KIND,
    UrlSingleUrlOutcome,
    build_url_single_url_contract,
    build_url_single_url_profiles,
)
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    RETRIEVAL_BUDGET_STATE_TYPE,
    RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
    build_retrieval_candidate_runtime_definition,
)
from app.successor_runtime.capabilities.retrieval_common import Candidate, CandidateBundle
from app.successor_runtime.capabilities.retrieval_material_native import (
    CANDIDATE_WORK_SEQUENCE_TYPE,
    RETRIEVAL_CONTROL_TYPE,
    RETRIEVAL_CANDIDATE_REVIEW_KIND,
    RETRIEVAL_FOLLOWUP_PLAN_KIND,
    RETRIEVAL_MATERIAL_FORMALIZE_KIND,
    RETRIEVAL_MATERIAL_READ_BODY_KIND,
    RETRIEVAL_MATERIAL_REVALIDATE_KIND,
    RETRIEVAL_TOPOLOGY_COMMIT_KIND,
    RETRIEVAL_LEAF_KINDS,
    RetrievalControl,
    build_candidate_work_codec,
    build_retrieval_leaf_contract,
    build_retrieval_leaf_profiles,
)
from app.successor_runtime.capabilities.batch_task_program import (
    build_ordered_dispatch_merge_registry,
)
from app.successor_runtime.capabilities.checksum import canonical_json
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.language.program import (
    ProgramSpec,
    decode_program_spec,
    encode_program_spec,
    program_atoms,
)
from app.successor_runtime.language.transforms import TransformRegistry
from app.successor_runtime.runtime.activation import activate_plan
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.node import DefiniteInterpreterFailure, RuntimeNode
from app.successor_runtime.runtime.resources import ResourceClass, ResourcePolicySnapshot
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    CapabilityAuthority,
)
from app.successor_runtime.substrate.postgres.runtime_activation import (
    ActivationTrigger,
    compiled_submission_request_digest,
    submit_compiled_program,
)
from app.successor_runtime.substrate.postgres.idempotency import IdempotencyBinding
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    RequestCancel,
    RuntimeLifecycleRepository,
)
from app.successor_runtime.substrate.postgres import session as runtime_session

from .test_runtime_substrate_postgres_integration import (
    LiveDatabase,
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
    _digest,
    live_database as live_database,  # noqa: F401
)

_FIXED_NOW = datetime(2020, 1, 1, tzinfo=UTC)


def _tag() -> str:
    return secrets.token_hex(4)


def _seed_project_scope(connection: sa.Connection) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    connection.execute(
        pg_insert(PUBLIC_TABLES["project_scope_registry"])
        .values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by="integration-test",
        )
        .on_conflict_do_nothing()
    )


def _dispatch_payload(dispatch_id: str, item_key: str) -> c4.BatchTaskSingleDispatchPayload:
    return c4.BatchTaskSingleDispatchPayload(
        schema_version=c4.DISPATCH_SINGLE_PAYLOAD_SCHEMA,
        operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id=dispatch_id,
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        registry_revision=REGISTRY_REVISION,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        capability_id=c4.BATCH_TASK_OWNER,
        item=c4.AgentBatchSubmissionItem(
            job_id="job:1",
            channel="source_library",
            item_key=item_key,
        ),
        lane="main",
        queue="celery",
    )


def _two_payloads(tag: str) -> tuple[c4.BatchTaskSingleDispatchPayload, c4.BatchTaskSingleDispatchPayload]:
    return (
        _dispatch_payload(f"dispatch:ordered:{tag}:001", f"source:{tag}:1"),
        _dispatch_payload(f"dispatch:ordered:{tag}:002", f"source:{tag}:2"),
    )


def _retrieval_plan(tag: str, *, query_count: int, max_materials: int = 2) -> dict[str, Any]:
    queries = [
        {
            "id": f"query:{tag}:{index}",
            "expression": f"water policy {tag} {index}",
            "language": "en",
            "source_route_id": f"route:{tag}",
        }
        for index in range(1, query_count + 1)
    ]
    return {
        "plan_id": f"plan:{tag}",
        "mode_version": "test.v1",
        "route_id": f"route:{tag}",
        "query_ids": [query["id"] for query in queries],
        "queries": queries,
        "limits": {
            "max_queries": query_count,
            "max_materials": max_materials,
            "max_followups": 0,
        },
    }


def _retrieval_followup_plan(tag: str, *, run_id: str) -> dict[str, Any]:
    plan = _retrieval_plan(tag, query_count=1, max_materials=2)
    route_id = str(plan["route_id"])
    query = dict(plan["queries"][0])
    plan["mode_id"] = "integration-retrieval"
    plan["limits"] = {"max_queries": 2, "max_materials": 2, "max_followups": 1}
    plan["topology_ref"] = {
        "project_key": PROJECT_KEY,
        "module_id": "retrieval",
        "namespace": "runs",
        "state_id": f"retrieval-run:{run_id}",
    }
    plan["topology_seed"] = {
        "domain_vocabulary": {
            "域名": "Retrieval integration",
            "节点类型": ["现场", "行动者"],
            "边类型": ["管理"],
            "问题意识视角": ["制度"],
            "大纲节": ["背景"],
            "池": ["来源池A"],
            "档": ["A", "B", "C", "D"],
        },
        "domain_source_ref": {
            "ref": {
                "project_key": PROJECT_KEY,
                "module_id": "retrieval",
                "namespace": "brief",
                "type_id": "source",
                "local_id": "integration-brief",
            },
            "observed_revision": "integration-r1",
            "content_digest": _digest("integration-brief"),
        },
        "source_routes": [{
            "route_id": route_id,
            "pool": "来源池A",
            "status": "planned",
            "outline_sections": ["背景"],
            "node_types": ["行动者"],
            "target_edges": ["管理"],
        }],
        "keyword_plans": [{
            "plan_id": query["id"],
            "kind": "query",
            "expression": query["expression"],
            "execution_status": "not_executed",
            "source_route_id": route_id,
        }],
        "source_registry": [],
    }
    return plan


def _install_retrieval_authority(
    connection: sa.Connection,
    live_database: LiveDatabase,
    *,
    registry: Any,
) -> None:
    administrator = RequestActorContext("deployment-admin", "deployment", True, "localdev-installation")
    candidate = build_retrieval_candidate_runtime_definition()
    declarations = (
        (candidate.operation_contract, candidate.profiles.resource),
        (build_url_single_url_contract(), build_url_single_url_profiles().resource),
        *(
            (build_retrieval_leaf_contract(kind), build_retrieval_leaf_profiles(kind).resource)
            for kind in RETRIEVAL_LEAF_KINDS
        ),
    )
    _seed_project_scope(connection)
    for index, (contract, resource_profile) in enumerate(declarations, start=1):
        resource_class = ResourceClass(resource_profile.resource_classes[0])
        install_runtime_authority(
            connection,
            administrator=administrator,
            project_scope=live_database.runtime_scope.project_scope,
            grant=AuthorityGrant(
                grant_id=f"retrieval-grant:{index}",
                actor_id=live_database.runtime_scope.actor_id,
                capability_id=contract.owner_capability_id,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=(contract.ref.kind,),
                    project_scope_digest=SCOPE_DIGEST,
                ),
                resource_ceiling_json=AuthorityResourceCeiling.from_content(
                    limits=(
                        AuthorityResourceLimit(
                            resource_class=resource_class.value,
                            units=1,
                        ),
                    ),
                    max_active=4,
                ),
                credential_ref=None,
                grant_epoch=1,
                expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            ),
            capability=CapabilityAuthority(
                capability_id=contract.owner_capability_id,
                mode="on",
                authority_epoch=1,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=_digest(f"retrieval-allowlist:{index}"),
                config_digest=_digest(f"retrieval-config:{index}"),
                effective_at=_FIXED_NOW,
                approval_ref=f"deployment:retrieval:{index}",
                rollback_target_ref=f"deployment:retrieval:{index}:disabled",
            ),
            resource=ResourcePolicySnapshot(
                project_key=PROJECT_KEY,
                capability_id=contract.owner_capability_id,
                resource_class=resource_class,
                policy_epoch=1,
                policy_digest=_digest(f"retrieval-policy:{index}"),
                max_project_active=4,
                max_capability_active=4,
                max_resource_active=4,
                max_units=4,
            ),
            installed=registry,
        )


def _submit_retrieval_root(
    connection: sa.Connection,
    live_database: LiveDatabase,
    *,
    tag: str,
    run_id: str,
    query_count: int,
    install_authority: bool,
    now: datetime,
) -> Any:
    return _submit_retrieval_plan(
        connection,
        live_database,
        tag=tag,
        run_id=run_id,
        plan=_retrieval_plan(tag, query_count=query_count),
        install_authority=install_authority,
        now=now,
    )


def _submit_retrieval_plan(
    connection: sa.Connection,
    live_database: LiveDatabase,
    *,
    tag: str,
    run_id: str,
    plan: dict[str, Any],
    install_authority: bool,
    now: datetime,
) -> Any:
    root = build_initial_retrieval_program(
        project_key=PROJECT_KEY,
        root_run_id=run_id,
        plan=plan,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        idempotency_key=f"retrieval-idem-key:{tag}",
    )
    if install_authority:
        _install_retrieval_authority(
            connection,
            live_database,
            registry=root.registry,
        )
    activation, _ = build_program_activation(
        connection,
        live_database.runtime_scope,
        root.program,
    )
    submit_compiled_program(
        connection,
        live_database.runtime_scope,
        program=root.program,
        operation_catalog=root.catalog,
        operation_contracts=root.registry,
        activation_catalog=activation,
        values=root.values,
        idempotency=IdempotencyBinding(
            idempotency_id=f"retrieval-idem:{tag}",
            capability_id=build_retrieval_candidate_runtime_definition().operation_contract.owner_capability_id,
            logical_request_id=root.logical_request_id,
            operation_kind=build_retrieval_candidate_runtime_definition().operation_contract.ref.kind,
            run_id=run_id,
            request_digest=compiled_submission_request_digest(
                root.program,
                live_database.runtime_scope,
                root.canonical_bindings,
                root.approvals_by_step,
            ),
        ),
        incarnation=root.incarnation,
        canonical_bindings=root.canonical_bindings,
        approvals_by_step=root.approvals_by_step,
        trigger=ActivationTrigger(now, f"trace:retrieval:{tag}", now),
    )
    return root


def _ready_work_ids(
    connection: sa.Connection,
    *,
    run_id: str,
) -> tuple[str, ...]:
    work = PUBLIC_TABLES["runtime_work_items"]
    return tuple(
        connection.execute(
            sa.select(work.c.work_item_id)
            .where(work.c.run_id == run_id, work.c.state == "READY")
            .order_by(work.c.enqueue_seq)
        ).scalars()
    )


def _install_real_task_transport(
    monkeypatch: pytest.MonkeyPatch,
    live_database: LiveDatabase,
) -> deque[str]:
    queued: deque[str] = deque()
    original_error_code = RuntimeNode._error_code

    def capture_node_error(exc: Exception, *, default: str = "NODE_PORT_RESULT_INVALID") -> str:
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        return original_error_code(exc, default=default)

    monkeypatch.setattr(RuntimeNode, "_error_code", staticmethod(capture_node_error))

    def capture_next(
        args: tuple[object, ...] = (),
        **_: object,
    ) -> object:
        queued.append(str(args[0]))
        return object()

    monkeypatch.setattr(
        runtime_session,
        "create_runtime_engine",
        lambda *_args, **_kwargs: live_database.engine,
    )
    monkeypatch.setattr(sa.engine.Engine, "dispose", lambda _engine: None)
    monkeypatch.setattr(tasks_module.task_successor_runtime, "apply_async", capture_next)
    return queued


def _run_real_task(work_item_id: str) -> dict[str, object]:
    return tasks_module.task_successor_runtime.run(work_item_id)


@contextmanager
def _persisted_materials(
    live_database: LiveDatabase,
    rows: tuple[dict[str, object], ...],
):
    tables = (Source.__table__, Material.__table__)
    with live_database.engine.begin() as connection:
        scoped = connection.execution_options(schema_translate_map={None: PROJECT_SCHEMA})
        Base.metadata.create_all(scoped, tables=tables, checkfirst=True)
        inserted = tuple(
            int(
                scoped.execute(
                    sa.insert(Material.__table__).values(**row).returning(Material.__table__.c.id)
                ).scalar_one()
            )
            for row in rows
        )
    try:
        yield inserted
    finally:
        with live_database.engine.begin() as connection:
            scoped = connection.execution_options(schema_translate_map={None: PROJECT_SCHEMA})
            Base.metadata.drop_all(scoped, tables=tuple(reversed(tables)), checkfirst=True)


@contextmanager
def _persisted_retrieval_plan(
    live_database: LiveDatabase,
    plan: dict[str, Any],
):
    tables = (
        ProjectRetrievalPlan.__table__,
        InformationTopologyState.__table__,
        InformationTopologyLink.__table__,
    )
    scoped_engine = live_database.engine.execution_options(
        schema_translate_map={None: PROJECT_SCHEMA}
    )
    previous_bind = models_base.SessionLocal.kw.get("bind")
    models_base.SessionLocal.configure(bind=scoped_engine)
    try:
        with live_database.engine.begin() as connection:
            scoped = connection.execution_options(schema_translate_map={None: PROJECT_SCHEMA})
            Base.metadata.create_all(scoped, tables=tables, checkfirst=True)
        with models_base.SessionLocal() as session:
            session.add(
                ProjectRetrievalPlan(
                    project_key=PROJECT_KEY,
                    plan_id=str(plan["plan_id"]),
                    mode_id=str(plan["mode_id"]),
                    mode_version=str(plan["mode_version"]),
                    payload=plan,
                )
            )
            session.commit()
        yield
    finally:
        models_base.SessionLocal.configure(bind=previous_bind)
        with live_database.engine.begin() as connection:
            scoped = connection.execution_options(schema_translate_map={None: PROJECT_SCHEMA})
            Base.metadata.drop_all(scoped, tables=tuple(reversed(tables)), checkfirst=True)


def test_ordered_program_compiles_to_ordered_effects() -> None:
    payloads = _two_payloads("static")
    catalog = c4.build_batch_task_single_dispatch_catalog()
    registry = c4.build_batch_task_single_dispatch_registry()
    program = ordered_dispatch_program(
        payloads=payloads,
        catalog=catalog,
        program_id="ordered-program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        merge_registry=build_ordered_dispatch_merge_registry(),
    )
    atoms = program_atoms(program.root)

    effects = [s for s in plan.ordered_steps if s.step_kind == "EFFECT"]
    merges = [s for s in plan.ordered_steps if s.step_kind == "MERGE"]
    assert len(effects) == 2
    assert len(merges) == 1
    assert [a.operation.operation_id for a in atoms] == [
        f"{c4.DISPATCH_SINGLE_OPERATION_ID}:{payload.dispatch_id}" for payload in payloads
    ]
    assert len({a.operation.payload_ref.value_id for a in atoms}) == 2
    # Ordered failfast: the second effect depends on the first terminal.
    assert effects[0].dependencies == ()
    assert effects[1].dependencies == (effects[0].step_id,)


def test_ordered_program_activation_releases_one_effect_first() -> None:
    payloads = _two_payloads("static")
    catalog = c4.build_batch_task_single_dispatch_catalog()
    registry = c4.build_batch_task_single_dispatch_registry()
    program = ordered_dispatch_program(
        payloads=payloads,
        catalog=catalog,
        program_id="ordered-program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        merge_registry=build_ordered_dispatch_merge_registry(),
    )
    empty = TransformRegistry(registry_id="empty")
    result = activate_plan(
        run_id="run:ordered",
        program=program,
        plan=plan,
        transform_registry=empty,
        merge_registry=build_ordered_dispatch_merge_registry(),
        discriminator_registry=empty,
    )
    assert len(result.activations) == 1
    effects = [s for s in plan.ordered_steps if s.step_kind == "EFFECT"]
    assert result.activations[0].step_id == effects[0].step_id


def test_dispatch_sequence_readback_builds_ordered_successor() -> None:
    payloads = _two_payloads("static")
    sequence_bytes = canonical_json(
        [dataclasses.asdict(payload) for payload in payloads],
    ).encode()
    contract = c4.build_batch_task_single_dispatch_contract()
    codec = c4.build_batch_task_single_dispatch_payload_codec(contract.ref)
    decoded = tuple(codec.decode_payload(item) for item in json.loads(sequence_bytes))
    assert [payload.dispatch_id for payload in decoded] == [payload.dispatch_id for payload in payloads]

    catalog = c4.build_batch_task_single_dispatch_catalog()
    successor = ordered_dispatch_program(
        payloads=decoded,
        catalog=catalog,
        program_id="successor-program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_program(
        successor,
        catalog,
        operation_contracts=c4.build_batch_task_single_dispatch_registry(),
        merge_registry=build_ordered_dispatch_merge_registry(),
    )
    effects = [s for s in plan.ordered_steps if s.step_kind == "EFFECT"]
    assert len(effects) == 2
    assert effects[1].dependencies == (effects[0].step_id,)


def test_retrieval_control_topology_seed_keeps_declared_shapes_through_activation() -> None:
    """The real followup control survives Program v2 persistence and PURE activation."""

    plan_snapshot = _retrieval_followup_plan(
        "shape-witness", run_id="retrieval-shape-witness"
    )
    control = RetrievalControl(
        project_key=PROJECT_KEY,
        root_run_id="retrieval-shape-witness",
        retrieval_budget_id="budget:shape-witness",
        plan_id=str(plan_snapshot["plan_id"]),
        mode_version=str(plan_snapshot["mode_version"]),
        route_id=str(plan_snapshot["route_id"]),
        round=1,
        plan_snapshot=plan_snapshot,
        budget={"max_queries": 2, "max_materials": 2, "max_followups": 1},
    )
    program = ProgramSpec(
        program_id="program:retrieval-shape-witness",
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        semantic_identity="project_retrieval.shape-witness.v1",
        input_type=CANDIDATE_WORK_SEQUENCE_TYPE,
        output_type=RETRIEVAL_CONTROL_TYPE,
        root=_control_literal_node(CANDIDATE_WORK_SEQUENCE_TYPE, control),
        algebra_refs=(),
        transform_refs=(),
        observation_profile="project_retrieval.shape-witness.observation.v1",
        metadata=freeze_json_object({"schema": "shape-witness.v1"}),
        program_digest="",
    ).with_digest()
    catalog, registry = _retrieval_operation_environment()
    empty = TransformRegistry(registry_id="shape-witness-empty")
    normalized = normalize_program(program)
    compiled = compile_program(
        normalized, catalog, operation_contracts=registry,
        transform_registry=empty, merge_registry=empty,
        discriminator_registry=empty,
    )
    decoded = decode_program_spec(encode_program_spec(normalized))
    recompiled = compile_program(
        decoded, catalog, operation_contracts=registry,
        transform_registry=empty, merge_registry=empty,
        discriminator_registry=empty,
    )
    result = activate_plan(
        run_id="retrieval-shape-witness", program=decoded, plan=recompiled,
        transform_registry=empty, merge_registry=empty,
        discriminator_registry=empty,
    )

    assert compiled.program_digest == normalized.program_digest == decoded.program_digest
    assert len(result.values) == 1 and result.materializations
    seed = result.values[0].value["plan_snapshot"]["topology_seed"]
    assert seed["source_registry"] == []
    assert isinstance(seed["source_registry"], list)
    vocabulary = seed["domain_vocabulary"]
    assert len(vocabulary) == 7 and isinstance(vocabulary, dict)
    assert all(isinstance(vocabulary[key], list) for key in (
        "节点类型", "边类型", "问题意识视角", "大纲节", "池", "档"
    ))
    assert seed["source_routes"][0]["outline_sections"] == ["背景"]
    assert seed["source_routes"][0]["node_types"] == ["行动者"]
    assert seed["source_routes"][0]["target_edges"] == ["管理"]
    assert isinstance(seed["domain_source_ref"]["ref"], dict)
    assert result.materializations[0].value == result.values[0].value


def _submit_ordered(
    connection: sa.Connection,
    live_database: LiveDatabase,
    *,
    tag: str,
    run_id: str,
    contract: Any,
    catalog: Any,
    registry: Any,
    program: Any,
    values: tuple[tuple[Any, bytes], ...],
    canonical_bindings: dict[str, tuple[int, str]],
    now: datetime,
) -> None:
    administrator = RequestActorContext(
        "deployment-admin",
        "deployment",
        True,
        "localdev-installation",
    )
    capability = CapabilityAuthority(
        capability_id=contract.owner_capability_id,
        mode="on",
        authority_epoch=1,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=_digest("allowlist"),
        config_digest=_digest("config"),
        effective_at=_FIXED_NOW,
        approval_ref="deployment:ordered-localdev",
        rollback_target_ref="deployment:ordered-localdev-disabled",
    )
    resource = ResourcePolicySnapshot(
        project_key=PROJECT_KEY,
        capability_id=contract.owner_capability_id,
        resource_class=ResourceClass.NETWORK_IO,
        policy_epoch=1,
        policy_digest=_digest("ordered-policy"),
        max_project_active=2,
        max_capability_active=2,
        max_resource_active=2,
        max_units=2,
    )
    grant = AuthorityGrant(
        grant_id="ordered-grant",
        actor_id=live_database.runtime_scope.actor_id,
        capability_id=contract.owner_capability_id,
        operation_scope_json=AuthorityOperationScope.from_content(
            operation_kinds=(contract.ref.kind,),
            project_scope_digest=SCOPE_DIGEST,
        ),
        resource_ceiling_json=AuthorityResourceCeiling.from_content(
            limits=(AuthorityResourceLimit(resource_class="NETWORK_IO", units=1),),
            max_active=2,
        ),
        credential_ref=None,
        grant_epoch=1,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    _seed_project_scope(connection)
    install_runtime_authority(
        connection,
        administrator=administrator,
        project_scope=live_database.runtime_scope.project_scope,
        grant=grant,
        capability=capability,
        resource=resource,
        installed=registry,
    )
    activation, _ = build_program_activation(
        connection,
        live_database.runtime_scope,
        program,
    )
    submit_compiled_program(
        connection,
        live_database.runtime_scope,
        program=program,
        operation_catalog=catalog,
        operation_contracts=registry,
        activation_catalog=activation,
        values=values,
        idempotency=IdempotencyBinding(
            idempotency_id=f"ordered-idem-{tag}",
            capability_id=contract.owner_capability_id,
            logical_request_id=f"ordered-request-{tag}",
            operation_kind=contract.ref.kind,
            run_id=run_id,
            request_digest=compiled_submission_request_digest(
                program,
                live_database.runtime_scope,
                canonical_bindings,
                {},
            ),
        ),
        incarnation="ordered-incarnation",
        canonical_bindings=canonical_bindings,
        approvals_by_step={},
        trigger=ActivationTrigger(now, "trace:ordered", now),
    )


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["success", "failfast", "broker_unknown"])
def test_two_item_ordered_dispatch_witness(live_database: LiveDatabase, mode: str) -> None:
    now = datetime.now(UTC)
    tag = _tag()
    run_id = f"ordered-run-{tag}"
    contract = c4.build_batch_task_single_dispatch_contract()
    catalog = c4.build_batch_task_single_dispatch_catalog(contract)
    registry = c4.build_batch_task_single_dispatch_registry(contract)
    payloads = _two_payloads(tag)
    program = ordered_dispatch_program(
        payloads=payloads,
        catalog=catalog,
        program_id=f"ordered-program-{tag}",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        merge_registry=build_ordered_dispatch_merge_registry(),
    )
    effects = [s for s in plan.ordered_steps if s.step_kind == "EFFECT"]
    atoms = program_atoms(program.root)
    canonical_bindings = {s.step_id: (0, "ordered-incarnation") for s in effects}
    values = tuple(
        (atom.operation.payload_ref, canonical_json(payload).encode()) for atom, payload in zip(atoms, payloads)
    )

    with live_database.engine.begin() as connection:
        _submit_ordered(
            connection,
            live_database,
            tag=tag,
            run_id=run_id,
            contract=contract,
            catalog=catalog,
            registry=registry,
            program=program,
            values=values,
            canonical_bindings=canonical_bindings,
            now=now,
        )
        work_rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"].c.work_item_id)
                .where(PUBLIC_TABLES["runtime_work_items"].c.run_id == run_id)
                .order_by(PUBLIC_TABLES["runtime_work_items"].c.enqueue_seq)
            )
            .scalars()
            .all()
        )
        assert len(work_rows) == 1
        first_work_id = work_rows[0]

    dispatched: list[str] = []

    def dispatch(actual: c4.BatchTaskSingleDispatchPayload) -> c4.BatchTaskSingleDispatchAck:
        if mode == "failfast":
            raise DefiniteInterpreterFailure("ORDERED_DISPATCH_DEFINITE_FAILURE")
        dispatched.append(actual.dispatch_id)
        if mode == "broker_unknown":
            raise ConnectionError("broker accepted but acknowledgement was lost")
        return c4.BatchTaskSingleDispatchAck(
            schema_version=c4.DISPATCH_SINGLE_ACK_SCHEMA,
            operation_kind=c4.DISPATCH_SINGLE_KIND,
            dispatch_id=actual.dispatch_id,
            channel=actual.item.channel,
            celery_task_id=f"celery:{actual.dispatch_id}",
            lane=actual.lane,
            queue=actual.queue or "celery",
        )

    first_report = execute_successor_work_item(
        engine=live_database.engine,
        work_item_id=first_work_id,
        node_id=f"ordered-node-{tag}-1",
        dispatch=dispatch,
    )
    assert first_report.claimed == 1
    assert first_report.results[0].committed
    expected_first_disposition = {
        "success": "SUCCEEDED",
        "failfast": "FAILED",
        "broker_unknown": "OUTCOME_UNKNOWN",
    }[mode]
    assert first_report.results[0].disposition.value == expected_first_disposition

    if mode == "failfast":
        with live_database.engine.connect() as connection:
            remaining = connection.execute(
                sa.select(sa.func.count())
                .select_from(
                    PUBLIC_TABLES["runtime_work_items"],
                )
                .where(
                    PUBLIC_TABLES["runtime_work_items"].c.run_id == run_id,
                    PUBLIC_TABLES["runtime_work_items"].c.state == "READY",
                )
            ).scalar_one()
            assert remaining == 0
            run_state = connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == run_id,
                )
            ).scalar_one()
            assert run_state != "COMPLETED"
        assert dispatched == []
        return

    if mode == "broker_unknown":
        # Element 0's outcome is unknown; its dispatch happened once and the
        # second element must never be dispatched. A reconcile work item is
        # scheduled for the unknown outcome rather than a second dispatch.
        with live_database.engine.connect() as connection:
            run_state = connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"].c.state).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == run_id,
                )
            ).scalar_one()
            assert run_state != "COMPLETED"
        assert dispatched == [payloads[0].dispatch_id]
        return

    with live_database.engine.connect() as connection:
        second_work_id = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"].c.work_item_id)
                .where(
                    PUBLIC_TABLES["runtime_work_items"].c.run_id == run_id,
                    PUBLIC_TABLES["runtime_work_items"].c.state == "READY",
                )
                .order_by(PUBLIC_TABLES["runtime_work_items"].c.enqueue_seq)
            )
            .scalars()
            .all()[-1]
        )

    second_report = execute_successor_work_item(
        engine=live_database.engine,
        work_item_id=second_work_id,
        node_id=f"ordered-node-{tag}-2",
        dispatch=dispatch,
    )
    assert second_report.claimed == 1
    assert second_report.results[0].disposition.value == "SUCCEEDED"
    assert dispatched == [payloads[0].dispatch_id, payloads[1].dispatch_id]

    with live_database.engine.connect() as connection:
        run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == run_id,
                )
            )
            .mappings()
            .one()
        )
        assert run["state"] == "COMPLETED"
        ack_values = (
            connection.execute(
                sa.select(live_database.project_tables.successor_values).where(
                    live_database.project_tables.successor_values.c.object_type == c4.DISPATCH_SINGLE_ACK_TYPE.type_id,
                )
            )
            .mappings()
            .all()
        )
        assert len(ack_values) == 2


@pytest.mark.integration
def test_two_item_ordered_dispatch_cancel(live_database: LiveDatabase) -> None:
    now = datetime.now(UTC)
    tag = _tag()
    run_id = f"ordered-cancel-run-{tag}"
    contract = c4.build_batch_task_single_dispatch_contract()
    catalog = c4.build_batch_task_single_dispatch_catalog(contract)
    registry = c4.build_batch_task_single_dispatch_registry(contract)
    payloads = _two_payloads(tag)
    program = ordered_dispatch_program(
        payloads=payloads,
        catalog=catalog,
        program_id=f"ordered-program-{tag}",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        merge_registry=build_ordered_dispatch_merge_registry(),
    )
    effects = [s for s in plan.ordered_steps if s.step_kind == "EFFECT"]
    atoms = program_atoms(program.root)
    canonical_bindings = {s.step_id: (0, "ordered-incarnation") for s in effects}
    values = tuple(
        (atom.operation.payload_ref, canonical_json(payload).encode()) for atom, payload in zip(atoms, payloads)
    )

    with live_database.engine.begin() as connection:
        _submit_ordered(
            connection,
            live_database,
            tag=tag,
            run_id=run_id,
            contract=contract,
            catalog=catalog,
            registry=registry,
            program=program,
            values=values,
            canonical_bindings=canonical_bindings,
            now=now,
        )
        run = RuntimeJournalRepository(connection, live_database.runtime_scope).load_run(
            run_id,
        )
        RuntimeLifecycleRepository(connection, live_database.runtime_scope).request_cancel(
            RequestCancel(
                run_id=run_id,
                expected_run_revision=int(run["revision"]),
                reason="test-cancel",
            ),
        )
        run_after = RuntimeJournalRepository(
            connection,
            live_database.runtime_scope,
        ).load_run(run_id)
        assert run_after["state"] in {"CANCELLED", "CANCELLING"}


def _drain_retrieval_root(
    live_database: LiveDatabase,
    queued: deque[str],
    run_id: str,
) -> tuple[dict[str, object], ...]:
    with live_database.engine.connect() as connection:
        queued.extend(_ready_work_ids(connection, run_id=run_id))
    executed: set[str] = set()
    reports: list[dict[str, object]] = []
    while queued:
        work_id = queued.popleft()
        if work_id in executed:
            continue
        executed.add(work_id)
        result = _run_real_task(work_id)
        assert isinstance(result["claimed"], int)
        reports.append(result)
    return tuple(reports)


def _retrieval_runtime_diagnostics(
    live_database: LiveDatabase,
    *,
    run_id: str,
    task_reports: tuple[dict[str, object], ...],
) -> dict[str, object]:
    with live_database.engine.connect() as connection:
        runs = PUBLIC_TABLES["runtime_runs"]
        steps = PUBLIC_TABLES["runtime_steps"]
        attempts = PUBLIC_TABLES["runtime_effect_attempts"]
        events = PUBLIC_TABLES["runtime_events"]
        root_events = tuple(dict(row) for row in connection.execute(
            sa.select(
                events.c.seq,
                events.c.event_type,
                events.c.step_id,
                events.c.attempt_id,
                events.c.event_metadata_json,
                events.c.payload_ref,
                events.c.payload_digest,
            ).where(events.c.run_id == run_id).order_by(events.c.seq)
        ).mappings())
        child_ids = tuple(
            str(row["event_metadata_json"]["child_run_id"])
            for row in root_events
            if row["event_type"] == "ActiveChildMaterialized"
        )
        children: dict[str, object] = {}
        for child_id in child_ids:
            outputs = read_installed_program_outputs(
                engine=live_database.engine,
                project_key=PROJECT_KEY,
                actor_id=live_database.runtime_scope.actor_id,
                run_id=child_id,
            )
            children[child_id] = {
                "run": dict(connection.execute(
                    sa.select(
                        runs.c.run_id,
                        runs.c.state,
                        runs.c.revision,
                        runs.c.execution_epoch,
                        runs.c.finished_at,
                    ).where(runs.c.run_id == child_id)
                ).mappings().one()),
                "steps": tuple(dict(row) for row in connection.execute(
                    sa.select(
                        steps.c.step_id,
                        steps.c.operation_kind,
                        steps.c.state,
                        steps.c.attempt_count,
                        steps.c.output_digest,
                        steps.c.failure_digest,
                    ).where(steps.c.run_id == child_id).order_by(steps.c.step_id)
                ).mappings()),
                "attempts": tuple(dict(row) for row in connection.execute(
                    sa.select(
                        attempts.c.attempt_id,
                        attempts.c.step_id,
                        attempts.c.disposition,
                        attempts.c.receipt_ref,
                        attempts.c.failure_ref,
                        attempts.c.failure_digest,
                    ).where(attempts.c.run_id == child_id).order_by(attempts.c.created_at)
                ).mappings()),
                "outputs": tuple(
                    {
                        "step_id": step_id,
                        "object_type": ref.object_type.type_id,
                        "value": json.loads(exact),
                    }
                    for step_id, ref, exact in outputs
                ),
            }
        return {
            "task_reports": task_reports,
            "run": dict(connection.execute(
                sa.select(
                    runs.c.run_id,
                    runs.c.state,
                    runs.c.revision,
                    runs.c.execution_epoch,
                    runs.c.finished_at,
                ).where(runs.c.run_id == run_id)
            ).mappings().one()),
            "steps": tuple(dict(row) for row in connection.execute(
                sa.select(
                    steps.c.step_id,
                    steps.c.operation_kind,
                    steps.c.state,
                    steps.c.attempt_count,
                    steps.c.output_digest,
                    steps.c.failure_digest,
                ).where(steps.c.run_id == run_id).order_by(steps.c.step_id)
            ).mappings()),
            "attempts": tuple(dict(row) for row in connection.execute(
                sa.select(
                    attempts.c.attempt_id,
                    attempts.c.step_id,
                    attempts.c.disposition,
                    attempts.c.receipt_ref,
                    attempts.c.failure_ref,
                    attempts.c.failure_digest,
                ).where(attempts.c.run_id == run_id).order_by(attempts.c.created_at)
            ).mappings()),
            "events": root_events,
            "children": children,
        }


@pytest.mark.integration
def test_retrieval_two_empty_parents_reuse_typed_n0_values_without_cleanup(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two roots settle one empty CandidateWork traversal without cleanup."""

    from app.services.search import candidate_search

    topics: list[str] = []
    node_errors: list[dict[str, str]] = []
    original_error_code = RuntimeNode._error_code

    def capture_node_error(exc: Exception, *, default: str = "NODE_PORT_RESULT_INVALID") -> str:
        node_errors.append({
            "type": type(exc).__name__,
            "message": str(exc),
            "repr": repr(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        })
        return original_error_code(exc, default=default)

    monkeypatch.setattr(RuntimeNode, "_error_code", staticmethod(capture_node_error))

    def no_candidates(request: Any) -> CandidateBundle:
        topics.append(request.topic)
        return CandidateBundle(
            request=request,
            candidates=(),
            occurrences=(),
            observations=(),
            stop_reason="no_candidates_observed",
        )

    monkeypatch.setattr(candidate_search, "discover_candidates", no_candidates)
    queued = _install_real_task_transport(monkeypatch, live_database)
    roots = []
    with live_database.engine.begin() as connection:
        for suffix, install in (("a", True), ("b", False)):
            roots.append(
                _submit_retrieval_root(
                    connection,
                    live_database,
                    tag=f"empty-{suffix}",
                    run_id=f"retrieval-empty-parent-{suffix}",
                    query_count=1,
                    install_authority=install,
                    now=datetime.now(UTC),
                )
            )
    task_reports = tuple(
        report
        for root in roots
        for report in _drain_retrieval_root(live_database, queued, root.run_id)
    )
    task_outcome_rows: list[dict[str, object]] = []
    for report in task_reports:
        outcomes = report.get("results")
        assert isinstance(outcomes, list), report
        for outcome in outcomes:
            assert isinstance(outcome, dict), report
            task_outcome_rows.append(outcome)
    task_outcomes = tuple(task_outcome_rows)
    task_errors = tuple(
        outcome
        for outcome in task_outcomes
        if outcome.get("failure_code") is not None
        or outcome.get("disposition") in {"FAILED", "OUTCOME_UNKNOWN"}
    )

    assert len(topics) == 2
    diagnostics = {
        root.run_id: _retrieval_runtime_diagnostics(
            live_database,
            run_id=root.run_id,
            task_reports=task_reports,
        )
        for root in roots
    }
    with live_database.engine.connect() as connection:
        runs = PUBLIC_TABLES["runtime_runs"]
        actual_runs = connection.execute(
            sa.select(runs.c.run_id, runs.c.state)
            .where(runs.c.run_id.in_(tuple(root.run_id for root in roots)))
            .order_by(runs.c.run_id)
        ).all()
        expected_runs = [
            ("retrieval-empty-parent-a", "COMPLETED"),
            ("retrieval-empty-parent-b", "COMPLETED"),
        ]
        assert not task_errors and actual_runs == expected_runs, json.dumps(
            {
                "node_errors": node_errors,
                "task_errors": task_errors,
                "task_outcomes": task_outcomes,
                "parent_journal": diagnostics,
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        events = PUBLIC_TABLES["runtime_events"]
        settlements = connection.execute(
            sa.select(events.c.run_id, events.c.event_metadata_json).where(
                events.c.run_id.in_(tuple(root.run_id for root in roots)),
                events.c.event_type == "ActiveChildrenSettled",
            )
        ).all()
        assert Counter(row.run_id for row in settlements) == {
            "retrieval-empty-parent-a": 1,
            "retrieval-empty-parent-b": 1,
        }
        assert all(row.event_metadata_json["child_count"] == 0 for row in settlements)
        values = live_database.project_tables.successor_values
        empty_work = connection.execute(
            sa.select(sa.func.count()).select_from(values).where(
                values.c.object_type == CANDIDATE_WORK_SEQUENCE_TYPE.type_id,
                values.c.content_bytes == b"[]",
            )
        ).scalar_one()
        assert empty_work == 1


@pytest.mark.integration
def test_retrieval_n2_real_task_frontier_rebuilds_children_and_reads_real_bodies(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted candidates execute the five-effect child and typed readback."""

    from app.services.ingest import url_pool
    from app.services.search import candidate_search
    from app.services.project_retrieval import execution as retrieval_execution

    candidate_topics: list[str] = []
    acquired_urls: list[str] = []
    queued = _install_real_task_transport(monkeypatch, live_database)
    test_session_factory = sessionmaker(
        bind=live_database.engine.execution_options(schema_translate_map={None: PROJECT_SCHEMA}),
        expire_on_commit=False,
    )
    monkeypatch.setattr(retrieval_topology, "SessionLocal", test_session_factory)
    monkeypatch.setattr(
        retrieval_execution,
        "build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    retrieval_plan = _retrieval_plan("n2-real-task", query_count=2)
    for query in retrieval_plan["queries"]:
        query["expression"] = "水务政策 " + query["id"]
        query["language"] = "zh"

    with _persisted_materials(
        live_database,
        (
            {
                "material_type": "web", "title": "英国水务政策", "status": "active",
                "content": "英国政府发布的水务政策正文。",
                "uri": "https://www.gov.uk/water-policy", "text_hash": _digest("gov-body"),
            },
            {
                "material_type": "web", "title": "美国环保署水务政策", "status": "active",
                "content": "美国环保署发布的水务政策正文。",
                "uri": "https://epa.gov/water-policy", "text_hash": _digest("epa-body"),
            },
        ),
    ) as material_ids:
        urls = ("https://www.gov.uk/water-policy", "https://epa.gov/water-policy")

        def discover(request: Any) -> CandidateBundle:
            index = len(candidate_topics)
            candidate_topics.append(request.topic)
            return CandidateBundle(
                request=request,
                candidates=(Candidate(
                    resource_uri=urls[index], title="水务政策", snippet="政策",
                    source="controlled-provider", keyword="water policy",
                    original_rank=1, result_rank=1, relevance_score=1.0,
                ),),
                occurrences=(), observations=(), stop_reason="candidates_observed",
            )

        def acquire(request: Any) -> UrlSingleUrlOutcome:
            acquired_urls.append(request.url)
            return UrlSingleUrlOutcome(
                status="completed", inserted=1, updated=0, skipped=0,
                material_id=material_ids[urls.index(request.url)],
            )

        monkeypatch.setattr(candidate_search, "discover_candidates", discover)
        monkeypatch.setattr(url_pool, "invoke_url_single_url", acquire)
        with live_database.engine.begin() as connection:
            root = _submit_retrieval_plan(
                connection, live_database, tag="n2-real-task",
                run_id="retrieval-n2-real-task-parent", plan=retrieval_plan,
                install_authority=True, now=datetime.now(UTC),
            )
        task_reports = _drain_retrieval_root(live_database, queued, root.run_id)

        assert candidate_topics == [
            "水务政策 query:n2-real-task:1",
            "水务政策 query:n2-real-task:2",
        ]
        assert acquired_urls == list(urls), json.dumps(
            _retrieval_runtime_diagnostics(
                live_database,
                run_id=root.run_id,
                task_reports=task_reports,
            ),
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        with live_database.engine.connect() as connection:
            parent = connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == root.run_id
                )
            ).mappings().one()
            assert parent["state"] == "COMPLETED"
            children = tuple(
                str(row["event_metadata_json"]["child_run_id"])
                for row in connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_events"].c.event_metadata_json).where(
                        PUBLIC_TABLES["runtime_events"].c.run_id == root.run_id,
                        PUBLIC_TABLES["runtime_events"].c.event_type == "ActiveChildMaterialized",
                    )
                ).mappings()
            )
            steps = PUBLIC_TABLES["runtime_steps"]
            child_steps = connection.execute(
                sa.select(steps.c.operation_kind, steps.c.state, steps.c.attempt_count).where(
                    steps.c.run_id.in_(children),
                    steps.c.operation_kind.in_((
                        RETRIEVAL_CANDIDATE_REVIEW_KIND, URL_SINGLE_URL_KIND,
                        RETRIEVAL_MATERIAL_READ_BODY_KIND, RETRIEVAL_MATERIAL_FORMALIZE_KIND,
                        RETRIEVAL_MATERIAL_REVALIDATE_KIND,
                    )),
                )
            ).all()
            assert len(children) == 2
            assert Counter(row.operation_kind for row in child_steps) == {
                RETRIEVAL_CANDIDATE_REVIEW_KIND: 2,
                URL_SINGLE_URL_KIND: 2,
                RETRIEVAL_MATERIAL_READ_BODY_KIND: 2,
                RETRIEVAL_MATERIAL_FORMALIZE_KIND: 2,
                RETRIEVAL_MATERIAL_REVALIDATE_KIND: 2,
            }
            assert all(row.state == "SUCCEEDED" and row.attempt_count == 1 for row in child_steps)

        outputs = read_installed_program_outputs(
            engine=live_database.engine, project_key=PROJECT_KEY,
            actor_id=live_database.runtime_scope.actor_id, run_id=root.run_id,
        )
        budget_static, started_bindings = read_installed_program_input_bindings(
            engine=live_database.engine, project_key=PROJECT_KEY,
            actor_id=live_database.runtime_scope.actor_id, run_id=root.run_id,
            static_input_type=RETRIEVAL_BUDGET_STATE_TYPE,
        )
        invocation_static, same_started_bindings = read_installed_program_input_bindings(
            engine=live_database.engine, project_key=PROJECT_KEY,
            actor_id=live_database.runtime_scope.actor_id, run_id=root.run_id,
            static_input_type=RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
        )
        assert len(budget_static) == 1
        assert budget_static[0][0].object_type == RETRIEVAL_BUDGET_STATE_TYPE
        assert len(invocation_static) == 2
        assert all(
            ref.object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
            for ref, _ in invocation_static
        )
        assert started_bindings == same_started_bindings
        invocation_started = tuple(
            item for item in started_bindings
            if item[2].object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
        )
        started_payloads = [json.loads(item[3]) for item in invocation_started]
        assert [item["request"]["topic"] for item in started_payloads] == candidate_topics
        assert all(
            canonical_json(item).encode("utf-8") == exact
            for item, (_, _, _, exact) in zip(started_payloads, invocation_started, strict=True)
        )
        attempts = PUBLIC_TABLES["runtime_effect_attempts"]
        with live_database.engine.connect() as connection:
            original_attempt = connection.execute(sa.select(
                attempts.c.handler_binding_digest,
                attempts.c.handler_realization_digest,
            ).where(attempts.c.attempt_id == invocation_started[0][1])).mappings().one()
        with live_database.engine.begin() as connection:
            connection.execute(sa.update(attempts).where(
                attempts.c.attempt_id == invocation_started[0][1],
            ).values(
                handler_binding_digest="0" * 64,
                handler_realization_digest="0" * 64,
            ))
        try:
            with pytest.raises(ExactBindingConflict, match="run/step/attempt binding drift"):
                read_installed_program_input_bindings(
                    engine=live_database.engine, project_key=PROJECT_KEY,
                    actor_id=live_database.runtime_scope.actor_id, run_id=root.run_id,
                    static_input_type=RETRIEVAL_BUDGET_STATE_TYPE,
                )
        finally:
            with live_database.engine.begin() as connection:
                connection.execute(sa.update(attempts).where(
                    attempts.c.attempt_id == invocation_started[0][1],
                ).values(
                    handler_binding_digest=original_attempt["handler_binding_digest"],
                    handler_realization_digest=original_attempt["handler_realization_digest"],
                ))

        settled = [json.loads(exact) for _, ref, exact in outputs
                   if ref.object_type == CANDIDATE_WORK_SEQUENCE_TYPE]
        assert len(settled) == 1 and len(settled[0]) == 2
        codec = build_candidate_work_codec(
            build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND).ref
        )
        works = [codec.decode_payload(item) for item in settled[0]]
        assert all(work.stage == "revalidated" for work in works)
        assert {work.body["title"] for work in works} == {"英国水务政策", "美国环保署水务政策"}
        assert {work.body_text for work in works} == {
            "英国政府发布的水务政策正文。",
            "美国环保署发布的水务政策正文。",
        }
        assert {work.body["material_id"] for work in works if work.body is not None} == set(material_ids)


@pytest.mark.integration
def test_retrieval_rejected_candidate_calls_no_downstream_effects(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected review returns typed work and executes no URL/body/formalizer effect."""

    from app.services.search import candidate_search
    from app.services.project_retrieval import execution as retrieval_execution

    def discover(request: Any) -> CandidateBundle:
        return CandidateBundle(
            request=request,
            candidates=(Candidate(
                resource_uri="https://blocked.invalid/source", title="Blocked", snippet="",
                source="controlled-provider", keyword="water", original_rank=1,
                result_rank=1, relevance_score=0.1,
            ),),
            occurrences=(), observations=(), stop_reason="candidates_observed",
        )

    monkeypatch.setattr(candidate_search, "discover_candidates", discover)
    monkeypatch.setattr(
        retrieval_execution,
        "build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "rejected", "blocked_reason": "policy"}]},
    )
    queued = _install_real_task_transport(monkeypatch, live_database)
    with live_database.engine.begin() as connection:
        root = _submit_retrieval_root(
            connection, live_database, tag="rejected",
            run_id="retrieval-rejected-parent", query_count=1,
            install_authority=True, now=datetime.now(UTC),
        )
    _drain_retrieval_root(live_database, queued, root.run_id)

    with live_database.engine.connect() as connection:
        events = PUBLIC_TABLES["runtime_events"]
        child_ids = tuple(
            str(row["event_metadata_json"]["child_run_id"])
            for row in connection.execute(
                sa.select(events.c.event_metadata_json).where(
                    events.c.run_id == root.run_id,
                    events.c.event_type == "ActiveChildMaterialized",
                )
            ).mappings()
        )
        steps = PUBLIC_TABLES["runtime_steps"]
        counts = Counter(
            connection.execute(
                sa.select(steps.c.operation_kind).where(
                    steps.c.run_id.in_(child_ids),
                    steps.c.attempt_count > 0,
                )
            ).scalars()
        )
        assert counts[RETRIEVAL_CANDIDATE_REVIEW_KIND] == 1
        assert all(counts[kind] == 0 for kind in (
            URL_SINGLE_URL_KIND, RETRIEVAL_MATERIAL_READ_BODY_KIND,
            RETRIEVAL_MATERIAL_FORMALIZE_KIND, RETRIEVAL_MATERIAL_REVALIDATE_KIND,
        ))


@pytest.mark.integration
def test_retrieval_gap_followup_consumes_suffix_budget_without_replaying_prefix(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A settled gap drives one real follow-up and one exact final readback."""

    from app.services.ingest import url_pool
    from app.services.project_retrieval import formalization
    from app.services.search import candidate_search

    tag = f"followup-{_tag()}"
    run_id = f"retrieval-{tag}-parent"
    plan = _retrieval_followup_plan(tag, run_id=run_id)
    initial_expression = str(plan["queries"][0]["expression"])
    urls = (
        f"https://www.epa.gov/water-research/{tag}",
        f"https://www.cdc.gov/environmental-health/{tag}",
    )
    candidate_topics: list[str] = []
    acquired_urls: list[str] = []
    formalized_bodies: list[str] = []
    queued = _install_real_task_transport(monkeypatch, live_database)
    monkeypatch.setattr(models_base, "engine", live_database.engine)
    monkeypatch.setattr(retrieval_topology, "SessionLocal", models_base.SessionLocal)

    with _persisted_materials(
        live_database,
        (
            {
                "material_type": "web",
                "title": "EPA water research",
                "status": "active",
                "content": "EPA initial body leaves a regulatory mechanism gap.",
                "uri": urls[0],
                "text_hash": _digest("followup-initial-body"),
            },
            {
                "material_type": "web",
                "title": "CDC environmental health",
                "status": "active",
                "content": "CDC follow-up body supplies a second bounded observation.",
                "uri": urls[1],
                "text_hash": _digest("followup-second-body"),
            },
        ),
    ) as material_ids, _persisted_retrieval_plan(live_database, plan):
        material_by_url = dict(zip(urls, material_ids, strict=True))

        def discover(request: Any) -> CandidateBundle:
            index = len(candidate_topics)
            candidate_topics.append(request.topic)
            return CandidateBundle(
                request=request,
                candidates=(Candidate(
                    resource_uri=urls[index],
                    title="Bounded government source",
                    snippet="water policy evidence",
                    source="controlled-provider",
                    keyword="regulatory mechanism",
                    original_rank=1,
                    result_rank=1,
                    relevance_score=1.0,
                ),),
                occurrences=(),
                observations=(),
                stop_reason="candidates_observed",
            )

        def acquire(request: Any) -> UrlSingleUrlOutcome:
            acquired_urls.append(request.url)
            return UrlSingleUrlOutcome(
                status="completed",
                inserted=1,
                updated=0,
                skipped=0,
                material_id=material_by_url[request.url],
            )

        def no_claim(payload: dict[str, Any]) -> dict[str, Any]:
            formalized_bodies.append(str(payload["body"]))
            return {
                "status": "no_claim",
                "gaps": ["regulatory mechanism evidence remains incomplete"],
            }

        monkeypatch.setattr(candidate_search, "discover_candidates", discover)
        monkeypatch.setattr(url_pool, "invoke_url_single_url", acquire)
        monkeypatch.setattr(formalization, "formalize_material", no_claim)

        with live_database.engine.begin() as connection:
            root = _submit_retrieval_plan(
                connection,
                live_database,
                tag=tag,
                run_id=run_id,
                plan=plan,
                install_authority=True,
                now=datetime.now(UTC),
            )
        _drain_retrieval_root(live_database, queued, root.run_id)

        assert len(candidate_topics) == 2
        assert candidate_topics[0] == initial_expression
        assert candidate_topics[1] != initial_expression
        assert acquired_urls == list(urls)
        assert len(formalized_bodies) == 2

        outputs = read_installed_program_outputs(
            engine=live_database.engine,
            project_key=PROJECT_KEY,
            actor_id=live_database.runtime_scope.actor_id,
            run_id=root.run_id,
        )
        planned_controls = [
            json.loads(exact)
            for _, ref, exact in outputs
            if ref.object_type == RETRIEVAL_CONTROL_TYPE
            and json.loads(exact).get("state") == "planned"
        ]
        assert len(planned_controls) == 1
        assert planned_controls[0]["budget"] == {
            "queries_attempted": 1,
            "materials_accepted": 1,
            "remaining_queries": 1,
            "remaining_materials": 1,
            "max_queries": 2,
            "max_materials": 2,
            "gap_count": 1,
        }
        assert planned_controls[0]["planned_query"]["max_results"] == 1

        control = RetrievalControl(
            project_key=PROJECT_KEY,
            root_run_id=root.run_id,
            retrieval_budget_id=root.budget.budget_id,
            plan_id=str(plan["plan_id"]),
            mode_version=str(plan["mode_version"]),
            route_id=str(plan["route_id"]),
            round=0,
            plan_snapshot=plan,
            budget={
                "max_queries": 2,
                "max_materials": 2,
                "max_followups": 1,
                "remaining_queries": 2,
                "remaining_materials": 2,
            },
        )
        journal = build_retrieval_runtime_journal_reader(
            engine=live_database.engine,
            actor_id=live_database.runtime_scope.actor_id,
        )(control)
        assert journal["budget"] == {
            "queries_attempted": 2,
            "materials_accepted": 2,
            "max_queries": 2,
            "max_materials": 2,
            "followup_rounds_started": 1,
            "max_followups": 1,
            "remaining_followups": 0,
            "remaining_queries": 0,
            "remaining_materials": 0,
        }
        assert len(journal["attempts"]) == 2
        assert len(journal["materials"]) == 2

        readback = ProjectRetrievalService().read_run(
            PROJECT_KEY,
            root.run_id,
            actor_id=live_database.runtime_scope.actor_id,
        )
        assert readback["status"] == "completed"
        assert len(readback["attempts"]) == 2
        assert len(readback["materials"]) == 2
        assert readback["topology_write"]["status"] == "completed", readback["topology_write"]

        with live_database.engine.connect() as connection:
            steps = PUBLIC_TABLES["runtime_steps"]
            root_effects = Counter(
                connection.execute(
                    sa.select(steps.c.operation_kind).where(
                        steps.c.run_id == root.run_id,
                        steps.c.attempt_count > 0,
                    )
                ).scalars()
            )
            assert root_effects[build_retrieval_candidate_runtime_definition().operation_contract.ref.kind] == 2
            assert root_effects[RETRIEVAL_FOLLOWUP_PLAN_KIND] == 1
            assert root_effects[RETRIEVAL_TOPOLOGY_COMMIT_KIND] == 1
            topology_row = connection.execution_options(
                schema_translate_map={None: PROJECT_SCHEMA}
            ).execute(
                sa.select(InformationTopologyState.__table__).where(
                    InformationTopologyState.__table__.c.project_key == PROJECT_KEY,
                    InformationTopologyState.__table__.c.state_id == f"retrieval-run:{run_id}",
                    InformationTopologyState.__table__.c.is_current.is_(True),
                )
            ).mappings().one()
            assert topology_row["revision"] == 1
            topology_elements = topology_row["payload"]["elements"]
            attempt_elements = [
                item
                for item in topology_elements
                if item["ref"]["ref"]["type_id"] == "attempt"
            ]
            assert len(attempt_elements) == 2


@pytest.mark.integration
@pytest.mark.parametrize("abort_before", [False, True])
def test_core_url_submit_reaches_canonical_runtime_and_preserves_abort(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch, abort_before: bool,
) -> None:
    from app.services.agent_core.authoring_tools import AuthoringToolContext, authoring_ingest_writing_batch_sources
    from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
    from app.services.agent_core.host_authorization import TrustedHostContext
    from app.services.agent_core.registry import CoreToolRegistry
    from app.services.agent_core.tool_contribution import register_project_tool_contributions
    from app.services.agent_sessions.service import AgentSessionService
    from app.services.agent_sessions.store import InMemoryAgentSessionStore
    from app.services.request_identity import authenticated_actor_context
    from app.services.ingest import url_pool

    queued = _install_real_task_transport(monkeypatch, live_database)
    monkeypatch.setattr("app.models.base.engine", live_database.engine)
    owner = build_initial_retrieval_program(
        project_key=PROJECT_KEY, root_run_id="authority-only", plan=_retrieval_plan("url-core", query_count=1),
        project_registry_revision=REGISTRY_REVISION, project_scope_digest=SCOPE_DIGEST,
        idempotency_key="authority-only",
    )
    with live_database.engine.begin() as connection:
        _install_retrieval_authority(connection, live_database, registry=owner.registry)
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    session_id = service.create_session(
        source="trusted_host", entrypoint_type="agent_core", goal="URL submission", project_key=PROJECT_KEY,
    )["session"]["session_id"]
    host = TrustedHostContext(
        PROJECT_KEY, session_id, "url-pg-thread", "url-pg-turn", "url-pg-input",
        actor_context=authenticated_actor_context(
            actor_id=live_database.runtime_scope.actor_id, source="test-host", auth_mode="test-auth",
        ),
    )
    service.create_host_user_message(host, content="Collect the URL")
    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, authoring_ingest_writing_batch_sources(
        AuthoringToolContext(service=service, structured_data_searcher=lambda **_: {}),
    )) is None
    acquired: list[str] = []

    def acquire(request: Any) -> UrlSingleUrlOutcome:
        acquired.append(request.url)
        return UrlSingleUrlOutcome(status="completed", inserted=0, updated=0, skipped=1)

    monkeypatch.setattr(url_pool, "invoke_url_single_url", acquire)
    runs, work = PUBLIC_TABLES["runtime_runs"], PUBLIC_TABLES["runtime_work_items"]
    with live_database.engine.connect() as connection:
        before_runs = set(connection.execute(sa.select(runs.c.run_id)).scalars())
        before_work = set(connection.execute(sa.select(work.c.work_item_id)).scalars())
    if abort_before:
        service.store.update_session(session_id, {"status": "canceled"})
    result = registry.execute_tool(
        tool_call=CoreToolCall(tool_name="ingest.url_pool.submit", call_id="url-pg-call", arguments={
            "url": "https://example.invalid/url-core", "async_mode": True,
        }),
        request=AgentCoreRequest(message="collect", session_id=session_id, project_key=PROJECT_KEY, turn_id=host.turn_id),
        trusted_context=host, authorization_service=service, emit=lambda _event: None,
    )
    if abort_before:
        assert result.status == "canceled", result.to_dict()
        with live_database.engine.connect() as connection:
            assert set(connection.execute(sa.select(runs.c.run_id)).scalars()) == before_runs
            assert set(connection.execute(sa.select(work.c.work_item_id)).scalars()) == before_work
        assert not queued and not acquired
        return
    assert result.status == "completed", result.to_dict()
    run_id = str(result.structured_content["runtime_run_ref"]).removeprefix("runtime-run:")
    assert result.structured_content["work_item_ids"]
    assert not acquired  # Core submits; the original task owns execution.
    _drain_retrieval_root(live_database, queued, run_id)
    with live_database.engine.connect() as connection:
        run = connection.execute(sa.select(runs).where(runs.c.run_id == run_id)).mappings().one()
        assert run["state"] == "COMPLETED"
        assert run["project_key"] == PROJECT_KEY
        attempts = PUBLIC_TABLES["runtime_effect_attempts"]
        assert connection.execute(sa.select(sa.func.count()).select_from(attempts).where(
            attempts.c.run_id == run_id,
        )).scalar_one() == 1
    readback_run, readback_steps, _events = read_installed_program(
        engine=live_database.engine,
        project_key=PROJECT_KEY,
        actor_id=live_database.runtime_scope.actor_id,
        run_id=run_id,
    )
    assert readback_run["state"] == "COMPLETED"
    url_steps = tuple(
        step for step in readback_steps
        if step["operation_kind"] == URL_SINGLE_URL_KIND
    )
    assert len(url_steps) == 1
    assert url_steps[0]["operation_contract_ref"] == build_url_single_url_contract().ref

    runtime_steps = PUBLIC_TABLES["runtime_steps"]
    with live_database.engine.begin() as connection:
        original_version = connection.execute(
            sa.select(runtime_steps.c.operation_version).where(
                runtime_steps.c.project_key == PROJECT_KEY,
                runtime_steps.c.run_id == run_id,
                runtime_steps.c.step_id == url_steps[0]["step_id"],
            )
        ).scalar_one()
        connection.execute(
            sa.update(runtime_steps).where(
                runtime_steps.c.project_key == PROJECT_KEY,
                runtime_steps.c.run_id == run_id,
                runtime_steps.c.step_id == url_steps[0]["step_id"],
            ).values(operation_version="1.1.0")
        )
    try:
        with pytest.raises(ExactBindingConflict, match="step differs from the exact Plan"):
            read_installed_program(
                engine=live_database.engine,
                project_key=PROJECT_KEY,
                actor_id=live_database.runtime_scope.actor_id,
                run_id=run_id,
            )
    finally:
        with live_database.engine.begin() as connection:
            connection.execute(
                sa.update(runtime_steps).where(
                    runtime_steps.c.project_key == PROJECT_KEY,
                    runtime_steps.c.run_id == run_id,
                    runtime_steps.c.step_id == url_steps[0]["step_id"],
                ).values(operation_version=original_version)
            )
    assert acquired == ["https://example.invalid/url-core"]
    assert service.list_artifacts(session_id)
