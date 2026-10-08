from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.successor_runtime.language.program import (
    DecisionBranch,
    decide_node,
    pure_node,
    then_node,
)
from app.successor_runtime.runtime.activation import BoundStepValue, activate_plan
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    InterpreterBinding,
    RecoveryBinding,
)
from app.successor_runtime.runtime.qualification import (
    AuthoritySourceBinding,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.postgres.runtime_activation import (
    ActivationCatalogEntry,
    OperationActivationCatalog,
    _assignment,
    _bind_materializations_to_project,
    _require_exact_existing,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
)
from tests.successor_runtime.test_p0c_activation import (
    INPUT,
    MID,
    OUTPUT,
    _claim_or_gap,
    _compile,
    _digest,
    _empty_registries,
    _operation,
    _program,
    _value,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


def test_project_rebind_preserves_dynamic_prefix_static_suffix_and_descriptor_digest() -> None:
    transforms, merges, discriminators = _empty_registries()
    first, first_contract = _operation("pg-first", INPUT, MID)
    second, second_contract = _operation("pg-second", MID, OUTPUT)
    program = _program(then_node(first, then_node(pure_node(MID, MID, {"seed": 1}, "json-v1"), second)))
    plan = _compile(
        program,
        (first_contract, second_contract),
        transforms,
        merges,
        discriminators,
    )
    first_step = next(step for step in plan.ordered_steps if step.operation_id == "pg-first")
    second_step = next(step for step in plan.ordered_steps if step.operation_id == "pg-second")
    dynamic = _value("pg-first-result", MID, value={"effect": 1})
    raw = activate_plan(
        run_id="run-pg-order",
        program=program,
        plan=plan,
        completed_outputs=(BoundStepValue(first_step.step_id, dynamic, {"effect": 1}),),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({first_step.step_id}),
    )
    rebound = _bind_materializations_to_project(raw, plan)

    descriptor = next(item for item in rebound.activations if item.step_id == second_step.step_id)
    assert descriptor.ordered_dependency_refs[0].storage_kind == "project_value_ref"
    assert descriptor.ordered_dependency_refs[0].storage_ref.startswith("project-value:")
    assert descriptor.ordered_input_refs == (
        *descriptor.ordered_dependency_refs,
        *second.operation.input_refs,
    )
    assert descriptor.input_closure_digest != raw.activations[0].input_closure_digest
    assert len(descriptor.activation_digest) == 64


def test_dependency_unmet_does_not_fabricate_downstream_activation() -> None:
    transforms, merges, discriminators = _empty_registries()
    first, first_contract = _operation("pg-dependency-first", INPUT, MID)
    second, second_contract = _operation("pg-dependency-second", MID, OUTPUT)
    program = _program(then_node(first, second))
    plan = _compile(
        program,
        (first_contract, second_contract),
        transforms,
        merges,
        discriminators,
    )
    result = activate_plan(
        run_id="run-pg-dependency",
        program=program,
        plan=plan,
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )
    assert tuple(item.operation_id for item in result.activations) == (
        "pg-dependency-first",
    )


def test_branch_releases_only_selected_effect_and_duplicate_pair_is_absent_or_exact(monkeypatch) -> None:
    transforms, merges, discriminators = _empty_registries()
    discriminator = discriminators.register_discriminator(
        name="activation.pg.branch",
        version="1",
        input_type=MID,
        branch_ids=("claim", "gap"),
        func=_claim_or_gap,
    )
    claim, claim_contract = _operation("pg-claim", MID, OUTPUT)
    gap, gap_contract = _operation("pg-gap", MID, OUTPUT)
    program = _program(
        then_node(
            pure_node(INPUT, MID, {"kind": "claim"}, "json-v1"),
            decide_node(
                discriminator,
                (
                    DecisionBranch("claim", "kind == 'claim'", claim),
                    DecisionBranch("gap", "kind == 'gap'", gap),
                ),
            ),
        ),
        transform_refs=(discriminator,),
    )
    plan = _compile(
        program,
        (claim_contract, gap_contract),
        transforms,
        merges,
        discriminators,
    )
    result = _bind_materializations_to_project(
        activate_plan(
            run_id="run-pg-branch",
            program=program,
            plan=plan,
            transform_registry=transforms,
            merge_registry=merges,
            discriminator_registry=discriminators,
        ),
        plan,
    )
    assert tuple(item.operation_id for item in result.activations) == ("pg-claim",)
    from types import SimpleNamespace
    from app.successor_runtime.substrate.postgres.runtime_activation import PostgresRuntimeActivationBindingAdapter
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    monkeypatch.setattr(PlanRepository, "get", lambda *_args: plan)
    descriptor = result.activations[0]
    assignment = SimpleNamespace(plan_digest=plan.plan_digest, step_id=descriptor.step_id)
    actual = PostgresRuntimeActivationBindingAdapter().semantic_input_ref(None, assignment, None, None, descriptor)
    assert actual == descriptor.ordered_dependency_refs[0]
    assert actual != descriptor.payload_ref
    assignment.step_id = "unselected-or-forged"
    with pytest.raises(ExactBindingConflict, match="exact assignment plan"):
        PostgresRuntimeActivationBindingAdapter().semantic_input_ref(None, assignment, None, None, descriptor)
    expected = {"work_item_id": "work:1", "assignment_digest": _digest("assignment")}
    _require_exact_existing(dict(expected), expected, "runtime work item")
    with pytest.raises(ExactBindingConflict, match="assignment_digest"):
        _require_exact_existing(
            {**expected, "assignment_digest": _digest("other")},
            expected,
            "runtime work item",
        )


def _entry(contract_digest: str, *, handler_digest_override: str | None = None):
    deployment = _digest("deployment")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=_digest("profile"),
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=_digest("project-scope"),
        resource_policy_epoch=3,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="p0c-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authoritative_readback_profile_ref="project-value-readback",
    )
    eligibility = QueueEligibility(
        project_key="activation-project",
        capability_id="activation-test",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=3,
        policy_digest=_digest("resource-policy"),
        concurrency_key="activation-project:p0c",
    )
    entry = ActivationCatalogEntry(
        operation_contract_digest=contract_digest,
        interpreter_binding=interpreter,
        recovery_binding=recovery,
        queue_eligibility=eligibility,
        required_node_profile_selector="node-profile:p0c",
        resource_policy_digest=eligibility.policy_digest,
        fairness_key="activation-project",
        effect_class="CPU_LIGHT",
    )
    return entry, interpreter, handler_digest_override or interpreter.binding_digest


def _authorization(step, interpreter: InterpreterBinding, payload_digest: str):
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:activation-project:1",
        source_digest=_digest("project-scope"),
        source_epoch=1,
    )
    eligibility = _entry(step.operation_contract_ref.contract_digest)[0].queue_eligibility
    return StepAuthorizationBinding.from_content(
        run_id="run-admission",
        step_id=step.step_id,
        operation_kind=step.operation_contract_ref.kind,
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        capability_id="activation-test",
        claim_owner="successor",
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        payload_digest=payload_digest,
        actor_id="actor:p0c",
        project_key="activation-project",
        project_registry_revision=1,
        project_scope_digest=_digest("project-scope"),
        interpreter_binding_digest=interpreter.binding_digest,
        deployment_catalog_digest=interpreter.deployment_catalog_digest,
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        resource_ceiling_digest=_digest("ceiling"),
        resource_policy_epoch=3,
        queue_eligibility_digest=eligibility.eligibility_digest,
        grant_epoch=1,
        expires_at=NOW + timedelta(hours=1),
        canonical_base_revision=0,
        canonical_incarnation="activation-project-incarnation",
    )


