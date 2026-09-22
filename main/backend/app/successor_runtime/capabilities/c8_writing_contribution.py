"""Native contribution source for the ordered C8.2 writing cell.

The module owns the C8.2 payload and the two authored operations.  ``compose``
produces the writing handoff from its typed payload; ``stage`` consumes that
handoff and emits the staged artifact.  The operations are ordered and are not
interchangeable.  Assembly, projection and binding validation are derived by
the shared non-graph C8 native contribution rule.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.successor_runtime.capabilities.c8_common import reject_c8_contract, reject_c8_value
from app.successor_runtime.capabilities.c8_native_contribution import (
    C8NativeAssemblyDeclaration,
    C8NativeAuthorSource,
    C8NativeOperationSource,
    C8_NATIVE_CONTRIBUTION_RULE,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.language.object_contracts import (
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
)
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from mrw_functorial_kit.core.c8_semantics import c8_writing_failures

__all__ = [
    "C8_2_CELL_ID",
    "C8_2_COMPOSE_INPUT_TYPE",
    "C8_2_COMPOSE_KIND",
    "C8_2_COMPOSE_OPERATION_ID",
    "C8_2_COMPOSE_PAYLOAD_CODEC_ID",
    "C8_2_COMPOSE_RESULT_TYPE",
    "C8_2_FAILURE_CODES",
    "C8_2_OBSERVATION_DIMENSIONS",
    "C8_2_OWNER",
    "C8_2_READBACK_PROFILE_REF",
    "C8_2_RETURN_CONTRACT_REF",
    "C8_2_ROLLBACK_REFS",
    "C8_2_STAGE_INPUT_TYPE",
    "C8_2_STAGE_KIND",
    "C8_2_STAGE_OPERATION_ID",
    "C8_2_STAGE_RESULT_TYPE",
    "C8WritingComposeInput",
    "C8_WRITING_AUTHOR_SOURCE",
    "C8_WRITING_NATIVE_DEFINITION",
    "c8_writing_native_contribution",
]

C8_2_CELL_ID = "C8.2"
C8_2_OWNER = "writing.c8.2.v1"

C8_2_COMPOSE_OPERATION_ID = "c8.writing.compose"
C8_2_COMPOSE_KIND = "c8.writing.compose.v1"
C8_2_COMPOSE_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-2.compose.payload.codec.v1"
C8_2_COMPOSE_INPUT_TYPE = ObjectType("C8WritingComposeInput.v1")
C8_2_COMPOSE_RESULT_TYPE = ObjectType("C8WritingHandoff.v1")
C8_2_STAGE_OPERATION_ID = "c8.writing.stage"
C8_2_STAGE_KIND = "c8.writing.stage.v1"
C8_2_STAGE_INPUT_TYPE = C8_2_COMPOSE_RESULT_TYPE
C8_2_STAGE_RESULT_TYPE = ObjectType("C8StagedWritingArtifact.v1")
C8_2_RETURN_CONTRACT_REF = SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF

C8_2_FAILURE_CODES = c8_writing_failures.codes
C8_2_READBACK_PROFILE_REF = "c8.writing.readback.v1"
C8_2_OBSERVATION_DIMENSIONS = (
    "ordered_composition",
    "declared_loss",
    "provenance_chain",
)
C8_2_ROLLBACK_REFS = (
    "main/backend/app/successor_migration/legacy_c8_writing.py",
    "main/backend/app/successor_runtime/assembly/c8_assembly.py",
)


def _payload_body_digest(payload: C8WritingComposeInput) -> str:
    return content_digest(
        {
            name: value
            for name, value in dataclasses.asdict(payload).items()
            if name != "payload_digest"
        }
    )


@dataclass(frozen=True, slots=True)
class C8WritingComposeInput:
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
            reject_c8_value(
                "C8WritingComposeInput.payload_digest does not match recomputed body digest"
            )


C8_WRITING_AUTHOR_SOURCE = C8NativeAuthorSource(
    contribution_id="mrw.successor.c8.c8-2.writing.v1",
    cell_id=C8_2_CELL_ID,
    owner=C8_2_OWNER,
    execution_class="PURE_TRANSFORM",
    operations=(
        C8NativeOperationSource(
            operation_id=C8_2_COMPOSE_OPERATION_ID,
            kind=C8_2_COMPOSE_KIND,
            input_type=C8_2_COMPOSE_INPUT_TYPE,
            output_type=C8_2_COMPOSE_RESULT_TYPE,
            return_contract_ref=C8_2_RETURN_CONTRACT_REF,
            value_suffix="c8-2-compose",
            payload_codec_id=C8_2_COMPOSE_PAYLOAD_CODEC_ID,
            payload_type=C8WritingComposeInput,
        ),
        C8NativeOperationSource(
            operation_id=C8_2_STAGE_OPERATION_ID,
            kind=C8_2_STAGE_KIND,
            input_type=C8_2_STAGE_INPUT_TYPE,
            output_type=C8_2_STAGE_RESULT_TYPE,
            return_contract_ref=C8_2_RETURN_CONTRACT_REF,
            value_suffix="c8-2-stage",
        ),
    ),
    ordered_operation_ids=(C8_2_COMPOSE_OPERATION_ID, C8_2_STAGE_OPERATION_ID),
    reads=(C8_2_COMPOSE_INPUT_TYPE.type_id,),
    creates=(C8_2_COMPOSE_RESULT_TYPE.type_id, C8_2_STAGE_RESULT_TYPE.type_id),
    failure_codes=C8_2_FAILURE_CODES,
    readback_profile_ref=C8_2_READBACK_PROFILE_REF,
    observation_dimensions=C8_2_OBSERVATION_DIMENSIONS,
    assembly=C8NativeAssemblyDeclaration(
        status="UNWIRED_DECLARED",
        operation_contract_refs=(C8_2_COMPOSE_KIND, C8_2_STAGE_KIND),
        recovery_binding_ref=(
            "c8.writing.recovery.v1#retained-staged-values-no-authority-reversal"
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
            "LOCAL_OFFLINE C8.2 compose+stage pure route handler installed; "
            "no PostgreSQL write adopted"
        ),
        rollback_refs=C8_2_ROLLBACK_REFS,
    ),
    failure_family=c8_writing_failures,
)

_compiled_c8_writing_native = compile_native_contribution(
    C8_WRITING_AUTHOR_SOURCE,
    C8_NATIVE_CONTRIBUTION_RULE,
)
if isinstance(_compiled_c8_writing_native, Failure):
    reject_c8_contract(
        f"invalid native C8.2 writing contribution: {_compiled_c8_writing_native.message}",
        exception_type=RuntimeError,
        operation=C8_2_COMPOSE_OPERATION_ID,
        site="c8_writing_contribution.import",
    )

c8_writing_native_contribution = _compiled_c8_writing_native
C8_WRITING_NATIVE_DEFINITION = c8_writing_native_contribution.definition
