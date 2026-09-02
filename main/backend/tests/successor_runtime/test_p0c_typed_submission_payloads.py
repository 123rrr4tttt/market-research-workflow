"""Exact typed payload closure for the P0-C submission Program."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

import pytest

from app.successor_runtime.capabilities.first_specimen import (
    CanonicalReadInput,
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    MarkdownComposeInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.capabilities.first_specimen_submission import (
    FirstSpecimenSubmissionService,
)
from app.successor_runtime.language.program import Atom, ProgramNode, ProgramSpec, Then

from .p0c_postgres_fixture import (
    LiveP0CDatabase,
    submission_command,
)
from .test_p0c_first_specimen_units import (
    PROJECT_KEY,
    _command,
    _compile_assignment,
    _DocumentPort,
    _FakeUoW,
    _LedgerPort,
    _ProgramPort,
    _rows,
    _RuntimePort,
    _service,
    _State,
    _ValuePort,
)

pytest_plugins = ("tests.successor_runtime.p0c_postgres_fixture",)

_KIND_BY_OPERATION = {
    "material.capture.source.a": "material.capture_document_snapshot.v1",
    "material.read.source.a": "material.read_canonical_ref.v1",
    "evidence.qualify.source.a": "evidence.qualify.v1",
    "material.capture.source.b": "material.capture_document_snapshot.v1",
    "material.read.source.b": "material.read_canonical_ref.v1",
    "evidence.qualify.source.b": "evidence.qualify.v1",
    "claim.form_or_open_gap": "claim.form_or_open_gap.v1",
    "artifact.compose_markdown": "artifact.compose_markdown.v1",
}

_DTO_BY_KIND = {
    "material.capture_document_snapshot.v1": CaptureDocumentSnapshotInput,
    "material.read_canonical_ref.v1": CanonicalReadInput,
    "evidence.qualify.v1": EvidenceQualificationInput,
    "claim.form_or_open_gap.v1": ClaimOrGapInput,
    "artifact.compose_markdown.v1": MarkdownComposeInput,
}


def _walk(node: ProgramNode):
    yield node
    if isinstance(node, Then):
        yield from _walk(node.first)
        yield from _walk(node.second)
        return
    for name in ("left", "right", "source"):
        child = getattr(node, name, None)
        if child is not None:
            yield from _walk(child)
    for branch in getattr(node, "branches", ()):
        yield from _walk(branch.program)


def _atoms(program: ProgramSpec) -> dict[str, Atom]:
    root = program.root
    return {
        node.operation.operation_id: node
        for node in _walk(root)
        if isinstance(node, Atom)
    }


def _assert_exact_typed_payloads(
    program: ProgramSpec,
    load_bytes: Callable[[str], bytes],
    *,
    project_key: str,
    submission_id: str,
) -> None:
    atoms = _atoms(program)
    assert tuple(
        operation_id
        for operation_id in atoms
        if operation_id in _KIND_BY_OPERATION
    ) == tuple(_KIND_BY_OPERATION)
    bundle = build_first_specimen_bundle()

    for operation_id, kind in _KIND_BY_OPERATION.items():
        atom = atoms[operation_id]
        ref = atom.operation.payload_ref
        codec = bundle.codec_by_kind(kind)
        assert ref.value_id == f"{submission_id}:payload:{operation_id}"
        assert ref.project_key == project_key
        assert ref.object_type.type_id == codec.payload_type_id
        assert ref.object_type.schema_version == codec.codec_version
        assert ref.codec_id == codec.codec_id
        assert ref.object_type.codec_id == codec.codec_id
        assert ref not in atom.operation.input_refs
        exact = load_bytes(ref.value_id)
        assert len(exact) == ref.byte_size
        assert hashlib.sha256(exact).hexdigest() == ref.content_digest
        decoded = codec.decode_payload(json.loads(exact))
        assert isinstance(decoded, _DTO_BY_KIND[kind])
        assert codec.encode_payload(decoded) == json.loads(exact)
        assert decoded.payload_digest != ref.content_digest


def test_submission_persists_eight_static_exact_typed_payload_values() -> None:
    state = _State()
    documents = _DocumentPort(_rows())
    command = _command()
    submitted = _service(state, documents).submit(command)

    _assert_exact_typed_payloads(
        submitted.program,
        lambda value_id: state.values[value_id]["content"],
        project_key=PROJECT_KEY,
        submission_id=command.submission_id,
    )
    payload_ids = {
        value_id
        for value_id in state.values
        if value_id.startswith(f"{command.submission_id}:payload:")
    }
    assert len(payload_ids) == 8
    delivery_payload = _atoms(submitted.program)[
        "delivery.internal_export"
    ].operation.payload_ref
    assert delivery_payload.object_type.type_id == "DeliveryIntentTemplate.v1"
    assert delivery_payload == submitted.delivery_template_value_ref
    assert not any(
        value_id.endswith(":payload:delivery.internal_export")
        for value_id in state.values
    )
    assert documents.reads == [101, 102]

    same = _service(state, documents).submit(command)
    assert same is submitted
    assert documents.reads == [101, 102]
    assert state.commits == 1


class _RejectTypedPayloadPort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.delegate = _ValuePort(uow)

    def put_exact(self, scope: object, **values: object) -> object:
        if values["value_id"] == (
            "submission:p0c:1:payload:claim.form_or_open_gap"
        ):
            raise RuntimeError("injected typed payload write failure")
        return self.delegate.put_exact(scope, **values)


def test_typed_payload_write_failure_rolls_back_entire_submission() -> None:
    state = _State()
    documents = _DocumentPort(_rows())

    def uow_factory() -> _FakeUoW:
        return _FakeUoW(state, documents)

    service = FirstSpecimenSubmissionService(
        uow_factory=uow_factory,
        document_port=lambda uow: uow.documents,
        value_port=lambda uow: _RejectTypedPayloadPort(uow),
        ledger_port=lambda uow: _LedgerPort(uow),
        program_port=lambda uow: _ProgramPort(uow),
        runtime_port=lambda uow: _RuntimePort(uow),
        compile_assignment_factory=_compile_assignment,
    )
    with pytest.raises(RuntimeError, match="typed payload write failure"):
        service.submit(_command())
    assert state.values == {}
    assert state.ledger == {}
    assert state.programs == {}
    assert state.runtime_packets == {}
    assert state.commits == 0 and state.rollbacks == 1


@pytest.mark.integration
def test_real_postgres_submission_persists_typed_payload_codecs(
    p0c_database: LiveP0CDatabase,
) -> None:
    command = submission_command(suffix="typed-payloads")
    submitted = p0c_database.submission_service().submit(command)
    _assert_exact_typed_payloads(
        submitted.program,
        p0c_database.value_bytes,
        project_key=command.intent.project_key,
        submission_id=command.submission_id,
    )
