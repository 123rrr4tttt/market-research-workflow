"""C7.2 canonical CommitIntent/VerificationBinding readback tests."""

from __future__ import annotations

from app.successor_runtime.substrate.postgres.c7_document_readback import (
    CanonicalCommitReadback,
    document_ref_from_readback,
)
from app.successor_runtime.capabilities import material_ingest_common as c7
from app.successor_runtime.capabilities.material_ingest_interpreters import (
    interpret_commit_readback,
)
from tests.successor_runtime.p4_c7_fixture import (
    PROJECT_KEY,
    canonical_commit_readback,
    commit_intent,
    verification_binding,
)


def test_commit_intent_reuses_canonical_binding_identity() -> None:
    binding = verification_binding()
    intent = commit_intent(binding=binding)
    assert intent.verification_binding_digest == binding.binding_digest
    assert intent.content_digest == binding.output_content_digest
    assert intent.ordered_event_closure_digest == (
        binding.ordered_event_payload_closure_digest
    )
    assert intent.project_key == PROJECT_KEY


def test_readback_interpreter_projects_typed_readback_without_writer() -> None:
    binding = verification_binding()
    intent = commit_intent(binding=binding)
    outcome = interpret_commit_readback(
        commit_intent_id=intent.commit_intent_id,
        content_digest_hex=intent.content_digest,
        verification_binding_digest=binding.binding_digest,
        state="PREPARED",
    )
    assert outcome.disposition == "SUCCEEDED"
    value = outcome.value
    assert value["document_write"] is False
    assert value["provider_calls"] == 0
    assert value["authority"] is False


def test_document_ref_binds_project_id_revision_incarnation_digest() -> None:
    readback = canonical_commit_readback(committed_revision=2)
    ref = document_ref_from_readback(readback)
    assert ref.project_key == PROJECT_KEY
    assert ref.object_id == readback.object_id
    assert ref.revision == readback.committed_revision
    assert ref.incarnation == readback.committed_incarnation
    assert ref.content_digest == readback.content_digest
    assert ref.canonical_owner == c7.DOCUMENT_CANONICAL_OWNER
    assert ref.binding_digest


def test_document_ref_comes_from_canonical_readback_not_runtime_intent() -> None:
    intent = commit_intent()
    readback = canonical_commit_readback(committed_revision=3)
    ref = document_ref_from_readback(readback)
    assert isinstance(readback, CanonicalCommitReadback)
    assert ref.revision != intent.expected_base_revision
    assert readback.canonical_commit_ref


def test_only_c7_2_admission_carries_write_boundary() -> None:
    from app.successor_runtime.capabilities.material_ingest_common import (
        stage_ingest_submission,
    )
    from tests.successor_runtime.p4_c7_fixture import submission

    staged = stage_ingest_submission(submission())
    assert staged.receipt["document_write_boundary"] is False
    assert c7.ADMISSION_WRITE_BOUNDARY
    assert c7.MATERIAL_INGEST_OWNER != c7.DOCUMENT_CANONICAL_OWNER
