"""Exact project-value replay for the first-specimen RuntimeNode.

Submission is the only boundary allowed to observe a legacy Document.  This
adapter starts from a durably claimed ``RuntimeAssignment``, re-opens its exact
Program/Plan closure, and reads immutable values only from the validated
project ``successor_values`` table.  It deliberately has no legacy adapter or
Document port dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    CanonicalReadInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    derive_material_ref,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    MapOutput,
    ProgramNode,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.materials import (
    CapturedMaterialSnapshot,
    MaterialRef,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.activation import ReadyActivation
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .models import PUBLIC_TABLES, project_tables
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import one_mapping
from .runtime_values import RuntimeValueBinding, RuntimeValueRepository
from .session import ProjectScopeStale, ServerProjectScopeResolver

MATERIAL_READ_OPERATION_KIND = "material.read_canonical_ref.v1"
CAPTURED_SNAPSHOT_TYPE = "CapturedMaterialSnapshot.v1"
MATERIAL_REF_TYPE = "MaterialRef.v1"
SOURCE_REF_TYPE = "SourceRef.v1"


class CapturedValueReplayError(RuntimeError):
    """The durable assignment cannot be replayed from its exact value closure."""


class ReadUnitOfWork(Protocol):
    connection: Any

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class ReadUnitOfWorkFactory(Protocol):
    def __call__(self) -> ReadUnitOfWork: ...


class CapturedActivationBindingPort(Protocol):
    def load_exact(
        self,
        connection: Any,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        tables: Any,
    ) -> ReadyActivation: ...


@dataclass(frozen=True, slots=True)
class MaterialReadReplay:
    """All exact, store-replayed inputs for one material-read assignment."""

    payload: CanonicalReadInput
    captured: CapturedDocumentValue
    expected_material: MaterialRef
    expected_material_value_ref: ValueRef


def _atoms(node: ProgramNode) -> tuple[Atom, ...]:
    if isinstance(node, Atom):
        return (node,)
    if isinstance(node, Then):
        return _atoms(node.first) + _atoms(node.second)
    if isinstance(node, MapOutput):
        return _atoms(node.source)
    if isinstance(node, ZipOrdered):
        return _atoms(node.left) + _atoms(node.right)
    if isinstance(node, TraverseOrdered):
        return _atoms(node.element_program)
    if isinstance(node, Decide):
        return tuple(
            atom for branch in node.branches for atom in _atoms(branch.program)
        )
    return ()


def _exact_atom(program: Any, operation_id: str) -> Atom:
    matches = tuple(
        atom
        for atom in _atoms(program.root)
        if atom.operation.operation_id == operation_id
    )
    if len(matches) != 1:
        raise CapturedValueReplayError(
            "Program must contain exactly one atom for the claimed operation"
        )
    return matches[0]


def _value_ref_by_storage(program: Any, storage_ref: str) -> ValueRef:
    refs: list[ValueRef] = []
    for atom in _atoms(program.root):
        refs.extend(atom.operation.input_refs)
        refs.append(atom.operation.payload_ref)
    matches = tuple(ref for ref in refs if ref.storage_ref == storage_ref)
    if not matches:
        raise CapturedValueReplayError(
            f"Program does not bind project value {storage_ref!r}"
        )
    first = matches[0]
    if any(ref != first for ref in matches[1:]):
        raise CapturedValueReplayError(
            f"Program contains conflicting ValueRefs for {storage_ref!r}"
        )
    return first


def _value_id(ref: ValueRef) -> str:
    prefix = "project-value:"
    if (
        ref.storage_kind != "project_value_ref"
        or ref.store_id != "successor_values"
        or ref.store_version != "1"
        or not ref.storage_ref.startswith(prefix)
    ):
        raise CapturedValueReplayError(
            "runtime input is not an exact project value ref"
        )
    value_id = ref.storage_ref[len(prefix) :]
    if not value_id or value_id != ref.value_id:
        raise CapturedValueReplayError("project value locator/value_id drift")
    return value_id


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise CapturedValueReplayError(f"{field} must be an ISO datetime string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CapturedValueReplayError(f"{field} must be timezone-aware")
    return parsed


def _source_ref(exact: bytes) -> SourceRef:
    try:
        value = json.loads(exact)
        source = SourceRef(
            source_ref_id=value["source_ref_id"],
            owner_id=value["owner_id"],
            locator=value["locator"],
            source_class=value["source_class"],
            observed_at=_datetime(value["observed_at"], "SourceRef.observed_at"),
            access_profile_ref=value["access_profile_ref"],
            content_digest=value["content_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CapturedValueReplayError("stored SourceRef is malformed") from exc
    if canonical_bytes(source) != exact:
        raise CapturedValueReplayError("stored SourceRef bytes are not canonical")
    return source


def _material_ref(exact: bytes) -> MaterialRef:
    try:
        value = json.loads(exact)
        snapshot_value = value["snapshot"]
        snapshot = CapturedMaterialSnapshot(
            value_ref=snapshot_value["value_ref"],
            document_id=snapshot_value["document_id"],
            observed_text_hash=snapshot_value["observed_text_hash"],
            observed_updated_at=_datetime(
                snapshot_value["observed_updated_at"],
                "CapturedMaterialSnapshot.observed_updated_at",
            ),
            byte_size=snapshot_value["byte_size"],
            content_digest=snapshot_value["content_digest"],
        )
        material = MaterialRef(
            material_ref_id=value["material_ref_id"],
            source_ref=value["source_ref"],
            snapshot=snapshot,
            content_digest=value["content_digest"],
            provenance_digest=value["provenance_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CapturedValueReplayError("stored MaterialRef is malformed") from exc
    if canonical_bytes(material) != exact:
        raise CapturedValueReplayError("stored MaterialRef bytes are not canonical")
    return material


def canonical_read_payload_from_source(source: SourceRef) -> CanonicalReadInput:
    """Build the capability DTO with its authoritative (Unicode-safe) digest."""

    payload_values = {
        "source_ref": source.source_ref_id,
        "locator": source.locator,
        "owner_id": source.owner_id,
        "observed_at": source.observed_at.isoformat(),
    }
    return CanonicalReadInput(
        **payload_values,
        payload_digest=content_digest(payload_values),
    )


class PostgresCapturedValueReplayAdapter:
    """Resolve exact runtime material inputs without re-reading a Document."""

    def __init__(
        self,
        uow_factory: ReadUnitOfWorkFactory,
        activation_bindings: CapturedActivationBindingPort | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._activation_bindings = activation_bindings

    def load_material_read(
        self,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> MaterialReadReplay:
        if (
            assignment.assignment_kind is not AssignmentKind.INTERPRET
            or assignment.operation_contract_ref is None
            or assignment.operation_contract_ref.kind != MATERIAL_READ_OPERATION_KIND
            or assignment.step_id is None
            or assignment.plan_digest is None
        ):
            raise CapturedValueReplayError(
                "captured-value adapter only accepts exact material-read assignments"
            )

        with self._uow_factory() as uow:
            connection = uow.connection
            run = one_mapping(
                connection.execute(
                    select(PUBLIC_TABLES["runtime_runs"]).where(
                        PUBLIC_TABLES["runtime_runs"].c.project_key
                        == assignment.project_key,
                        PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                    )
                )
            )
            if run is None:
                raise CapturedValueReplayError("assignment run is absent")
            if (
                run["program_digest"] != assignment.program_digest
                or run["plan_digest"] != assignment.plan_digest
                or run["incarnation"] != assignment.incarnation
            ):
                raise CapturedValueReplayError(
                    "assignment run/program/plan identity drift"
                )

            resolver = ServerProjectScopeResolver(connection=connection)
            expected_scope = resolver.resolve_expected(
                assignment.project_key,
                int(run["project_registry_revision"]),
                str(run["project_scope_digest"]),
            )
            if isinstance(expected_scope, ProjectScopeStale):
                raise CapturedValueReplayError("assignment project scope is stale")
            if resolver.resolve(assignment.project_key) != expected_scope:
                raise CapturedValueReplayError(
                    "assignment project scope is no longer current"
                )
            scope = RuntimeScope(project_scope=expected_scope, actor_id=actor_id)
            tables = project_tables(MetaData(), expected_scope.resolved_schema)

            program = ProgramRepository(connection, tables).get(
                scope,
                str(run["program_id"]),
                expected_digest=assignment.program_digest,
            )
            plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
            steps = tuple(
                step
                for step in plan.ordered_steps
                if step.step_id == assignment.step_id
            )
            if len(steps) != 1 or steps[0].operation_id is None:
                raise CapturedValueReplayError(
                    "plan does not contain the exact claimed step"
                )
            step = steps[0]
            if (
                step.operation_contract_ref != assignment.operation_contract_ref
                or step.operation_contract_ref.contract_digest
                != assignment.operation_contract_digest
            ):
                raise CapturedValueReplayError(
                    "plan/assignment operation contract drift"
                )

            atom = _exact_atom(program, step.operation_id)
            if atom.operation.contract_ref != assignment.operation_contract_ref:
                raise CapturedValueReplayError(
                    "Program/assignment operation contract drift"
                )
            static_refs = atom.operation.input_refs
            static_locators = tuple(ref.storage_ref for ref in static_refs)
            if (
                not static_locators
                or assignment.input_refs[-len(static_locators) :] != static_locators
            ):
                raise CapturedValueReplayError(
                    "assignment does not preserve the Program static input suffix"
                )
            dynamic_locators = assignment.input_refs[: -len(static_locators)]
            if dynamic_locators:
                if self._activation_bindings is None:
                    raise CapturedValueReplayError(
                        "dynamic material input requires exact activation binding"
                    )
                descriptor = self._activation_bindings.load_exact(
                    connection, assignment, scope, tables
                )
                if (
                    tuple(
                        ref.storage_ref for ref in descriptor.ordered_input_refs
                    )
                    != assignment.input_refs
                    or descriptor.input_closure_digest
                    != assignment.input_closure_digest
                    or descriptor.payload_ref != atom.operation.payload_ref
                ):
                    raise CapturedValueReplayError(
                        "material activation descriptor drift"
                    )
            elif assignment.input_closure_digest != canonical_digest(static_locators):
                raise CapturedValueReplayError("assignment input closure digest drift")
            if len(atom.operation.input_refs) != 1:
                raise CapturedValueReplayError(
                    "material read requires exactly one input ref"
                )

            snapshot_ref = atom.operation.input_refs[0]
            if dynamic_locators and any(
                locator != snapshot_ref.storage_ref for locator in dynamic_locators
            ):
                raise CapturedValueReplayError(
                    "material dependency output differs from exact snapshot input"
                )
            if snapshot_ref.object_type.type_id != CAPTURED_SNAPSHOT_TYPE:
                raise CapturedValueReplayError(
                    "material read input is not a captured snapshot"
                )
            snapshot_exact, snapshot_provenance = self._read_value(
                connection, tables, scope, snapshot_ref
            )
            captured = self._captured(snapshot_ref, snapshot_exact, snapshot_provenance)

            source_storage_ref = f"project-value:{snapshot_provenance['source_ref']}"
            source_ref = _value_ref_by_storage(program, source_storage_ref)
            if source_ref.object_type.type_id != SOURCE_REF_TYPE:
                raise CapturedValueReplayError(
                    "captured source is not an exact SourceRef"
                )
            source_exact, _ = self._read_value(connection, tables, scope, source_ref)
            source = _source_ref(source_exact)

            payload_ref = atom.operation.payload_ref
            codec = build_first_specimen_bundle().codec_by_kind(
                MATERIAL_READ_OPERATION_KIND
            )
            if (
                payload_ref.object_type.type_id != codec.payload_type_id
                or payload_ref.codec_id != codec.codec_id
            ):
                raise CapturedValueReplayError(
                    "material read payload is not CanonicalReadInput"
                )
            payload_exact, payload_provenance = self._read_value(
                connection, tables, scope, payload_ref
            )
            if (
                payload_provenance.get("operation_kind")
                != MATERIAL_READ_OPERATION_KIND
                or payload_provenance.get("codec_digest") != codec.codec_digest
            ):
                raise CapturedValueReplayError(
                    "material read typed payload provenance drift"
                )
            try:
                payload_json = json.loads(payload_exact)
                payload = codec.decode_payload(payload_json)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CapturedValueReplayError(
                    "material read typed payload is malformed"
                ) from exc
            if (
                not isinstance(payload, CanonicalReadInput)
                or canonical_bytes(codec.encode_payload(payload)) != payload_exact
                or payload != canonical_read_payload_from_source(source)
            ):
                raise CapturedValueReplayError(
                    "material read payload/source exact binding drift"
                )

            derived_material = derive_material_ref(
                source_ref=source.source_ref_id,
                snapshot=captured.snapshot,
                owner_id=source.owner_id,
                locator=source.locator,
                observed_at=source.observed_at.isoformat(),
            )
            material_storage_ref = f"project-value:{derived_material.material_ref_id}"
            material_ref = _value_ref_by_storage(program, material_storage_ref)
            if material_ref.object_type.type_id != MATERIAL_REF_TYPE:
                raise CapturedValueReplayError(
                    "Program does not bind the derived MaterialRef"
                )
            material_exact, _ = self._read_value(
                connection, tables, scope, material_ref
            )
            expected_material = _material_ref(material_exact)
            if (
                expected_material != derived_material
            ):
                raise CapturedValueReplayError(
                    "captured input/source do not derive the exact Program material"
                )
            return MaterialReadReplay(
                payload=payload,
                captured=captured,
                expected_material=expected_material,
                expected_material_value_ref=material_ref,
            )

    def publish_material_result(
        self,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
        replay: MaterialReadReplay,
    ) -> None:
        """Publish an opaque runtime alias for the exact project MaterialRef."""

        ref = replay.expected_material_value_ref
        with self._uow_factory() as uow:
            connection = uow.connection
            run = one_mapping(
                connection.execute(
                    select(PUBLIC_TABLES["runtime_runs"]).where(
                        PUBLIC_TABLES["runtime_runs"].c.project_key
                        == assignment.project_key,
                        PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                    )
                )
            )
            if run is None:
                raise CapturedValueReplayError("material result run is absent")
            resolver = ServerProjectScopeResolver(connection=connection)
            scope_ref = resolver.resolve_expected(
                assignment.project_key,
                int(run["project_registry_revision"]),
                str(run["project_scope_digest"]),
            )
            if isinstance(scope_ref, ProjectScopeStale):
                raise CapturedValueReplayError("material result scope is stale")
            scope = RuntimeScope(project_scope=scope_ref, actor_id=actor_id)
            tables = project_tables(MetaData(), scope_ref.resolved_schema)
            row = one_mapping(
                connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key == assignment.project_key,
                        tables.successor_values.c.value_id == ref.value_id,
                        tables.successor_values.c.content_digest == ref.content_digest,
                        tables.successor_values.c.codec_id == ref.codec_id,
                        tables.successor_values.c.state == "AVAILABLE",
                    )
                )
            )
            if row is None or int(row["revision"]) != 1:
                raise CapturedValueReplayError("exact project MaterialRef is absent")
            runtime_value_id = (
                f"result:{assignment.run_id}:{assignment.step_id}:"
                f"epoch-{assignment.execution_epoch}"
            )
            storage_digest = canonical_digest(
                {
                    "contract": "MaterialReadRuntimeValueBinding.v1",
                    "assignment_digest": assignment.assignment_digest,
                    "handler_binding_digest": assignment.handler_binding_digest,
                    "input_closure_digest": assignment.input_closure_digest,
                    "project_value_ref": ref.storage_ref,
                    "content_digest": ref.content_digest,
                }
            )
            RuntimeValueRepository(connection, scope).put_exact(
                RuntimeValueBinding(
                    value_id=runtime_value_id,
                    object_type=ref.object_type.type_id,
                    codec_id=ref.codec_id,
                    content_digest=ref.content_digest,
                    byte_size=ref.byte_size,
                    project_value_ref=ref.storage_ref,
                    storage_digest=storage_digest,
                    write_intent_digest=str(row["write_intent_digest"]),
                )
            )
            uow.commit()

    @staticmethod
    def _read_value(
        connection: Any,
        tables: Any,
        scope: RuntimeScope,
        ref: ValueRef,
    ) -> tuple[bytes, dict[str, Any]]:
        value_id = _value_id(ref)
        table = tables.successor_values
        row = one_mapping(
            connection.execute(
                select(table).where(
                    table.c.project_key == scope.project_scope.project_key,
                    table.c.value_id == value_id,
                )
            )
        )
        if row is None:
            raise CapturedValueReplayError(f"exact project value is absent: {value_id}")
        if row["content_bytes"] is None or row["content_json"] is not None:
            raise CapturedValueReplayError(
                "runtime value must contain exact bytes only"
            )
        exact = bytes(row["content_bytes"])
        provenance = dict(row["provenance_json"])
        submission_id = provenance.get("submission_id")
        expected_incarnation = (
            f"p0c:{submission_id}:{value_id}"
            if isinstance(submission_id, str) and submission_id
            else None
        )
        expected = {
            "project_key": ref.project_key,
            "value_id": ref.value_id,
            "object_type": ref.object_type.type_id,
            "codec_id": ref.codec_id,
            "content_digest": ref.content_digest,
            "byte_size": ref.byte_size,
            "provenance_digest": ref.provenance_digest,
            "state": "AVAILABLE",
            "revision": 1,
            "incarnation": expected_incarnation,
        }
        if any(row[key] != value for key, value in expected.items()):
            raise CapturedValueReplayError(
                f"project value identity/revision/incarnation/codec drift: {value_id}"
            )
        if scope.project_scope.project_key != ref.project_key:
            raise CapturedValueReplayError("project value crosses the assignment scope")
        if hashlib.sha256(exact).hexdigest() != ref.content_digest:
            raise CapturedValueReplayError("project value content digest drift")
        if len(exact) != ref.byte_size:
            raise CapturedValueReplayError("project value byte size drift")
        if sha256_hex(provenance) != ref.provenance_digest:
            raise CapturedValueReplayError("project value provenance digest drift")
        return exact, provenance

    @staticmethod
    def _captured(
        ref: ValueRef,
        exact: bytes,
        provenance: dict[str, Any],
    ) -> CapturedDocumentValue:
        try:
            document_id = provenance["document_id"]
            source_ref = provenance["source_ref"]
            observed_text_hash = provenance["observed_text_hash"]
            observed_updated_at = _datetime(
                provenance["observed_updated_at"],
                "CapturedMaterialSnapshot.observed_updated_at",
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CapturedValueReplayError(
                "captured-value provenance is malformed"
            ) from exc
        if not isinstance(document_id, int) or isinstance(document_id, bool):
            raise CapturedValueReplayError("captured document identity is malformed")
        if not isinstance(source_ref, str) or not source_ref:
            raise CapturedValueReplayError("captured source_ref is malformed")
        if observed_text_hash is not None and not isinstance(observed_text_hash, str):
            raise CapturedValueReplayError("captured observed_text_hash is malformed")
        snapshot = CapturedMaterialSnapshot(
            value_ref=ref.storage_ref,
            document_id=document_id,
            observed_text_hash=observed_text_hash,
            observed_updated_at=observed_updated_at,
            byte_size=len(exact),
        )
        return CapturedDocumentValue(
            exact_bytes=exact,
            snapshot=snapshot,
            exact_bytes_digest=ref.content_digest,
        )


__all__ = [
    "CapturedValueReplayError",
    "MaterialReadReplay",
    "PostgresCapturedValueReplayAdapter",
    "canonical_read_payload_from_source",
]
