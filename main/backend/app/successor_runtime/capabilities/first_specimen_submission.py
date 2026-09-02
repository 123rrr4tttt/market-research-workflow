"""Atomic P0-C submission service for the frozen first specimen.

One transaction observes two legacy Documents through the read-only sibling
port, captures their exact bytes in project ``successor_values``, records only
research objects/refs in the Research Ledger, stores the exact Program, and
creates the SUBMITTED run, initial event and COMPILE work item.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Self, cast

from app.successor_runtime.capabilities import (
    DELIVERY_TEMPLATE_TYPE,
    DeliveryIntentTemplate,
    ExactOperationValues,
    FirstSpecimenPayloadContext,
    FirstSpecimenProgramValues,
    SourcePayloadContext,
    build_runtime_first_specimen_program,
    derive_material_ref,
    persist_first_specimen_payloads,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.combinators import Registries
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.inquiries import (
    Inquiry,
    ResearchIntent,
    ResearchPlan,
)
from app.successor_runtime.research.materials import (
    CapturedMaterialSnapshot,
    MaterialRef,
)
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
    ObjectType,
)
from app.successor_runtime.research.sources import SourceRef


class SubmissionRejected(RuntimeError):
    """The exact submission cannot be created without weakening its bindings."""


@dataclass(frozen=True, slots=True)
class SubmissionCommand:
    submission_id: str
    scope: object
    program_id: str
    run_id: str
    run_incarnation: str
    intent: ResearchIntent
    inquiry: Inquiry
    research_plan: ResearchPlan
    source_refs: tuple[SourceRef, SourceRef]
    document_ids: tuple[int, int]
    delivery_template: DeliveryIntentTemplate
    catalog: OperationContractCatalogSnapshot
    registries: Registries
    compiler_binding: object
    deployment_catalog_digest: str
    submission_authority_digest: str
    claim_authority_epoch: int
    claim_policy_digest: str
    resource_policy_digest: str
    resource_policy_epoch: int
    queue_eligibility_digest: str
    required_node_profile_selector: str
    fairness_key: str
    trace_id: str
    due_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.submission_id,
            self.program_id,
            self.run_id,
            self.run_incarnation,
            self.trace_id,
            self.required_node_profile_selector,
            self.fairness_key,
        )
        if any(not value for value in required):
            raise ValueError("submission identities must be non-empty")
        project_key = _project_key(self.scope)
        if self.intent.project_key != project_key:
            raise ValueError("ResearchIntent project scope drift")
        if self.inquiry.intent_ref != self.intent.intent_id:
            raise ValueError("Inquiry does not bind the submitted ResearchIntent")
        if self.research_plan.inquiry_ref != self.inquiry.inquiry_id:
            raise ValueError("ResearchPlan does not bind the submitted Inquiry")
        if len(set(self.document_ids)) != 2 or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in self.document_ids
        ):
            raise ValueError("first specimen requires two distinct positive Document IDs")
        if len({source.locator for source in self.source_refs}) != 2:
            raise ValueError("first specimen requires two distinct SourceRef locators")
        for source, document_id in zip(self.source_refs, self.document_ids, strict=True):
            if source.locator != f"document://{project_key}/{document_id}":
                raise ValueError("SourceRef locator does not bind the exact Document ID")
            if source.access_profile_ref != "DocumentCanonicalReadPort":
                raise ValueError("SourceRef must use DocumentCanonicalReadPort")
        for name in (
            "deployment_catalog_digest",
            "submission_authority_digest",
            "claim_policy_digest",
            "resource_policy_digest",
            "queue_eligibility_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be canonical sha256 hex")
        if self.submission_authority_digest == "0" * 64:
            raise ValueError("submission authority cannot be a placeholder")
        if self.claim_authority_epoch < 0 or self.resource_policy_epoch < 0:
            raise ValueError("submission epochs must be non-negative")
        if (
            getattr(self.compiler_binding, "operation_catalog_digest", None)
            != self.catalog.catalog_digest
        ):
            raise ValueError("CompilerBinding operation catalog drift")


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    source_ref: SourceRef
    observation: CanonicalDocumentObservation
    snapshot: CapturedMaterialSnapshot
    snapshot_value_ref: ValueRef
    source_value_ref: ValueRef
    material: MaterialRef
    material_value_ref: ValueRef
    material_object_ref: ResearchObjectRef


@dataclass(frozen=True, slots=True)
class SubmittedRuntimePacket:
    submission_id: str
    run_id: str
    run_incarnation: str
    state: str
    program_id: str
    program_digest: str
    program_storage_ref: str
    contract_version: str
    submission_authority_digest: str
    event_type: str
    compile_assignment: object
    required_node_profile_selector: str
    resource_policy_digest: str
    fairness_key: str
    work_item_state: str
    due_at: datetime


@dataclass(frozen=True, slots=True)
class SubmittedFirstSpecimen:
    submission_id: str
    program: ProgramSpec
    intent_ref: ResearchObjectRef
    inquiry_ref: ResearchObjectRef
    plan_ref: ResearchObjectRef
    captures: tuple[CaptureReceipt, CaptureReceipt]
    delivery_template_value_ref: ValueRef
    compile_assignment: object
    runtime_receipt: object


class _UoW(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def commit(self) -> None: ...


class CanonicalDocumentObservation(Protocol):
    document_id: int
    text_hash: str | None
    updated_at: datetime
    exact_bytes: bytes


class SubmissionDocumentPort(Protocol):
    def read_document(
        self, scope: object, document_id: int
    ) -> CanonicalDocumentObservation: ...


class SubmissionValuePort(Protocol):
    def put_exact(
        self,
        scope: object,
        *,
        value_id: str,
        object_type: str,
        codec_id: str,
        content: bytes,
        expected_digest: str,
        provenance_digest: str,
        expected_revision: int,
        expected_incarnation: str,
        source_ref: str | None = None,
        provenance: dict[str, object] | None = None,
    ) -> object: ...


class SubmissionLedgerPort(Protocol):
    def put_object(
        self,
        scope: object,
        ref: ResearchObjectRef,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef: ...


class SubmissionProgramPort(Protocol):
    def put_exact(
        self, scope: object, program: ProgramSpec, expected_digest: str
    ) -> ProgramSpec: ...


class SubmissionRuntimePort(Protocol):
    def get_submission(
        self, scope: object, submission_id: str
    ) -> SubmittedFirstSpecimen | None: ...

    def create_submitted(
        self, scope: object, packet: SubmittedRuntimePacket
    ) -> object: ...


PortFactory = Callable[[_UoW], object]
CompileAssignmentFactory = Callable[["CompileAssignmentRequest"], object]


@dataclass(frozen=True, slots=True)
class CompileAssignmentRequest:
    command: SubmissionCommand
    program: ProgramSpec
    input_refs: tuple[str, ...]


def _project_key(scope: object) -> str:
    project_scope = getattr(scope, "project_scope", None)
    project_key = getattr(project_scope, "project_key", None)
    if not isinstance(project_key, str) or not project_key:
        raise TypeError("submission scope must expose a validated project_scope")
    return project_key


def _project_scope_value(scope: object, field: str) -> object:
    project_scope = getattr(scope, "project_scope", None)
    if project_scope is None or not hasattr(project_scope, field):
        raise TypeError("submission scope must expose a validated project_scope")
    return getattr(project_scope, field)


def _validate_document_observation(
    observation: CanonicalDocumentObservation, document_id: int
) -> None:
    if observation.document_id != document_id:
        raise SubmissionRejected("DocumentCanonicalReadPort identity drift")
    if not isinstance(observation.exact_bytes, bytes):
        raise SubmissionRejected("DocumentCanonicalReadPort must return independent bytes")
    if observation.updated_at.tzinfo is None:
        raise SubmissionRejected("DocumentCanonicalReadPort timestamp must be timezone-aware")
    if observation.text_hash is not None and not isinstance(observation.text_hash, str):
        raise SubmissionRejected("DocumentCanonicalReadPort text_hash type drift")


def _incarnation(submission_id: str, label: str) -> str:
    return f"p0c:{submission_id}:{label}"


def _value_ref(
    *,
    project_key: str,
    value_id: str,
    object_type: ObjectType,
    exact: bytes,
    provenance_digest: str,
) -> ValueRef:
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest=hashlib.sha256(exact).hexdigest(),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact),
        provenance_digest=provenance_digest,
    )


def _put_value(
    port: SubmissionValuePort,
    command: SubmissionCommand,
    *,
    value_id: str,
    object_type: ObjectType,
    content: object,
    provenance: dict[str, object],
    source_ref: str | None = None,
) -> ValueRef:
    exact = bytes(content) if isinstance(content, bytes) else canonical_bytes(content)
    provenance_digest = sha256_hex(provenance)
    ref = _value_ref(
        project_key=_project_key(command.scope),
        value_id=value_id,
        object_type=object_type,
        exact=exact,
        provenance_digest=provenance_digest,
    )
    port.put_exact(
        command.scope,
        value_id=value_id,
        object_type=object_type.type_id,
        codec_id=object_type.codec_id,
        content=exact,
        expected_digest=ref.content_digest,
        provenance_digest=provenance_digest,
        expected_revision=0,
        expected_incarnation=_incarnation(command.submission_id, value_id),
        source_ref=source_ref,
        provenance=provenance,
    )
    return ref


def _ledger_ref(
    command: SubmissionCommand,
    *,
    object_id: str,
    object_type: ObjectType,
    value_ref: ValueRef,
    owner: str,
) -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id=object_id,
        object_type=object_type,
        project_key=_project_key(command.scope),
        revision=1,
        incarnation=_incarnation(command.submission_id, f"object:{object_id}"),
        owner_binding_ref=owner,
        content_ref=value_ref.storage_ref,
        content_digest=value_ref.content_digest,
        provenance_closure_digest=value_ref.provenance_digest,
        lifecycle_state="ADMITTED",
    )


class FirstSpecimenSubmissionService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], _UoW],
        document_port: PortFactory,
        value_port: PortFactory,
        ledger_port: PortFactory,
        program_port: PortFactory,
        runtime_port: PortFactory,
        compile_assignment_factory: CompileAssignmentFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._document_port = document_port
        self._value_port = value_port
        self._ledger_port = ledger_port
        self._program_port = program_port
        self._runtime_port = runtime_port
        self._compile_assignment_factory = compile_assignment_factory

    def submit(self, command: SubmissionCommand) -> SubmittedFirstSpecimen:
        with self._uow_factory() as uow:
            documents = cast(SubmissionDocumentPort, self._document_port(uow))
            values = cast(SubmissionValuePort, self._value_port(uow))
            ledger = cast(SubmissionLedgerPort, self._ledger_port(uow))
            programs = cast(SubmissionProgramPort, self._program_port(uow))
            runtime = cast(SubmissionRuntimePort, self._runtime_port(uow))

            existing = runtime.get_submission(command.scope, command.submission_id)
            if existing is not None:
                return existing

            intent_value = _put_value(
                values,
                command,
                value_id=command.intent.intent_id,
                object_type=RESEARCH_INTENT_TYPE,
                content=command.intent,
                provenance={"submission_id": command.submission_id, "kind": "ResearchIntent"},
            )
            inquiry_value = _put_value(
                values,
                command,
                value_id=command.inquiry.inquiry_id,
                object_type=INQUIRY_TYPE,
                content=command.inquiry,
                provenance={
                    "submission_id": command.submission_id,
                    "intent_ref": command.intent.intent_id,
                },
            )
            plan_value = _put_value(
                values,
                command,
                value_id=command.research_plan.plan_id,
                object_type=RESEARCH_PLAN_TYPE,
                content=command.research_plan,
                provenance={
                    "submission_id": command.submission_id,
                    "inquiry_ref": command.inquiry.inquiry_id,
                },
            )
            template_value = _put_value(
                values,
                command,
                value_id=command.delivery_template.value_id,
                object_type=DELIVERY_TEMPLATE_TYPE,
                content=command.delivery_template.to_payload(),
                provenance={
                    "submission_id": command.submission_id,
                    "approval_ref": command.delivery_template.approval_ref,
                    "authority_digest": command.delivery_template.authority_digest,
                },
            )

            intent_ref = _ledger_ref(
                command,
                object_id=command.intent.intent_id,
                object_type=RESEARCH_INTENT_TYPE,
                value_ref=intent_value,
                owner="ResearchLedger",
            )
            inquiry_ref = _ledger_ref(
                command,
                object_id=command.inquiry.inquiry_id,
                object_type=INQUIRY_TYPE,
                value_ref=inquiry_value,
                owner="ResearchLedger",
            )
            plan_ref = _ledger_ref(
                command,
                object_id=command.research_plan.plan_id,
                object_type=RESEARCH_PLAN_TYPE,
                value_ref=plan_value,
                owner="ResearchLedger",
            )
            for ref in (intent_ref, inquiry_ref, plan_ref):
                ledger.put_object(
                    command.scope,
                    ref,
                    expected_revision=0,
                    expected_incarnation=ref.incarnation,
                )

            captures: list[CaptureReceipt] = []
            for label, source, document_id in zip(
                ("a", "b"),
                command.source_refs,
                command.document_ids,
                strict=True,
            ):
                observation = documents.read_document(command.scope, document_id)
                _validate_document_observation(observation, document_id)
                snapshot_value = _put_value(
                    values,
                    command,
                    value_id=f"{command.submission_id}:snapshot:{label}",
                    object_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
                    content=observation.exact_bytes,
                    provenance={
                        "submission_id": command.submission_id,
                        "document_id": document_id,
                        "source_ref": source.source_ref_id,
                        "observed_text_hash": observation.text_hash,
                        "observed_updated_at": observation.updated_at.isoformat(),
                    },
                    source_ref=source.source_ref_id,
                )
                snapshot = CapturedMaterialSnapshot(
                    value_ref=snapshot_value.storage_ref,
                    document_id=document_id,
                    observed_text_hash=observation.text_hash,
                    observed_updated_at=observation.updated_at,
                    byte_size=len(observation.exact_bytes),
                )
                material = derive_material_ref(
                    source_ref=source.source_ref_id,
                    snapshot=snapshot,
                    owner_id=source.owner_id,
                    locator=source.locator,
                    observed_at=source.observed_at.isoformat(),
                )
                source_value = _put_value(
                    values,
                    command,
                    value_id=source.source_ref_id,
                    object_type=SOURCE_REF_TYPE,
                    content=source,
                    provenance={
                        "submission_id": command.submission_id,
                        "document_id": document_id,
                        "owner_id": source.owner_id,
                    },
                    source_ref=source.source_ref_id,
                )
                material_value = _put_value(
                    values,
                    command,
                    value_id=material.material_ref_id,
                    object_type=MATERIAL_REF_TYPE,
                    content=material,
                    provenance={
                        "submission_id": command.submission_id,
                        "source_ref": source.source_ref_id,
                        "snapshot_value_ref": snapshot.value_ref,
                        "snapshot_digest": snapshot_value.content_digest,
                    },
                    source_ref=source.source_ref_id,
                )
                source_object_ref = _ledger_ref(
                    command,
                    object_id=source.source_ref_id,
                    object_type=SOURCE_REF_TYPE,
                    value_ref=source_value,
                    owner="legacy_source_or_document_locator",
                )
                material_object_ref = _ledger_ref(
                    command,
                    object_id=material.material_ref_id,
                    object_type=MATERIAL_REF_TYPE,
                    value_ref=material_value,
                    owner="CapturedMaterialSnapshot",
                )
                for ref in (source_object_ref, material_object_ref):
                    ledger.put_object(
                        command.scope,
                        ref,
                        expected_revision=0,
                        expected_incarnation=ref.incarnation,
                    )
                captures.append(
                    CaptureReceipt(
                        source_ref=source,
                        observation=observation,
                        snapshot=snapshot,
                        snapshot_value_ref=snapshot_value,
                        source_value_ref=source_value,
                        material=material,
                        material_value_ref=material_value,
                        material_object_ref=material_object_ref,
                    )
                )

            capture_a, capture_b = captures
            typed_payloads = persist_first_specimen_payloads(
                values,
                command.scope,
                FirstSpecimenPayloadContext(
                    submission_id=command.submission_id,
                    run_id=command.run_id,
                    project_key=_project_key(command.scope),
                    inquiry_ref=command.inquiry.inquiry_id,
                    sources=tuple(
                        SourcePayloadContext(
                            label=label,
                            source_ref=capture.source_ref.source_ref_id,
                            document_id=capture.observation.document_id,
                            locator=capture.source_ref.locator,
                            owner_id=capture.source_ref.owner_id,
                            observed_at=capture.source_ref.observed_at,
                            captured_content_digest=(
                                capture.snapshot_value_ref.content_digest
                            ),
                            captured_updated_at=(
                                capture.observation.updated_at
                            ),
                            captured_byte_size=(
                                capture.snapshot_value_ref.byte_size
                            ),
                            material_ref=capture.material.material_ref_id,
                        )
                        for label, capture in zip(
                            ("a", "b"), (capture_a, capture_b), strict=True
                        )
                    ),
                ),
            )
            program_values = FirstSpecimenProgramValues(
                intent=intent_value,
                inquiry=inquiry_value,
                research_plan=plan_value,
                source_a=capture_a.source_value_ref,
                source_b=capture_b.source_value_ref,
                delivery_template=template_value,
                operations=(
                    (
                        "material.capture.source.a",
                        ExactOperationValues(
                            (capture_a.source_value_ref,),
                            typed_payloads.for_operation(
                                "material.capture.source.a"
                            ),
                        ),
                    ),
                    (
                        "material.read.source.a",
                        ExactOperationValues(
                            (capture_a.snapshot_value_ref,),
                            typed_payloads.for_operation("material.read.source.a"),
                        ),
                    ),
                    (
                        "evidence.qualify.source.a",
                        ExactOperationValues(
                            (capture_a.material_value_ref,),
                            typed_payloads.for_operation(
                                "evidence.qualify.source.a"
                            ),
                        ),
                    ),
                    (
                        "material.capture.source.b",
                        ExactOperationValues(
                            (capture_b.source_value_ref,),
                            typed_payloads.for_operation(
                                "material.capture.source.b"
                            ),
                        ),
                    ),
                    (
                        "material.read.source.b",
                        ExactOperationValues(
                            (capture_b.snapshot_value_ref,),
                            typed_payloads.for_operation("material.read.source.b"),
                        ),
                    ),
                    (
                        "evidence.qualify.source.b",
                        ExactOperationValues(
                            (capture_b.material_value_ref,),
                            typed_payloads.for_operation(
                                "evidence.qualify.source.b"
                            ),
                        ),
                    ),
                    (
                        "claim.form_or_open_gap",
                        ExactOperationValues(
                            (
                                capture_a.material_value_ref,
                                capture_b.material_value_ref,
                            ),
                            typed_payloads.for_operation(
                                "claim.form_or_open_gap"
                            ),
                        ),
                    ),
                    (
                        "artifact.compose_markdown",
                        ExactOperationValues(
                            (
                                capture_a.material_value_ref,
                                capture_b.material_value_ref,
                            ),
                            typed_payloads.for_operation(
                                "artifact.compose_markdown"
                            ),
                        ),
                    ),
                    (
                        "delivery.internal_export",
                        ExactOperationValues((template_value,), template_value),
                    ),
                ),
            )
            program = build_runtime_first_specimen_program(
                catalog=command.catalog,
                registries=command.registries,
                values=program_values,
                program_id=command.program_id,
                project_key=_project_key(command.scope),
                project_scope_digest=str(
                    _project_scope_value(command.scope, "scope_digest")
                ),
                project_registry_revision=(
                    int(_project_scope_value(command.scope, "project_registry_revision"))
                ),
                delivery_template=command.delivery_template.to_payload(),
            )
            programs.put_exact(command.scope, program, program.program_digest)

            input_refs = (
                intent_value.storage_ref,
                inquiry_value.storage_ref,
                plan_value.storage_ref,
                capture_a.snapshot_value_ref.storage_ref,
                capture_b.snapshot_value_ref.storage_ref,
                template_value.storage_ref,
            )
            compile_assignment = self._compile_assignment_factory(
                CompileAssignmentRequest(
                    command=command,
                    program=program,
                    input_refs=input_refs,
                )
            )
            _validate_compile_assignment(compile_assignment, command, program)
            packet = SubmittedRuntimePacket(
                submission_id=command.submission_id,
                run_id=command.run_id,
                run_incarnation=command.run_incarnation,
                state="SUBMITTED",
                program_id=program.program_id,
                program_digest=program.program_digest,
                program_storage_ref=f"project-value:program:{program.program_id}",
                contract_version=program.contract_version,
                submission_authority_digest=command.submission_authority_digest,
                event_type="ProgramAccepted",
                compile_assignment=compile_assignment,
                required_node_profile_selector=command.required_node_profile_selector,
                resource_policy_digest=command.resource_policy_digest,
                fairness_key=command.fairness_key,
                work_item_state="READY",
                due_at=command.due_at,
            )
            runtime_receipt = runtime.create_submitted(command.scope, packet)
            submitted = SubmittedFirstSpecimen(
                submission_id=command.submission_id,
                program=program,
                intent_ref=intent_ref,
                inquiry_ref=inquiry_ref,
                plan_ref=plan_ref,
                captures=(capture_a, capture_b),
                delivery_template_value_ref=template_value,
                compile_assignment=compile_assignment,
                runtime_receipt=runtime_receipt,
            )
            record = getattr(runtime, "record_submission", None)
            if callable(record):
                record(command.scope, submitted)
            uow.commit()
            return submitted


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _validate_compile_assignment(
    assignment: object, command: SubmissionCommand, program: ProgramSpec
) -> None:
    expected = {
        "assignment_kind": "COMPILE",
        "project_key": _project_key(command.scope),
        "run_id": command.run_id,
        "program_digest": program.program_digest,
        "deployment_catalog_digest": command.deployment_catalog_digest,
        "claim_authority_epoch": command.claim_authority_epoch,
        "claim_policy_digest": command.claim_policy_digest,
    }
    mismatches = [
        field
        for field, value in expected.items()
        if _enum_value(getattr(assignment, field, None)) != value
    ]
    if mismatches:
        raise SubmissionRejected(
            "COMPILE assignment exact binding drift: " + ", ".join(mismatches)
        )
    if not getattr(assignment, "assignment_digest", None):
        raise SubmissionRejected("COMPILE assignment lacks exact digest")


__all__ = [
    "CaptureReceipt",
    "CompileAssignmentRequest",
    "FirstSpecimenSubmissionService",
    "SubmissionCommand",
    "SubmissionRejected",
    "SubmittedFirstSpecimen",
    "SubmittedRuntimePacket",
]