def test_admission_assignment_binds_staged_effect_pair_and_catalog_rejects_handler_drift() -> None:
    transforms, merges, discriminators = _empty_registries()
    atom, contract = _operation("pg-admitted", INPUT, OUTPUT, admission=True)
    program = _program(atom)
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    effect = next(step for step in plan.ordered_steps if step.step_kind == "EFFECT")
    admission = next(step for step in plan.ordered_steps if step.step_kind == "ADMISSION")
    dynamic = _value("pg-staged", OUTPUT, value={"candidate": 1})
    result = activate_plan(
        run_id="run-admission",
        program=program,
        plan=plan,
        completed_outputs=(BoundStepValue(effect.step_id, dynamic, {"candidate": 1}),),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
        already_activated_step_ids=frozenset({effect.step_id}),
    )
    descriptor = result.activations[0]
    entry, interpreter, _ = _entry(contract.ref.contract_digest)
    authorization = _authorization(admission, interpreter, descriptor.payload_ref.content_digest)
    assignment = _assignment(
        run={
            "project_key": "activation-project",
            "run_id": "run-admission",
            "program_digest": program.program_digest,
            "execution_epoch": 2,
            "incarnation": "run-incarnation",
        },
        plan=plan,
        step=admission,
        descriptor=descriptor,
        authorization=authorization,
        entry=entry,
        trace_id="trace:p0c",
    )
    assert assignment.assignment_kind is AssignmentKind.VERIFY_ADMIT
    assert assignment.compiled_admission_binding is not None
    assert assignment.compiled_admission_binding.effect_step_id == effect.step_id
    assert assignment.input_refs == (
        dynamic.storage_ref,
        *tuple(ref.storage_ref for ref in atom.operation.input_refs),
    )
    assert assignment.payload_ref == atom.operation.payload_ref.storage_ref

    other, _, _ = _entry(_digest("other-contract"))
    with pytest.raises(ValueError, match="interpreter/operation"):
        ActivationCatalogEntry(
            operation_contract_digest=contract.ref.contract_digest,
            interpreter_binding=other.interpreter_binding,
            recovery_binding=other.recovery_binding,
            queue_eligibility=other.queue_eligibility,
            required_node_profile_selector="node-profile:p0c",
            resource_policy_digest=other.resource_policy_digest,
            fairness_key="activation-project",
            effect_class="CPU_LIGHT",
        )

    OperationActivationCatalog(
        entries=(entry,),
        transform_registry=transforms,
        merge_registry=merges,
        discriminator_registry=discriminators,
    )


