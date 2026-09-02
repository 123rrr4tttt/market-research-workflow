"""Exact PostgreSQL effect handlers for first-specimen semantic operations.

The handlers in this module are deliberately narrower than the production
composition root.  They realize one already-claimed ``INTERPRET`` assignment,
replay its exact typed payload and ordered inputs from project
``successor_values``, call the capability-owned semantic interpreters, and
atomically publish only non-canonical runtime outputs:

* exact bytes remain in the project ``successor_values`` owner;
* ``runtime_values`` contains only an opaque project-value locator;
* admission-required results are ``runtime_staged_artifacts`` candidates;
* the Research Ledger is never mutated here.

Submission is the sole legacy Document read boundary.  Capture therefore finds
and validates the submission-frozen snapshot in ``successor_values`` by its
exact digest and never imports or invokes a Document adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.first_specimen import (
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    MarkdownComposeInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    ClaimOrGapOutput,
    FirstSpecimenInterpreters,
    InterpreterFailure,
    InterpreterSuccess,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    MapOutput,
    ProgramNode,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from app.successor_runtime.research import (
    CapturedMaterialSnapshot,
    Claim,
    EvidenceQualification,
    Gap,
    MaterialRef,
    ResearchArtifact,
)
from app.successor_runtime.research.codec import (
    canonical_bytes,
    dataclass_to_json,
    sha256_hex,
)
from app.successor_runtime.research.evidence import Validity
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    CLAIM_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
    SOURCE_REF_TYPE,
    ObjectType,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.activation import ReadyActivation
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .models import PUBLIC_TABLES, ProjectTables, project_tables
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import (
    one_mapping,
)
from .runtime_values import RuntimeValueBinding, RuntimeValueRepository
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .staged_artifacts import StagedArtifactBinding, StagedArtifactRepository
from .values import ValueRepository

CAPTURE_OPERATION = "material.capture_document_snapshot.v1"
QUALIFY_OPERATION = "evidence.qualify.v1"
CLAIM_OPERATION = "claim.form_or_open_gap.v1"
ARTIFACT_OPERATION = "artifact.compose_markdown.v1"

SUPPORTED_SEMANTIC_OPERATIONS = frozenset(
    {CAPTURE_OPERATION, QUALIFY_OPERATION, CLAIM_OPERATION, ARTIFACT_OPERATION}
)


class FirstSpecimenHandlerError(RuntimeError):
    """An exact semantic handler cannot safely adopt or create its output."""


class FirstSpecimenReplayDrift(FirstSpecimenHandlerError):
    """Program, Plan, typed payload, ordered inputs, or scope drifted."""


class FirstSpecimenOutputDrift(FirstSpecimenHandlerError):
    """An existing output does not bind the exact assignment and attempt."""


@dataclass(frozen=True, slots=True)
class InstalledFirstSpecimenEffectHandler:
    """Immutable installed realization for one exact operation contract."""

    operation_kind: str
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    payload_codec_id: str
    payload_codec_digest: str
    admission_required: bool

    def __post_init__(self) -> None:
        if self.operation_kind not in SUPPORTED_SEMANTIC_OPERATIONS:
            raise ValueError("unsupported first-specimen semantic operation")
        for field_name in (
            "handler_binding_digest",
            "interpreter_profile_digest",
            "operation_contract_digest",
            "payload_codec_digest",
        ):
            require_digest(getattr(self, field_name), field_name)
        bundle = build_first_specimen_bundle()
        operation = bundle.operation_by_kind(self.operation_kind)
        codec = bundle.codec_by_kind(self.operation_kind)
        if operation.ref.contract_digest != self.operation_contract_digest:
            raise ValueError("installed operation contract digest drift")
        if codec.codec_id != self.payload_codec_id:
            raise ValueError("installed payload codec id drift")
        if codec.codec_digest != self.payload_codec_digest:
            raise ValueError("installed payload codec digest drift")
        returns = build_first_specimen_return_contract_registry().resolve(
            operation.return_contract_ref
        )
        if returns is None:  # pragma: no cover - frozen catalog construction error
            raise ValueError("installed return contract is absent")
        if returns.admission_required != self.admission_required:
            raise ValueError("installed return admission requirement drift")

    @classmethod
    def bind(
        cls,
        *,
        operation_kind: str,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
    ) -> InstalledFirstSpecimenEffectHandler:
        bundle = build_first_specimen_bundle()
        operation = bundle.operation_by_kind(operation_kind)
        codec = bundle.codec_by_kind(operation_kind)
        return cls(
            operation_kind=operation_kind,
            handler_binding_digest=handler_binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            operation_contract_digest=operation.ref.contract_digest,
            payload_codec_id=codec.codec_id,
            payload_codec_digest=codec.codec_digest,
            admission_required=(
                build_first_specimen_return_contract_registry()
                .resolve(operation.return_contract_ref)
                .admission_required
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplayedProjectValue:
    """One exact project ValueRef plus authoritative stored bytes/provenance."""

    ref: ValueRef
    exact_bytes: bytes
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FirstSpecimenEffectReplay:
    """All exact values needed to run one semantic interpreter once."""

    scope: RuntimeScope
    tables: ProjectTables
    payload: object
    payload_value: ReplayedProjectValue
    inputs: tuple[ReplayedProjectValue, ...]


class FirstSpecimenHandlerUnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class FirstSpecimenHandlerUnitOfWorkFactory(Protocol):
    def __call__(self) -> FirstSpecimenHandlerUnitOfWork: ...


class FirstSpecimenEffectReplayPort(Protocol):
    """Resolve scope first, then replay upstream values only if no output exists."""

    def resolve_scope(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> tuple[RuntimeScope, ProjectTables]: ...

    def load_exact(
        self,
        connection: Connection,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> FirstSpecimenEffectReplay: ...


class FirstSpecimenActivationBindingPort(Protocol):
    """Load the exact persisted ReadyActivation for dynamic dependencies."""

    def load_exact(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> ReadyActivation: ...


class FirstSpecimenEffectOutputPort(Protocol):
    """Execute or exact-readback one claimed semantic effect."""

    def execute_exact(
        self,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome: ...


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


def _value_id(ref: ValueRef) -> str:
    prefix = "project-value:"
    if (
        ref.storage_kind != "project_value_ref"
        or ref.store_id != "successor_values"
        or ref.store_version != "1"
        or not ref.storage_ref.startswith(prefix)
    ):
        raise FirstSpecimenReplayDrift("runtime value is not a project successor value")
    value_id = ref.storage_ref.removeprefix(prefix)
    if not value_id or value_id != ref.value_id:
        raise FirstSpecimenReplayDrift("project value locator/value_id drift")
    return value_id


class PostgresFirstSpecimenEffectReplay:
    """Re-open exact Program/Plan/ValueRef closure on the handler UoW."""

    def __init__(
        self,
        activation_bindings: FirstSpecimenActivationBindingPort | None = None,
    ) -> None:
        self._activation_bindings = activation_bindings

    def resolve_scope(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> tuple[RuntimeScope, ProjectTables]:
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
            raise FirstSpecimenReplayDrift("assignment run is absent")
        if (
            run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or run["incarnation"] != assignment.incarnation
        ):
            raise FirstSpecimenReplayDrift("assignment run/program/plan identity drift")
        resolver = ServerProjectScopeResolver(connection=connection)
        expected = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(expected, ProjectScopeStale):
            raise FirstSpecimenReplayDrift("assignment project scope is stale")
        if resolver.resolve(assignment.project_key) != expected:
            raise FirstSpecimenReplayDrift("assignment project scope is no longer current")
        scope = RuntimeScope(project_scope=expected, actor_id=actor_id)
        return scope, project_tables(MetaData(), expected.resolved_schema)

    def load_exact(
        self,
        connection: Connection,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> FirstSpecimenEffectReplay:
        runs = PUBLIC_TABLES["runtime_runs"]
        run = one_mapping(
            connection.execute(
                select(runs).where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
            )
        )
        assert run is not None
        program = ProgramRepository(connection, tables).get(
            scope,
            str(run["program_id"]),
            expected_digest=assignment.program_digest,
        )
        if assignment.plan_digest is None or assignment.step_id is None:
            raise FirstSpecimenReplayDrift("semantic assignment lacks Plan/step identity")
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        steps = tuple(
            step for step in plan.ordered_steps if step.step_id == assignment.step_id
        )
        if len(steps) != 1 or steps[0].operation_id is None:
            raise FirstSpecimenReplayDrift("Plan lacks one exact claimed operation")
        step = steps[0]
        if (
            step.operation_contract_ref != assignment.operation_contract_ref
            or step.operation_contract_ref is None
            or step.operation_contract_ref.contract_digest
            != assignment.operation_contract_digest
        ):
            raise FirstSpecimenReplayDrift("Plan/assignment operation contract drift")
        atoms = tuple(
            atom
            for atom in _atoms(program.root)
            if atom.operation.operation_id == step.operation_id
        )
        if len(atoms) != 1:
            raise FirstSpecimenReplayDrift("Program lacks one exact claimed Atom")
        atom = atoms[0]
        static_refs = atom.operation.input_refs
        static_locators = tuple(ref.storage_ref for ref in static_refs)
        if not static_locators or assignment.input_refs[-len(static_locators) :] != (
            static_locators
        ):
            raise FirstSpecimenReplayDrift(
                "assignment does not preserve the Program static input suffix"
            )
        dynamic_locators = assignment.input_refs[: -len(static_locators)]
        descriptor = None
        if dynamic_locators:
            if self._activation_bindings is None:
                raise FirstSpecimenReplayDrift(
                    "dynamic inputs require an exact persisted ReadyActivation binding"
                )
            descriptor = self._activation_bindings.load_exact(
                connection,
                assignment,
                scope,
                tables,
            )
        ordered_refs = require_exact_activation_binding(
            assignment=assignment,
            plan_digest=plan.plan_digest,
            step_kind=step.step_kind,
            operation_id=step.operation_id,
            operation_contract_digest=step.operation_contract_ref.contract_digest,
            static_refs=static_refs,
            payload_ref=atom.operation.payload_ref,
            descriptor=descriptor,
        )
        if atom.operation.payload_ref.storage_ref != assignment.payload_ref:
            raise FirstSpecimenReplayDrift("assignment payload ref differs from Program")
        if atom.operation.payload_ref.content_digest != assignment.payload_digest:
            raise FirstSpecimenReplayDrift("assignment payload digest differs from Program")
        if atom.operation.contract_ref.kind != installation.operation_kind:
            raise FirstSpecimenReplayDrift("Program Atom operation kind drift")

        payload_value = self._read_value(
            connection, tables, scope, atom.operation.payload_ref
        )
        payload = self._decode_payload(installation, payload_value)
        inputs = tuple(
            self._read_value(connection, tables, scope, ref) for ref in ordered_refs
        )
        return FirstSpecimenEffectReplay(
            scope=scope,
            tables=tables,
            payload=payload,
            payload_value=payload_value,
            inputs=inputs,
        )

    @staticmethod
    def _read_value(
        connection: Connection,
        tables: ProjectTables,
        scope: RuntimeScope,
        ref: ValueRef,
    ) -> ReplayedProjectValue:
        value_id = _value_id(ref)
        row = one_mapping(
            connection.execute(
                select(tables.successor_values).where(
                    tables.successor_values.c.project_key == assignment_project(scope),
                    tables.successor_values.c.value_id == value_id,
                )
            )
        )
        if row is None:
            raise FirstSpecimenReplayDrift(f"project value is absent: {value_id}")
        if row["content_bytes"] is None or row["content_json"] is not None:
            raise FirstSpecimenReplayDrift("runtime input must contain exact bytes only")
        exact = bytes(row["content_bytes"])
        provenance = dict(row["provenance_json"])
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
        }
        if any(row[key] != value for key, value in expected.items()):
            raise FirstSpecimenReplayDrift(f"project ValueRef drift: {value_id}")
        if assignment_project(scope) != ref.project_key:
            raise FirstSpecimenReplayDrift("project ValueRef crosses assignment scope")
        if hashlib.sha256(exact).hexdigest() != ref.content_digest:
            raise FirstSpecimenReplayDrift("project value content digest drift")
        if len(exact) != ref.byte_size:
            raise FirstSpecimenReplayDrift("project value byte size drift")
        if sha256_hex(provenance) != ref.provenance_digest:
            raise FirstSpecimenReplayDrift("project value provenance digest drift")
        return ReplayedProjectValue(ref, exact, provenance)

    @staticmethod
    def _decode_payload(
        installation: InstalledFirstSpecimenEffectHandler,
        value: ReplayedProjectValue,
    ) -> object:
        bundle = build_first_specimen_bundle()
        codec = bundle.codec_by_kind(installation.operation_kind)
        if (
            value.ref.codec_id != installation.payload_codec_id
            or value.ref.object_type.type_id != codec.payload_type_id
            or value.provenance.get("codec_id") != installation.payload_codec_id
            or value.provenance.get("codec_digest") != installation.payload_codec_digest
            or value.provenance.get("operation_kind") != installation.operation_kind
        ):
            raise FirstSpecimenReplayDrift("typed payload codec/operation binding drift")
        try:
            decoded_json = json.loads(value.exact_bytes)
            if not isinstance(decoded_json, dict):
                raise TypeError("payload root is not an object")
            payload = codec.decode_payload(decoded_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FirstSpecimenReplayDrift("typed payload bytes are malformed") from exc
        if canonical_bytes(codec.encode_payload(payload)) != value.exact_bytes:
            raise FirstSpecimenReplayDrift("typed payload codec round-trip drift")
        # Payload self-digest binds semantic fields while ValueRef binds the
        # encoded bytes.  They are intentionally distinct identities.
        if (
            getattr(payload, "payload_digest", None) != value.ref.content_digest
            and getattr(payload, "payload_digest", None)
            != assignment_payload_digest(payload)
        ):
            raise FirstSpecimenReplayDrift("typed payload semantic digest drift")
        return payload


def assignment_project(scope: RuntimeScope) -> str:
    return scope.project_scope.project_key


def assignment_payload_digest(payload: object) -> str:
    from app.successor_runtime.capabilities.checksum import content_digest

    return content_digest(payload, omit_fields=("payload_digest",))


def _activation_closure(
    *,
    plan_digest: str,
    step_id: str,
    step_kind: str,
    dynamic_refs: tuple[ValueRef, ...],
    static_refs: tuple[ValueRef, ...],
    payload_ref: ValueRef,
) -> dict[str, object]:
    return {
        "schema_version": "mrw.activation-input-closure.v1",
        "plan_digest": plan_digest,
        "step_id": step_id,
        "step_kind": step_kind,
        "ordered_dependency_refs": tuple(ref.to_plain() for ref in dynamic_refs),
        "static_atom_input_refs": tuple(ref.to_plain() for ref in static_refs),
        "payload_ref": payload_ref.to_plain(),
    }


def require_exact_activation_binding(
    *,
    assignment: RuntimeAssignment,
    plan_digest: str,
    step_kind: str,
    operation_id: str,
    operation_contract_digest: str,
    static_refs: tuple[ValueRef, ...],
    payload_ref: ValueRef,
    descriptor: ReadyActivation | None,
) -> tuple[ValueRef, ...]:
    """Validate dynamic-prefix/static-suffix order and activation digests.

    ``RuntimeAssignment`` intentionally carries only bounded opaque locators.
    Therefore a dynamic dependency cannot be reconstructed from the public row
    without losing its original ValueRef store/provenance identity.  Callers
    must inject the exact persisted ``ReadyActivation``.  Static-only Atoms are
    fully reconstructible from Program+Plan and need no extra store.
    """

    if assignment.step_id is None:
        raise FirstSpecimenReplayDrift("activation binding requires step_id")
    static_locators = tuple(ref.storage_ref for ref in static_refs)
    if not static_locators or assignment.input_refs[-len(static_locators) :] != (
        static_locators
    ):
        raise FirstSpecimenReplayDrift("activation static input suffix drift")
    dynamic_locators = assignment.input_refs[: -len(static_locators)]
    if dynamic_locators:
        if descriptor is None:
            raise FirstSpecimenReplayDrift(
                "dynamic inputs require exact ReadyActivation descriptor"
            )
        if (
            descriptor.step_id != assignment.step_id
            or descriptor.step_kind != step_kind
            or descriptor.operation_id != operation_id
            or descriptor.static_atom_input_refs != static_refs
            or descriptor.payload_ref != payload_ref
            or tuple(ref.storage_ref for ref in descriptor.ordered_dependency_refs)
            != dynamic_locators
            or descriptor.ordered_input_refs
            != descriptor.ordered_dependency_refs + static_refs
        ):
            raise FirstSpecimenReplayDrift("ReadyActivation exact binding drift")
        dynamic_refs = descriptor.ordered_dependency_refs
    else:
        if descriptor is not None and descriptor.ordered_dependency_refs:
            raise FirstSpecimenReplayDrift("static assignment received dynamic descriptor")
        dynamic_refs = ()
    closure = _activation_closure(
        plan_digest=plan_digest,
        step_id=assignment.step_id,
        step_kind=step_kind,
        dynamic_refs=dynamic_refs,
        static_refs=static_refs,
        payload_ref=payload_ref,
    )
    closure_digest = sha256_hex(closure)
    if assignment.input_closure_digest != closure_digest:
        raise FirstSpecimenReplayDrift("activation input closure digest drift")
    if descriptor is not None:
        descriptor_payload = {
            **closure,
            "operation_id": operation_id,
            "operation_contract_digest": operation_contract_digest,
            "input_closure_digest": closure_digest,
        }
        if (
            descriptor.input_closure_digest != closure_digest
            or descriptor.activation_digest != sha256_hex(descriptor_payload)
        ):
            raise FirstSpecimenReplayDrift("ReadyActivation descriptor digest drift")
    return dynamic_refs + static_refs


def _result_value_id(assignment: RuntimeAssignment) -> str:
    assert assignment.step_id is not None
    return (
        f"result:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _result_incarnation(assignment: RuntimeAssignment) -> str:
    assert assignment.step_id is not None
    return (
        f"result:{assignment.incarnation}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _stage_id(assignment: RuntimeAssignment) -> str:
    assert assignment.step_id is not None
    return (
        f"stage:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _output_binding_provenance(
    installation: InstalledFirstSpecimenEffectHandler,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> dict[str, object]:
    return {
        "contract": "FirstSpecimenEffectOutput.v1",
        "operation_kind": installation.operation_kind,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "assignment_digest": assignment.assignment_digest,
        "attempt_id": claim.attempt_id,
        "handler_binding_digest": installation.handler_binding_digest,
        "interpreter_profile_digest": installation.interpreter_profile_digest,
        "operation_contract_digest": installation.operation_contract_digest,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "ordered_input_refs": list(assignment.input_refs),
        "input_closure_digest": assignment.input_closure_digest,
        "admission_required": installation.admission_required,
    }


def _runtime_storage_digest(
    *,
    installation: InstalledFirstSpecimenEffectHandler,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    runtime_value_id: str,
    project_value_ref: str,
    content_digest: str,
    codec_id: str,
) -> str:
    return canonical_digest(
        {
            "contract": "ProjectRuntimeValueBinding.v1",
            "project_key": assignment.project_key,
            "runtime_value_id": runtime_value_id,
            "project_value_ref": project_value_ref,
            "content_digest": content_digest,
            "codec_id": codec_id,
            "assignment_digest": assignment.assignment_digest,
            "attempt_id": claim.attempt_id,
            "handler_binding_digest": installation.handler_binding_digest,
        }
    )


@dataclass(frozen=True, slots=True)
class _EffectProduct:
    object_type: ObjectType
    exact_bytes: bytes
    content_digest: str
    source_ref: str | None
    provenance: dict[str, object]
    existing_project_value_id: str | None = None
    existing_project_incarnation: str | None = None
    artifact_exact_bytes: bytes | None = None


class FirstSpecimenEffectOutputStore:
    """Atomic exact-readback/interpret/project+public+stage output boundary."""

    def __init__(
        self,
        uow_factory: FirstSpecimenHandlerUnitOfWorkFactory,
        *,
        replay: FirstSpecimenEffectReplayPort | None = None,
        interpreters: FirstSpecimenInterpreters | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._replay = replay or PostgresFirstSpecimenEffectReplay()
        self._interpreters = interpreters or FirstSpecimenInterpreters()

    def execute_exact(
        self,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _require_exact_handler(installation, assignment, claim)
        with self._uow_factory() as uow:
            scope, tables = self._replay.resolve_scope(
                uow.connection,
                assignment,
                actor_id=context.node.node_id,
            )
            readback = self._readback(
                uow.connection,
                scope,
                tables,
                installation,
                assignment,
                claim,
            )
            if readback is not None:
                uow.commit()
                return InterpreterOutcome.succeeded(readback)
            replay = self._replay.load_exact(
                uow.connection,
                installation,
                assignment,
                scope,
                tables,
            )
            product = self._interpret(
                uow.connection,
                installation,
                assignment,
                claim,
                replay,
            )
            result = self._persist(
                uow.connection,
                scope,
                tables,
                installation,
                assignment,
                claim,
                product,
            )
            uow.commit()
            return InterpreterOutcome.succeeded(result)

    def _readback(
        self,
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> str | None:
        value_id = _result_value_id(assignment)
        public = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_values"]).where(
                    PUBLIC_TABLES["runtime_values"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_values"].c.value_id == value_id,
                )
            )
        )
        if public is None:
            return None
        project_ref = public["project_value_ref"]
        if not isinstance(project_ref, str) or not project_ref.startswith(
            "project-value:"
        ):
            raise FirstSpecimenOutputDrift("runtime output owner ref drift")
        project_value_id = project_ref.removeprefix("project-value:")
        row = one_mapping(
            connection.execute(
                select(tables.successor_values).where(
                    tables.successor_values.c.project_key == assignment.project_key,
                    tables.successor_values.c.value_id == project_value_id,
                )
            )
        )
        if row is None or row["state"] != "AVAILABLE":
            raise FirstSpecimenOutputDrift("project output readback is absent/unavailable")
        provenance = dict(row["provenance_json"])
        if installation.operation_kind != CAPTURE_OPERATION:
            expected_provenance = _output_binding_provenance(
                installation, assignment, claim
            )
            if any(
                provenance.get(key) != value
                for key, value in expected_provenance.items()
            ):
                raise FirstSpecimenOutputDrift("project output attempt/assignment drift")
        if sha256_hex(provenance) != row["provenance_digest"]:
            raise FirstSpecimenOutputDrift("project output provenance digest drift")
        artifact_bytes_ref = provenance.get("artifact_exact_bytes_ref")
        if artifact_bytes_ref is not None:
            if not isinstance(artifact_bytes_ref, str) or not artifact_bytes_ref.startswith(
                "project-value:"
            ):
                raise FirstSpecimenOutputDrift("artifact exact bytes ref drift")
            content_row = one_mapping(
                connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key
                        == assignment.project_key,
                        tables.successor_values.c.value_id
                        == artifact_bytes_ref.removeprefix("project-value:"),
                    )
                )
            )
            if content_row is None or content_row["content_bytes"] is None:
                raise FirstSpecimenOutputDrift("artifact exact bytes are absent")
            content_bytes = bytes(content_row["content_bytes"])
            if hashlib.sha256(content_bytes).hexdigest() != provenance.get(
                "artifact_exact_bytes_digest"
            ):
                raise FirstSpecimenOutputDrift("artifact exact bytes readback drift")
        exact = (
            bytes(row["content_bytes"])
            if row["content_bytes"] is not None
            else canonical_bytes(row["content_json"])
        )
        if hashlib.sha256(exact).hexdigest() != row["content_digest"]:
            raise FirstSpecimenOutputDrift("project output content readback drift")
        binding = RuntimeValueBinding(
            value_id=value_id,
            object_type=str(public["object_type"]),
            codec_id=str(public["codec_id"]),
            content_digest=str(public["content_digest"]),
            byte_size=int(public["byte_size"]),
            project_value_ref=project_ref,
            storage_digest=str(public["storage_digest"]),
            write_intent_digest=public["write_intent_digest"],
            write_receipt_digest=public["write_receipt_digest"],
        )
        RuntimeValueRepository(connection, scope).load_exact(binding)
        expected_storage_digest = _runtime_storage_digest(
            installation=installation,
            assignment=assignment,
            claim=claim,
            runtime_value_id=value_id,
            project_value_ref=project_ref,
            content_digest=str(row["content_digest"]),
            codec_id=str(public["codec_id"]),
        )
        if public["storage_digest"] != expected_storage_digest:
            raise FirstSpecimenOutputDrift("runtime output attempt storage binding drift")
        if row["content_digest"] != public["content_digest"]:
            raise FirstSpecimenOutputDrift("public/project output digest drift")
        if installation.admission_required:
            staged = StagedArtifactRepository(connection, scope).load(
                _stage_id(assignment)
            )
            expected_stage = StagedArtifactBinding(
                artifact_id=_stage_id(assignment),
                run_id=assignment.run_id,
                step_id=assignment.step_id or "",
                attempt_id=claim.attempt_id,
                value_id=value_id,
                qualifier_ref=_qualifier_ref(installation),
            )
            if staged["state"] != "STAGED" or any(
                staged[field] != value
                for field, value in expected_stage.values().items()
            ):
                raise FirstSpecimenOutputDrift("admission staging readback drift")
        return str(row["content_digest"])

    def _interpret(
        self,
        connection: Connection,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenEffectReplay,
    ) -> _EffectProduct:
        if installation.operation_kind == QUALIFY_OPERATION:
            return self._qualify(assignment, claim, replay)
        if installation.operation_kind == CLAIM_OPERATION:
            return self._claim(assignment, claim, replay)
        if installation.operation_kind == ARTIFACT_OPERATION:
            return self._artifact(connection, assignment, claim, replay)
        if installation.operation_kind == CAPTURE_OPERATION:
            return self._capture(connection, assignment, claim, replay)
        raise FirstSpecimenHandlerError("unsupported semantic operation")

    def _qualify(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenEffectReplay,
    ) -> _EffectProduct:
        if not isinstance(replay.payload, EvidenceQualificationInput):
            raise FirstSpecimenReplayDrift("qualification payload type drift")
        materials = tuple(
            _decode_material(value)
            for value in replay.inputs
            if value.ref.object_type.type_id == MATERIAL_REF_TYPE.type_id
        )
        if len(materials) != 1:
            raise FirstSpecimenReplayDrift(
                "qualification requires one exact static MaterialRef"
            )
        material = materials[0]
        if material.material_ref_id != replay.payload.material_ref:
            raise FirstSpecimenReplayDrift("qualification material payload/input drift")
        for value in replay.inputs:
            if value.ref.object_type.type_id == MATERIAL_REF_TYPE.type_id:
                continue
            if value.ref.object_type.type_id != "EvidenceBundle.v1":
                raise FirstSpecimenReplayDrift(
                    "qualification dynamic input is not EvidenceBundle"
                )
            bundle = _decode_mapping(value, "EvidenceBundle")
            if (
                bundle.get("material_ref") != replay.payload.material_ref
                or bundle.get("inquiry_ref")
                not in {None, replay.payload.inquiry_ref}
            ):
                raise FirstSpecimenReplayDrift(
                    "qualification dynamic bundle/payload drift"
                )
        provenance = _output_binding_provenance(
            InstalledFirstSpecimenEffectHandler.bind(
                operation_kind=QUALIFY_OPERATION,
                handler_binding_digest=assignment.handler_binding_digest,
                interpreter_profile_digest=claim.interpreter_profile_digest or "",
            ),
            assignment,
            claim,
        )
        closure = sha256_hex(
            {
                "schema": "EvidenceQualificationProvenanceClosure.v1",
                "payload_digest": replay.payload.payload_digest,
                "ordered_input_refs": list(assignment.input_refs),
                "ordered_input_provenance": [
                    value.ref.provenance_digest for value in replay.inputs
                ],
                "assignment_digest": assignment.assignment_digest,
            }
        )
        interpreted = self._interpreters.qualify_evidence(
            replay.payload,
            project_key=assignment.project_key,
            provenance_closure_digest=closure,
            validity=Validity(
                valid_from=material.snapshot.observed_updated_at,
                valid_to=None,
            ),
            observed_at=material.snapshot.observed_updated_at,
        )
        value = _require_success(interpreted)
        assert isinstance(value, EvidenceQualification)
        exact = canonical_bytes(
            dataclass_to_json(value, ("qualification_digest",))
        )
        digest = hashlib.sha256(exact).hexdigest()
        if digest != value.qualification_digest:
            raise FirstSpecimenHandlerError("qualification canonical digest drift")
        provenance.update(
            {
                "semantic_object_id": value.qualification_id,
                "semantic_content_digest": value.qualification_digest,
                "provenance_closure_digest": closure,
                "relation_storage": value.RELATION_STORAGE,
            }
        )
        return _EffectProduct(
            object_type=EVIDENCE_QUALIFICATION_TYPE,
            exact_bytes=exact,
            content_digest=digest,
            source_ref=material.material_ref_id,
            provenance=provenance,
        )

    def _claim(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenEffectReplay,
    ) -> _EffectProduct:
        if not isinstance(replay.payload, ClaimOrGapInput):
            raise FirstSpecimenReplayDrift("claim payload type drift")
        qualifications: list[EvidenceQualification] = []
        materials: list[MaterialRef] = []
        qualification_closure_refs: list[ValueRef] = []
        for value in replay.inputs:
            if value.ref.object_type.type_id == EVIDENCE_QUALIFICATION_TYPE.type_id:
                qualifications.append(_decode_qualification(value))
                qualification_closure_refs.append(value.ref)
            elif value.ref.object_type.type_id == "EvidenceQualificationBundle.v1":
                bundle = _decode_mapping(value, "EvidenceQualificationBundle")
                raw_items = bundle.get("evidence_qualifications")
                if not isinstance(raw_items, list):
                    raise FirstSpecimenReplayDrift(
                        "qualification bundle lacks ordered qualifications"
                    )
                qualifications.extend(
                    _decode_qualification_mapping(item) for item in raw_items
                )
                qualification_closure_refs.append(value.ref)
            elif value.ref.object_type.type_id == MATERIAL_REF_TYPE.type_id:
                materials.append(_decode_material(value))
            else:
                raise FirstSpecimenReplayDrift("claim received unsupported input type")
        qualification_tuple = tuple(qualifications)
        material_tuple = tuple(materials)
        expected_relation_order = (
            replay.payload.support_relation_refs
            + replay.payload.contradiction_relation_refs
        )
        if tuple(item.qualification_id for item in qualification_tuple) != (
            expected_relation_order
        ):
            raise FirstSpecimenReplayDrift("claim ordered relation closure drift")
        if material_tuple and any(
            item.material_ref
            not in {material.material_ref_id for material in material_tuple}
            for item in qualification_tuple
        ):
            raise FirstSpecimenReplayDrift("claim qualification/material closure drift")
        support = tuple(
            value.qualification_id
            for value in qualification_tuple
            if value.direction == "SUPPORTS"
        )
        contradictions = tuple(
            value.qualification_id
            for value in qualification_tuple
            if value.direction == "CONTRADICTS"
        )
        if (
            support != replay.payload.support_relation_refs
            or contradictions != replay.payload.contradiction_relation_refs
        ):
            raise FirstSpecimenReplayDrift(
                "claim support/contradiction ordered closure drift"
            )
        if any(
            value.uncertainty_profile_ref
            != replay.payload.uncertainty_profile_ref
            for value in qualification_tuple
        ):
            raise FirstSpecimenReplayDrift("claim uncertainty profile drift")
        closure = sha256_hex(
            {
                "schema": "ClaimOrGapProvenanceClosure.v1",
                "payload_digest": replay.payload.payload_digest,
                "ordered_relation_digests": [
                    value.qualification_digest for value in qualification_tuple
                ],
                "ordered_input_refs": list(assignment.input_refs),
            }
        )
        interpreted = self._interpreters.form_claim_or_open_gap(
            replay.payload,
            provenance_closure_digest=closure,
        )
        outcome = _require_success(interpreted)
        assert isinstance(outcome, ClaimOrGapOutput)
        value = outcome.value
        if isinstance(value, Claim):
            object_type = CLAIM_TYPE
            object_id = value.claim_id
        elif isinstance(value, Gap):
            object_type = GAP_TYPE
            object_id = value.gap_id
        else:  # pragma: no cover - guarded by the capability interpreter
            raise FirstSpecimenHandlerError("claim interpreter returned unknown union arm")
        exact = canonical_bytes(dataclass_to_json(value, ("content_digest",)))
        digest = hashlib.sha256(exact).hexdigest()
        if digest != value.content_digest:
            raise FirstSpecimenHandlerError("claim/gap canonical digest drift")
        installation = InstalledFirstSpecimenEffectHandler.bind(
            operation_kind=CLAIM_OPERATION,
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=claim.interpreter_profile_digest or "",
        )
        provenance = _output_binding_provenance(installation, assignment, claim)
        provenance.update(
            {
                "semantic_object_id": object_id,
                "semantic_content_digest": digest,
                "provenance_closure_digest": closure,
                "support_relation_refs": list(outcome.support_relation_refs),
                "contradiction_relation_refs": list(
                    outcome.contradiction_relation_refs
                ),
                "uncertainty_profile_ref": outcome.uncertainty_profile_ref,
                "qualification_closure_value_refs": [
                    ref.to_plain() for ref in qualification_closure_refs
                ],
            }
        )
        return _EffectProduct(
            object_type=object_type,
            exact_bytes=exact,
            content_digest=digest,
            source_ref=replay.payload.inquiry_ref,
            provenance=provenance,
        )

    def _artifact(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenEffectReplay,
    ) -> _EffectProduct:
        if not isinstance(replay.payload, MarkdownComposeInput):
            raise FirstSpecimenReplayDrift("artifact payload type drift")
        semantic = tuple(
            (value, _decode_semantic_input(value)) for value in replay.inputs
        )
        outcomes = tuple(
            (stored, value)
            for stored, value in semantic
            if isinstance(value, (Claim, Gap))
        )
        materials = tuple(
            value for _, value in semantic if isinstance(value, MaterialRef)
        )
        if len(outcomes) != 1:
            raise FirstSpecimenReplayDrift("artifact requires one claim-or-gap input")
        outcome_value, outcome = outcomes[0]
        qualifications = _load_admitted_qualification_closure(
            connection,
            replay,
            outcome_value,
        )
        if tuple(value.qualification_id for value in qualifications) != (
            replay.payload.evidence_relation_closure
        ):
            raise FirstSpecimenReplayDrift("artifact qualification ordered closure drift")
        if tuple(value.material_ref_id for value in materials) != (
            replay.payload.citation_closure
        ):
            raise FirstSpecimenReplayDrift("artifact citation ordered closure drift")
        outcome = _claim_output(outcome)
        interpreted = self._interpreters.compose_markdown(
            replay.payload,
            outcome,
            qualifications=qualifications,
            materials=materials,
        )
        composed = _require_success(interpreted)
        artifact = composed.artifact
        assert isinstance(artifact, ResearchArtifact)
        exact = canonical_bytes(dataclass_to_json(artifact, ("content_digest",)))
        digest = hashlib.sha256(exact).hexdigest()
        if digest != artifact.content_digest:
            raise FirstSpecimenHandlerError("artifact canonical metadata digest drift")
        installation = InstalledFirstSpecimenEffectHandler.bind(
            operation_kind=ARTIFACT_OPERATION,
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=claim.interpreter_profile_digest or "",
        )
        provenance = _output_binding_provenance(installation, assignment, claim)
        content_value_id = f"{_result_value_id(assignment)}:content"
        provenance.update(
            {
                "semantic_object_id": artifact.artifact_id,
                "semantic_content_digest": digest,
                "artifact_exact_bytes_digest": composed.exact_bytes_digest,
                "artifact_exact_bytes_ref": f"project-value:{content_value_id}",
                "claim_closure": list(artifact.claim_closure),
                "evidence_relation_closure": list(
                    artifact.evidence_relation_closure
                ),
                "citation_closure": list(artifact.citation_closure),
                "qualification_closure_value_refs": outcome_value.provenance[
                    "qualification_closure_value_refs"
                ],
            }
        )
        return _EffectProduct(
            object_type=RESEARCH_ARTIFACT_TYPE,
            exact_bytes=exact,
            content_digest=digest,
            source_ref=outcome.value.claim_id
            if isinstance(outcome.value, Claim)
            else outcome.value.gap_id,
            provenance=provenance,
            artifact_exact_bytes=composed.exact_bytes,
        )

    def _capture(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenEffectReplay,
    ) -> _EffectProduct:
        if not isinstance(replay.payload, CaptureDocumentSnapshotInput):
            raise FirstSpecimenReplayDrift("capture payload type drift")
        sources = tuple(_decode_source(value) for value in replay.inputs)
        if not sources or any(source != sources[0] for source in sources[1:]):
            raise FirstSpecimenReplayDrift(
                "capture requires one exact SourceRef across dynamic/static inputs"
            )
        source = sources[0]
        if source.source_ref_id != replay.payload.source_ref:
            raise FirstSpecimenReplayDrift("capture source payload/input drift")
        table = replay.tables.successor_values
        row = one_mapping(
            connection.execute(
                select(table).where(
                    table.c.project_key == assignment.project_key,
                    table.c.object_type == CAPTURED_MATERIAL_SNAPSHOT_TYPE.type_id,
                    table.c.content_digest == replay.payload.content_sha256_hex,
                    table.c.state == "AVAILABLE",
                )
            )
        )
        if row is None or row["content_bytes"] is None:
            raise FirstSpecimenReplayDrift("submission-captured snapshot is absent")
        exact = bytes(row["content_bytes"])
        stored_provenance = dict(row["provenance_json"])
        try:
            snapshot = CapturedMaterialSnapshot(
                value_ref=f"project-value:{row['value_id']}",
                document_id=int(stored_provenance["document_id"]),
                observed_text_hash=stored_provenance["observed_text_hash"],
                observed_updated_at=datetime.fromisoformat(
                    str(stored_provenance["observed_updated_at"]).replace(
                        "Z", "+00:00"
                    )
                ),
                byte_size=len(exact),
            )
            captured = CapturedDocumentValue(
                exact_bytes=exact,
                snapshot=snapshot,
                exact_bytes_digest=str(row["content_digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FirstSpecimenReplayDrift("captured snapshot provenance is malformed") from exc
        interpreted = self._interpreters.capture_document_snapshot(
            replay.payload,
            captured,
        )
        _require_success(interpreted)
        installation = InstalledFirstSpecimenEffectHandler.bind(
            operation_kind=CAPTURE_OPERATION,
            handler_binding_digest=assignment.handler_binding_digest,
            interpreter_profile_digest=claim.interpreter_profile_digest or "",
        )
        provenance = _output_binding_provenance(installation, assignment, claim)
        provenance.update(
            {
                "semantic_object_id": str(row["value_id"]),
                "semantic_content_digest": str(row["content_digest"]),
                "submission_snapshot_provenance_digest": str(
                    row["provenance_digest"]
                ),
            }
        )
        # The project owner remains the immutable submission snapshot.  The
        # output public value is a deterministic alias to that exact value.
        return _EffectProduct(
            object_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
            exact_bytes=exact,
            content_digest=str(row["content_digest"]),
            source_ref=source.source_ref_id,
            provenance=provenance,
            existing_project_value_id=str(row["value_id"]),
            existing_project_incarnation=str(row["incarnation"]),
        )

    def _persist(
        self,
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: InstalledFirstSpecimenEffectHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        product: _EffectProduct,
    ) -> str:
        value_id = product.existing_project_value_id or _result_value_id(assignment)
        incarnation = product.existing_project_incarnation or _result_incarnation(
            assignment
        )
        provenance_digest = sha256_hex(product.provenance)
        values = ValueRepository(connection, tables)
        if product.artifact_exact_bytes is not None:
            content_value_id = f"{_result_value_id(assignment)}:content"
            content_digest = hashlib.sha256(product.artifact_exact_bytes).hexdigest()
            if product.provenance.get("artifact_exact_bytes_digest") != content_digest:
                raise FirstSpecimenOutputDrift("artifact exact bytes digest drift")
            content_provenance = {
                **_output_binding_provenance(installation, assignment, claim),
                "contract": "ResearchArtifactExactBytes.v1",
                "artifact_metadata_value_id": _result_value_id(assignment),
                "artifact_exact_bytes_digest": content_digest,
            }
            content_provenance_digest = sha256_hex(content_provenance)
            content_stored = values.put_exact(
                scope,
                value_id=content_value_id,
                object_type="ResearchArtifactMarkdown.v1",
                codec_id="mrw.markdown.utf8.v1",
                content=product.artifact_exact_bytes,
                expected_digest=content_digest,
                provenance_digest=content_provenance_digest,
                expected_revision=0,
                expected_incarnation=f"{_result_incarnation(assignment)}:content",
                source_ref=product.source_ref,
                provenance=content_provenance,
            )
            if content_stored.content_digest != content_digest:
                raise FirstSpecimenOutputDrift("artifact exact bytes write drift")
        if product.existing_project_value_id is not None:
            existing = one_mapping(
                connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key == assignment.project_key,
                        tables.successor_values.c.value_id == value_id,
                    )
                )
            )
            if existing is None:
                raise FirstSpecimenOutputDrift("captured project output disappeared")
            # Re-adopt the exact immutable project bytes without changing their
            # submission provenance; the execution binding is held by the
            # deterministic public alias below.
            project_intent_digest = existing["write_intent_digest"]
        else:
            stored = values.put_exact(
                scope,
                value_id=value_id,
                object_type=product.object_type.type_id,
                codec_id=CANONICAL_CODEC_ID,
                content=product.exact_bytes,
                expected_digest=product.content_digest,
                provenance_digest=provenance_digest,
                expected_revision=0,
                expected_incarnation=incarnation,
                source_ref=product.source_ref,
                provenance=product.provenance,
            )
            if stored.content_digest != product.content_digest:
                raise FirstSpecimenOutputDrift("project output write/readback drift")
            existing = one_mapping(
                connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key == assignment.project_key,
                        tables.successor_values.c.value_id == value_id,
                    )
                )
            )
            assert existing is not None
            project_intent_digest = existing["write_intent_digest"]
        public_value_id = _result_value_id(assignment)
        project_ref = f"project-value:{value_id}"
        storage_digest = _runtime_storage_digest(
            installation=installation,
            assignment=assignment,
            claim=claim,
            runtime_value_id=public_value_id,
            project_value_ref=project_ref,
            content_digest=product.content_digest,
            codec_id=CANONICAL_CODEC_ID,
        )
        RuntimeValueRepository(connection, scope).put_exact(
            RuntimeValueBinding(
                value_id=public_value_id,
                object_type=product.object_type.type_id,
                codec_id=CANONICAL_CODEC_ID,
                content_digest=product.content_digest,
                byte_size=len(product.exact_bytes),
                project_value_ref=project_ref,
                storage_digest=storage_digest,
                write_intent_digest=str(project_intent_digest),
            )
        )
        if installation.admission_required:
            StagedArtifactRepository(connection, scope).stage(
                StagedArtifactBinding(
                    artifact_id=_stage_id(assignment),
                    run_id=assignment.run_id,
                    step_id=assignment.step_id or "",
                    attempt_id=claim.attempt_id,
                    value_id=public_value_id,
                    qualifier_ref=_qualifier_ref(installation),
                )
            )
        return product.content_digest


class PostgresFirstSpecimenEffectHandler(RuntimeHandler):
    """RuntimeNode handler that realizes exactly one immutable installation."""

    def __init__(
        self,
        installation: InstalledFirstSpecimenEffectHandler,
        effects: FirstSpecimenEffectOutputPort,
    ) -> None:
        self.installation = installation
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._effects = effects

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        try:
            _require_exact_handler(self.installation, assignment, claim)
            return self._effects.execute_exact(
                self.installation,
                assignment,
                claim,
                context,
            )
        except FirstSpecimenHandlerError as exc:
            detail = re.sub(r"[^A-Z0-9]+", "_", str(exc).upper()).strip("_")
            code = type(exc).__name__.upper()
            if detail:
                code = f"{code}:{detail[:96]}"
            raise DefiniteInterpreterFailure(code) from exc


def _require_exact_handler(
    installation: InstalledFirstSpecimenEffectHandler,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> None:
    claim.validate_against(assignment)
    if assignment.assignment_kind is not AssignmentKind.INTERPRET:
        raise FirstSpecimenReplayDrift("semantic handler accepts INTERPRET only")
    ref = assignment.operation_contract_ref
    binding = assignment.handler_binding
    if (
        ref is None
        or ref.kind != installation.operation_kind
        or ref.contract_digest != installation.operation_contract_digest
        or assignment.operation_contract_digest
        != installation.operation_contract_digest
        or assignment.handler_binding_digest
        != installation.handler_binding_digest
        or getattr(binding, "interpreter_profile_digest", None)
        != installation.interpreter_profile_digest
        or claim.interpreter_profile_digest
        != installation.interpreter_profile_digest
        or assignment.return_contract_binding is None
        or assignment.return_contract_binding.admission_required
        != installation.admission_required
    ):
        raise FirstSpecimenReplayDrift("exact semantic handler binding drift")


def _qualifier_ref(installation: InstalledFirstSpecimenEffectHandler) -> str:
    return (
        f"staged:qualifier:{installation.operation_kind}:"
        f"sha256:{installation.handler_binding_digest}"
    )


def _require_success(outcome: object) -> object:
    if isinstance(outcome, InterpreterFailure):
        raise FirstSpecimenHandlerError(outcome.code)
    if not isinstance(outcome, InterpreterSuccess):
        raise FirstSpecimenHandlerError("semantic interpreter returned no exact success")
    return outcome.value


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise FirstSpecimenReplayDrift(f"{field} must be an ISO datetime")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FirstSpecimenReplayDrift(f"{field} must be timezone-aware")
    return parsed


def _decode_source(value: ReplayedProjectValue) -> SourceRef:
    if value.ref.object_type.type_id != SOURCE_REF_TYPE.type_id:
        raise FirstSpecimenReplayDrift("ordered capture input is not SourceRef")
    try:
        raw = json.loads(value.exact_bytes)
        source = SourceRef(
            source_ref_id=raw["source_ref_id"],
            owner_id=raw["owner_id"],
            locator=raw["locator"],
            source_class=raw["source_class"],
            observed_at=_datetime(raw["observed_at"], "SourceRef.observed_at"),
            access_profile_ref=raw["access_profile_ref"],
            content_digest=raw["content_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FirstSpecimenReplayDrift("stored SourceRef is malformed") from exc
    if canonical_bytes(source) != value.exact_bytes:
        raise FirstSpecimenReplayDrift("stored SourceRef bytes are not canonical")
    return source


def _decode_snapshot(raw: Mapping[str, Any]) -> CapturedMaterialSnapshot:
    return CapturedMaterialSnapshot(
        value_ref=raw["value_ref"],
        document_id=raw["document_id"],
        observed_text_hash=raw["observed_text_hash"],
        observed_updated_at=_datetime(
            raw["observed_updated_at"],
            "CapturedMaterialSnapshot.observed_updated_at",
        ),
        byte_size=raw["byte_size"],
        content_digest=raw["content_digest"],
    )


def _decode_material(value: ReplayedProjectValue) -> MaterialRef:
    if value.ref.object_type.type_id != MATERIAL_REF_TYPE.type_id:
        raise FirstSpecimenReplayDrift("ordered input is not MaterialRef")
    try:
        raw = json.loads(value.exact_bytes)
        material = MaterialRef(
            material_ref_id=raw["material_ref_id"],
            source_ref=raw["source_ref"],
            snapshot=_decode_snapshot(raw["snapshot"]),
            content_digest=raw["content_digest"],
            provenance_digest=raw["provenance_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FirstSpecimenReplayDrift("stored MaterialRef is malformed") from exc
    if canonical_bytes(material) != value.exact_bytes:
        raise FirstSpecimenReplayDrift("stored MaterialRef bytes are not canonical")
    return material


def _decode_qualification(value: ReplayedProjectValue) -> EvidenceQualification:
    if value.ref.object_type.type_id != EVIDENCE_QUALIFICATION_TYPE.type_id:
        raise FirstSpecimenReplayDrift("ordered input is not EvidenceQualification")
    try:
        raw = json.loads(value.exact_bytes)
        validity = raw["validity"]
        qualification = EvidenceQualification(
            qualification_id=raw["qualification_id"],
            project_key=raw["project_key"],
            material_ref=raw["material_ref"],
            inquiry_ref=raw["inquiry_ref"],
            claim_ref=raw["claim_ref"],
            direction=raw["direction"],
            scope_statement_ref=raw["scope_statement_ref"],
            uncertainty_profile_ref=raw["uncertainty_profile_ref"],
            verifier_profile_ref=raw["verifier_profile_ref"],
            provenance_closure_digest=raw["provenance_closure_digest"],
            validity=Validity(
                valid_from=None
                if validity["valid_from"] is None
                else _datetime(validity["valid_from"], "Validity.valid_from"),
                valid_to=None
                if validity["valid_to"] is None
                else _datetime(validity["valid_to"], "Validity.valid_to"),
            ),
            source_time=None
            if raw["source_time"] is None
            else _datetime(raw["source_time"], "source_time"),
            observed_at=None
            if raw["observed_at"] is None
            else _datetime(raw["observed_at"], "observed_at"),
            revision=raw["revision"],
            incarnation=raw["incarnation"],
            state=raw["state"],
            qualification_digest=hashlib.sha256(value.exact_bytes).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FirstSpecimenReplayDrift(
            "stored EvidenceQualification is malformed"
        ) from exc
    if qualification.qualification_digest != value.ref.content_digest:
        raise FirstSpecimenReplayDrift("qualification ValueRef digest drift")
    return qualification


def _decode_mapping(value: ReplayedProjectValue, name: str) -> dict[str, Any]:
    try:
        raw = json.loads(value.exact_bytes)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FirstSpecimenReplayDrift(f"stored {name} is malformed") from exc
    if not isinstance(raw, dict) or canonical_bytes(raw) != value.exact_bytes:
        raise FirstSpecimenReplayDrift(f"stored {name} is not a canonical object")
    return raw


def _decode_qualification_mapping(raw: object) -> EvidenceQualification:
    if not isinstance(raw, Mapping):
        raise FirstSpecimenReplayDrift("qualification bundle member is not an object")
    try:
        validity = raw["validity"]
        if not isinstance(validity, Mapping):
            raise TypeError("validity is not an object")
        semantic = {
            key: value
            for key, value in raw.items()
            if key != "qualification_digest"
        }
        digest = sha256_hex(semantic)
        qualification = EvidenceQualification(
            qualification_id=raw["qualification_id"],
            project_key=raw["project_key"],
            material_ref=raw["material_ref"],
            inquiry_ref=raw["inquiry_ref"],
            claim_ref=raw["claim_ref"],
            direction=raw["direction"],
            scope_statement_ref=raw["scope_statement_ref"],
            uncertainty_profile_ref=raw["uncertainty_profile_ref"],
            verifier_profile_ref=raw["verifier_profile_ref"],
            provenance_closure_digest=raw["provenance_closure_digest"],
            validity=Validity(
                valid_from=None
                if validity["valid_from"] is None
                else _datetime(validity["valid_from"], "Validity.valid_from"),
                valid_to=None
                if validity["valid_to"] is None
                else _datetime(validity["valid_to"], "Validity.valid_to"),
            ),
            source_time=None
            if raw["source_time"] is None
            else _datetime(raw["source_time"], "source_time"),
            observed_at=None
            if raw["observed_at"] is None
            else _datetime(raw["observed_at"], "observed_at"),
            revision=raw["revision"],
            incarnation=raw["incarnation"],
            state=raw["state"],
            qualification_digest=digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FirstSpecimenReplayDrift(
            "qualification bundle member is malformed"
        ) from exc
    supplied_digest = raw.get("qualification_digest")
    if supplied_digest is not None and supplied_digest != digest:
        raise FirstSpecimenReplayDrift("qualification bundle member digest drift")
    return qualification


def _decode_value_ref_plain(raw: object) -> ValueRef:
    if not isinstance(raw, Mapping):
        raise FirstSpecimenReplayDrift("qualification closure ref is not an object")
    object_type = raw.get("object_type")
    if not isinstance(object_type, Mapping):
        raise FirstSpecimenReplayDrift("qualification closure ref lacks object type")
    try:
        return ValueRef(
            value_id=raw["value_id"],
            project_key=raw["project_key"],
            object_type=ObjectType(
                type_id=object_type["type_id"],
                schema_version=object_type["schema_version"],
                codec_id=object_type["codec_id"],
                canonical_codec_version=object_type["canonical_codec_version"],
            ),
            codec_id=raw["codec_id"],
            content_digest=raw["content_digest"],
            storage_kind=raw["storage_kind"],
            store_id=raw["store_id"],
            store_version=raw["store_version"],
            storage_ref=raw["storage_ref"],
            byte_size=raw["byte_size"],
            provenance_digest=raw["provenance_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FirstSpecimenReplayDrift(
            "qualification closure ValueRef is malformed"
        ) from exc


def _load_admitted_qualification_closure(
    connection: Connection,
    replay: FirstSpecimenEffectReplay,
    outcome_value: ReplayedProjectValue,
) -> tuple[EvidenceQualification, ...]:
    raw_refs = outcome_value.provenance.get("qualification_closure_value_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        raise FirstSpecimenReplayDrift(
            "claim/gap provenance lacks qualification closure ValueRefs"
        )
    qualifications: list[EvidenceQualification] = []
    for raw_ref in raw_refs:
        ref = _decode_value_ref_plain(raw_ref)
        direct = tuple(value for value in replay.inputs if value.ref == ref)
        if len(direct) > 1:
            raise FirstSpecimenReplayDrift(
                "qualification closure ValueRef is duplicated in artifact inputs"
            )
        stored = (
            direct[0]
            if direct
            else PostgresFirstSpecimenEffectReplay._read_value(
                connection,
                replay.tables,
                replay.scope,
                ref,
            )
        )
        if ref.object_type.type_id == EVIDENCE_QUALIFICATION_TYPE.type_id:
            qualifications.append(_decode_qualification(stored))
            continue
        if ref.object_type.type_id != "EvidenceQualificationBundle.v1":
            raise FirstSpecimenReplayDrift(
                "claim/gap qualification closure ref has unsupported type"
            )
        bundle = _decode_mapping(stored, "EvidenceQualificationBundle")
        raw_items = bundle.get("evidence_qualifications")
        if not isinstance(raw_items, list):
            raise FirstSpecimenReplayDrift(
                "qualification closure bundle lacks ordered qualifications"
            )
        qualifications.extend(
            _decode_qualification_mapping(item) for item in raw_items
        )
    result = tuple(qualifications)
    _require_admitted_qualification_relations(connection, replay, result)
    return result


def _require_admitted_qualification_relations(
    connection: Connection,
    replay: FirstSpecimenEffectReplay,
    qualifications: tuple[EvidenceQualification, ...],
) -> None:
    table = replay.tables.research_relations
    for qualification in qualifications:
        row = one_mapping(
            connection.execute(
                select(table).where(
                    table.c.project_key == replay.scope.project_scope.project_key,
                    table.c.relation_id == qualification.qualification_id,
                    table.c.revision == qualification.revision,
                    table.c.incarnation == qualification.incarnation,
                )
            )
        )
        if row is None:
            raise FirstSpecimenReplayDrift(
                "artifact qualification lacks exact admitted relation"
            )
        expected_relation_type = {
            "SUPPORTS": "supports",
            "CONTRADICTS": "contradicts",
            "CONTEXT": "derived_from",
            "INSUFFICIENT": "opens",
        }[qualification.direction]
        validity = {
            "valid_from": qualification.validity.valid_from.isoformat()
            if qualification.validity.valid_from
            else None,
            "valid_to": qualification.validity.valid_to.isoformat()
            if qualification.validity.valid_to
            else None,
            "source_time": qualification.source_time.isoformat()
            if qualification.source_time
            else None,
            "observed_at": qualification.observed_at.isoformat()
            if qualification.observed_at
            else None,
            "claim_ref": qualification.claim_ref,
            "verifier_profile_ref": qualification.verifier_profile_ref,
        }
        if (
            row["relation_type"] != expected_relation_type
            or row["direction"] != qualification.direction
            or row["scope_ref"] != qualification.scope_statement_ref
            or row["uncertainty_profile_ref"]
            != qualification.uncertainty_profile_ref
            or row["validity_json"] != validity
            or row["provenance_closure_digest"]
            != qualification.provenance_closure_digest
            or row["state"] != qualification.state
        ):
            raise FirstSpecimenReplayDrift(
                "artifact qualification admitted relation drift"
            )
        try:
            source = json.loads(row["source_object_ref"])
            target = json.loads(row["target_object_ref"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise FirstSpecimenReplayDrift(
                "artifact qualification relation endpoint is malformed"
            ) from exc
        if (
            source.get("object_id") != qualification.material_ref
            or target.get("object_id") != qualification.inquiry_ref
            or source.get("project_key") != qualification.project_key
            or target.get("project_key") != qualification.project_key
        ):
            raise FirstSpecimenReplayDrift(
                "artifact qualification relation endpoint drift"
            )


def _decode_claim_or_gap(value: ReplayedProjectValue) -> Claim | Gap:
    try:
        raw = json.loads(value.exact_bytes)
        digest = hashlib.sha256(value.exact_bytes).hexdigest()
        if value.ref.object_type.type_id == CLAIM_TYPE.type_id:
            result: Claim | Gap = Claim(
                claim_id=raw["claim_id"],
                statement_ref=raw["statement_ref"],
                support_relation_refs=tuple(raw["support_relation_refs"]),
                contradiction_relation_refs=tuple(
                    raw["contradiction_relation_refs"]
                ),
                uncertainty_profile_ref=raw["uncertainty_profile_ref"],
                lifecycle_state=raw["lifecycle_state"],
                scope=dict(raw["scope"]),
                content_digest=digest,
            )
        elif value.ref.object_type.type_id == GAP_TYPE.type_id:
            result = Gap(
                gap_id=raw["gap_id"],
                inquiry_ref=raw["inquiry_ref"],
                requirement=raw["requirement"],
                reason=raw["reason"],
                closure_condition=raw["closure_condition"],
                reopen_policy=dict(raw["reopen_policy"]),
                missing_evidence_or_decision=raw["missing_evidence_or_decision"],
                content_digest=digest,
            )
        else:
            raise FirstSpecimenReplayDrift("ordered input is not Claim or Gap")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FirstSpecimenReplayDrift("stored Claim/Gap is malformed") from exc
    return result


def _decode_semantic_input(value: ReplayedProjectValue) -> object:
    if value.ref.object_type.type_id == MATERIAL_REF_TYPE.type_id:
        return _decode_material(value)
    if value.ref.object_type.type_id == EVIDENCE_QUALIFICATION_TYPE.type_id:
        return _decode_qualification(value)
    if value.ref.object_type.type_id in {CLAIM_TYPE.type_id, GAP_TYPE.type_id}:
        return _decode_claim_or_gap(value)
    raise FirstSpecimenReplayDrift("unsupported artifact semantic input type")


def _claim_output(value: Claim | Gap) -> ClaimOrGapOutput:
    if isinstance(value, Claim):
        closure = value.scope.get("provenance_closure_digest")
        support = value.support_relation_refs
        contradictions = value.contradiction_relation_refs
        uncertainty = value.uncertainty_profile_ref
    else:
        closure = value.reopen_policy.get("provenance_closure_digest")
        support = tuple(value.reopen_policy.get("support_relation_refs", ()))
        contradictions = tuple(
            value.reopen_policy.get("contradiction_relation_refs", ())
        )
        uncertainty = value.reopen_policy.get("uncertainty_profile_ref")
    if not isinstance(closure, str) or not isinstance(uncertainty, str):
        raise FirstSpecimenReplayDrift("claim/gap provenance closure is absent")
    return ClaimOrGapOutput(
        value=value,
        support_relation_refs=tuple(support),
        contradiction_relation_refs=tuple(contradictions),
        uncertainty_profile_ref=uncertainty,
        provenance_closure_digest=closure,
    )


__all__ = [
    "ARTIFACT_OPERATION",
    "CAPTURE_OPERATION",
    "CLAIM_OPERATION",
    "QUALIFY_OPERATION",
    "SUPPORTED_SEMANTIC_OPERATIONS",
    "FirstSpecimenActivationBindingPort",
    "FirstSpecimenEffectOutputPort",
    "FirstSpecimenEffectOutputStore",
    "FirstSpecimenEffectReplay",
    "FirstSpecimenEffectReplayPort",
    "FirstSpecimenHandlerError",
    "FirstSpecimenOutputDrift",
    "FirstSpecimenReplayDrift",
    "InstalledFirstSpecimenEffectHandler",
    "PostgresFirstSpecimenEffectHandler",
    "PostgresFirstSpecimenEffectReplay",
    "ReplayedProjectValue",
    "require_exact_activation_binding",
]
