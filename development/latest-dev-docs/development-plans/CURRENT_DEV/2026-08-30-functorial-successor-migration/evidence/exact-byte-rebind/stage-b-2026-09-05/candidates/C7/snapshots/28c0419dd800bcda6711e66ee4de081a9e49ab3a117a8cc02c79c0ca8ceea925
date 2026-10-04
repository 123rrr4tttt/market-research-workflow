"""C7.2 canonical commit-intent readback and DocumentRef contracts.

This adapter reuses the canonical runtime ``CommitIntent`` and
``VerificationBinding`` contracts.  The C7 test fake prepares typed readback
only; canonical commit is hard-disabled, so no ``Document`` write can occur
through this family-local slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.successor_runtime.capabilities.ingest_c7_common import (
    DOCUMENT_CANONICAL_OWNER,
)
from app.successor_runtime.runtime.admission import (
    CommitIntent,
    CommitIntentState,
    VerificationBinding,
)
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.substrate.postgres.c7_document_readback import (
    CanonicalCommitReadback,
    DocumentRef,
    document_ref_from_readback,
)

__all__ = [
    "DOCUMENT_CANONICAL_OWNER",
    "CanonicalCommitReadback",
    "CanonicalDocumentReadPort",
    "CanonicalDocumentState",
    "CommitHardDisabledError",
    "CommitReadback",
    "DocumentRef",
    "DocumentRepositoryC7",
    "TestDocumentRepositoryC7",
    "document_ref_from_intent",
    "document_ref_from_readback",
]


class CommitHardDisabledError(RuntimeError):
    """Raised because the C7 ahead-of-time slice never commits documents."""


@dataclass(frozen=True, slots=True)
class CanonicalDocumentState:
    project_key: str
    object_id: str
    revision: int
    incarnation: str
    content_digest: str
    canonical_commit_ref: str


@runtime_checkable
class CanonicalDocumentReadPort(Protocol):
    """Read-only canonical Document port used by C7 projectors."""

    def read_document(self, object_id: str) -> CanonicalDocumentState | None: ...


@dataclass(frozen=True, slots=True)
class CommitReadback:
    commit_intent_id: str
    capability_id: str
    project_key: str
    object_id: str
    content_digest: str
    verification_binding_digest: str
    state: str
    readback_digest: str = ""

    def __post_init__(self) -> None:
        if self.readback_digest == "":
            object.__setattr__(
                self,
                "readback_digest",
                canonical_digest(
                    {
                        "commit_intent_id": self.commit_intent_id,
                        "capability_id": self.capability_id,
                        "project_key": self.project_key,
                        "object_id": self.object_id,
                        "content_digest": self.content_digest,
                        "verification_binding_digest": (
                            self.verification_binding_digest
                        ),
                        "state": self.state,
                    }
                ),
            )


@runtime_checkable
class DocumentRepositoryC7(Protocol):
    """Readback-only C7.2 surface; no Document write is declared."""

    def prepare(
        self,
        intent: CommitIntent,
        *,
        verification_binding: VerificationBinding,
    ) -> CommitReadback: ...

    def readback(self, commit_intent_id: str) -> CommitReadback | None: ...

    @property
    def write_calls(self) -> int: ...


def document_ref_from_intent(intent: CommitIntent) -> DocumentRef:
    return DocumentRef.from_content(
        project_key=intent.project_key,
        object_id=intent.object_id,
        revision=intent.expected_base_revision,
        incarnation=intent.expected_incarnation,
        content_digest=intent.content_digest,
    )


class TestDocumentRepositoryC7:
    """In-memory test double; prepares typed readback but never commits."""

    __test__ = False  # application double, not a pytest test class

    def __init__(self) -> None:
        self._readbacks: dict[str, CommitReadback] = {}
        self._write_calls = 0
        self.prepare_calls = 0

    @property
    def write_calls(self) -> int:
        return self._write_calls

    def prepare(
        self,
        intent: CommitIntent,
        *,
        verification_binding: VerificationBinding,
    ) -> CommitReadback:
        self.prepare_calls += 1
        if intent.verification_binding_digest != verification_binding.binding_digest:
            raise ValueError("verification binding drift before readback")
        readback = CommitReadback(
            commit_intent_id=intent.commit_intent_id,
            capability_id=intent.canonical_owner,
            project_key=intent.project_key,
            object_id=intent.object_id,
            content_digest=intent.content_digest,
            verification_binding_digest=verification_binding.binding_digest,
            state=CommitIntentState.PREPARED.value,
        )
        self._readbacks[intent.commit_intent_id] = readback
        return readback

    def readback(self, commit_intent_id: str) -> CommitReadback | None:
        return self._readbacks.get(commit_intent_id)

    def commit(self, *_args: object, **_kwargs: object) -> None:
        """Hard-disabled canonical commit; any call is a scaffold violation."""

        self._write_calls += 1
        raise CommitHardDisabledError(
            "C7 ahead-of-time scaffolding never commits documents"
        )
