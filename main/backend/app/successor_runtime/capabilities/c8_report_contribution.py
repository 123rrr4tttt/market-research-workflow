"""Native contribution for the existing C8.3 report stage.

This module owns the report-stage payload and the cell's authored facts.  The
shared C8 native rule derives the operation contract, codec, profiles, atom,
projection, rollback declaration and binding validation.  Admission and
delivery remain interface references only; no export or delivery permission is
introduced here.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.successor_runtime.capabilities.c8_common import (
    reject_c8_contract,
    reject_c8_value,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities import c8_common
from app.successor_runtime.capabilities.c8_native_contribution import (
    C8NativeAssemblyContext,
    C8NativeAssemblyDeclaration,
    C8NativeAuthorSource,
    C8NativeDefinition,
    C8NativeOperationSource,
    C8NativeRuntimeBinding,
    C8_NATIVE_CONTRIBUTION_RULE,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
)
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from mrw_functorial_kit.core.c8_semantics import c8_report_delivery_failures

__all__ = [
    "C8_3_CELL_ID",
    "C8_3_CONTRIBUTION_ID",
    "C8_3_DECLARED_LOSS",
    "C8_3_FAILURE_CODES",
    "C8_3_INPUT_TYPE",
    "C8_3_KIND",
    "C8_3_OPERATION_ID",
    "C8_3_OWNER",
    "C8_3_PAYLOAD_CODEC_ID",
    "C8_3_RESULT_TYPE",
    "C8_3_RETURN_CONTRACT_REF",
    "C8_3_ROLLBACK_REF",
    "C8ReportStageInput",
    "C8_REPORT_STAGE_AUTHOR_SOURCE",
    "c8_report_native_contribution",
]

C8_3_CELL_ID = "C8.3"
C8_3_CONTRIBUTION_ID = "mrw.successor.c8.report.v1"
C8_3_OWNER = "report.c8.3.v1"
C8_3_OPERATION_ID = "c8.report.stage"
C8_3_KIND = "c8.report.stage.v1"
C8_3_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-3.payload.codec.v1"
C8_3_INPUT_TYPE = ObjectType("C8ReportSourceReads.v1")
C8_3_RESULT_TYPE = ObjectType("C8StagedReport.v1")
C8_3_RETURN_CONTRACT_REF = RUNTIME_VALUE_RETURN_CONTRACT_REF
C8_3_FAILURE_CODES = c8_report_delivery_failures.codes
C8_3_DECLARED_LOSS = ("graph_node_filter", "report_export_body")
C8_3_ROLLBACK_REF = "main/backend/app/successor_migration/legacy_c8_report.py"


def _payload_body_digest(payload: C8ReportStageInput) -> str:
    return content_digest(
        {
            name: value
            for name, value in dataclasses.asdict(payload).items()
            if name != "payload_digest"
        }
    )


@dataclass(frozen=True, slots=True)
class C8ReportStageInput:
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
            reject_c8_value(
                "C8ReportStageInput.payload_digest does not match recomputed body digest"
            )


C8_REPORT_STAGE_AUTHOR_SOURCE = C8NativeAuthorSource(
    contribution_id=C8_3_CONTRIBUTION_ID,
    cell_id=C8_3_CELL_ID,
    owner=C8_3_OWNER,
    execution_class="ADMISSION",
    operations=(
        C8NativeOperationSource(
            operation_id=C8_3_OPERATION_ID,
            kind=C8_3_KIND,
            input_type=C8_3_INPUT_TYPE,
            output_type=C8_3_RESULT_TYPE,
            return_contract_ref=C8_3_RETURN_CONTRACT_REF,
            value_suffix="c8-3",
            payload_codec_id=C8_3_PAYLOAD_CODEC_ID,
            payload_type=C8ReportStageInput,
        ),
    ),
    ordered_operation_ids=(C8_3_OPERATION_ID,),
    reads=("C8ReportSourceReads.v1",),
    creates=("C8StagedReport.v1",),
    failure_codes=C8_3_FAILURE_CODES,
    readback_profile_ref="c8.report.admission.readback.v1",
    observation_dimensions=(
        "read_only_unavailable",
        "admission_interface_only",
        "declared_loss",
    ),
    failure_family=c8_report_delivery_failures,
    declared_loss=C8_3_DECLARED_LOSS,
    extra_program_metadata={
        "admission_interface_digest": c8_common.C8_3_ADMISSION_INTERFACE_DIGEST,
        "delivery_interface_digest": c8_common.C8_3_DELIVERY_INTERFACE_DIGEST,
    },
    assembly=C8NativeAssemblyDeclaration(
        status="UNWIRED_DECLARED",
        operation_contract_refs=(
            "c8.report.stage.v1",
            "c8.report.admission.v1",
            "c8.report.delivery.v1",
        ),
        recovery_binding_ref=(
            "c8.report.admission.recovery.v1#verification-and-receipt-readback-only;"
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
        rollback_refs=(C8_3_ROLLBACK_REF,),
    ),
)


_compiled_c8_report_native = compile_native_contribution(
    C8_REPORT_STAGE_AUTHOR_SOURCE,
    C8_NATIVE_CONTRIBUTION_RULE,
)
if isinstance(_compiled_c8_report_native, Failure):
    reject_c8_contract(
        f"invalid native C8 report contribution: {_compiled_c8_report_native.message}",
        exception_type=RuntimeError,
        operation=C8_3_OPERATION_ID,
        site="c8_report_contribution.import",
    )

c8_report_native_contribution: NativeContribution[
    C8NativeDefinition,
    C8NativeAssemblyContext,
    C8NativeRuntimeBinding,
] = _compiled_c8_report_native
