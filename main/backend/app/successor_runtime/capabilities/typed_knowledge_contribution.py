"""Native C8.1 typed-knowledge demand-read contribution.
KNOWLEDGE_READ_CELL_ID owns the C8.1 payload and the typed declaration consumed by the
shared non-graph C8 native rule.  It intentionally does not add a stricter
issuance path or change the existing demand-read handler, permissions, or
failure behavior.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from app.successor_runtime.capabilities.knowledge_common import KNOWLEDGE_READ_CELL_ID, reject_knowledge_value
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64
from app.successor_runtime.language.object_contracts import READ_CANONICAL_REF_RETURN_CONTRACT_REF
from app.successor_runtime.research.object_types import ObjectType
from functorial_kit.contribution_compiler import compile_native_contribution
from functorial_kit.core.failure import Failure
from functorial_kit.native_contribution import NativeContribution
from mrw_functorial_kit.core.knowledge_semantics import knowledge_typed_knowledge_failures
from . import (
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
    KnowledgeNativeAssemblyContext,
    KnowledgeNativeAssemblyDeclaration,
    KnowledgeNativeAuthorSource,
    KnowledgeNativeDefinition,
    KnowledgeNativeOperationSource,
)

__all__ = [
    "KNOWLEDGE_READ_CELL_ID",
    "KNOWLEDGE_READ_CONTRIBUTION_ID",
    "KNOWLEDGE_READ_INPUT_TYPE",
    "KNOWLEDGE_READ_KIND",
    "KNOWLEDGE_READ_OPERATION_ID",
    "KNOWLEDGE_READ_OWNER",
    "KNOWLEDGE_READ_PAYLOAD_CODEC_ID",
    "KNOWLEDGE_READ_READBACK_PROFILE_REF",
    "KNOWLEDGE_READ_RESULT_TYPE",
    "KNOWLEDGE_READ_RETURN_CONTRACT_REF",
    "KNOWLEDGE_READ_ROLLBACK_REFS",
    "KnowledgeDemandReadInput",
    "KNOWLEDGE_TYPED_KNOWLEDGE_ASSEMBLY",
    "KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE",
    "KNOWLEDGE_TYPED_KNOWLEDGE_NATIVE",
]

KNOWLEDGE_READ_CONTRIBUTION_ID = "mrw.knowledge.read.native.v2"
KNOWLEDGE_READ_OWNER = "knowledge.read.v2"
KNOWLEDGE_READ_OPERATION_ID = "knowledge.read.demand"
KNOWLEDGE_READ_KIND = "knowledge.read.demand.v2"
KNOWLEDGE_READ_PAYLOAD_CODEC_ID = "mrw.knowledge.demand-read.codec.v2"
KNOWLEDGE_READ_INPUT_TYPE = ObjectType("KnowledgeDemandReadInput.v2")
KNOWLEDGE_READ_RESULT_TYPE = ObjectType("KnowledgeDemandReadResult.v2")
KNOWLEDGE_READ_RETURN_CONTRACT_REF = READ_CANONICAL_REF_RETURN_CONTRACT_REF
KNOWLEDGE_READ_READBACK_PROFILE_REF = "knowledge.read.readback.v2"
KNOWLEDGE_READ_RECOVERY_BINDING_REF = (
    "knowledge.read.recovery.v2#route-back-to-legacy-repository-"
    "read-handle-retained;no-dual-write"
)
KNOWLEDGE_READ_ROLLBACK_REFS = (
    "main/backend/app/successor_migration/legacy_c8_typed_knowledge.py",
    "main/backend/app/successor_runtime/assembly/c8_assembly.py",
)


@dataclass(frozen=True, slots=True)
class KnowledgeDemandReadInput:
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
            reject_knowledge_value(
                "C8DemandReadInput.payload_digest does not match recomputed body digest"
            )


KNOWLEDGE_TYPED_KNOWLEDGE_ASSEMBLY = KnowledgeNativeAssemblyDeclaration(
    status="UNWIRED_DECLARED",
    operation_contract_refs=(KNOWLEDGE_READ_KIND,),
    recovery_binding_ref=KNOWLEDGE_READ_RECOVERY_BINDING_REF,
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
        "LOCAL_OFFLINE knowledge.read.v2 demand_read pure route handler installed; "
        "read-only; no PostgreSQL write adopted"
    ),
    rollback_refs=KNOWLEDGE_READ_ROLLBACK_REFS,
)

KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE = KnowledgeNativeAuthorSource(
    contribution_id=KNOWLEDGE_READ_CONTRIBUTION_ID,
    cell_id=KNOWLEDGE_READ_CELL_ID,
    owner="knowledge.read.v2",
    runtime_owner=KNOWLEDGE_READ_OWNER,
    execution_class="EFFECTFUL",
    operations=(
        KnowledgeNativeOperationSource(
            operation_id=KNOWLEDGE_READ_OPERATION_ID,
            kind=KNOWLEDGE_READ_KIND,
            input_type=KNOWLEDGE_READ_INPUT_TYPE,
            output_type=KNOWLEDGE_READ_RESULT_TYPE,
            return_contract_ref=KNOWLEDGE_READ_RETURN_CONTRACT_REF,
            value_suffix="knowledge-read",
            payload_codec_id=KNOWLEDGE_READ_PAYLOAD_CODEC_ID,
            payload_type=KnowledgeDemandReadInput,
            catalog_operation_id="knowledge.read.demand.v2",
            catalog_input_type_id="KnowledgeDemandReadInput.v2",
            catalog_output_type_id="KnowledgeDemandReadResult.v2",
            catalog_payload_codec_id="mrw.knowledge.demand-read.codec.v2",
        ),
    ),
    ordered_operation_ids=(KNOWLEDGE_READ_OPERATION_ID,),
    reads=(KNOWLEDGE_READ_INPUT_TYPE.type_id,),
    creates=(KNOWLEDGE_READ_RESULT_TYPE.type_id,),
    failure_codes=knowledge_typed_knowledge_failures.codes,
    readback_profile_ref=KNOWLEDGE_READ_READBACK_PROFILE_REF,
    observation_dimensions=("read_handle", "canonical_identity", "provider_calls_zero"),
    assembly=KNOWLEDGE_TYPED_KNOWLEDGE_ASSEMBLY,
    failure_family=knowledge_typed_knowledge_failures,
)

KNOWLEDGE_TYPED_KNOWLEDGE_NATIVE = compile_native_contribution(
    KNOWLEDGE_TYPED_KNOWLEDGE_AUTHOR_SOURCE,
    KNOWLEDGE_NATIVE_CONTRIBUTION_RULE,
)
