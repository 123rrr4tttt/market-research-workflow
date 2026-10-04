"""Native contribution for the existing C8.3 report stage.
shared C8 native rule derives the operation contract, codec, profiles, atom,
projection, rollback declaration and binding validation.  Admission and
delivery remain interface references only; no export or delivery permission is
introduced here.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.successor_runtime.capabilities.knowledge_common import (
    KNOWLEDGE_REPORT_CELL_ID,
    reject_knowledge_contract,
    reject_knowledge_value,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities import knowledge_common
from app.successor_runtime.language.object_contracts import RUNTIME_VALUE_RETURN_CONTRACT_REF
from app.successor_runtime.research.object_types import ObjectType
from mrw_functorial_kit.core.knowledge_semantics import (
    knowledge_report_delivery_failures,
    knowledge_report_export_contract_failures,
    knowledge_report_export_token_failures,
    knowledge_report_export_token_state_failures,
)
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from . import (
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeAssemblyDeclaration,
    KnowledgeNativeAuthorSource,
    KnowledgeNativeDefinition,
    KnowledgeNativeRuntimeBinding,
    KnowledgeNativeOperationSource,
)

__all__ = [
    "KNOWLEDGE_REPORT_CELL_ID",
    "KNOWLEDGE_REPORT_CONTRIBUTION_ID",
    "KNOWLEDGE_REPORT_DECLARED_LOSS",
    "KNOWLEDGE_REPORT_FAILURE_CODES",
    "KNOWLEDGE_REPORT_INPUT_TYPE",
    "KNOWLEDGE_REPORT_KIND",
    "KNOWLEDGE_REPORT_OPERATION_ID",
    "KNOWLEDGE_REPORT_OWNER",
    "KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID",
    "KNOWLEDGE_REPORT_RESULT_TYPE",
    "KNOWLEDGE_REPORT_RETURN_CONTRACT_REF",
    "KNOWLEDGE_REPORT_ROLLBACK_REF",
    "KnowledgeReportStageInput",
    "KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE",
    "knowledge_report_native_contribution",
]

KNOWLEDGE_REPORT_CONTRIBUTION_ID = "mrw.knowledge.report.native.v2"
KNOWLEDGE_REPORT_OWNER = "knowledge.report.v2"
KNOWLEDGE_REPORT_OPERATION_ID = "knowledge.report.stage"
KNOWLEDGE_REPORT_KIND = "knowledge.report.stage.v2"
KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID = "mrw.knowledge.report-stage.codec.v2"
KNOWLEDGE_REPORT_INPUT_TYPE = ObjectType("KnowledgeReportSourceReads.v2")
KNOWLEDGE_REPORT_RESULT_TYPE = ObjectType("StagedKnowledgeReport.v2")
KNOWLEDGE_REPORT_RETURN_CONTRACT_REF = RUNTIME_VALUE_RETURN_CONTRACT_REF
KNOWLEDGE_REPORT_FAILURE_CODES = knowledge_report_delivery_failures.codes
KNOWLEDGE_REPORT_DECLARED_LOSS = ("graph_node_filter", "report_export_body")
KNOWLEDGE_REPORT_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_report.py"


def _payload_body_digest(payload: KnowledgeReportStageInput) -> str:
    return content_digest(
        {
            name: value
            for name, value in dataclasses.asdict(payload).items()
            if name != "payload_digest"
        }
    )


@dataclass(frozen=True, slots=True)
class KnowledgeReportStageInput:
    project_key: str
    report_id: str
    topic: str
    source_keys: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        expected = _payload_body_digest(self)
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
            return
        require_hex64(self.payload_digest, "C8ReportStageInput.payload_digest")
        if self.payload_digest != expected:
            reject_knowledge_value(
                "C8ReportStageInput.payload_digest does not match recomputed body digest"
            )


KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE = KnowledgeNativeAuthorSource(
    contribution_id=KNOWLEDGE_REPORT_CONTRIBUTION_ID,
    cell_id=KNOWLEDGE_REPORT_CELL_ID,
    owner="knowledge.report.v2",
    runtime_owner=KNOWLEDGE_REPORT_OWNER,
    execution_class="ADMISSION",
    operations=(
        KnowledgeNativeOperationSource(
            operation_id=KNOWLEDGE_REPORT_OPERATION_ID,
            kind=KNOWLEDGE_REPORT_KIND,
            input_type=KNOWLEDGE_REPORT_INPUT_TYPE,
            output_type=KNOWLEDGE_REPORT_RESULT_TYPE,
            return_contract_ref=KNOWLEDGE_REPORT_RETURN_CONTRACT_REF,
            value_suffix="knowledge-report-stage",
            payload_codec_id=KNOWLEDGE_REPORT_PAYLOAD_CODEC_ID,
            payload_type=KnowledgeReportStageInput,
            catalog_operation_id="knowledge.report.stage.v2",
            catalog_input_type_id="KnowledgeReportSourceReads.v2",
            catalog_output_type_id="StagedKnowledgeReport.v2",
            catalog_payload_codec_id="mrw.knowledge.report-stage.codec.v2",
        ),
    ),
    ordered_operation_ids=(KNOWLEDGE_REPORT_OPERATION_ID,),
    reads=(KNOWLEDGE_REPORT_INPUT_TYPE.type_id,),
    creates=(KNOWLEDGE_REPORT_RESULT_TYPE.type_id,),
    failure_codes=KNOWLEDGE_REPORT_FAILURE_CODES,
    readback_profile_ref="knowledge.report.admission.readback.v2",
    observation_dimensions=(
        "read_only_unavailable",
        "admission_interface_only",
        "declared_loss",
    ),
    failure_family=knowledge_report_delivery_failures,
    additional_failure_families=(
        knowledge_report_export_contract_failures,
        knowledge_report_export_token_failures,
        knowledge_report_export_token_state_failures,
        successor_capability_contract_failures,
    ),
    declared_loss=KNOWLEDGE_REPORT_DECLARED_LOSS,
    extra_program_metadata={
        "admission_interface_digest": knowledge_common.KNOWLEDGE_REPORT_ADMISSION_INTERFACE_DIGEST,
        "delivery_interface_digest": knowledge_common.KNOWLEDGE_REPORT_DELIVERY_INTERFACE_DIGEST,
    },
    assembly=KnowledgeNativeAssemblyDeclaration(
        status="UNWIRED_DECLARED",
        operation_contract_refs=(
            "knowledge.report.stage.v2",
            "knowledge.report.admission.v2",
            "knowledge.report.delivery.v2",
        ),
        recovery_binding_ref=(
            "knowledge.report.admission.recovery.v2#verification-and-receipt-readback-only;"
            "no-repeat-export"
        ),
        required_wiring=(
            "app 层调用方/挂载",
            "admission/export authority gate 保持关闭",
        ),
        note=(
            "build_postgres_c8_delivery_assembly exists but no app caller "
            "instantiates it; admission/export authority gate stays closed"
        ),
        rollback_refs=(KNOWLEDGE_REPORT_ROLLBACK_REF,),
    ),
)


_compiled_knowledge_report_native = compile_native_contribution(
    KNOWLEDGE_REPORT_STAGE_AUTHOR_SOURCE,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
)
if isinstance(_compiled_knowledge_report_native, Failure):
    reject_knowledge_contract(
        "invalid native knowledge report contribution: "
        f"{_compiled_knowledge_report_native.message}",
        exception_type=RuntimeError,
        operation=KNOWLEDGE_REPORT_OPERATION_ID,
        site="c8_report_contribution.import",
    )

knowledge_report_native_contribution: NativeContribution[
    KnowledgeNativeDefinition,
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeRuntimeBinding,
] = _compiled_knowledge_report_native
