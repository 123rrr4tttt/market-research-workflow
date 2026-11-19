"""Fixtures for the retained single-dispatch Program witnesses."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.capabilities import batch_task
from app.successor_runtime.capabilities.batch_task_program import (
    _ordered_dispatch_sequence_type,
    _register_ordered_dispatch_merges,
    build_batch_task_single_dispatch_program,
)
from app.successor_runtime.capabilities.checksum import sha256_hex
from app.successor_runtime.capabilities.source_contracts import project_scope_digest
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.program import ProgramSpec, zip_ordered_node
from app.successor_runtime.language.transforms import TransformRegistry


PROJECT_KEY = "batch-task-demo"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_batch_task_demo"
SCOPE_INCARNATION = "scope-inc-batch-task-demo"
SCOPE_DIGEST = project_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
DEPLOYMENT_CATALOG_DIGEST = sha256_hex(b"batch-task-dispatch-deployment")
PROGRAM_ID = "program:batch-task-direct-test"


def ordered_dispatch_program(
    *,
    payloads: tuple[batch_task.BatchTaskSingleDispatchPayload, ...]
    | list[batch_task.BatchTaskSingleDispatchPayload],
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    """Build an ordered Program from the installed single-dispatch contract."""

    pair, append = _register_ordered_dispatch_merges(TransformRegistry())
    roots = []
    for index, payload in enumerate(payloads):
        item = build_batch_task_single_dispatch_program(
            payload=payload,
            catalog=catalog,
            program_id=f"{program_id}:{index}",
            project_key=project_key,
            project_registry_revision=project_registry_revision,
            project_scope_digest=project_scope_digest,
        )
        roots.append(
            dataclasses.replace(
                item.root,
                operation=dataclasses.replace(
                    item.root.operation,
                    operation_id=(
                        f"{batch_task.DISPATCH_SINGLE_OPERATION_ID}:"
                        f"{payload.dispatch_id}"
                    ),
                ),
            )
        )
    root = roots[0]
    for index, atom in enumerate(roots[1:], start=1):
        root = zip_ordered_node(
            left=root,
            right=atom,
            merge_ref=pair if index == 1 else append,
            output_type=_ordered_dispatch_sequence_type(),
        )
    return dataclasses.replace(
        item,
        program_id=f"{program_id}:ordered-dispatch",
        root=root,
        input_type=root.input_type,
        output_type=root.output_type,
        metadata=freeze_json_object({"ordered_element_count": len(payloads)}),
        program_digest="",
    ).with_digest()