def test_project_rebind_reuses_original_content_ref_and_rejects_type_drift() -> None:
    from dataclasses import replace
    transforms, merges, discriminators = _empty_registries()
    effect, contract = _operation("canonical-following", MID, OUTPUT)
    program = _program(then_node(pure_node(INPUT, MID, {"same": 1}, "json-v1"), effect))
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    raw = activate_plan(run_id="canonical-run", program=program, plan=plan,
        transform_registry=transforms, merge_registry=merges, discriminator_registry=discriminators)
    original = _bind_materializations_to_project(raw, plan).materializations[0].value_ref
    original = replace(original, value_id="original-content", storage_ref="project-value:original-content",
                       provenance_digest="a" * 64)
    rebound = _bind_materializations_to_project(raw, plan, canonical_value=lambda item: original)
    assert rebound.materializations[0].value_ref == original
    assert rebound.activations[0].ordered_dependency_refs == (original,)
    assert rebound.materializations[0].step_id == raw.materializations[0].step_id
    with pytest.raises(ExactBindingConflict, match="canonical value binding drift"):
        _bind_materializations_to_project(raw, plan, canonical_value=lambda item: replace(original, object_type=OUTPUT))


def test_traversal_rebind_digest_binds_canonical_input_and_occurrence() -> None:
    from dataclasses import replace
    from app.successor_runtime.language.program import traverse_ordered_node
    from app.successor_runtime.language.checksum import sha256_hex

    transforms, merges, discriminators = _empty_registries()
    element, contract = _operation("canonical-traversal-element", MID, OUTPUT)
    traversal = traverse_ordered_node(element, "MATERIALIZED_SHAPE", sequence_codec_version="2")
    program = _program(then_node(pure_node(INPUT, traversal.input_type, ({"seed": 1},), traversal.input_type.codec_id), traversal))
    plan = _compile(program, (contract,), transforms, merges, discriminators)
    raw = activate_plan(run_id="canonical-traversal", program=program, plan=plan,
        transform_registry=transforms, merge_registry=merges, discriminator_registry=discriminators)
    original = _bind_materializations_to_project(raw, plan).materializations[0].value_ref
    canonical = replace(original, value_id="original-sequence", storage_ref="project-value:original-sequence",
                        provenance_digest="b" * 64)
    rebound = _bind_materializations_to_project(raw, plan, canonical_value=lambda item: canonical)
    descriptor = rebound.traversal_materializations[0]
    assert descriptor.input_ref == canonical
    assert descriptor.materialization_digest != raw.traversal_materializations[0].materialization_digest
    assert descriptor.materialization_digest == sha256_hex({
        "schema": "mrw.traverse-ordered.materialization.v1", "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest, "step_id": descriptor.step_id, "input_ref": canonical.to_plain(),
        "input_sequence_digest": descriptor.input_sequence_digest, "shape_digest": descriptor.shape_digest,
        "binding_digest": descriptor.binding_digest,
    })
    assert descriptor.element_count == 1
    assert not rebound.activations


def _settled_sequence(value):
    return [{"seed": index} for index in range(value["count"])]


def _select_claim(_value):
    return "claim"


