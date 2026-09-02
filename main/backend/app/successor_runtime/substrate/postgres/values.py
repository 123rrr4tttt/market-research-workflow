"""Exact project values and immutable delivery receipt repositories."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

from .research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
    assert_table_scope,
    one_mapping,
    project_table,
    require_sha256,
    utcnow,
)


@dataclass(frozen=True, slots=True)
class StoredValue:
    value_id: str
    content_digest: str
    revision: int
    incarnation: str
    byte_size: int


def derive_value_write_intent_digest(
    *,
    project_key: str,
    value_id: str,
    object_type: str,
    codec_id: str,
    content_digest: str,
    provenance_digest: str,
    source_ref: str | None,
    expected_revision: int,
    expected_incarnation: str,
    state: str,
) -> str:
    """Bind an absent-value write to its exact identity and semantic content."""

    payload = {
        "contract": "SuccessorValueWriteIntent.v1",
        "project_key": project_key,
        "value_id": value_id,
        "object_type": object_type,
        "codec_id": codec_id,
        "content_digest": content_digest,
        "provenance_digest": provenance_digest,
        "source_ref": source_ref,
        # put_exact is an immutable absent-or-exact creation contract.  A
        # readback retry may supply stored revision 1, but it must retain the
        # original create intent rather than minting an update intent.
        "expected_revision": 0,
        "target_revision": 1,
        "incarnation": expected_incarnation,
        "state": state,
    }
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _datetime_key(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ValueRepository:
    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        *,
        value_id: str,
        object_type: str,
        codec_id: str,
        content: bytes | dict[str, Any] | list[Any],
        expected_digest: str,
        provenance_digest: str,
        expected_revision: int,
        expected_incarnation: str,
        source_ref: str | None = None,
        provenance: dict[str, Any] | None = None,
        state: str = "AVAILABLE",
        write_intent_digest: str | None = None,
        write_receipt_digest: str | None = None,
    ) -> StoredValue:
        table = project_table(self.tables, "successor_values")
        project_key = assert_table_scope(table, scope)
        exact = bytes(content) if isinstance(content, bytes) else canonical_bytes(content)
        if hashlib.sha256(exact).hexdigest() != expected_digest:
            raise ExactContentConflict("value digest does not bind exact content bytes")
        require_sha256(provenance_digest, "provenance_digest")
        expected_write_intent_digest = derive_value_write_intent_digest(
            project_key=project_key,
            value_id=value_id,
            object_type=object_type,
            codec_id=codec_id,
            content_digest=expected_digest,
            provenance_digest=provenance_digest,
            source_ref=source_ref,
            expected_revision=expected_revision,
            expected_incarnation=expected_incarnation,
            state=state,
        )
        if write_intent_digest is not None:
            require_sha256(write_intent_digest, "write_intent_digest")
            if write_intent_digest != expected_write_intent_digest:
                raise ExactContentConflict(
                    "write intent digest does not bind exact value write"
                )
        write_intent_digest = expected_write_intent_digest
        row = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == project_key, table.c.value_id == value_id
        )))
        digest_row = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == project_key, table.c.content_digest == expected_digest
        )))
        for existing in (row, digest_row):
            if existing is None:
                continue
            stored = existing["content_bytes"]
            if stored is None:
                stored = canonical_bytes(existing["content_json"])
            else:
                stored = bytes(stored)
            if stored != exact or existing["value_id"] != value_id:
                raise ExactContentConflict("same value identity/digest has different bytes")
        if row is not None:
            exact_binding = {
                "object_type": object_type,
                "codec_id": codec_id,
                "content_digest": expected_digest,
                "byte_size": len(exact),
                "source_ref": source_ref,
                "provenance_digest": provenance_digest,
                "state": state,
                "write_intent_digest": write_intent_digest,
            }
            drift = tuple(
                field
                for field, expected in exact_binding.items()
                if row[field] != expected
            )
            if drift:
                raise ExactContentConflict(
                    "existing value identity has a different exact write binding: "
                    + ", ".join(drift)
                )
            if (
                expected_revision not in {0, int(row["revision"])}
                or row["incarnation"] != expected_incarnation
            ):
                raise ProjectCASConflict("stale value revision/incarnation")
            return StoredValue(value_id, expected_digest, row["revision"], row["incarnation"], row["byte_size"])
        if expected_revision != 0:
            raise ProjectCASConflict("new exact value requires expected revision 0")
        now = utcnow()
        values = {
            "project_key": project_key,
            "value_id": value_id,
            "object_type": object_type,
            "codec_id": codec_id,
            "content_digest": expected_digest,
            "byte_size": len(exact),
            "source_ref": source_ref,
            "provenance_json": provenance or {},
            "provenance_digest": provenance_digest,
            "state": state,
            "revision": 1,
            "incarnation": expected_incarnation,
            "write_intent_digest": write_intent_digest,
            "write_receipt_digest": write_receipt_digest,
            "created_at": now,
            "updated_at": now,
        }
        if isinstance(content, bytes):
            values["content_bytes"] = exact
        else:
            values["content_json"] = content
        self.connection.execute(insert(table).values(**values))
        return StoredValue(value_id, expected_digest, 1, expected_incarnation, len(exact))

    def get_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        value_id: str,
        *,
        expected_revision: int,
        expected_incarnation: str,
        expected_digest: str,
    ) -> bytes:
        table = project_table(self.tables, "successor_values")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == project_key, table.c.value_id == value_id,
            table.c.revision == expected_revision,
            table.c.incarnation == expected_incarnation,
            table.c.content_digest == expected_digest,
        )))
        if row is None:
            raise ProjectRecordNotFound(f"exact value not found: {value_id}")
        exact = bytes(row["content_bytes"]) if row["content_bytes"] is not None else canonical_bytes(row["content_json"])
        if hashlib.sha256(exact).hexdigest() != expected_digest:
            raise ExactContentConflict("stored value content fails digest readback")
        return exact


class ReceiptRepository:
    """Immutable absent-or-exact provider receipt store."""

    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        *,
        receipt_id: str,
        receipt_digest: str,
        delivery_intent_ref: str,
        attempt_ref: str,
        provider_locator: str,
        content: bytes | dict[str, Any],
        outcome_time: datetime,
    ) -> str:
        table = project_table(self.tables, "successor_receipts")
        project_key = assert_table_scope(table, scope)
        exact = content if isinstance(content, bytes) else canonical_bytes(content)
        if hashlib.sha256(exact).hexdigest() != receipt_digest:
            raise ExactContentConflict("receipt digest does not bind exact receipt bytes")
        rows = (
            one_mapping(self.connection.execute(select(table).where(table.c.project_key == project_key, table.c.receipt_id == receipt_id))),
            one_mapping(self.connection.execute(select(table).where(table.c.project_key == project_key, table.c.receipt_digest == receipt_digest))),
        )
        for row in rows:
            if row is None:
                continue
            stored = bytes(row["receipt_bytes"]) if row["receipt_bytes"] is not None else canonical_bytes(row["receipt_json"])
            immutable = (
                row["delivery_intent_ref"], row["attempt_ref"],
                row["provider_locator"], _datetime_key(row["outcome_time"]), stored,
            )
            supplied = (
                delivery_intent_ref, attempt_ref, provider_locator,
                _datetime_key(outcome_time), exact,
            )
            if row["receipt_id"] != receipt_id or immutable != supplied:
                raise ExactContentConflict("immutable receipt identity/digest conflict")
        if rows[0] is not None:
            return receipt_id
        now = utcnow()
        values = {
            "project_key": project_key,
            "receipt_id": receipt_id,
            "receipt_digest": receipt_digest,
            "delivery_intent_ref": delivery_intent_ref,
            "attempt_ref": attempt_ref,
            "provider_locator": provider_locator,
            "outcome_time": outcome_time,
            "created_at": now,
            "updated_at": now,
        }
        if isinstance(content, bytes):
            values["receipt_bytes"] = exact
        else:
            values["receipt_json"] = content
        self.connection.execute(insert(table).values(**values))
        return receipt_id


__all__ = [
    "ReceiptRepository",
    "StoredValue",
    "ValueRepository",
    "derive_value_write_intent_digest",
]
