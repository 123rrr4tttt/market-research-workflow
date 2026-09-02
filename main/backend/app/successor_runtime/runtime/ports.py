"""Runtime capability ports.

This module is intentionally infrastructure-free.  Implementations live at the
outer boundary; importing database, broker, filesystem, or legacy adapters here
would invert the dependency direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol, TypeAlias, runtime_checkable

from .admission import CommitIntent, VerificationBinding
from .assignments import RuntimeAssignment
from .qualification import AuthorityContext, StepAuthorizationBinding
from .recovery import NonStartProof
from .work_items import WorkItemRecord

ControlPlanePermission: TypeAlias = Literal["runtime.cross_project_claim"]
RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION: Final[ControlPlanePermission] = (
    "runtime.cross_project_claim"
)
CONTROL_PLANE_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION}
)


@dataclass(frozen=True, slots=True)
class ProjectScopeRef:
    """Server-validated project scope identity.

    Only a ``ProjectScopeResolver`` may construct this ref from the
    authenticated project binding; a bare caller-chosen ``project_key`` is
    never an acceptable scope on a Port.
    """

    project_key: str
    resolved_schema: str
    project_registry_revision: int
    incarnation: str
    scope_digest: str

    def __post_init__(self) -> None:
        if not self.project_key:
            raise ValueError("ProjectScopeRef requires project_key")
        if not self.resolved_schema:
            raise ValueError("ProjectScopeRef requires resolved_schema")
        if (
            not isinstance(self.project_registry_revision, int)
            or isinstance(self.project_registry_revision, bool)
            or self.project_registry_revision < 0
        ):
            raise ValueError("ProjectScopeRef registry_revision must be >= 0")
        if (
            not isinstance(self.incarnation, str)
            or not self.incarnation
            or self.incarnation != self.incarnation.strip()
            or len(self.incarnation) > 128
        ):
            raise ValueError(
                "ProjectScopeRef incarnation must be a non-empty canonical identity"
            )
        if len(self.scope_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.scope_digest
        ):
            raise ValueError("ProjectScopeRef scope_digest must be canonical sha256 hex")


@dataclass(frozen=True, slots=True)
class RuntimeScope:
    """Project-scoped runtime authority carried by every scoped Port call."""

    project_scope: ProjectScopeRef
    actor_id: str

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise ValueError("RuntimeScope requires actor_id")


@dataclass(frozen=True, slots=True)
class ControlPlaneScope:
    """System-created cross-project claim scope for ``WorkItemPort``."""

    system_actor_id: str
    permission: ControlPlanePermission
    authority_epoch: int

    def __post_init__(self) -> None:
        if not self.system_actor_id:
            raise ValueError("ControlPlaneScope requires system_actor_id")
        if self.permission not in CONTROL_PLANE_PERMISSIONS:
            raise ValueError(
                "ControlPlaneScope permission must be an allowed control-plane permission"
            )
        if self.authority_epoch < 0:
            raise ValueError("ControlPlaneScope authority_epoch must be >= 0")

    def require_permission(self, required: ControlPlanePermission) -> None:
        """Fail closed unless this system scope carries the exact permission.

        Claim interpreters must invoke this guard at their effect boundary before
        reading or locking cross-project work.  The scope intentionally contains
        no caller-supplied project key; project identity comes from the claimed
        server-owned work-item row and its validated registry binding.
        """

        if required not in CONTROL_PLANE_PERMISSIONS:
            raise ValueError("required permission is not a known control-plane permission")
        if self.permission != required:
            raise PermissionError(f"ControlPlaneScope lacks permission: {required}")


@dataclass(frozen=True, slots=True)
class CanonicalDocumentRead:
    """One authoritative observation of mutable legacy Document content."""

    document_id: int
    text_hash: str | None
    updated_at: datetime
    exact_bytes: bytes


@runtime_checkable
class DocumentCanonicalReadPort(Protocol):
    """Read exact Document bytes within a validated project scope."""

    def read_document(
        self, scope: RuntimeScope, document_id: int
    ) -> CanonicalDocumentRead: ...


@runtime_checkable
class ProgramCompiler(Protocol):
    def compile(self, program: object) -> object: ...


@runtime_checkable
class RuntimeUnitOfWork(Protocol):
    programs: object
    plans: object
    store: object
    work_items: "WorkItemPort"
    values: "ValueStorePort"
    qualifications: object
    resources: "ResourcePolicyPort"
    approvals: object
    commit_intents: object

    def __enter__(self) -> "RuntimeUnitOfWork": ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


@runtime_checkable
class WorkItemPort(Protocol):
    def enqueue(
        self, scope: RuntimeScope, assignment: RuntimeAssignment
    ) -> WorkItemRecord: ...
    def claim_due(
        self,
        control_scope: ControlPlaneScope,
        limit: int,
        lease: object,
        node_profile_digest: str,
        deployment_catalog_digest: str,
        authority_snapshot_digest: str,
    ) -> tuple[WorkItemRecord, ...]: ...
    def heartbeat(
        self,
        control_scope: ControlPlaneScope,
        work_item_id: str,
        lease_token: str,
        expected_revision: int,
        new_expiry: datetime,
    ) -> WorkItemRecord: ...
    def complete(
        self,
        scope: RuntimeScope,
        work_item_id: str,
        lease_token: str,
        expected_revision: int,
        result_digest: str,
    ) -> WorkItemRecord: ...
    def fail_or_reschedule(
        self,
        scope: RuntimeScope,
        work_item_id: str,
        lease_token: str,
        expected_revision: int,
        failure: object,
        next_attempt_at: datetime | None,
    ) -> WorkItemRecord: ...


@runtime_checkable
class ValueStorePort(Protocol):
    def put_inline(self, scope: object, value: object) -> object: ...
    def prepare_blob(self, scope: object, intent: object) -> object: ...
    def finalize_blob(
        self, scope: object, value_id: str, expected_revision: int, receipt: object
    ) -> object: ...
    def readback_blob(self, scope: object, value_ref: object) -> object: ...
    def get(self, scope: object, value_ref: object) -> object: ...
    def stage(self, scope: object, artifact: object) -> object: ...


@runtime_checkable
class QualificationPort(Protocol):
    def qualify(self, plan: object, authority: AuthorityContext) -> object: ...


@runtime_checkable
class AuthorityProvider(Protocol):
    def current_context(self, scope: object, actor_id: str) -> AuthorityContext: ...
    def current_step_binding(
        self, scope: object, run_id: str, step_id: str
    ) -> StepAuthorizationBinding: ...
    def current_approval(self, scope: object, approval_id: str) -> object: ...
    def current_canonical_head(
        self, scope: object, canonical_owner: str, object_id: str
    ) -> object: ...
    def is_revoked(self, scope: object, binding_digest: str, grant_epoch: int) -> bool: ...


@runtime_checkable
class EffectInterpreter(Protocol):
    interpreter_id: str
    operation_kinds: frozenset[str]

    def execute(self, step: object, context: object) -> object: ...
    def readback(self, attempt: object) -> object: ...
    def prove_not_started(self, attempt: object) -> NonStartProof | object: ...
    def cancel(self, attempt: object) -> object: ...


@runtime_checkable
class AdmissionPort(Protocol):
    def verify_and_commit(
        self,
        scope: object,
        intent: CommitIntent,
        candidate: object,
        binding: VerificationBinding,
    ) -> object: ...
    def readback_commit(self, scope: object, commit_intent_id: str) -> object: ...


@runtime_checkable
class ResourcePolicyPort(Protocol):
    def reserve(
        self, scope: object, request: object, expected_policy_epoch: int
    ) -> object: ...
    def release(self, scope: object, reservation_id: str, lease_token: str) -> None: ...
    def reap_expired(self, scope: object, now: datetime) -> tuple[str, ...]: ...


@runtime_checkable
class Projector(Protocol):
    projector_id: str
    projector_version: str
    source_kind: str

    def apply(self, scope: object, source: object, offset: object) -> object: ...
    def rebuild(self, scope: object, source: object) -> object: ...