@pytest.mark.parametrize("count", [0, 2])
def test_settled_traversal_releases_suffix_only_with_exact_project_witness(count: int) -> None:
    from dataclasses import replace
    from app.successor_runtime.language.program import map_output_node, traverse_ordered_node
    from app.successor_runtime.language.checksum import canonical_bytes
    from app.successor_runtime.language.algebra import sha256_digest_bytes
    from app.successor_runtime.runtime.activation import ActivationError, SettledTraversalValue

    transforms, merges, discriminators = _empty_registries()
    element, contract = _operation("settled-element", MID, OUTPUT)
    traversal = traverse_ordered_node(element, "MATERIALIZED_SHAPE", sequence_codec_version="2")
    suffix, suffix_contract = _operation("settled-suffix", traversal.output_type, OUTPUT)
    transform = transforms.register_transform(name="test.settled-sequence", version="1",
        input_type=MID, output_type=traversal.input_type, func=_settled_sequence)
    program = _program(then_node(then_node(
        map_output_node(pure_node(INPUT, MID, {"count": count}, MID.codec_id), transform, traversal.input_type),
        traversal), suffix), transform_refs=(transform,))
    plan = _compile(program, (contract, suffix_contract), transforms, merges, discriminators)
    args = dict(run_id="settled-run", program=program, plan=plan,
                transform_registry=transforms, merge_registry=merges, discriminator_registry=discriminators)
    initial = activate_plan(**args)
    original = _bind_materializations_to_project(initial, plan).materializations[-1].value_ref
    canonical = replace(original, value_id="canonical-input", storage_ref="project-value:canonical-input",
                        provenance_digest="b" * 64)
    descriptor = _bind_materializations_to_project(initial, plan,
        canonical_value=lambda item: canonical if item.value_ref.object_type == traversal.input_type else None).traversal_materializations[0]
    output = [{"result": i} for i in range(count)]
    exact = canonical_bytes(output)
    ref = replace(_value("settled-output", traversal.output_type),
                  content_digest=sha256_digest_bytes(exact), byte_size=len(exact))
    settled = SettledTraversalValue(
        descriptor.step_id, ref, output, descriptor, exact_bytes=exact
    )
    resumed = activate_plan(**args, completed_outputs=(settled,))
    assert not resumed.traversal_materializations
    assert len(resumed.activations) == 1
    assert resumed.activations[0].operation_id == "settled-suffix"
    assert resumed.activations[0].ordered_dependency_refs == (ref,)

    bad_descriptors = [
        replace(descriptor, shape_digest="f" * 64),
        replace(descriptor, materialization_digest="f" * 64),
        replace(descriptor, binding_digest="f" * 64),
        replace(descriptor, element_program_digest="f" * 64),
        replace(descriptor, input_sequence_digest="f" * 64),
        replace(descriptor, input_ref=replace(canonical, project_key="other-project")),
        replace(descriptor, input_ref=replace(canonical, codec_id="other-codec")),
        replace(descriptor, input_ref=replace(canonical, object_type=OUTPUT)),
        replace(descriptor, input_ref=replace(canonical, byte_size=canonical.byte_size + 1)),
        replace(descriptor, input_ref=replace(canonical, value_id="forged", storage_ref="project-value:forged")),
        replace(descriptor, element_count=True),
    ]
    if count:
        bad_descriptors.append(replace(descriptor, element_digests=tuple(reversed(descriptor.element_digests))))
    malformed = [replace(settled, materialization=item) for item in bad_descriptors]
    malformed.extend([
        BoundStepValue(settled.step_id, settled.value_ref, settled.value),
        replace(settled, value_ref=replace(ref, content_digest="f" * 64)),
        replace(settled, value_ref=replace(ref, byte_size=len(exact) + 1)),
        replace(settled, value_ref=replace(ref, codec_id="other-codec")),
        replace(settled, value_ref=replace(ref, object_type=OUTPUT)),
        replace(settled, value=[*output, {"extra": True}]),
        replace(settled, step_id=initial.materializations[0].step_id),
    ])
    semantic = canonical_bytes([{"semantic": "drift"}])
    semantic_ref = replace(
        ref, content_digest=sha256_digest_bytes(semantic), byte_size=len(semantic)
    )
    malformed.append(replace(
        settled, value_ref=semantic_ref, value=[{"semantic": "drift"}],
        exact_bytes=semantic,
    ))
    for candidate in malformed:
        with pytest.raises(ActivationError):
            activate_plan(**args, completed_outputs=(candidate,))

    discriminator = discriminators.register_discriminator(name="test.settled-branch", version="1",
        input_type=traversal.input_type, branch_ids=("claim", "gap"), func=_select_claim)
    branched = _program(then_node(
        map_output_node(pure_node(INPUT, MID, {"count": count}, MID.codec_id), transform, traversal.input_type),
        decide_node(discriminator, (
            DecisionBranch("claim", "True", pure_node(traversal.input_type, traversal.output_type,
                                                                 [{"result": "unused"}], traversal.output_type.codec_id)),
            DecisionBranch("gap", "False", traversal),
        ))), transform_refs=(transform, discriminator))
    branch_plan = _compile(branched, (contract,), transforms, merges, discriminators)
    unselected = next(step for step in branch_plan.ordered_steps if step.transform_ref is not None
                      and step.transform_ref.name == "mrw.traverse_ordered.materialize")
    forged = replace(settled, step_id=unselected.step_id,
                     materialization=replace(descriptor, step_id=unselected.step_id))
    with pytest.raises(ActivationError, match="no released dependency path"):
        activate_plan(**{**args, "program": branched, "plan": branch_plan}, completed_outputs=(forged,))


