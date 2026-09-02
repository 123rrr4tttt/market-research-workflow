"""Family-local PostgreSQL command/query adapters for the C9 facade.

The command adapter reserves the exact request through the shared
``runtime_idempotency`` root inside the caller transaction.  A PostgreSQL
advisory transaction lock serializes concurrent duplicates for the same
project/capability/command id; the first exact reservation is durable and
every later exact duplicate returns the same receipt.  A changed body raises
a typed conflict and never submits a second command.  No provider, network,
index or rebuild effect runs here.  The query adapter is read-only and reads
the active ``runtime_projection_offsets`` row only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, select, text
from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.facade_contracts import (
    C9_ROLLBACK_TRANSITION_CONTRACT,
    C9CommandBaseConflict,
    C9CommandBlocked,
    C9CommandConflict,
    C9ContractViolation,
    C9TransactionFatal,
    C9Unavailable,
    CommandReceipt,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionCandidateValueV2,
    ProjectionResponseMetaV2,
    ProjectionSnapshotDataV2,
    QueryResult,
    validate_command_v2,
    validate_query_v2,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.qualification import AuthorityContext
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrantRepository,
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.idempotency import (
    IdempotencyBinding,
    IdempotencyRepository,
)
from app.successor_runtime.substrate.postgres.models import (
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
)
from app.successor_runtime.substrate.postgres.values import (
    ReceiptRepository,
    ValueRepository,
)

__all__ = [
    "C9_CAPABILITY_ID",
    "PostgresC9CommandRepository",
    "PostgresC9QueryRepository",
    "derive_c9_receipt_ref",
]

C9_CAPABILITY_ID = "capability:successor-runtime:c9"
_C9_OPERATION_KIND_PREFIX = "successor.runtime.c9."
_ADVISORY_LOCK_PREFIX = "mrw.c9.submission."
_C9_LOCAL_SINK_OBJECT_TYPES: Mapping[str, str] = {
    "agent_session": "AgentSessionLocalProjection.v1",
    "graph": "GraphLocalProjection.v1",
    "search": "SearchLocalProjection.v1",
}
_EXPECTED_BASE_PATTERN = re.compile(
    r"^generation:(?P<generation>[0-9]+)\|revision:(?P<revision>[0-9]+)\|"
    r"incarnation:(?P<incarnation>[A-Za-z0-9][A-Za-z0-9._:/-]{0,127})$"
)


def derive_c9_receipt_ref(row: Mapping[str, Any]) -> str:
    """Return the durable receipt ref bound to the canonical idempotency row."""

    return f"c9-receipt:{row['idempotency_id']}"


def _binding(command: FacadeCommandV2) -> IdempotencyBinding:
    return IdempotencyBinding(
        idempotency_id=f"idem:c9:{command.command_id}",
        capability_id=C9_CAPABILITY_ID,
        logical_request_id=command.command_id,
        operation_kind=f"{_C9_OPERATION_KIND_PREFIX}{command.command_kind}",
        request_digest=command.idempotency_key,
        run_id=None,
    )


def _command_source_key(command: FacadeCommandV2) -> ProjectionOffsetKey:
    payload = dict(command.payload)
    try:
        return ProjectionOffsetKey(
            projector_id=str(payload["projector_id"]),
            projector_version=str(payload["projector_version"]),
            source_kind=str(payload["source_kind"]),
            source_ref=str(payload["source_ref"]),
            source_incarnation=str(payload["source_incarnation"]),
        )
    except KeyError as exc:
        raise C9ContractViolation(
            "command payload lacks exact projector/source identity"
        ) from exc


def _parse_expected_base(token: str) -> tuple[int, int, str]:
    match = _EXPECTED_BASE_PATTERN.fullmatch(token)
    if match is None:
        raise C9ContractViolation("expected_base_token has an invalid format")
    return (
        int(match.group("generation")),
        int(match.group("revision")),
        match.group("incarnation"),
    )


def _require_effect_authority(
    connection: Connection,
    scope: RuntimeScope,
    command: FacadeCommandV2,
    *,
    canonical_base_revision: int,
    canonical_incarnation: str,
) -> AuthorityContext:
    """Reuse the existing scope/grant/approval authority boundary."""

    if command.project_scope_ref != scope.project_scope:
        raise C9CommandBlocked(
            "command scope does not exactly match the repository RuntimeScope"
        )
    if command.actor_ref != scope.actor_id:
        raise C9CommandBlocked("command actor does not match the server-resolved actor")
    try:
        ProjectScopeRegistryRepository(connection, scope).require_current()
    except (RecordNotFound, ExactBindingConflict) as exc:
        raise C9CommandBlocked("project scope binding is stale or absent") from exc
    approval_refs = (command.approval_locator,) if command.approval_locator else ()
    try:
        context = PostgresAuthorityProvider(connection, scope).current_context(
            command.actor_ref,
            capability_id=C9_CAPABILITY_ID,
            approval_refs=approval_refs,
            canonical_base_revision=canonical_base_revision,
            canonical_incarnation=canonical_incarnation,
        )
    except (ExactBindingConflict, RecordNotFound) as exc:
        raise C9CommandBlocked(str(exc)) from exc
    for approval_ref in approval_refs:
        approval = ApprovalRepository(connection, scope).load(approval_ref)
        if approval["payload_digest"] != command.idempotency_key:
            raise C9CommandBlocked(
                "approval does not bind the exact command request digest"
            )
    grants = AuthorityGrantRepository(connection, scope).current_for(
        actor_id=command.actor_ref,
        capability_id=C9_CAPABILITY_ID,
        at=datetime.now(UTC),
    )
    if not grants:
        raise C9CommandBlocked("no active authority grant for command capability")
    covered_kinds: set[str] = set()
    for grant in grants:
        operation_scope = grant.get("operation_scope_json")
        if isinstance(operation_scope, Mapping):
            covered_kinds.update(
                str(kind) for kind in operation_scope.get("operation_kinds", [])
            )
    if command.command_kind not in covered_kinds:
        raise C9CommandBlocked(
            "authority grant does not cover the requested command kind"
        )
    return context


def _command_receipt_id(command_id: str) -> str:
    return f"c9:command-receipt:{sha256_hex(command_id)[:16]}"


def _command_receipt_content(
    *,
    receipt_ref: str,
    command: FacadeCommandV2,
    context: AuthorityContext,
    canonical_base_revision: int,
    canonical_incarnation: str,
) -> dict[str, Any]:
    return {
        "schema_version": "mrw.successor.c9.command-receipt.v1",
        "receipt_ref": receipt_ref,
        "command_id": command.command_id,
        "request_digest": command.idempotency_key,
        "authority_context_digest": context.context_digest,
        "grant_epoch": int(context.grant_epoch),
        "grants_digest": context.grants_digest,
        "approval_refs": list(context.approval_refs),
        "canonical_base_revision": canonical_base_revision,
        "canonical_incarnation": canonical_incarnation,
    }


def _receipt_from_row(
    row: Mapping[str, Any],
    *,
    command: FacadeCommandV2,
    state: str,
) -> CommandReceipt:
    content = row["receipt_json"]
    if not isinstance(content, Mapping):
        raise C9CommandConflict("persisted command receipt payload is malformed")
    return CommandReceipt(
        receipt_ref=str(content["receipt_ref"]),
        command_id=str(content["command_id"]),
        request_digest=str(content["request_digest"]),
        state=state,  # type: ignore[arg-type]
        idempotency_id=f"idem:c9:{command.command_id}",
        logical_request_id=command.command_id,
        run_id=None,
        authority_context_digest=str(content["authority_context_digest"]),
        grant_epoch=int(content["grant_epoch"]),
        grants_digest=str(content["grants_digest"]),
        observed_at=(
            row["outcome_time"].astimezone(UTC).isoformat()
            if row["outcome_time"]
            else None
        ),
    )


class PostgresC9CommandRepository:
    """One durable submission per exact scope/command intent."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        tables: ProjectTables | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        if tables is None:
            metadata = MetaData(schema=scope.project_scope.resolved_schema)
            tables = project_tables(metadata, scope.project_scope.resolved_schema)
        self.tables = tables

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        if not validate_command_v2(command).valid:
            raise C9ContractViolation("invalid v2 facade command")
        if command.project_scope_ref != self.scope.project_scope:
            raise C9CommandBlocked(
                "command scope does not exactly match the repository RuntimeScope"
            )
        if command.actor_ref != self.scope.actor_id:
            raise C9CommandBlocked(
                "command actor does not match the server-resolved actor"
            )
        project_key = self.scope.project_scope.project_key
        lock_key = (
            f"{_ADVISORY_LOCK_PREFIX}{project_key}.{C9_CAPABILITY_ID}."
            f"{command.command_id}"
        )
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )
        key = _command_source_key(command)
        receipt_id = _command_receipt_id(command.command_id)
        receipt_table = self.tables.successor_receipts
        existing = (
            self.connection.execute(
                select(receipt_table).where(
                    receipt_table.c.project_key == project_key,
                    receipt_table.c.receipt_id == receipt_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            persisted_content = existing["receipt_json"]
            if not isinstance(persisted_content, Mapping):
                raise C9CommandConflict(
                    "persisted command receipt payload is malformed"
                )
            if sha256_hex(persisted_content) != existing["receipt_digest"]:
                raise C9CommandConflict("persisted command receipt digest drift")
            try:
                persisted_binding = IdempotencyRepository(
                    self.connection, self.scope
                ).load(C9_CAPABILITY_ID, command.command_id)
            except RecordNotFound as exc:
                raise C9CommandConflict(
                    "persisted command receipt lacks an idempotency binding"
                ) from exc
            state = str(persisted_binding["state"])
            persisted = _receipt_from_row(existing, command=command, state=state)
            if persisted.request_digest != command.idempotency_key:
                raise C9CommandConflict(
                    "persisted command receipt request digest drift"
                )
            return persisted
        # First-time request: the full authority/approval/scope/base validation
        # must complete before reservation, so a typed rejection leaves zero
        # idempotency/receipt residue and cannot occupy the command id.
        offset_row = ProjectionOffsetRepository(
            self.connection, self.scope
        ).load_source(key)
        if command.expected_base_token is not None:
            expected = _parse_expected_base(command.expected_base_token)
            observed = None
            if offset_row is not None:
                observed = (
                    int(offset_row["projection_generation"]),
                    int(offset_row["revision"]),
                    str(offset_row["source_incarnation"]),
                )
            if observed != expected:
                raise C9CommandBaseConflict(
                    "expected base token does not match the active projection offset"
                )
        canonical_base_revision = (
            int(offset_row["projection_generation"]) if offset_row is not None else 0
        )
        canonical_incarnation = (
            str(offset_row["source_incarnation"])
            if offset_row is not None
            else self.scope.project_scope.incarnation
        )
        context = _require_effect_authority(
            self.connection,
            self.scope,
            command,
            canonical_base_revision=canonical_base_revision,
            canonical_incarnation=canonical_incarnation,
        )
        binding = _binding(command)
        savepoint = self.connection.begin_nested()
        try:
            try:
                row = IdempotencyRepository(self.connection, self.scope).reserve(
                    binding
                )
            except ExactBindingConflict as exc:
                raise C9CommandConflict(
                    "command id is already bound to a different request body"
                ) from exc
            state = str(row["state"])
            receipt_ref = derive_c9_receipt_ref(row)
            content = _command_receipt_content(
                receipt_ref=receipt_ref,
                command=command,
                context=context,
                canonical_base_revision=canonical_base_revision,
                canonical_incarnation=canonical_incarnation,
            )
            observed_at = datetime.now(UTC)
            ReceiptRepository(self.connection, self.tables).put_exact(
                scope=self.scope,
                receipt_id=receipt_id,
                receipt_digest=sha256_hex(content),
                delivery_intent_ref=f"c9-command-submission:{project_key}",
                attempt_ref=f"c9-submission:{command.command_id}",
                provider_locator=(
                    f"local:postgres:{self.scope.project_scope.resolved_schema}:commands"
                ),
                content=content,
                outcome_time=observed_at,
            )
            try:
                savepoint.commit()
            except Exception:
                if savepoint.is_active:
                    savepoint.rollback()
                    raise
                # ACK lost after a real commit: readback-first before mapping.
                committed = self._readback_committed_receipt(
                    command=command,
                    project_key=project_key,
                    receipt_id=receipt_id,
                )
                if committed is not None:
                    return committed
                raise
        except C9TransactionFatal:
            raise
        except Exception:
            if savepoint.is_active:
                savepoint.rollback()
            raise
        return _receipt_from_row(
            {
                "receipt_json": content,
                "outcome_time": observed_at,
            },
            command=command,
            state=state,
        )

    def _readback_committed_receipt(
        self,
        *,
        command: FacadeCommandV2,
        project_key: str,
        receipt_id: str,
    ) -> CommandReceipt | None:
        """Exact readback after an ACK-lost commit; fatal on partial state."""

        receipt_table = self.tables.successor_receipts
        receipt = (
            self.connection.execute(
                select(receipt_table).where(
                    receipt_table.c.project_key == project_key,
                    receipt_table.c.receipt_id == receipt_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        try:
            binding = IdempotencyRepository(self.connection, self.scope).load(
                C9_CAPABILITY_ID, command.command_id
            )
        except RecordNotFound:
            binding = None
        if receipt is None:
            if binding is not None:
                raise C9TransactionFatal(
                    "partial committed submission: idempotency exists without receipt"
                )
            return None
        if binding is None:
            raise C9TransactionFatal(
                "inconsistent committed submission: receipt without idempotency"
            )
        content = receipt["receipt_json"]
        if not isinstance(content, Mapping):
            raise C9TransactionFatal("committed receipt payload is malformed")
        if sha256_hex(content) != receipt["receipt_digest"]:
            raise C9TransactionFatal("committed receipt digest drift")
        if content.get("command_id") != command.command_id:
            raise C9TransactionFatal("committed receipt command identity drift")
        if content.get("request_digest") != command.idempotency_key:
            raise C9TransactionFatal("committed receipt request digest drift")
        if binding["request_digest"] != command.idempotency_key:
            raise C9TransactionFatal("committed idempotency request digest drift")
        if not content.get("authority_context_digest") or not content.get(
            "grants_digest"
        ):
            raise C9TransactionFatal("committed receipt lacks authority provenance")
        return _receipt_from_row(receipt, command=command, state=str(binding["state"]))


class PostgresC9QueryRepository:
    """Read-only snapshot of the active projection offset for one source."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        tables: ProjectTables | None = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        if tables is None:
            metadata = MetaData(schema=scope.project_scope.resolved_schema)
            tables = project_tables(metadata, scope.project_scope.resolved_schema)
        self.tables = tables

    def read(self, query: FacadeQueryV2) -> QueryResult:
        if not validate_query_v2(query).valid:
            raise C9ContractViolation("invalid v2 facade query")
        if query.project_scope_ref != self.scope.project_scope:
            raise C9CommandBlocked(
                "query scope does not exactly match the repository RuntimeScope"
            )
        if query.actor_ref != self.scope.actor_id:
            raise C9CommandBlocked(
                "query actor does not match the server-resolved actor"
            )
        try:
            ProjectScopeRegistryRepository(
                self.connection, self.scope
            ).require_current()
        except (RecordNotFound, ExactBindingConflict) as exc:
            raise C9CommandBlocked("project scope binding is stale or absent") from exc
        if query.query_kind != "projection_snapshot":
            raise C9Unavailable(f"query kind is not supported: {query.query_kind}")
        params = dict(query.params)
        projection_id = params.get("projection_id")
        if not projection_id:
            raise C9Unavailable("projection snapshot query requires projection_id")
        try:
            key = ProjectionOffsetKey(
                projector_id=params["projector_id"],
                projector_version=params["projector_version"],
                source_kind=params.get("source_kind", "successor_values"),
                source_ref=params["source_ref"],
                source_incarnation=params["source_incarnation"],
            )
        except KeyError as exc:
            raise C9Unavailable(
                "projection snapshot query is missing source identity"
            ) from exc
        row = ProjectionOffsetRepository(self.connection, self.scope).load_source(key)
        if row is None:
            raise C9Unavailable("active projection offset not found")
        generation = int(row["projection_generation"])
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=str(projection_id),
            project_scope_ref=self.scope.project_scope,
            projector_id=str(row["projector_id"]),
            projector_version=str(row["projector_version"]),
            source_kind=str(row["source_kind"]),
            source_ref=str(row["source_ref"]),
            source_incarnation=str(row["source_incarnation"]),
            projection_generation=generation,
            offset_revision=int(row["revision"]),
            projection_revision=generation,
            source_digest=str(row["source_digest"]),
            cursor=int(row["source_revision"]),
        )
        snapshot = ProjectionSnapshotDataV2(
            projection_id=str(projection_id),
            projector_id=str(row["projector_id"]),
            projector_version=str(row["projector_version"]),
            source_kind=str(row["source_kind"]),
            source_ref=str(row["source_ref"]),
            source_incarnation=str(row["source_incarnation"]),
            projection_generation=generation,
            offset_revision=int(row["revision"]),
            projection_revision=generation,
            source_digest=str(row["source_digest"]),
            cursor=int(row["source_revision"]),
            offset_ref=str(row["offset_ref"]),
            candidate_values=self._projection_candidates(key, generation),
            rollback_transition=self._rollback_transition(
                key,
                generation,
                int(row["revision"]),
            ),
        )
        return QueryResult(
            data=snapshot,
            meta=meta,
        )

    def _projection_candidates(
        self,
        key: ProjectionOffsetKey,
        generation: int,
    ) -> tuple[ProjectionCandidateValueV2, ...]:
        """Exact one-candidate-per-required-sink readback with full verification."""

        table = self.tables.successor_values
        rows = (
            self.connection.execute(
                select(table).where(
                    table.c.project_key == self.scope.project_scope.project_key,
                    table.c.object_type.in_(
                        tuple(_C9_LOCAL_SINK_OBJECT_TYPES.values())
                    ),
                    table.c.provenance_json["projector_id"].as_string()
                    == key.projector_id,
                    table.c.provenance_json["projector_version"].as_string()
                    == key.projector_version,
                    table.c.provenance_json["source_kind"].as_string()
                    == key.source_kind,
                    table.c.provenance_json["source_ref"].as_string() == key.source_ref,
                    table.c.provenance_json["source_incarnation"].as_string()
                    == key.source_incarnation,
                    table.c.provenance_json["projection_generation"].as_integer()
                    == generation,
                )
            )
            .mappings()
            .all()
        )
        by_object_type: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            by_object_type.setdefault(str(row["object_type"]), []).append(row)
        candidates: list[ProjectionCandidateValueV2] = []
        for sink, object_type in _C9_LOCAL_SINK_OBJECT_TYPES.items():
            matches = by_object_type.get(object_type, [])
            if not matches:
                raise C9Unavailable(f"required projection candidate missing: {sink}")
            if len(matches) != 1:
                raise C9Unavailable(f"required projection candidate collision: {sink}")
            candidates.append(self._verify_candidate(matches[0], key, generation, sink))
        return tuple(candidates)

    def _verify_candidate(
        self,
        row: Mapping[str, Any],
        key: ProjectionOffsetKey,
        generation: int,
        sink: str,
    ) -> ProjectionCandidateValueV2:
        value_id = str(row["value_id"])
        revision = int(row["revision"])
        incarnation = str(row["incarnation"])
        content_digest = str(row["content_digest"])
        byte_size = int(row["byte_size"])
        provenance = row["provenance_json"]
        if not isinstance(provenance, Mapping):
            raise C9Unavailable(
                f"required projection candidate provenance missing: {sink}"
            )
        expected_provenance = {
            "projector_id": key.projector_id,
            "projector_version": key.projector_version,
            "source_kind": key.source_kind,
            "source_ref": key.source_ref,
            "source_incarnation": key.source_incarnation,
            "projection_generation": generation,
            "sink": sink,
        }
        for field, expected in expected_provenance.items():
            if provenance.get(field) != expected:
                raise C9Unavailable(
                    f"required projection candidate provenance drift: {sink}.{field}"
                )
        envelope = row["content_json"]
        if not isinstance(envelope, Mapping):
            raise C9Unavailable(
                f"required projection candidate envelope missing: {sink}"
            )
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            raise C9Unavailable(
                f"required projection candidate typed payload missing: {sink}"
            )
        try:
            exact = ValueRepository(self.connection, self.tables).get_exact(
                self.scope,
                value_id=value_id,
                expected_revision=revision,
                expected_incarnation=incarnation,
                expected_digest=content_digest,
            )
        except (
            ProjectRecordNotFound,
            ExactContentConflict,
            ProjectCASConflict,
        ) as exc:
            raise C9Unavailable(
                f"required projection candidate readback failed: {sink}"
            ) from exc
        if len(exact) != byte_size:
            raise C9Unavailable(
                f"required projection candidate byte_size drift: {sink}"
            )
        return ProjectionCandidateValueV2(
            value_id=value_id,
            value_ref=f"value:{self.scope.project_scope.resolved_schema}:{value_id}",
            content_digest=content_digest,
            byte_size=byte_size,
            sink=sink,
            payload=payload,
        )

    def _rollback_transition(
        self,
        key: ProjectionOffsetKey,
        generation: int,
        offset_revision: int,
    ) -> Mapping[str, Any] | None:
        table = self.tables.successor_receipts
        rows = (
            self.connection.execute(
                select(table).where(
                    table.c.project_key == self.scope.project_scope.project_key,
                    table.c.receipt_id.like("c9:rollback-transition:%"),
                )
            )
            .mappings()
            .all()
        )
        matches: list[Mapping[str, Any]] = []
        for row in rows:
            content = row["receipt_json"]
            if not isinstance(content, Mapping):
                continue
            if content.get("contract") != C9_ROLLBACK_TRANSITION_CONTRACT:
                continue
            if content.get("projector_id") != key.projector_id:
                continue
            if content.get("source_ref") != key.source_ref:
                continue
            to_position = content.get("to")
            if not isinstance(to_position, Mapping):
                continue
            if (
                to_position.get("projection_generation") != generation
                or to_position.get("offset_revision") != offset_revision
            ):
                continue
            if sha256_hex(content) != row["receipt_digest"]:
                raise C9Unavailable("rollback receipt digest drift")
            expected_digest = sha256_hex(
                {name: value for name, value in content.items() if name != "digest"}
            )
            if content.get("digest") != expected_digest:
                raise C9Unavailable("rollback receipt transition digest drift")
            matches.append(row)
        if len(matches) > 1:
            raise C9Unavailable("rollback transition for active offset is duplicated")
        if not matches:
            return None
        row = matches[0]
        content = row["receipt_json"]
        return dict(content)
