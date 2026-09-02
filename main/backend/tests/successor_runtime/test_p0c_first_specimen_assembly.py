from __future__ import annotations

import hashlib

import sqlalchemy as sa

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.runtime.assignments import (
    InterpreterBinding,
    RecoveryBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    ActivationCatalogEntry,
    FirstSpecimenActivationCatalog,
)
from app.successor_runtime.substrate.postgres.first_specimen_assembly import (
    build_postgres_first_specimen_assembly,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_assembly_installs_one_exact_dual_role_handler_per_operation(tmp_path) -> None:
    bundle = build_first_specimen_bundle()
    registries = default_registries()
    entries = []
    for operation in bundle.operations:
        profile = operation.interpreter_compatibility_ref.profile_digest
        binding = InterpreterBinding.from_content(
            operation_contract_digest=operation.ref.contract_digest,
            interpreter_profile_digest=profile,
            deployment_catalog_digest=_digest("deployment"),
            runtime_protocol_version="1",
            project_scope_digest=_digest("scope"),
            resource_policy_epoch=1,
            authority_requirement_digest=_digest("authority"),
        )
        recovery = RecoveryBinding.from_content(
            recovery_handler_id=f"recovery:{operation.ref.kind}",
            recovery_handler_version="1",
            interpreter_profile_digest=profile,
            authoritative_readback_profile_ref=f"readback:{operation.ref.kind}",
        )
        entries.append(
            ActivationCatalogEntry(
                operation_contract_digest=operation.ref.contract_digest,
                interpreter_binding=binding,
                recovery_binding=recovery,
                queue_eligibility=QueueEligibility(
                    project_key="p0c",
                    capability_id=operation.owner_capability_id,
                    resource_class=ResourceClass.CPU_LIGHT,
                    units=1,
                    policy_epoch=1,
                    policy_digest=_digest("resource-policy"),
                    concurrency_key=f"p0c:{operation.ref.kind}",
                ),
                required_node_profile_selector=_digest("node-profile"),
                resource_policy_digest=_digest("resource-policy"),
                fairness_key="p0c",
                effect_class="LOCAL_SUCCESSOR_NATIVE",
                external_gate_required=(
                    operation.ref.kind == "delivery.internal_export.v1"
                ),
            )
        )
    catalog = FirstSpecimenActivationCatalog(
        entries=tuple(entries),
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
    )
    delivery_contract = bundle.operation_by_kind("delivery.internal_export.v1")
    assembly = build_postgres_first_specimen_assembly(
        engine=sa.create_engine("sqlite://"),
        activation_catalog=catalog,
        delivery_interpreter=InternalExportInterpreter(
            operation_contract_ref=delivery_contract.ref,
            blob_store=ProjectBlobStore(tmp_path),
        ),
    )

    assert len(assembly.handlers) == len(bundle.operations) == 6
    assert len({item.handler_binding_digest for item in assembly.handlers}) == 6
    admission_kinds = {
        operation.ref.kind
        for operation, handler in zip(bundle.operations, assembly.handlers, strict=True)
        if handler.verify_admit is not None
    }
    assert admission_kinds == {
        "evidence.qualify.v1",
        "claim.form_or_open_gap.v1",
        "artifact.compose_markdown.v1",
        "delivery.internal_export.v1",
    }