@pytest.mark.parametrize("mutation", ["duplicate_index", "bool_index", "missing_source", "duplicate_child", "materialization", "missing_current", "multiple_parents"])
def test_ordered_active_child_lineage_rejects_drift(mutation: str) -> None:
    from app.successor_runtime.substrate.postgres.runtime_activation import ordered_active_child_lineage
    rows = [{"run_id": "parent", "event_metadata_json": {
        "source_step_id": "traverse", "child_run_id": f"child-{index}",
        "element_index": index, "materialization_digest": "a" * 64,
    }} for index in range(2)]
    current = {"run_id": "parent", "event_metadata_json": dict(rows[1]["event_metadata_json"])}
    if mutation == "duplicate_index":
        rows[0]["event_metadata_json"]["element_index"] = 1
    elif mutation == "bool_index":
        current["event_metadata_json"]["element_index"] = True
    elif mutation == "missing_source":
        current["event_metadata_json"].pop("source_step_id")
    elif mutation == "duplicate_child":
        rows[0]["event_metadata_json"]["child_run_id"] = "child-1"
    elif mutation == "materialization":
        rows[0]["event_metadata_json"]["materialization_digest"] = "b" * 64
    elif mutation == "missing_current":
        rows.pop()

    class Rows:
        def __init__(self, values):
            self.values = values
        def mappings(self):
            return self
        def __iter__(self):
            return iter(self.values)
        def all(self):
            return self.values
    class Connection:
        def __init__(self):
            self.results = iter(([current, current] if mutation == "multiple_parents" else [current], rows))
        def execute(self, _statement):
            return Rows(next(self.results))
    with pytest.raises(ExactBindingConflict):
        ordered_active_child_lineage(Connection(), project_key="project", child_run_id="child-1")


@pytest.mark.parametrize("drift", [None, "bytes", "size", "type", "codec", "exact_absent"])
def test_project_value_reader_preserves_exact_owner_checks(drift: str | None) -> None:
    import hashlib
    from sqlalchemy import MetaData
    from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
    from app.successor_runtime.substrate.postgres.models import project_tables
    from app.successor_runtime.substrate.postgres.runtime_activation import _read_project_value
    from app.successor_runtime.substrate.postgres.research_ledger import ExactContentConflict, ProjectRecordNotFound
    from tests.successor_runtime.test_p0b_control_plane import _Result
    exact = b'{"value":1}'
    row = {"value_id": "value-a", "project_key": "project-a", "object_type": INPUT.type_id,
           "codec_id": INPUT.codec_id, "content_bytes": exact, "content_json": None,
           "content_digest": hashlib.sha256(exact).hexdigest(), "byte_size": len(exact),
           "provenance_digest": "b" * 64, "revision": 3, "incarnation": "value-inc", "state": "AVAILABLE"}
    if drift == "bytes":
        row["content_bytes"] = b'{}'
    elif drift == "size":
        row["byte_size"] = 100
    elif drift == "type":
        row["object_type"] = "other-type"
    class Connection:
        def __init__(self):
            self.statements = []
        def execute(self, statement):
            self.statements.append(statement)
            # The original query must exclude a value in another codec namespace.
            if drift == "codec":
                assert INPUT.codec_id in statement.compile().params.values()
                return _Result(None)
            return _Result(None if drift == "exact_absent" and len(self.statements) == 2 else row)
    scope = RuntimeScope(ProjectScopeRef("project-a", "project_a", 3, "scope-inc", "a" * 64), "actor")
    connection = Connection()
    tables = project_tables(MetaData(), "project_a")
    if drift is not None:
        with pytest.raises((ExactBindingConflict, ExactContentConflict, ProjectRecordNotFound)):
            _read_project_value(connection, scope, tables, "project-value:value-a", INPUT)
    else:
        ref, observed, stored = _read_project_value(connection, scope, tables, "project-value:value-a", INPUT)
        assert observed == exact and stored["revision"] == 3 and ref.byte_size == len(exact)
        params = connection.statements[1].compile().params
        assert 3 in params.values() and "value-inc" in params.values()
        assert ref.content_digest in params.values()


