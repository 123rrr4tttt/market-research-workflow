"""C7.2 canonical CommitIntent/VerificationBinding readback tests."""

from __future__ import annotations

import pytest

from app.successor_migration.document_repository_c7 import (
    CanonicalCommitReadback,
    CommitHardDisabledError,
    CommitReadback,
    TestDocumentRepositoryC7,
    document_ref_from_readback,
)
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.capabilities.ingest_c7_interpreters import (
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


def test_test_repository_prepares_typed_readback_with_zero_writes() -> None:
    repo = TestDocumentRepositoryC7()
    binding = verification_binding()
    readback = repo.prepare(
        commit_intent(binding=binding),
        verification_binding=binding,
    )
    assert isinstance(readback, CommitReadback)
    assert readback.state == "PREPARED"
    assert readback.verification_binding_digest == binding.binding_digest
    assert repo.readback(readback.commit_intent_id) is readback
    assert repo.write_calls == 0
    assert repo.prepare_calls == 1


def test_fake_commit_is_hard_disabled() -> None:
    repo = TestDocumentRepositoryC7()
    with pytest.raises(CommitHardDisabledError):
        repo.commit({"document": "write"})
    assert repo.write_calls == 1
    assert repo.readback("commit:p4-c7:001") is None


def test_missing_commit_reads_back_as_uncommitted_not_fake_success() -> None:
    repo = TestDocumentRepositoryC7()
    assert repo.readback("ingest:missing") is None
    assert repo.write_calls == 0


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
    from app.successor_runtime.capabilities.ingest_c7_common import (
        stage_ingest_submission,
    )
    from tests.successor_runtime.p4_c7_fixture import submission

    staged = stage_ingest_submission(submission())
    assert staged.receipt["document_write_boundary"] is False
    assert c7.ADMISSION_WRITE_BOUNDARY
    assert c7.C7_INGEST_OWNER != c7.DOCUMENT_CANONICAL_OWNER
