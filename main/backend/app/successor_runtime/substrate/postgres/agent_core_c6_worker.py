"""Family-local PostgreSQL worker store for the P3 C6 evidence line.

The store is deliberately self-contained: it owns one table inside a
caller-created disposable schema (the family test uses the unique
``mrw_p3_c6_worker_test`` schema), uses only parameterized SQLAlchemy ``text``
statements and never touches shared successor tables, migrations or runtime
protocols.  It only accepts already-redacted receipts; raw sentinel values are
rejected at the persistence boundary.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.agent_core_c6_common import thaw_json_value
from app.successor_runtime.capabilities.checksum import content_digest, require_hex64

__all__ = [
    "AgentCoreC6WorkerStore",
    "C6WorkerSchemaError",
    "ForbiddenRawValueDetected",
    "ReceiptExactConflict",
    "ReceiptNotFound",
]


_SCHEMA_PATTERN = re.compile(r"^mrw_[a-z0-9_]+$")
_TABLE_NAME = "agent_core_c6_evidence"
_ALLOWED_CELLS = frozenset({"c6_1", "c6_2", "c6_3"})


class C6WorkerSchemaError(ValueError):
    """The disposable worker schema identifier is not family-owned."""


class ForbiddenRawValueDetected(ValueError):
    """A raw sentinel value reached the persistence boundary."""


class ReceiptExactConflict(ValueError):
    """A stored receipt id is already bound to different canonical content."""


class ReceiptNotFound(KeyError):
    """No exact receipt row exists at the requested identifier."""


class AgentCoreC6WorkerStore:
    """Store only redacted C6 receipts; raw values are rejected."""

    def __init__(self, connection: Connection, schema: str) -> None:
        if _SCHEMA_PATTERN.fullmatch(schema) is None:
            raise C6WorkerSchemaError(
                f"worker schema must match mrw_[a-z0-9_]+: {schema!r}"
            )
        self.connection = connection
        self.schema = schema
        self.table = f'"{schema}"."{_TABLE_NAME}"'

    def install(self) -> None:
        self.connection.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
        self.connection.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    receipt_id TEXT PRIMARY KEY,
                    cell TEXT NOT NULL,
                    outcome_code TEXT NOT NULL,
                    provider_calls INTEGER NOT NULL,
                    redacted_value JSONB NOT NULL,
                    receipt_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )

    def persist_receipt(
        self,
        *,
        cell: str,
        receipt_id: str,
        outcome_code: str,
        provider_calls: int,
        redacted_value: dict[str, Any],
        receipt_plain: dict[str, Any],
        forbidden_sentinel: str,
    ) -> Mapping[str, Any]:
        if cell not in _ALLOWED_CELLS:
            raise C6WorkerSchemaError(f"unsupported worker cell {cell!r}")
        if not isinstance(forbidden_sentinel, str) or not forbidden_sentinel:
            raise ValueError("forbidden_sentinel is a mandatory redaction binding")
        if not isinstance(receipt_plain, dict) or not receipt_plain:
            raise ValueError("receipt_plain is required")
        redacted_value = thaw_json_value(redacted_value)
        if (
            not isinstance(provider_calls, int)
            or isinstance(provider_calls, bool)
            or provider_calls < 0
        ):
            raise ValueError("provider_calls must be a non-negative int")
        encoded_receipt = json.dumps(
            receipt_plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        encoded_redacted = json.dumps(
            redacted_value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if (
            forbidden_sentinel in encoded_receipt
            or forbidden_sentinel in encoded_redacted
        ):
            raise ForbiddenRawValueDetected(
                "raw sentinel value reached the redacted persistence boundary"
            )
        derived_receipt_id = content_digest(receipt_plain)
        if receipt_id != derived_receipt_id:
            raise ValueError(
                "receipt_id must equal the canonical digest of receipt_plain"
            )
        self._require_receipt_digest_binding(receipt_plain)
        self._require_redaction_policy_binding(
            cell,
            receipt_plain,
            redacted_value,
        )
        existing = self._select_receipt(receipt_id)
        if existing is not None:
            if (
                existing["cell"] != cell
                or existing["outcome_code"] != outcome_code
                or int(existing["provider_calls"]) != provider_calls
                or existing["redacted_value"] != redacted_value
                or existing["receipt_json"] != receipt_plain
            ):
                raise ReceiptExactConflict(
                    "receipt id is already bound to different canonical content"
                )
            return existing
        try:
            self.connection.execute(
                sa.text(
                    f"""
                    INSERT INTO {self.table}
                        (receipt_id, cell, outcome_code, provider_calls,
                         redacted_value, receipt_json)
                    VALUES (:receipt_id, :cell, :outcome_code, :provider_calls,
                            CAST(:redacted_value AS JSONB), CAST(:receipt_json AS JSONB))
                    """
                ),
                {
                    "receipt_id": receipt_id,
                    "cell": cell,
                    "outcome_code": outcome_code,
                    "provider_calls": provider_calls,
                    "redacted_value": encoded_redacted,
                    "receipt_json": encoded_receipt,
                },
            )
        except Exception as exc:
            raced = self._select_receipt(receipt_id)
            if raced is None:
                raise
            if (
                raced["cell"] != cell
                or raced["outcome_code"] != outcome_code
                or int(raced["provider_calls"]) != provider_calls
                or raced["redacted_value"] != redacted_value
                or raced["receipt_json"] != receipt_plain
            ):
                raise ReceiptExactConflict(
                    "receipt id is already bound to different canonical content"
                ) from exc
            return raced
        return self.read_receipt(receipt_id)

    def _select_receipt(self, receipt_id: str) -> Mapping[str, Any] | None:
        row = (
            self.connection.execute(
                sa.text(
                    f"""
                SELECT receipt_id, cell, outcome_code, provider_calls,
                       redacted_value, receipt_json
                FROM {self.table}
                WHERE receipt_id = :receipt_id
                """
                ),
                {"receipt_id": receipt_id},
            )
            .mappings()
            .first()
        )
        return row

    def _require_receipt_digest_binding(
        self,
        receipt_plain: dict[str, Any],
    ) -> None:
        declared = receipt_plain.get("receipt_digest")
        require_hex64(declared, "receipt_plain.receipt_digest")
        body = {
            key: value
            for key, value in receipt_plain.items()
            if key != "receipt_digest"
        }
        if content_digest(body) != declared:
            raise ValueError("receipt_plain.receipt_digest does not bind content")

    def _require_redaction_policy_binding(
        self,
        cell: str,
        receipt_plain: dict[str, Any],
        redacted_value: dict[str, Any],
    ) -> None:
        evidence = receipt_plain.get("evidence")
        if cell == "c6_3":
            if not isinstance(evidence, dict):
                raise ValueError("c6_3 receipts require bound evidence")
            if evidence.get("raw_value_persisted") is not False:
                raise ValueError("evidence.raw_value_persisted must be false")
            policy = evidence.get("policy")
            if not isinstance(policy, dict):
                raise ValueError("evidence.policy is required")
            require_hex64(
                str(policy.get("policy_digest") or ""), "policy.policy_digest"
            )
            if evidence.get("redacted_value") != redacted_value:
                raise ValueError(
                    "evidence.redacted_value must equal the persisted redacted_value"
                )
            expected_redacted = content_digest(
                {
                    "schema": "mrw.successor.agent-core.c6-3.evidence.v1",
                    "redacted_value": redacted_value,
                }
            )
            if evidence.get("redacted_digest") != expected_redacted:
                raise ValueError(
                    "evidence.redacted_digest does not bind redacted_value"
                )
        policy_receipt = receipt_plain.get("policy_application_receipt")
        if isinstance(policy_receipt, dict) and (
            policy_receipt.get("applied_before_persistence") is not True
        ):
            raise ValueError(
                "policy_application_receipt.applied_before_persistence must be true"
            )
        if cell == "c6_3" and not isinstance(policy_receipt, dict):
            raise ValueError("c6_3 receipts require a redaction policy receipt")

    def read_receipt(self, receipt_id: str) -> Mapping[str, Any]:
        row = (
            self.connection.execute(
                sa.text(
                    f"""
                SELECT receipt_id, cell, outcome_code, provider_calls,
                       redacted_value, receipt_json
                FROM {self.table}
                WHERE receipt_id = :receipt_id
                """
                ),
                {"receipt_id": receipt_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ReceiptNotFound(receipt_id)
        return row

    def raw_sentinel_present(self, sentinel: str) -> bool:
        row = (
            self.connection.execute(
                sa.text(
                    f"""
                SELECT EXISTS (
                    SELECT 1 FROM {self.table}
                    WHERE redacted_value::text LIKE '%' || :sentinel || '%'
                       OR receipt_json::text LIKE '%' || :sentinel || '%'
                ) AS present
                """
                ),
                {"sentinel": sentinel},
            )
            .mappings()
            .first()
        )
        return bool(row["present"]) if row is not None else False

    def count_receipts(self, cell: str | None = None) -> int:
        if cell is None:
            statement = f"SELECT count(*) AS n FROM {self.table}"
            parameters: dict[str, Any] = {}
        else:
            statement = f"SELECT count(*) AS n FROM {self.table} WHERE cell = :cell"
            parameters = {"cell": cell}
        row = self.connection.execute(sa.text(statement), parameters).mappings().first()
        return int(row["n"]) if row is not None else 0