@pytest.mark.parametrize("drift", [None, "budget", "template"])
def test_operation_payload_slot_uses_semantic_ref_and_preserves_static_checks(monkeypatch, drift) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace
    from app.successor_runtime.capabilities.codecs import PayloadCodec
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure
    from app.successor_runtime.runtime.ports import ProjectScopeRef
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver
    atom, contract = _operation("payload-slot", INPUT, INPUT)
    _, binding, _ = _entry(contract.ref.contract_digest)
    template = atom.operation.payload_ref
    dynamic = _value("selected-input", INPUT, value={"selected": True})
    budget = _value("budget-same-type", INPUT, value={"budget": 1})
    descriptor = SimpleNamespace(payload_ref=template, static_atom_input_refs=(budget, template))
    project = ProjectScopeRef("activation-project", "activation_project", 1, "scope-inc", _digest("project-scope"))
    monkeypatch.setattr(ServerProjectScopeResolver, "resolve", lambda *_args: project)
    reads, invoked, observed = [], [], []
    @contextmanager
    def uow():
        yield SimpleNamespace(connection=object(), commit=lambda: None)
    codec = PayloadCodec(INPUT.codec_id, "1", contract.ref, INPUT.type_id, lambda x: x, lambda x: x, _digest("codec"))
    handler = PersistentOperationHandler(uow_factory=uow, binding=binding, contract=contract,
        input_codec=codec, output_codec=codec, invoke=lambda payload: invoked.append(payload) or payload,
        validate_bound_inputs=lambda payload, inputs: observed.append((payload, inputs)),
        bound_payload_source="semantic")
    def read(_connection, _scope, _tables, ref):
        reads.append(ref)
        if (ref == budget and drift == "budget") or (ref == template and drift == "template"):
            raise ExactBindingConflict("original budget bytes drift")
        return b'{"selected":true}' if ref == dynamic else b'{"budget":1}'
    handler._values = SimpleNamespace(load_exact=lambda *_args: descriptor,
        semantic_input_ref=lambda *_args: dynamic, read_value_bytes=read,
        publish_output=lambda *_args, **_kwargs: _digest("output"))
    assignment = SimpleNamespace(assignment_kind=AssignmentKind.INTERPRET, handler_binding=binding,
        operation_contract_ref=contract.ref, project_key=project.project_key, capability_id="activation-test")
    claim = SimpleNamespace(validate_against=lambda _: None)
    context = SimpleNamespace(node=SimpleNamespace(node_id="node"))
    if drift is not None:
        with pytest.raises(DefiniteInterpreterFailure):
            handler.execute(assignment, claim, context)
        assert invoked == [] and observed == []
    else:
        handler.execute(assignment, claim, context)
        assert invoked == [{"selected": True}]
        assert observed == [({"selected": True}, ((budget, b'{"budget":1}'), (dynamic, b'{"selected":true}')))]
    assert reads == ([dynamic, budget] if drift == "budget" else [dynamic, budget, template])


