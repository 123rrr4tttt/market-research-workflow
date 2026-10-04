"""Native contribution source for the ordered C8.2 writing cell.
produces the writing handoff from its typed payload; ``stage`` consumes that
handoff and emits the staged artifact.  The operations are ordered and are not
interchangeable.  Assembly, projection and binding validation are derived by
the shared non-graph C8 native contribution rule.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from mrw_functorial_kit.core.knowledge_semantics import knowledge_writing_failures

from app.successor_runtime.capabilities.knowledge_common import (
    KNOWLEDGE_WRITING_CELL_ID,
    reject_knowledge_contract,
    reject_knowledge_value,
)
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.language.object_contracts import SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF
from . import (
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeAssemblyDeclaration,
    KnowledgeNativeAuthorSource,
    KnowledgeNativeDefinition,
    KnowledgeNativeOperationSource,
)

__all__ = [
    "KNOWLEDGE_WRITING_CELL_ID",
    "KNOWLEDGE_WRITING_COMPOSE_INPUT_TYPE",
    "KNOWLEDGE_WRITING_COMPOSE_KIND",
    "KNOWLEDGE_WRITING_COMPOSE_OPERATION_ID",
    "KNOWLEDGE_WRITING_COMPOSE_PAYLOAD_CODEC_ID",
    "KNOWLEDGE_WRITING_COMPOSE_RESULT_TYPE",
    "KNOWLEDGE_WRITING_FAILURE_CODES",
    "KNOWLEDGE_WRITING_OBSERVATION_DIMENSIONS",
    "KNOWLEDGE_WRITING_OWNER",
    "KNOWLEDGE_WRITING_READBACK_PROFILE_REF",
    "KNOWLEDGE_WRITING_RETURN_CONTRACT_REF",
    "KNOWLEDGE_WRITING_ROLLBACK_REFS",
    "KNOWLEDGE_WRITING_STAGE_INPUT_TYPE",
    "KNOWLEDGE_WRITING_STAGE_KIND",
    "KNOWLEDGE_WRITING_STAGE_OPERATION_ID",
    "KNOWLEDGE_WRITING_STAGE_RESULT_TYPE",
    "KnowledgeWritingComposeInput",
    "KNOWLEDGE_WRITING_AUTHOR_SOURCE",
    "KNOWLEDGE_WRITING_NATIVE_DEFINITION",
    "knowledge_writing_native_contribution",
]

KNOWLEDGE_WRITING_OWNER = "knowledge.writing.v2"

KNOWLEDGE_WRITING_COMPOSE_OPERATION_ID = "knowledge.writing.compose"
KNOWLEDGE_WRITING_COMPOSE_KIND = "knowledge.writing.compose.v2"
KNOWLEDGE_WRITING_COMPOSE_PAYLOAD_CODEC_ID = "mrw.knowledge.writing-compose.codec.v2"
KNOWLEDGE_WRITING_COMPOSE_INPUT_TYPE = ObjectType("KnowledgeWritingComposeInput.v2")
KNOWLEDGE_WRITING_COMPOSE_RESULT_TYPE = ObjectType("KnowledgeWritingHandoff.v2")
KNOWLEDGE_WRITING_STAGE_OPERATION_ID = "knowledge.writing.stage"
KNOWLEDGE_WRITING_STAGE_KIND = "knowledge.writing.stage.v2"
KNOWLEDGE_WRITING_STAGE_INPUT_TYPE = KNOWLEDGE_WRITING_COMPOSE_RESULT_TYPE
KNOWLEDGE_WRITING_STAGE_RESULT_TYPE = ObjectType("StagedKnowledgeWritingArtifact.v2")
KNOWLEDGE_WRITING_RETURN_CONTRACT_REF = SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF

KNOWLEDGE_WRITING_FAILURE_CODES = knowledge_writing_failures.codes
KNOWLEDGE_WRITING_READBACK_PROFILE_REF = "knowledge.writing.readback.v2"
KNOWLEDGE_WRITING_OBSERVATION_DIMENSIONS = (
    "ordered_composition",
    "declared_loss",
    "provenance_chain",
)
KNOWLEDGE_WRITING_ROLLBACK_REFS = (
    "main/backend/app/successor_migration/legacy_c8_writing.py",
    "main/backend/app/successor_runtime/assembly/c8_assembly.py",
)


def _payload_body_digest(payload: KnowledgeWritingComposeInput) -> str:
    return content_digest(
        {
            name: value
            for name, value in dataclasses.asdict(payload).items()
            if name != "payload_digest"
        }
    )


@dataclass(frozen=True, slots=True)
class KnowledgeWritingComposeInput:
    project_key: str
    knowledge_item_key: str
    selection_hash: str
    selection_text: str
    demand_fields: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        expected = _payload_body_digest(self)
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
            return
        require_hex64(self.payload_digest, "C8WritingComposeInput.payload_digest")
        if self.payload_digest != expected:
            reject_knowledge_value(
                "C8WritingComposeInput.payload_digest does not match recomputed body digest"
            )


KNOWLEDGE_WRITING_AUTHOR_SOURCE = KnowledgeNativeAuthorSource(
    contribution_id="mrw.knowledge.writing.native.v2",
    cell_id=KNOWLEDGE_WRITING_CELL_ID,
    owner="knowledge.writing.v2",
    runtime_owner=KNOWLEDGE_WRITING_OWNER,
    execution_class="PURE_TRANSFORM",
    operations=(
        KnowledgeNativeOperationSource(
            operation_id=KNOWLEDGE_WRITING_COMPOSE_OPERATION_ID,
            kind=KNOWLEDGE_WRITING_COMPOSE_KIND,
            input_type=KNOWLEDGE_WRITING_COMPOSE_INPUT_TYPE,
            output_type=KNOWLEDGE_WRITING_COMPOSE_RESULT_TYPE,
            return_contract_ref=KNOWLEDGE_WRITING_RETURN_CONTRACT_REF,
            value_suffix="knowledge-writing-compose",
            payload_codec_id=KNOWLEDGE_WRITING_COMPOSE_PAYLOAD_CODEC_ID,
            payload_type=KnowledgeWritingComposeInput,
            catalog_operation_id="knowledge.writing.compose.v2",
            catalog_input_type_id="KnowledgeWritingComposeInput.v2",
            catalog_output_type_id="KnowledgeWritingHandoff.v2",
            catalog_payload_codec_id="mrw.knowledge.writing-compose.codec.v2",
        ),
        KnowledgeNativeOperationSource(
            operation_id=KNOWLEDGE_WRITING_STAGE_OPERATION_ID,
            kind=KNOWLEDGE_WRITING_STAGE_KIND,
            input_type=KNOWLEDGE_WRITING_STAGE_INPUT_TYPE,
            output_type=KNOWLEDGE_WRITING_STAGE_RESULT_TYPE,
            return_contract_ref=KNOWLEDGE_WRITING_RETURN_CONTRACT_REF,
            value_suffix="knowledge-writing-stage",
            catalog_operation_id="knowledge.writing.stage.v2",
            catalog_input_type_id="KnowledgeWritingHandoff.v2",
            catalog_output_type_id="StagedKnowledgeWritingArtifact.v2",
        ),
    ),
    ordered_operation_ids=(KNOWLEDGE_WRITING_COMPOSE_OPERATION_ID, KNOWLEDGE_WRITING_STAGE_OPERATION_ID),
    reads=(KNOWLEDGE_WRITING_COMPOSE_INPUT_TYPE.type_id,),
    creates=(KNOWLEDGE_WRITING_COMPOSE_RESULT_TYPE.type_id, KNOWLEDGE_WRITING_STAGE_RESULT_TYPE.type_id),
    failure_codes=KNOWLEDGE_WRITING_FAILURE_CODES,
    readback_profile_ref=KNOWLEDGE_WRITING_READBACK_PROFILE_REF,
    observation_dimensions=KNOWLEDGE_WRITING_OBSERVATION_DIMENSIONS,
    assembly=KnowledgeNativeAssemblyDeclaration(
        status="UNWIRED_DECLARED",
        operation_contract_refs=(KNOWLEDGE_WRITING_COMPOSE_KIND, KNOWLEDGE_WRITING_STAGE_KIND),
        recovery_binding_ref=(
            "knowledge.writing.recovery.v2#retained-staged-values-no-authority-reversal"
        ),
        required_wiring=(
            "c82_payload compose+stage 纯 route closure",
            "admission_not_called/export_not_executed 保持",
        ),
        note=(
            "缺 c82_payload 的 compose_writing_handoff + stage_writing_artifact "
            "纯 route closure（read/handoff 输入）；"
            "admission/export authority closed"
        ),
        installed_required_wiring=("admission_not_called/export_not_executed 保持",),
        installed_note=(
            "LOCAL_OFFLINE knowledge.writing.v2 compose+stage pure route handler installed; "
            "no PostgreSQL write adopted"
        ),
        rollback_refs=KNOWLEDGE_WRITING_ROLLBACK_REFS,
    ),
    failure_family=knowledge_writing_failures,
)

_compiled_knowledge_writing_native = compile_native_contribution(
    KNOWLEDGE_WRITING_AUTHOR_SOURCE,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
)
if isinstance(_compiled_knowledge_writing_native, Failure):
    reject_knowledge_contract(
        "invalid native knowledge writing contribution: "
        f"{_compiled_knowledge_writing_native.message}",
        exception_type=RuntimeError,
        operation=KNOWLEDGE_WRITING_COMPOSE_OPERATION_ID,
        site="c8_writing_contribution.import",
    )

knowledge_writing_native_contribution = _compiled_knowledge_writing_native
KNOWLEDGE_WRITING_NATIVE_DEFINITION = knowledge_writing_native_contribution.definition
