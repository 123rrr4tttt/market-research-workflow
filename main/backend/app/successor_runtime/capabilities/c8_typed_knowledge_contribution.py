"""Native C8.1 typed-knowledge demand-read contribution.

This module owns the C8.1 payload and the typed declaration consumed by the
shared non-graph C8 native rule.  It intentionally does not add a stricter
issuance path or change the existing demand-read handler, permissions, or
failure behavior.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from app.successor_runtime.capabilities.c8_common import reject_c8_value
from app.successor_runtime.capabilities.c8_native_contribution import (
    C8NativeAssemblyDeclaration,
    C8NativeAuthorSource,
    C8NativeOperationSource,
    C8_NATIVE_CONTRIBUTION_RULE,
)
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.language.object_contracts import (
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
)
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from mrw_functorial_kit.core.c8_semantics import c8_typed_knowledge_failures

__all__ = [
    "C8_1_CELL_ID",
    "C8_1_CONTRIBUTION_ID",
    "C8_1_INPUT_TYPE",
    "C8_1_KIND",
    "C8_1_OPERATION_ID",
    "C8_1_OWNER",
    "C8_1_PAYLOAD_CODEC_ID",
    "C8_1_READBACK_PROFILE_REF",
    "C8_1_RESULT_TYPE",
    "C8_1_RETURN_CONTRACT_REF",
    "C8_1_ROLLBACK_REFS",
    "C8DemandReadInput",
    "C8_TYPED_KNOWLEDGE_ASSEMBLY",
    "C8_TYPED_KNOWLEDGE_AUTHOR_SOURCE",
    "C8_TYPED_KNOWLEDGE_NATIVE",
]

C8_1_CELL_ID = "C8.1"
C8_1_CONTRIBUTION_ID = "mrw.successor.c8.typed-knowledge.v1"
C8_1_OWNER = "typed_knowledge.c8.1.v1"
C8_1_OPERATION_ID = "c8.typed_knowledge.demand_read"
C8_1_KIND = "c8.typed_knowledge.demand_read.v1"
C8_1_PAYLOAD_CODEC_ID = "mrw.successor.c8.c8-1.payload.codec.v1"
C8_1_INPUT_TYPE = ObjectType("C8DemandReadInput.v1")
C8_1_RESULT_TYPE = ObjectType("C8DemandReadResult.v1")
C8_1_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF
C8_1_READBACK_PROFILE_REF = "c8.typed_knowledge.readback.v1"
C8_1_RECOVERY_BINDING_REF = (
    "c8.typed_knowledge.recovery.v1#route-back-to-legacy-repository-"
    "read-handle-retained;no-dual-write"
)
C8_1_ROLLBACK_REFS = (
    "main/backend/app/successor_migration/legacy_c8_typed_knowledge.py",
    "main/backend/app/successor_runtime/assembly/c8_assembly.py",
)


@dataclass(frozen=True, slots=True)
class C8DemandReadInput:
    project_key: str
    item_key: str
    fields: tuple[str, ...]
    payload_digest: str = ""

    def __post_init__(self) -> None:
        body = {
            name: value
            for name, value in dataclasses.asdict(self).items()
            if name != "payload_digest"
        }
        expected = content_digest(body)
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
            return
        require_hex64(self.payload_digest, "C8DemandReadInput.payload_digest")
        if self.payload_digest != expected:
            reject_c8_value(
                "C8DemandReadInput.payload_digest does not match recomputed body digest"
            )


C8_TYPED_KNOWLEDGE_ASSEMBLY = C8NativeAssemblyDeclaration(
    status="UNWIRED_DECLARED",
    operation_contract_refs=(C8_1_KIND,),
    recovery_binding_ref=C8_1_RECOVERY_BINDING_REF,
    required_wiring=(
        "c81_payload demand-read 纯 route closure",
        "admission_not_called/export_not_executed 保持",
    ),
    note=(
        "缺 c81_payload 的 demand_read 纯 route closure"
        "（item(s)/item_key/fields/project_key/registry）；"
        "admission/export authority closed"
    ),
    installed_required_wiring=("admission_not_called/export_not_executed 保持",),
    installed_note=(
        "LOCAL_OFFLINE C8.1 demand_read pure route handler installed; "
        "read-only; no PostgreSQL write adopted"
    ),
    rollback_refs=C8_1_ROLLBACK_REFS,
)

C8_TYPED_KNOWLEDGE_AUTHOR_SOURCE = C8NativeAuthorSource(
    contribution_id=C8_1_CONTRIBUTION_ID,
    cell_id=C8_1_CELL_ID,
    owner=C8_1_OWNER,
    execution_class="EFFECTFUL",
    operations=(
        C8NativeOperationSource(
            operation_id=C8_1_OPERATION_ID,
            kind=C8_1_KIND,
            input_type=C8_1_INPUT_TYPE,
            output_type=C8_1_RESULT_TYPE,
            return_contract_ref=C8_1_RETURN_CONTRACT_REF,
            value_suffix="c8-1",
            payload_codec_id=C8_1_PAYLOAD_CODEC_ID,
            payload_type=C8DemandReadInput,
        ),
    ),
    ordered_operation_ids=(C8_1_OPERATION_ID,),
    reads=("C8DemandReadInput.v1",),
    creates=("C8DemandReadResult.v1",),
    failure_codes=c8_typed_knowledge_failures.codes,
    readback_profile_ref=C8_1_READBACK_PROFILE_REF,
    observation_dimensions=("read_handle", "canonical_identity", "provider_calls_zero"),
    assembly=C8_TYPED_KNOWLEDGE_ASSEMBLY,
    failure_family=c8_typed_knowledge_failures,
)

C8_TYPED_KNOWLEDGE_NATIVE = compile_native_contribution(
    C8_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
    C8_NATIVE_CONTRIBUTION_RULE,
)