@pytest.mark.parametrize("drift", [None, "workflow_id", "cursor"])
def test_operation_preserves_workflow_static_occurrence_before_effect(monkeypatch, drift):
    from contextlib import contextmanager
    from dataclasses import replace
    from functools import partial
    import json
    from types import SimpleNamespace
    from app.services.workflow_graph.runtime import invoke_workflow_runtime_node
    from app.successor_runtime.capabilities.checksum import canonical_json, sha256_hex
    from app.successor_runtime.capabilities.workflow_native_contribution import (
        build_workflow_runtime_definition, build_workflow_runtime_program,
        validate_workflow_context_bound_inputs,
    )
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure
    from app.successor_runtime.runtime.ports import ProjectScopeRef
    from app.successor_runtime.substrate.postgres.batch_task_submission_handler import PersistentOperationHandler
    from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

    runtime = build_workflow_runtime_program(
        workflow_id="bound-workflow", nodes=(
            {"node_id": "first", "node_type": "join", "params": {}, "depends_on": []},
            {"node_id": "second", "node_type": "join", "params": {}, "depends_on": ["first"]},
        ), topo_order=("first", "second"), inputs={"query": "non-default"},
        program_id="occurrence-program", project_key="activation-project",
        project_registry_revision=1, project_scope_digest=_digest("project-scope"),
        incarnation="occurrence-inc", trace_id="occurrence-trace",
    )
    operation = build_workflow_runtime_definition().operation_for_node_type("join")
    codec = operation.context_codec
    first = codec.decode_payload(json.loads(runtime.values[0][1]))
    payload = invoke_workflow_runtime_node(first)
    assert payload.cursor == 1 and set(payload.results) == {"first"}
    if drift == "workflow_id":
        payload = replace(payload, workflow_id="foreign-workflow")
    elif drift == "cursor":
        payload = first
    static_ref, static_exact = runtime.values[1]
    exact = canonical_json(codec.encode_payload(payload)).encode()
    dynamic_ref = replace(static_ref, value_id="dynamic-occurrence", storage_ref="project-value:dynamic-occurrence",
                          content_digest=sha256_hex(exact), byte_size=len(exact))
    _, binding, _ = _entry(operation.contract.ref.contract_digest)
    project = ProjectScopeRef("activation-project", "activation_project", 1, "scope-inc", _digest("project-scope"))
    monkeypatch.setattr(ServerProjectScopeResolver, "resolve", lambda *_args: project)
    @contextmanager
    def uow():
        yield SimpleNamespace(connection=object(), commit=lambda: None)
    invoked, published, reads = [], [], []
    def invoke(context):
        invoked.append(context)
        return invoke_workflow_runtime_node(context)
    handler = PersistentOperationHandler(
        uow_factory=uow, binding=binding, contract=operation.contract,
        input_codec=codec, output_codec=codec, invoke=invoke,
        validate_bound_inputs=partial(validate_workflow_context_bound_inputs, operation=operation),
    )
    def read(_connection, _scope, _tables, ref):
        reads.append(ref)
        content = {static_ref: static_exact, dynamic_ref: exact}[ref]
        assert ref.content_digest == sha256_hex(content) and ref.byte_size == len(content)
        return content
    handler._values = SimpleNamespace(
        load_exact=lambda *_args: SimpleNamespace(payload_ref=static_ref, static_atom_input_refs=(static_ref,)),
        semantic_input_ref=lambda *_args: dynamic_ref, read_value_bytes=read,
        publish_output=lambda *_args, content: published.append(content) or _digest("output"),
    )
    assignment = SimpleNamespace(assignment_kind=AssignmentKind.INTERPRET, handler_binding=binding,
        operation_contract_ref=operation.contract.ref, project_key=project.project_key, capability_id="activation-test")
    claim = SimpleNamespace(validate_against=lambda _: None)
    context = SimpleNamespace(node=SimpleNamespace(node_id="node"))
    if drift is not None:
        with pytest.raises(DefiniteInterpreterFailure, match="OPERATION_PAYLOAD_INVALID"):
            handler.execute(assignment, claim, context)
        assert invoked == [] and published == []
    else:
        handler.execute(assignment, claim, context)
        settled = codec.decode_payload(json.loads(published[0]))
        assert settled.cursor == 2 and set(settled.results) == {"first", "second"}
        assert settled.results["second"]["sources"] == ["first"]
    assert reads == [dynamic_ref, static_ref]


def _ordered_input_pair(left, right):
    return [left, right]


