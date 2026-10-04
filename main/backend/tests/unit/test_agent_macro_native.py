from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest
from functorial_kit.core.failure import Failure

from app.successor_runtime.assembly.base import CellBinding
from app.successor_runtime.capabilities.agent_macro_native import (
    OPEN_MACRO_INPUT_TYPE, OPEN_MACRO_OUTPUT_TYPE,
    MacroAssemblyContext, MacroCellDefinition, MacroObservation, MacroRelationRealization,
    SkillContentRef, compile_agent_macro_native, project_macro_cell_structure,
)
from app.successor_runtime.capabilities.retrieval_flow_native import (
    FlowInterface, FlowOperation, FlowOperationBinding, FlowPort, FlowThen, PortWire,
    RetrievalFlowSource, lower_retrieval_flow_source,
)

pytestmark = pytest.mark.unit


def _definition(name="test.macro", tool="project.current") -> MacroCellDefinition:
    return MacroCellDefinition(
        operation=FlowOperation(
            name, "1", FlowInterface((FlowPort("message", OPEN_MACRO_INPUT_TYPE),)),
            FlowInterface((FlowPort("observation", OPEN_MACRO_OUTPUT_TYPE),)),
            effect_refs=("project.read",), failure_refs=("native.failure",),
            authority_ref="project.permissions", stop_ref="native.stop",
            entrypoint_ref="native.invoke", control_kind="macro",
        ),
        owner="test.owner", core_binding_ref="codex.native",
        conceptual_rule_refs=("native.session", "project.contract"),
        skill_contents=(SkillContentRef("pilot", "skills/pilot/SKILL.md", "pilot:sha256:abc",
                                       "pilot#scope", "pilot#outcome", (tool,)),),
        tool_refs=(tool,), facility_refs=("project.service",), readback_refs=("project.readback",),
        relations=(
            MacroRelationRealization("project.read", "core", tool, "macro", "virtual", tool,
                                     "project.permissions", ("project.failure",), ("project.readback",)),
            MacroRelationRealization("project.read", tool, "project.store", "storage", "real",
                                     "project.service", "project.permissions"),
        ),
    )


def _context(definition: MacroCellDefinition, invoke: Mock) -> MacroAssemblyContext:
    operation = definition.operation
    return MacroAssemblyContext(
        cell_binding=CellBinding(definition.cell_id, definition.family_id, "INSTALLED",
                                 (operation.operation_id,), handler_binding_digest="a" * 64),
        operation_binding=FlowOperationBinding(
            operation.operation_id, operation.version, operation.inputs.ports[0].object_type,
            operation.outputs.ports[0].object_type, operation.effect_refs, operation.failure_refs,
            operation.authority_ref, operation.stop_ref, operation.entrypoint_ref, invoke,
        ),
        core_binding_ref=definition.core_binding_ref, core_mode=definition.core_mode,
        skill_contents=definition.skill_contents, tool_refs=definition.tool_refs,
        facility_refs=definition.facility_refs,
    )


def test_compilation_projection_and_assembly_are_inert() -> None:
    definition = _definition()
    invoke = Mock(side_effect=AssertionError("must not execute native Core"))
    native = compile_agent_macro_native(definition)
    assert not isinstance(native, Failure)
    assert native.definition is definition
    binding = native.assemble(_context(definition, invoke))
    assert not isinstance(binding, Failure)
    assert binding.definition is definition
    invoke.assert_not_called()
    structure = project_macro_cell_structure(definition)
    assert [item["realization"] for item in structure["relations"]] == ["virtual", "real"]
    assert [item["observation_boundary"] for item in structure["relations"]] == ["macro", "storage"]
    assert structure["readback_refs"] == ("project.readback",)


def test_nondefault_definition_drives_contribution_and_host_binding() -> None:
    definition = _definition("test.nondefault", "project.alternative")
    native = compile_agent_macro_native(definition)
    assert not isinstance(native, Failure)
    assert native.projection.id == "test.nondefault.1"
    assert "project.alternative" in native.projection.objects[0].references
    assert "project.current" not in native.projection.objects[0].references
    context = _context(definition, Mock())
    assert not isinstance(native.assemble(context), Failure)
    assert isinstance(native.assemble(replace(context, tool_refs=("project.current",))), Failure)
    changed_content = replace(context.skill_contents[0], content_id="changed")
    assert isinstance(native.assemble(replace(context, skill_contents=(changed_content,))), Failure)


def test_registration_does_not_install_or_grant_authority() -> None:
    definition = _definition()
    native = compile_agent_macro_native(definition)
    assert not isinstance(native, Failure)
    context = _context(definition, Mock())
    declared = replace(context.cell_binding, status="UNWIRED_DECLARED", handler_binding_digest=None)
    assert isinstance(native.assemble(replace(context, cell_binding=declared)), Failure)
    unauthorized_binding = replace(context.operation_binding, authority_ref="other.permission")
    assert isinstance(native.assemble(replace(context, operation_binding=unauthorized_binding)), Failure)
    assert isinstance(native.assemble(replace(context, core_mode="model-only")), Failure)


def test_repeated_occurrences_and_open_message_are_not_classified_or_deduplicated() -> None:
    definition = _definition()
    # A continuation-facing macro may expose the same open envelope on both ends.
    definition = replace(definition, operation=replace(definition.operation, outputs=definition.operation.inputs))
    source = RetrievalFlowSource("test.repeat", "1", "test.owner", FlowThen(
        definition.occurrence("first"), definition.occurrence("second"), (PortWire("message", "message"),),
    ))
    lowered = lower_retrieval_flow_source(source)
    assert not isinstance(lowered, Failure)
    assert [item.occurrence_id for item in lowered.occurrences] == ["first", "second"]
    assert lowered.occurrences[0].operation is lowered.occurrences[1].operation
    observation = MacroObservation("call:second", "failed", "原始自由回答，不属于预设业务类型。",
                                   ("partial:artifact",), ("original:receipt",), failure_ref="owner:failure",
                                   occurrence_id="second")
    assert observation.response == "原始自由回答，不属于预设业务类型。"
    assert observation.artifact_refs == ("partial:artifact",)
    assert observation.receipt_refs == ("original:receipt",)
    assert observation.outcome == "failed"


def test_missing_content_owner_or_duplicate_relation_observation_is_rejected() -> None:
    definition = _definition()
    bad_skill = replace(definition.skill_contents[0], content_id="")
    assert isinstance(compile_agent_macro_native(replace(definition, skill_contents=(bad_skill,))), Failure)
    assert isinstance(compile_agent_macro_native(replace(definition, conceptual_rule_refs=())), Failure)
    duplicate = replace(definition, relations=(definition.relations[0], definition.relations[0]))
    assert isinstance(compile_agent_macro_native(duplicate), Failure)
    unknown_tool = replace(definition.skill_contents[0], tool_refs=("missing.tool",))
    assert isinstance(compile_agent_macro_native(replace(definition, skill_contents=(unknown_tool,))), Failure)
