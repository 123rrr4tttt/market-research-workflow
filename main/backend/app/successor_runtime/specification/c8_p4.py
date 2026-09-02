"""Thin C8/P4 family fragment config for the shared family generator.

This module declares only the C8 family data and differences: family
identity, the C8.2 capability cell spec and runtime kernel ABI inputs, exact
binding targets, the four C8.1-C8.4 cell declarations and the family
observation glue that calls the existing C8 modules.  No full fragment
generator is copied; shared schema/digest/path/authority/check mechanics live
in ``shared_family_generator``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.graph.models import (
    GraphEdge as LegacyGraphEdge,
)
from app.services.graph.models import (
    GraphNode as LegacyGraphNode,
)
from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
)
from app.successor_migration.legacy_c8_graph import LegacyC8GraphAdapter
from app.successor_migration.legacy_c8_interpreter import (
    LegacyC8DemandReadDonor,
    LegacyC8DonorRegistry,
    LegacyC8GraphDonor,
    LegacyC8ProgramInterpreter,
    LegacyC8ReportDonor,
    LegacyC8WritingComposeDonor,
    LegacyC8WritingStageDonor,
)
from app.successor_migration.legacy_c8_report import (
    UNBOUND_C8_3_REPORT_LOCATOR,
    LegacyC8ReportAdapter,
)
from app.successor_migration.legacy_c8_typed_knowledge import (
    LegacyC8TypedKnowledgeAdapter,
)
from app.successor_migration.legacy_c8_writing import LegacyC8WritingAdapter
from app.successor_runtime.capabilities import (
    c8_common as c8common,
)
from app.successor_runtime.capabilities import (
    c8_graph as c8g,
)
from app.successor_runtime.capabilities import (
    c8_program as c8p,
)
from app.successor_runtime.capabilities import (
    c8_report as c8r,
)
from app.successor_runtime.capabilities import (
    c8_typed_knowledge as c8,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import (
    CanonicalRef,
    KnowledgeItem,
    ReadHandleRegistry,
    demand_read,
    item_digest,
)
from app.successor_runtime.capabilities.c8_writing import (
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification.shared_family_generator import (
    BindingsByKind,
    BindingTarget,
    FamilyFragmentConfig,
)
from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    build_c8_interpreter_binding,
    handler_binding_ref,
)

PROJECT_KEY = "p4-c8-fragment"
TOPIC = "C8.knowledge-writing-report-graph"
SELECTION_HASH = "selection:robotics"
SELECTION_TEXT = "robotics investment"
NORMALIZED_QUERY = "robotics investment"
PROJECT_REGISTRY_REVISION = 1
PROJECT_SCOPE_DIGEST = content_digest(
    {
        "project": PROJECT_KEY,
        "resolved_schema": "mrw_p4_c8_fragment",
        "registry_revision": PROJECT_REGISTRY_REVISION,
        "incarnation": "scope-inc-c8-fragment",
    }
)
DEPLOYMENT_CATALOG_DIGEST = content_digest(
    {"catalog": "mrw.successor.deployment-catalog.c8.v1"}
)
AUTHORITY_REQUIREMENT_DIGEST = content_digest({"authority": False})
LIFECYCLE_STATE = "P4_NOT_STARTED"

FRAGMENT_ID = "p4-c8-family-local-ahead-of-time-scaffolding"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p4_fragment.v1"
FRAGMENT_PHASE = "P4"
FRAGMENT_FAMILY = "C8"
FRAGMENT_STATUS = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"

_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
CELL_SPEC_PATH = f"{_EVIDENCE_ROOT}/capability-specs/C8.2.v1.json"
RUNTIME_KERNEL_ABI_PATH = f"{_EVIDENCE_ROOT}/capability-specs/RuntimeKernelABI.v1.json"
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p4-fragments/C8.json"

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (
            REPOSITORY_ROOT / _EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json"
        ).read_text()
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(cell_id: str) -> str:
    cell = _p1_cells()[cell_id]
    return content_digest(cell)


def _successor_item(
    *,
    key: str,
    evidence_refs: tuple[str, ...] = ("ev:1", "ev:2"),
    node_type: str = "Topic",
) -> KnowledgeItem:
    body = KnowledgeItem(
        key=key,
        project_key=PROJECT_KEY,
        canonical_statement="机器人产品市场证据",
        primary_type_node_key=node_type,
        evidence_refs=evidence_refs,
        topic_cluster_keys=("tc:robotics",),
        booklet_keys=("bk:robotics",),
        review_state="human_confirmed",
        quality_grade="gold",
        locale="zh",
        visibility_scope="downstream_ready",
    )
    return KnowledgeItem(
        key=body.key,
        project_key=body.project_key,
        canonical_statement=body.canonical_statement,
        primary_type_node_key=body.primary_type_node_key,
        evidence_refs=body.evidence_refs,
        topic_cluster_keys=body.topic_cluster_keys,
        booklet_keys=body.booklet_keys,
        review_state=body.review_state,
        quality_grade=body.quality_grade,
        locale=body.locale,
        visibility_scope=body.visibility_scope,
        canonical_ref=CanonicalRef(
            identity=f"knowledge:{PROJECT_KEY}:{key}",
            content_digest=item_digest(body),
            revision=1,
            incarnation="p4-c8-captured-1",
        ),
    )


def _legacy_item() -> Any:
    from app.services.typed_knowledge.contracts import (
        KnowledgeItem as LegacyKnowledgeItem,
    )

    return LegacyKnowledgeItem(
        key="ki:robotics",
        project_key=PROJECT_KEY,
        canonical_statement="机器人产品市场证据",
        primary_type_node_key="Topic",
        evidence_refs=("ev:1", "ev:2"),
        topic_cluster_keys=("tc:robotics",),
        booklet_keys=("bk:robotics",),
        review_state="human_confirmed",
        quality_grade="gold",
        locale="zh",
        updated_at="2026-08-30T00:00:00Z",
    )


def _demand_read() -> c8.KnowledgeRead:
    item = _successor_item(key="ki:robotics")
    return demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=ReadHandleRegistry(),
    )


def _c8_payload(cell_id: str) -> Any:
    if cell_id == "C8.1":
        return c8p.C8DemandReadInput(
            project_key=PROJECT_KEY,
            item_key="ki:robotics",
            fields=("canonical_statement", "evidence_refs"),
        )
    if cell_id == "C8.2":
        return c8p.C8WritingComposeInput(
            project_key=PROJECT_KEY,
            knowledge_item_key="ki:robotics",
            selection_hash=SELECTION_HASH,
            selection_text=SELECTION_TEXT,
            demand_fields=("canonical_statement", "evidence_refs"),
        )
    if cell_id == "C8.3":
        return c8p.C8ReportStageInput(
            project_key=PROJECT_KEY,
            report_id="p4-c8-report-1",
            topic=TOPIC,
            source_keys=("ki:robotics",),
        )
    return c8p.C8GraphProjectInput(
        project_key=PROJECT_KEY,
        graph_id="p4-c8-graph-1",
        node_keys=("ki:a", "ki:b"),
        node_types=("Topic",),
    )


def _program_observation(cell_id: str) -> dict[str, object]:
    bundle = c8p.build_c8_bundle()
    catalog = c8p.build_c8_catalog(bundle)
    registry = c8p.build_c8_registry(bundle)
    payload = _c8_payload(cell_id)
    program = c8p.build_c8_program(
        cell_id=cell_id,
        payload=payload,
        catalog=catalog,
        program_id=f"program:p4-c8-{cell_id.lower().replace('.', '-')}",
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    primary_kind = {
        "C8.1": c8p.C8_1_KIND,
        "C8.2": c8p.C8_2_COMPOSE_KIND,
        "C8.3": c8p.C8_3_KIND,
        "C8.4": c8p.C8_4_KIND,
    }[cell_id]
    contract = c8p.exact_contract_ref(catalog, kind=primary_kind)
    cell_profiles = bundle.profiles[cell_id]
    interpreter_profile_digest = cell_profiles["interpreter"].profile_digest
    primary_binding = build_c8_interpreter_binding(
        c8p.handler_binding_payload(
            operation_contract_digest=contract.contract_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=PROJECT_SCOPE_DIGEST,
            authority_requirement_digest=AUTHORITY_REQUIREMENT_DIGEST,
        )
    )
    binding_closure = []
    for entry in c8p.handler_binding_closure_payloads(
        plan,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        authority_requirement_digest=AUTHORITY_REQUIREMENT_DIGEST,
    ):
        step_binding = build_c8_interpreter_binding(entry["payload"])
        binding_closure.append(
            {
                "step_id": entry["step_id"],
                "operation_id": entry["operation_id"],
                "operation_kind": entry["operation_kind"],
                "handler_binding_kind": step_binding.binding_kind.value,
                "handler_binding_digest": step_binding.binding_digest,
                "handler_binding_ref": handler_binding_ref(step_binding),
            }
        )
    donors = LegacyC8DonorRegistry()
    items_by_key = {"ki:robotics": _legacy_item()}
    if cell_id == "C8.1":
        donors.register(
            catalog.lookup(c8p.C8_1_KIND).contract_digest,
            LegacyC8DemandReadDonor(
                items_by_key=items_by_key,
                selection_hash=SELECTION_HASH,
                selection_text=SELECTION_TEXT,
            ).run,
        )
    elif cell_id == "C8.2":
        donors.register(
            catalog.lookup(c8p.C8_2_COMPOSE_KIND).contract_digest,
            LegacyC8WritingComposeDonor(
                items_by_key=items_by_key,
                selection_hash=SELECTION_HASH,
                selection_text=SELECTION_TEXT,
            ).run,
        )
        donors.register(
            catalog.lookup(c8p.C8_2_STAGE_KIND).contract_digest,
            LegacyC8WritingStageDonor(
                normalized_query=NORMALIZED_QUERY,
            ).run,
        )
    elif cell_id == "C8.3":
        donors.register(
            catalog.lookup(c8p.C8_3_KIND).contract_digest,
            LegacyC8ReportDonor().run,
        )
    else:
        post = LegacyGraphNode(type="Post", id="1")
        keyword = LegacyGraphNode(type="Keyword", id="k1")
        donors.register(
            catalog.lookup(c8p.C8_4_KIND).contract_digest,
            LegacyC8GraphDonor(nodes={"Post:1": post, "Keyword:k1": keyword}).run,
        )
    seed_inputs = {plan.ordered_steps[0].step_id: (payload, payload.payload_digest)}
    legacy_trace = LegacyC8ProgramInterpreter().consume(
        program,
        plan,
        donors=donors,
        seed_inputs=seed_inputs,
    )
    successor_trace = {
        "ordered_step_trace": [step.operation_id for step in plan.ordered_steps]
    }
    same_ast = (
        legacy_trace["ordered_step_trace"] == successor_trace["ordered_step_trace"]
        and legacy_trace["consumed_plan_digest"] == plan.plan_digest
    )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "handler_binding_kind": primary_binding.binding_kind.value,
        "handler_binding_digest": primary_binding.binding_digest,
        "handler_binding_ref": handler_binding_ref(primary_binding),
        "handler_binding_closure": binding_closure,
        "ordered_steps": len(plan.ordered_steps),
        "consumed_program_digest": legacy_trace["consumed_program_digest"],
        "consumed_plan_digest": legacy_trace["consumed_plan_digest"],
        "ordered_step_trace": list(legacy_trace["ordered_step_trace"]),
        "consumed_operation_digests": list(legacy_trace["consumed_operation_digests"]),
        "parity": {
            "executions": len(legacy_trace["step_executions"]),
            "failures": [
                execution["failure"]
                for execution in legacy_trace["step_executions"]
                if execution["failure"] is not None
            ],
        },
        "step_outputs": list(legacy_trace["step_outputs"]),
        "same_ast": same_ast,
        "lifecycle_state": LIFECYCLE_STATE,
    }


def _c8_1_observations() -> tuple[dict[str, object], dict[str, object]]:
    read = _demand_read()
    program_info = _program_observation("C8.1")
    legacy = LegacyC8TypedKnowledgeAdapter()
    return {
        "interpreter_id": "successor.c8.demand_read.v1",
        "handle_id": read.handle.handle_id,
        "field_mask": list(read.handle.field_mask),
        "fields_returned": sorted(read.fields),
        "canonical_identity": read.provenance.canonical_identity,
        "canonical_digest": read.provenance.canonical_digest,
        "canonical_revision": read.provenance.canonical_revision,
        "canonical_incarnation": read.provenance.canonical_incarnation,
        **program_info,
        "provider_calls": 0,
        "store_writes": 0,
    }, legacy.build_handoff_payload(
        _legacy_item(),
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    ) | {
        "program_digest": program_info["program_digest"],
        "plan_digest": program_info["plan_digest"],
        "same_ast": True,
    }


def _c8_2_observations() -> tuple[dict[str, object], dict[str, object]]:
    read = _demand_read()
    program_info = _program_observation("C8.2")
    handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    card = project_writing_card(handoff)
    artifact = stage_writing_artifact(card)
    contract = build_downstream_contract_draft(_legacy_item())
    legacy_handoff = build_writing_knowledge_handoff(
        contract,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    legacy = LegacyC8WritingAdapter().build_card_observation(
        legacy_handoff,
        normalized_query=NORMALIZED_QUERY,
    )
    return {
        "interpreter_id": "successor.c8.writing.v1",
        "handoff_contract": handoff.contract_version,
        "card_source_type": card.source_type,
        "card_publisher": card.publisher,
        "card_id": card.card_id,
        "stage_sequence": list(artifact.stage_sequence),
        "composition_digest": artifact.composition_digest,
        "artifact_id": artifact.artifact_id,
        "declared_loss": list(artifact.declared_loss),
        "provenance_chain": list(artifact.provenance_chain),
        "provenance_revision": artifact.provenance.canonical_revision,
        "provenance_incarnation": artifact.provenance.canonical_incarnation,
        "step_parity": {
            "compose_statement": (
                program_info["step_outputs"][0]["canonical_statement"]
                == handoff.canonical_statement
            ),
            "stage_card_source": (
                program_info["step_outputs"][1]["source_type"] == "resource"
            ),
            "stage_card_publisher": (
                program_info["step_outputs"][1]["publisher"] == "typed_knowledge"
            ),
        },
        **program_info,
        "provider_calls": 0,
        "store_writes": 0,
        "export_calls": 0,
    }, legacy | {
        "program_digest": program_info["program_digest"],
        "plan_digest": program_info["plan_digest"],
        "same_ast": True,
    }


def _c8_3_observations() -> tuple[dict[str, object], dict[str, object]]:
    read = _demand_read()
    program_info = _program_observation("C8.3")
    artifact = c8r.build_report_artifact(
        report_id="p4-c8-report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=(read,),
    )
    admission = c8r.build_report_admission_intent(artifact)
    delivery = c8r.build_report_delivery_intent(artifact)
    legacy = LegacyC8ReportAdapter().observe_staging(artifact)
    p1_c8_3 = _p1_cells()["C8.3"]
    locator_status = p1_c8_3["locator_status"]
    legacy = {
        **legacy,
        "locator_status": locator_status["state"],
        "missing_paths": list(locator_status.get("missing_paths") or ()),
        "supporting_implementations_found": list(
            locator_status.get("supporting_implementations_found") or ()
        ),
    }
    return {
        "interpreter_id": "successor.c8.report.v1",
        "report_id": artifact.report_id,
        "row_statuses": [row.status for row in artifact.rows],
        "artifact_digest": artifact.artifact_digest,
        "staging_sequence": list(artifact.staging_sequence),
        "declared_loss": list(artifact.declared_loss),
        "source_identities": list(artifact.source_identities),
        "provenance_revision": artifact.provenance.canonical_revision,
        "provenance_incarnation": artifact.provenance.canonical_incarnation,
        "closure": [
            {
                "identity": item.provenance.canonical_identity,
                "digest": item.provenance.canonical_digest,
                "revision": item.provenance.canonical_revision,
                "incarnation": item.provenance.canonical_incarnation,
                "handle_id": item.handle.handle_id,
            }
            for item in (read,)
        ],
        "admission_contract": admission.contract_version,
        "delivery_contract": delivery.contract_version,
        "admission_interface_digest": c8common.C8_3_ADMISSION_INTERFACE_DIGEST,
        "delivery_interface_digest": c8common.C8_3_DELIVERY_INTERFACE_DIGEST,
        "admission_intent_admitted": admission.admitted,
        "delivery_intent_delivered": delivery.delivered,
        "admission_calls": 0,
        "export_calls": 0,
        "delivery_calls": 0,
        **program_info,
        "provider_calls": 0,
        "store_writes": 0,
    }, legacy | {
        "program_digest": program_info["program_digest"],
        "plan_digest": program_info["plan_digest"],
        "same_ast": True,
    }


def _c8_4_observations() -> tuple[dict[str, object], dict[str, object]]:
    first = _successor_item(key="ki:a", evidence_refs=("ki:b", "ki:c"))
    second = _successor_item(key="ki:b", evidence_refs=())
    program_info = _program_observation("C8.4")
    context = c8g.build_graph_context_from_items(
        graph_id="p4-c8-graph-1",
        project_key=PROJECT_KEY,
        items=(first, second),
        registry=ReadHandleRegistry(),
        node_types=("Topic",),
    )
    post = LegacyGraphNode(type="Post", id="1")
    keyword = LegacyGraphNode(type="Keyword", id="k1")
    edge = LegacyGraphEdge(type="MENTIONS_KEYWORD", from_node=post, to_node=keyword)
    legacy = LegacyC8GraphAdapter().project(
        {"Post:1": post, "Keyword:k1": keyword},
        [edge],
        ["Post", "Keyword"],
    )
    return {
        "interpreter_id": "successor.c8.graph.v1",
        "projection": context.schema_version,
        "node_keys": sorted(node.key for node in context.nodes),
        "edge_keys": [f"{edge.from_key}:{edge.to_key}" for edge in context.edges],
        "omitted_edge_keys": [
            f"{edge.from_key}:{edge.to_key}" for edge in context.omitted_edges
        ],
        "declared_loss": list(context.declared_loss),
        "canonical_identity": context.provenance.canonical_identity,
        "canonical_digest": context.provenance.canonical_digest,
        "canonical_revision": context.provenance.canonical_revision,
        "canonical_incarnation": context.provenance.canonical_incarnation,
        "source_identities": list(context.source_identities),
        "source_digests": list(context.source_digests),
        "source_closure": [
            {
                "identity": entry.identity,
                "digest": entry.digest,
                "revision": entry.revision,
                "incarnation": entry.incarnation,
                "handle_id": entry.handle_id,
            }
            for entry in context.source_closure
        ],
        "projection_digest": context.projection_digest,
        **program_info,
        "provider_calls": 0,
        "store_writes": 0,
    }, legacy | {
        "program_digest": program_info["program_digest"],
        "plan_digest": program_info["plan_digest"],
        "same_ast": True,
    }


def _operation_bindings() -> dict[str, list[dict[str, object]]]:
    bundle = c8p.build_c8_bundle()
    by_kind = {operation.ref.kind: operation for operation in bundle.operations}

    def binding(operation_kind: str, role: str) -> dict[str, object]:
        return {
            "operation_kind": operation_kind,
            "contract_digest": by_kind[operation_kind].ref.contract_digest,
            "role": role,
        }

    def interface_binding(operation_kind: str, role: str) -> dict[str, object]:
        return {
            "operation_kind": operation_kind,
            "contract_digest": {
                c8r.REPORT_ADMISSION_CONTRACT: (
                    c8common.C8_3_ADMISSION_INTERFACE_DIGEST
                ),
                c8r.REPORT_DELIVERY_CONTRACT: (c8common.C8_3_DELIVERY_INTERFACE_DIGEST),
            }[operation_kind],
            "role": role,
        }

    return {
        "c8_1": [
            binding(
                c8p.C8_1_KIND,
                "typed_knowledge_demand_read",
            )
        ],
        "c8_2": [
            binding(c8p.C8_2_COMPOSE_KIND, "writing_ordered_composition"),
            binding(c8p.C8_2_STAGE_KIND, "writing_staged_artifact"),
        ],
        "c8_3": [
            binding(c8p.C8_3_KIND, "report_stage"),
            interface_binding(
                c8r.REPORT_ADMISSION_CONTRACT, "report_admission_interface"
            ),
            interface_binding(
                c8r.REPORT_DELIVERY_CONTRACT, "report_delivery_interface"
            ),
        ],
        "c8_4": [binding(c8p.C8_4_KIND, "graph_declared_loss_projection")],
    }


_SOURCE_BINDINGS = (
    BindingTarget(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/"
        "01_functorial-successor-migration-development-contract.md",
        "development_contract_01",
    ),
    BindingTarget(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/"
        "02_functorial-successor-migration-development-contract.freeze.json",
        "freeze_manifest_02",
    ),
    BindingTarget(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/"
        "06_functorial-successor-runtime-architecture-correction.draft.zh-CN.md",
        "architecture_correction_06",
    ),
    BindingTarget(
        f"{_EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json", "p1_eligibility"
    ),
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C8.json", "p1_fragment"),
    BindingTarget(
        "main/backend/app/services/typed_knowledge/contracts.py",
        "legacy_donor_c8_1_typed_knowledge_contracts",
    ),
    BindingTarget(
        "main/backend/app/services/document_views/writing_card_view.py",
        "legacy_donor_c8_2_writing_card_builder",
    ),
    BindingTarget(
        "main/backend/app/services/graph/projection.py",
        "legacy_donor_c8_4_graph_projection",
    ),
    BindingTarget(
        "main/backend/app/services/graph/models.py",
        "legacy_donor_c8_4_graph_models",
    ),
)

_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_common.py",
        "c8_common_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_program.py",
        "c8_program_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/projections/"
        "c8_handler_bindings.py",
        "c8_handler_binding_substrate",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_typed_knowledge.py",
        "c8_1_typed_knowledge",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_writing.py",
        "c8_2_writing",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_report.py",
        "c8_3_report",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/c8_graph.py",
        "c8_4_graph",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_c8_typed_knowledge.py",
        "legacy_c8_1_typed_knowledge",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_c8_writing.py",
        "legacy_c8_2_writing",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_c8_report.py",
        "legacy_c8_3_report_unbound_locator",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_c8_graph.py",
        "legacy_c8_4_graph",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_c8_interpreter.py",
        "legacy_c8_program_interpreter",
    ),
    BindingTarget(
        "main/backend/scripts/generate_successor_p4_c8_fragment.py",
        "evidence_generator",
    ),
)

_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/p4_c8_fixture.py",
        "captured_fixture",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_1_typed_knowledge.py",
        "c8_1_typed_knowledge",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_2_writing.py",
        "c8_2_writing",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_3_report.py",
        "c8_3_report",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_4_graph.py",
        "c8_4_graph",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_5_program.py",
        "c8_5_program",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_legacy_adapters.py",
        "c8_legacy_adapters",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c8_evidence_generator.py",
        "c8_evidence_generator",
    ),
)


def _rollback_digest(*, cell_id: str) -> str:
    return content_digest(
        {
            "cell_id": cell_id,
            "claim_owner": "legacy",
            "staged_values_retained": True,
            "no_admission": True,
            "no_export": True,
            "no_provider": True,
        }
    )


def _build_body(_root: Path, bindings: BindingsByKind) -> dict[str, Any]:
    c8_1_successor, c8_1_legacy = _c8_1_observations()
    c8_2_successor, c8_2_legacy = _c8_2_observations()
    c8_3_successor, c8_3_legacy = _c8_3_observations()
    c8_4_successor, c8_4_legacy = _c8_4_observations()
    operations = _operation_bindings()

    cells = [
        {
            "cell_id": "C8.1",
            "p1_cell_digest": _p1_cell_digest("C8.1"),
            "operation_bindings": operations["c8_1"],
            "owner_capability_id": c8.C8_CAPABILITY_OWNER,
            "program_digest": {
                "value": c8_1_successor["program_digest"],
                "reason": (
                    "exact shared ProgramSpec for the C8.1 demand-read atom "
                    "compiled through the shared compiler"
                ),
            },
            "plan_digest": {
                "value": c8_1_successor["plan_digest"],
                "reason": ("compiled shared ExecutionPlan for the C8.1 atom"),
            },
            "legacy_observation": c8_1_legacy,
            "successor_observation": c8_1_successor,
            "rollback_observation": {
                "rollback_digest": _rollback_digest(cell_id="C8.1"),
                "read_handle_retained": True,
                "no_store_write": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C8.2",
            "p1_cell_digest": _p1_cell_digest("C8.2"),
            "operation_bindings": operations["c8_2"],
            "owner_capability_id": c8.C8_CAPABILITY_OWNER,
            "program_digest": {
                "value": c8_2_successor["program_digest"],
                "reason": (
                    "exact shared ProgramSpec for ordered C8.2 compose-then-"
                    "stage composition"
                ),
            },
            "plan_digest": {
                "value": c8_2_successor["plan_digest"],
                "reason": ("compiled shared ExecutionPlan with two ordered steps"),
            },
            "legacy_observation": c8_2_legacy,
            "successor_observation": c8_2_successor,
            "rollback_observation": {
                "rollback_digest": _rollback_digest(cell_id="C8.2"),
                "stage_sequence_retained": True,
                "no_export_write": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C8.3",
            "p1_cell_digest": _p1_cell_digest("C8.3"),
            "operation_bindings": operations["c8_3"],
            "owner_capability_id": c8.C8_CAPABILITY_OWNER,
            "program_digest": {
                "value": c8_3_successor["program_digest"],
                "reason": (
                    "exact shared ProgramSpec for report staging; admission/"
                    "delivery remain interface contracts only"
                ),
            },
            "plan_digest": {
                "value": c8_3_successor["plan_digest"],
                "reason": (
                    "compiled shared ExecutionPlan for report staging; no "
                    "admission or export is called"
                ),
            },
            "legacy_observation": c8_3_legacy,
            "successor_observation": c8_3_successor,
            "rollback_observation": {
                "rollback_digest": _rollback_digest(cell_id="C8.3"),
                "admission_not_called": True,
                "export_not_called": True,
                "delivery_not_called": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C8.4",
            "p1_cell_digest": _p1_cell_digest("C8.4"),
            "operation_bindings": operations["c8_4"],
            "owner_capability_id": c8.C8_CAPABILITY_OWNER,
            "program_digest": {
                "value": c8_4_successor["program_digest"],
                "reason": (
                    "exact shared ProgramSpec for the C8.4 declared-loss "
                    "graph projection atom"
                ),
            },
            "plan_digest": {
                "value": c8_4_successor["plan_digest"],
                "reason": ("compiled shared ExecutionPlan for the C8.4 graph atom"),
            },
            "legacy_observation": c8_4_legacy,
            "successor_observation": c8_4_successor,
            "rollback_observation": {
                "rollback_digest": _rollback_digest(cell_id="C8.4"),
                "declared_loss_retained": True,
                "no_projection_write": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
    ]

    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "lifecycle_state": LIFECYCLE_STATE,
        "cells": cells,
        "source_bindings": bindings["source_bindings"],
        "implementation_bindings": bindings["implementation_bindings"],
        "test_bindings": bindings["test_bindings"],
        "authority": {
            "production_canonical_write": False,
            "live_provider": False,
            "live_credential": False,
            "network": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "p4_promotion": False,
        },
        "open_findings": [
            {
                "id": "C8_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
                "severity": "P1",
                "description": (
                    "P4 C8 files are family-local scaffolding; no adoption, "
                    "promotion or runtime wiring is claimed"
                ),
            },
            {
                "id": "C8_3_REPORT_ADMISSION_DELIVERY_LOCATOR_UNBOUND",
                "severity": "P1",
                "description": (
                    "P1 records C8.3 locator as PARTIAL_MISSING because "
                    "main/backend/app/services/llm_report_export_token_state.py "
                    "is absent; no donor file or adoption is guessed"
                ),
            },
            {
                "id": "C8_P4_NOT_STARTED",
                "severity": "P1",
                "description": (
                    "lifecycle_state P4_NOT_STARTED; Programs compile ahead of "
                    "time but are not executed or adopted"
                ),
            },
            {
                "id": "C8_PROGRAMS_COMPILED_NOT_EXECUTED",
                "severity": "P1",
                "description": (
                    "shared ProgramSpec/ExecutionPlan digests are bound but "
                    "no handler execution, admission or delivery is wired"
                ),
            },
            {
                "id": "P4_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
                "severity": "P1",
                "description": (
                    "capability surface remains untracked; exact review tree pending"
                ),
            },
        ],
    }


def _self_check(fragment: Mapping[str, Any]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == FRAGMENT_PHASE
    assert fragment["family"] == FRAGMENT_FAMILY
    assert fragment["status"] == FRAGMENT_STATUS
    assert fragment["lifecycle_state"] == LIFECYCLE_STATE
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    assert fragment["content_digest"] == content_digest(body)
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "lifecycle_state",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C8.1",
        "C8.2",
        "C8.3",
        "C8.4",
    ]
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C8_3_REPORT_ADMISSION_DELIVERY_LOCATOR_UNBOUND" in finding_ids
    assert "P0_TARGET_RUNTIME_ARCHITECTURE_UNFROZEN" not in finding_ids
    assert all(
        cell["program_digest"]["value"] and cell["plan_digest"]["value"]
        for cell in fragment["cells"]
    )
    assert all(
        binding["contract_digest"]
        for cell in fragment["cells"]
        for binding in cell["operation_bindings"]
    )
    assert all(
        isinstance(cell["p1_cell_digest"], str) and len(cell["p1_cell_digest"]) == 64
        for cell in fragment["cells"]
    )
    assert UNBOUND_C8_3_REPORT_LOCATOR in str(
        fragment["cells"][2]["legacy_observation"]["locator"]
    )


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    lifecycle_state=LIFECYCLE_STATE,
    cell_spec_path=CELL_SPEC_PATH,
    runtime_kernel_abi_path=RUNTIME_KERNEL_ABI_PATH,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority={
        "production_canonical_write": False,
        "live_provider": False,
        "live_credential": False,
        "network": False,
        "cutover": False,
        "authority_transfer": False,
        "legacy_retired": False,
        "p4_promotion": False,
    },
    open_findings=(
        {
            "id": "C8_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
            "severity": "P1",
            "description": (
                "P4 C8 files are family-local scaffolding; no adoption, "
                "promotion or runtime wiring is claimed"
            ),
        },
        {
            "id": "C8_3_REPORT_ADMISSION_DELIVERY_LOCATOR_UNBOUND",
            "severity": "P1",
            "description": (
                "P1 records C8.3 locator as PARTIAL_MISSING because "
                "main/backend/app/services/llm_report_export_token_state.py "
                "is absent; no donor file or adoption is guessed"
            ),
        },
        {
            "id": "C8_P4_NOT_STARTED",
            "severity": "P1",
            "description": (
                "lifecycle_state P4_NOT_STARTED; Programs compile ahead of "
                "time but are not executed or adopted"
            ),
        },
        {
            "id": "C8_PROGRAMS_COMPILED_NOT_EXECUTED",
            "severity": "P1",
            "description": (
                "shared ProgramSpec/ExecutionPlan digests are bound but "
                "no handler execution, admission or delivery is wired"
            ),
        },
        {
            "id": "P4_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
            "severity": "P1",
            "description": (
                "capability surface remains untracked; exact review tree pending"
            ),
        },
    ),
    body_builder=_build_body,
    self_check=_self_check,
)