def test_zip_siblings_bind_shared_input_separately_from_order(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from app.successor_runtime.language.program import zip_ordered_node
    from app.successor_runtime.substrate.postgres.runtime_activation import PostgresRuntimeActivationBindingAdapter
    from app.successor_runtime.substrate.postgres.plans import PlanRepository
    transforms, merges, discriminators = _empty_registries()
    left, left_contract = _operation("data-left", INPUT, OUTPUT)
    right, right_contract = _operation("data-right", INPUT, OUTPUT)
    merge = merges.register_merge(name="shared-input-pair", version="1", left_type=OUTPUT,
        right_type=OUTPUT, output_type=OUTPUT, func=_ordered_input_pair)
    program = _program(then_node(
        pure_node(INPUT, INPUT, {"shared": True}, "json-v1"),
        zip_ordered_node(left, right, merge, OUTPUT),
    ))
    plan = _compile(program, (left_contract, right_contract), transforms, merges, discriminators)
    kwargs = dict(run_id="shared-input", program=program, plan=plan,
        transform_registry=transforms, merge_registry=merges, discriminator_registry=discriminators)
    first = activate_plan(**kwargs)
    assert [item.operation_id for item in first.activations] == ["data-left"]
    left_step = next(step for step in plan.ordered_steps if step.operation_id == "data-left")
    output = _value("left-output", OUTPUT)
    result = _bind_materializations_to_project(activate_plan(**kwargs,
        completed_outputs=(BoundStepValue(left_step.step_id, output, {"left": True}),)), plan)
    descriptor = result.activations[0]
    assert descriptor.operation_id == "data-right"
    assert descriptor.ordered_dependency_refs[0] == output
    shared = descriptor.ordered_dependency_refs[1]
    assert shared.object_type == INPUT
    monkeypatch.setattr(PlanRepository, "get", lambda *_args: plan)
    assignment = SimpleNamespace(plan_digest=plan.plan_digest, step_id=descriptor.step_id)
    adapter = PostgresRuntimeActivationBindingAdapter()
    assert adapter.semantic_input_ref(None, assignment, None, None, descriptor) == shared
    with pytest.raises((ValueError, ExactBindingConflict)):
        adapter.semantic_input_ref(None, assignment, None, None,
            replace(descriptor, ordered_dependency_refs=(output,)))
    with pytest.raises(ExactBindingConflict, match="endpoint type drift"):
        adapter.semantic_input_ref(None, assignment, None, None,
            replace(descriptor, ordered_dependency_refs=(output, output)))


@pytest.mark.parametrize("drift", [None, "bytes", "type", "provenance"])
def test_effect_publication_reuses_exact_pure_content_owner(monkeypatch, drift):
    import hashlib
    from sqlalchemy import MetaData
    from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
    from app.successor_runtime.substrate.postgres import runtime_activation as module
    from app.successor_runtime.substrate.postgres.models import project_tables
    from app.successor_runtime.substrate.postgres.values import ValueRepository, derive_value_write_intent_digest
    from app.successor_runtime.substrate.postgres.runtime_values import RuntimeValueRepository
    from app.successor_runtime.substrate.postgres.research_ledger import ExactContentConflict
    from tests.successor_runtime.test_p0b_control_plane import _Result
    content = b'{"value":1}'
    row = dict(project_key="project-a", value_id="activation:original", object_type=INPUT.type_id,
               codec_id=INPUT.codec_id, content_digest=hashlib.sha256(content).hexdigest(),
               content_bytes=content, content_json=None, byte_size=len(content), source_ref=None,
               provenance_digest=_digest("original-provenance"), revision=1,
               incarnation="original-incarnation", state="AVAILABLE")
    row["write_intent_digest"] = derive_value_write_intent_digest(
        **{key: row[key] for key in ("project_key", "value_id", "object_type", "codec_id",
                                    "content_digest", "provenance_digest", "source_ref", "state")},
        expected_revision=0, expected_incarnation=row["incarnation"],
    )
    if drift == "bytes":
        row["content_bytes"] = b'{}'
    elif drift == "type":
        row["object_type"] = OUTPUT.type_id
    elif drift == "provenance":
        row["provenance_digest"] = _digest("forged-provenance")
    class Connection:
        def execute(self, statement):
            return _Result(row)
    published = []
    def no_rewrite(*args, **kwargs):
        pytest.fail("existing canonical project value must not be rewritten")
    monkeypatch.setattr(ValueRepository, "put_exact", no_rewrite)
    monkeypatch.setattr(RuntimeValueRepository, "put_exact", lambda self, binding: published.append(binding))
    scope = RuntimeScope(ProjectScopeRef("project-a", "project_a", 1, "scope-inc", "a" * 64), "actor")
    kwargs = dict(connection=Connection(), scope=scope, tables=project_tables(MetaData(), "project_a"),
                  value_id="operation-output:new-occurrence", object_type=INPUT, content=content,
                  incarnation="new-occurrence", provenance={"schema": "new-occurrence"})
    if drift:
        with pytest.raises((ExactBindingConflict, ExactContentConflict)):
            module._publish_typed_content(**kwargs)
        assert published == []
    else:
        ref = module._publish_typed_content(**kwargs)
        assert ref.value_id == "activation:original"
        assert ref.provenance_digest == row["provenance_digest"]
        assert len(published) == 1 and published[0].value_id == ref.value_id
        assert published[0].write_intent_digest == row["write_intent_digest"]
