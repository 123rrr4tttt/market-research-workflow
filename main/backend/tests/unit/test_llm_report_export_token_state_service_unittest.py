from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.unit, pytest.mark.mocked]

try:
    from app.services import llm_report_export_token_state

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    llm_report_export_token_state = None
    _IMPORT_ERROR = exc


def _token_payload(**overrides):
    payload = {
        "contract_version": "llm_report.export_artifact_token.v1",
        "artifact_id": "artifact-token-state-1",
        "markdown_sha256": "a" * 64,
        "gate": {
            "decision": "pass",
            "gate_version": "test-gate-v1",
            "hard_failures": [],
            "soft_failures": [],
            "missing_items": [],
        },
        "gate_mode": "strict",
        "trace_id": "trace-token-state-1",
        "request_id": "request-token-state-1",
        "project_key": "demo_proj",
        "job_id": 7101,
        "actor_id": "analyst-1",
        "issued_at": "2026-05-24T10:00:00+00:00",
        "expires_at": "2026-05-24T11:00:00+00:00",
        "ttl_seconds": 3600,
        "one_time_use": True,
    }
    payload.update(overrides)
    return payload


def _clear_token_state_memory():
    if llm_report_export_token_state is None:
        return
    clear_fn = getattr(
        llm_report_export_token_state,
        "clear_llm_report_export_token_state_memory",
        None,
    )
    if callable(clear_fn):
        clear_fn()
    for memory_name in (
        "_LLM_REPORT_EXPORT_TOKEN_STATES",
        "_LLM_REPORT_EXPORT_TOKEN_STATE_MEMORY",
        "_USED_EXPORT_ARTIFACT_IDS",
        "_REVOKED_EXPORT_ARTIFACT_IDS",
    ):
        memory = getattr(llm_report_export_token_state, memory_name, None)
        if hasattr(memory, "clear"):
            memory.clear()


def _truthy_field(record, *names):
    for name in names:
        if isinstance(record, dict) and bool(record.get(name)):
            return True
    return False


def _record_is_used(record):
    return _truthy_field(record, "used", "is_used", "token_used", "used_at")


def _record_is_revoked(record):
    return _truthy_field(record, "revoked", "is_revoked", "token_revoked", "revoked_at")


def _first_present(record, *names):
    for name in names:
        if isinstance(record, dict) and name in record:
            return record[name]
    return None


def _stored_payload(record):
    for name in ("payload", "token_payload", "artifact_token_payload", "raw_payload"):
        value = _first_present(record, name)
        if isinstance(value, dict):
            return value
    return {}


class _NoExistingRowResult:
    def scalar_one_or_none(self):
        return None


class _NoExistingRowSession:
    def execute(self, _statement):
        return _NoExistingRowResult()

    def add(self, _row):
        return None

    def flush(self):
        return None


def _run_with_empty_session(operation, **_kwargs):
    return operation(_NoExistingRowSession())


class _StatefulRowResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _InMemoryTokenStateSession:
    def __init__(self):
        self.rows = {}
        self._pending = []

    def execute(self, statement):
        artifact_id = self._artifact_id_from_statement(statement)
        return _StatefulRowResult(self.rows.get(artifact_id))

    def add(self, row):
        self._pending.append(row)

    def flush(self):
        for row in self._pending:
            if getattr(row, "artifact_id", None):
                self.rows[row.artifact_id] = row
        self._pending.clear()

    @staticmethod
    def _artifact_id_from_statement(statement):
        try:
            params = dict(statement.compile().params)
        except Exception:  # noqa: BLE001
            params = {}
        for key, value in params.items():
            if key.startswith("artifact_id"):
                return value
        return None


class _InMemoryTokenStateStore:
    def __init__(self):
        self.session = _InMemoryTokenStateSession()

    def run_with_session_retry(self, operation, **_kwargs):
        return operation(self.session)


def _claim_fn():
    claim = getattr(
        llm_report_export_token_state,
        "claim_llm_report_export_token_use",
        None,
    )
    if not callable(claim):
        raise unittest.SkipTest("claim_llm_report_export_token_use is not implemented yet")
    return claim


def _prune_fn():
    prune = getattr(
        llm_report_export_token_state,
        "prune_llm_report_export_token_states",
        None,
    )
    if not callable(prune):
        raise unittest.SkipTest("prune_llm_report_export_token_states is not implemented yet")
    return prune


def _summary_count(summary, *names):
    for name in names:
        value = _first_present(summary, name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _summary_is_degraded(summary):
    return _truthy_field(
        summary,
        "degraded",
        "token_state_store_degraded",
        "export_token_state_store_degraded",
        "memory_fallback",
    ) or str(summary.get("status") or "").lower() in {"degraded", "degraded_success"}


def _token_state_row(
    artifact_id: str,
    *,
    used_at=None,
    revoked_at=None,
    last_seen_at=None,
):
    row = llm_report_export_token_state.LlmReportExportTokenState(artifact_id=artifact_id)
    row.actor_id = "analyst-1"
    row.project_key = "demo_proj"
    row.trace_id = f"trace-{artifact_id}"
    row.request_id = f"request-{artifact_id}"
    row.job_id = 7101
    row.used_at = used_at
    row.revoked_at = revoked_at
    row.revoke_reason = "unit-test-revoked" if revoked_at else None
    row.last_seen_at = last_seen_at or used_at or revoked_at or datetime(2026, 5, 24, tzinfo=timezone.utc)
    row.payload = {"artifact_id": artifact_id}
    row.created_at = row.last_seen_at
    row.updated_at = row.last_seen_at
    return row


class _RowsResult:
    def __init__(self, rows=None, *, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self.rowcount

    def scalar_one(self):
        return self.rowcount


class _PruneTokenStateSession:
    def __init__(self, rows):
        self.rows = {row.artifact_id: row for row in rows}
        self.deleted_artifact_ids = []
        self.executed_sql = []

    def execute(self, statement):
        sql, params = self._compiled(statement)
        self.executed_sql.append(sql)
        if sql.strip().upper().startswith("DELETE"):
            deleted = self._delete_for_statement(sql, params)
            return _RowsResult(rowcount=deleted)
        return _RowsResult(self._select_for_statement(sql, params))

    def delete(self, row):
        artifact_id = getattr(row, "artifact_id", None)
        if artifact_id in self.rows:
            self.deleted_artifact_ids.append(artifact_id)
            del self.rows[artifact_id]

    def flush(self):
        return None

    def commit(self):
        return None

    def remaining_ids(self):
        return set(self.rows)

    def _select_for_statement(self, sql, params):
        if "llm_report_export_token_states" not in sql:
            return []
        cutoff = self._cutoff_from_params(params)
        if cutoff is None or ("used_at" not in sql and "revoked_at" not in sql):
            return list(self.rows.values())
        return [row for row in self.rows.values() if self._is_prunable(row, cutoff)]

    def _delete_for_statement(self, sql, params):
        cutoff = self._cutoff_from_params(params)
        if cutoff is not None and ("used_at" in sql or "revoked_at" in sql):
            to_delete = [row for row in self.rows.values() if self._is_prunable(row, cutoff)]
        else:
            to_delete = list(self.rows.values())
        for row in to_delete:
            self.delete(row)
        return len(to_delete)

    @staticmethod
    def _compiled(statement):
        try:
            compiled = statement.compile()
            return str(compiled), dict(compiled.params)
        except Exception:  # noqa: BLE001
            return str(statement), {}

    @staticmethod
    def _cutoff_from_params(params):
        datetimes = [value for value in params.values() if isinstance(value, datetime)]
        if not datetimes:
            return None
        return min(datetimes)

    @staticmethod
    def _is_prunable(row, cutoff):
        used_at = getattr(row, "used_at", None)
        revoked_at = getattr(row, "revoked_at", None)
        return bool(
            (isinstance(used_at, datetime) and used_at < cutoff)
            or (isinstance(revoked_at, datetime) and revoked_at < cutoff)
        )


class _PruneTokenStateStore:
    def __init__(self, rows):
        self.session = _PruneTokenStateSession(rows)

    def run_with_session_retry(self, operation, **_kwargs):
        return operation(self.session)


class LlmReportExportTokenStateServiceTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                f"llm report export token state service tests require service implementation: {_IMPORT_ERROR}"
            )
        _clear_token_state_memory()

    def tearDown(self):
        _clear_token_state_memory()

    def test_mark_used_persists_required_record_fields(self):
        payload = _token_payload()
        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=_run_with_empty_session,
            create=True,
        ):
            recorded = llm_report_export_token_state.mark_llm_report_export_token_used_persistent(payload)

        self.assertIsInstance(recorded, dict)
        self.assertEqual(recorded["artifact_id"], "artifact-token-state-1")
        self.assertTrue(_record_is_used(recorded))
        self.assertFalse(_record_is_revoked(recorded))
        self.assertEqual(recorded["trace_id"], "trace-token-state-1")
        self.assertEqual(recorded["request_id"], "request-token-state-1")
        self.assertEqual(recorded["project_key"], "demo_proj")
        self.assertEqual(recorded["actor_id"], "analyst-1")
        self.assertEqual(recorded["job_id"], 7101)
        self.assertIn("used_at", recorded)
        self.assertFalse(
            _truthy_field(
                recorded,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertEqual(_stored_payload(recorded).get("artifact_id"), "artifact-token-state-1")
        self.assertEqual(_stored_payload(recorded).get("one_time_use"), True)

    def test_revoke_persists_required_record_fields(self):
        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=_run_with_empty_session,
            create=True,
        ):
            recorded = llm_report_export_token_state.revoke_llm_report_export_token_persistent(
                "artifact-token-revoked-1",
                actor_id="admin-1",
                reason="operator_revoked",
                payload={"request_id": "request-revoke-1", "trace_id": "trace-revoke-1"},
            )

        self.assertIsInstance(recorded, dict)
        self.assertEqual(recorded["artifact_id"], "artifact-token-revoked-1")
        self.assertTrue(_record_is_revoked(recorded))
        self.assertFalse(_record_is_used(recorded))
        self.assertEqual(
            _first_present(recorded, "revoked_by_actor_id", "revoked_actor_id", "actor_id"),
            "admin-1",
        )
        self.assertEqual(
            _first_present(recorded, "revocation_reason", "revoke_reason", "reason"),
            "operator_revoked",
        )
        self.assertIn("revoked_at", recorded)
        self.assertFalse(
            _truthy_field(
                recorded,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertEqual(_stored_payload(recorded).get("request_id"), "request-revoke-1")
        self.assertEqual(_stored_payload(recorded).get("trace_id"), "trace-revoke-1")

    def test_is_used_and_is_revoked_query_memory_backed_state(self):
        used_payload = _token_payload(artifact_id="artifact-token-used-query")
        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=RuntimeError("db unavailable in unit test"),
            create=True,
        ):
            used_record = llm_report_export_token_state.mark_llm_report_export_token_used_persistent(used_payload)
            revoked_record = llm_report_export_token_state.revoke_llm_report_export_token_persistent(
                "artifact-token-revoked-query",
                actor_id="admin-1",
                reason="operator_revoked",
                payload={"trace_id": "trace-revoked-query"},
            )
            used_state = llm_report_export_token_state.get_llm_report_export_token_state(
                "artifact-token-used-query"
            )
            revoked_state = llm_report_export_token_state.get_llm_report_export_token_state(
                "artifact-token-revoked-query"
            )
            missing_state = llm_report_export_token_state.get_llm_report_export_token_state(
                "artifact-token-missing-query"
            )
            used_query = llm_report_export_token_state.is_llm_report_export_token_used(
                "artifact-token-used-query"
            )
            used_revoked_query = llm_report_export_token_state.is_llm_report_export_token_revoked(
                "artifact-token-used-query"
            )
            revoked_query = llm_report_export_token_state.is_llm_report_export_token_revoked(
                "artifact-token-revoked-query"
            )
            missing_used_query = llm_report_export_token_state.is_llm_report_export_token_used(
                "artifact-token-missing-query"
            )
            missing_revoked_query = llm_report_export_token_state.is_llm_report_export_token_revoked(
                "artifact-token-missing-query"
            )

        self.assertTrue(
            _truthy_field(
                used_record,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertTrue(
            _truthy_field(
                revoked_record,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertTrue(used_query)
        self.assertFalse(used_revoked_query)
        self.assertTrue(revoked_query)
        self.assertFalse(missing_used_query)
        self.assertFalse(missing_revoked_query)
        self.assertEqual(used_state["artifact_id"], "artifact-token-used-query")
        self.assertTrue(_record_is_used(used_state))
        self.assertEqual(revoked_state["artifact_id"], "artifact-token-revoked-query")
        self.assertTrue(_record_is_revoked(revoked_state))
        self.assertIsNone(missing_state)

    def test_database_unavailable_degrades_without_raising(self):
        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=RuntimeError("db down"),
            create=True,
        ):
            used_record = llm_report_export_token_state.mark_llm_report_export_token_used_persistent(
                _token_payload(artifact_id="artifact-token-db-down-used")
            )
            revoked_record = llm_report_export_token_state.revoke_llm_report_export_token_persistent(
                "artifact-token-db-down-revoked",
                actor_id="admin-1",
                reason="db_down_smoke",
                payload={"request_id": "request-db-down"},
            )

        self.assertEqual(used_record["artifact_id"], "artifact-token-db-down-used")
        self.assertEqual(revoked_record["artifact_id"], "artifact-token-db-down-revoked")
        self.assertTrue(
            _truthy_field(
                used_record,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertTrue(
            _truthy_field(
                revoked_record,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertIn("degraded_reason", used_record)
        self.assertIn("degraded_reason", revoked_record)

    def test_claim_first_use_marks_artifact_claimed_with_used_at(self):
        claim = _claim_fn()
        store = _InMemoryTokenStateStore()

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            claimed = claim(_token_payload(artifact_id="artifact-token-claim-first"))

        self.assertIsInstance(claimed, dict)
        self.assertEqual(claimed["artifact_id"], "artifact-token-claim-first")
        self.assertIs(claimed.get("claimed"), True)
        self.assertIn("used_at", claimed)
        self.assertTrue(claimed.get("used_at"))
        self.assertFalse(claimed.get("already_used", False))
        self.assertFalse(claimed.get("revoked", False))
        self.assertFalse(
            _truthy_field(
                claimed,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )

    def test_claim_same_artifact_second_time_reports_already_used(self):
        claim = _claim_fn()
        store = _InMemoryTokenStateStore()
        payload = _token_payload(artifact_id="artifact-token-claim-repeat")

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            first_claim = claim(payload)
            second_claim = claim(payload)

        self.assertIs(first_claim.get("claimed"), True)
        self.assertEqual(second_claim["artifact_id"], "artifact-token-claim-repeat")
        self.assertIs(second_claim.get("claimed"), False)
        self.assertIs(second_claim.get("already_used"), True)
        self.assertFalse(second_claim.get("revoked", False))
        self.assertTrue(_record_is_used(second_claim))

    def test_claim_revoked_artifact_reports_revoked_without_claiming(self):
        claim = _claim_fn()
        store = _InMemoryTokenStateStore()

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            revoked_record = llm_report_export_token_state.revoke_llm_report_export_token_persistent(
                "artifact-token-claim-revoked",
                actor_id="admin-1",
                reason="operator_revoked",
                payload={"trace_id": "trace-claim-revoked"},
            )
            claimed = claim(_token_payload(artifact_id="artifact-token-claim-revoked"))

        self.assertTrue(_record_is_revoked(revoked_record))
        self.assertEqual(claimed["artifact_id"], "artifact-token-claim-revoked")
        self.assertIs(claimed.get("claimed"), False)
        self.assertIs(claimed.get("revoked"), True)
        self.assertFalse(claimed.get("already_used", False))
        self.assertTrue(_record_is_revoked(claimed))

    def test_claim_database_unavailable_uses_memory_fallback_once_then_rejects_repeat(self):
        claim = _claim_fn()
        payload = _token_payload(artifact_id="artifact-token-claim-db-down")

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=RuntimeError("db down"),
            create=True,
        ):
            first_claim = claim(payload)
            second_claim = claim(payload)

        self.assertIs(first_claim.get("claimed"), True)
        self.assertEqual(first_claim["artifact_id"], "artifact-token-claim-db-down")
        self.assertIn("used_at", first_claim)
        self.assertTrue(first_claim.get("used_at"))
        self.assertTrue(
            _truthy_field(
                first_claim,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )
        self.assertIs(second_claim.get("claimed"), False)
        self.assertIs(second_claim.get("already_used"), True)
        self.assertTrue(
            _truthy_field(
                second_claim,
                "degraded",
                "token_state_store_degraded",
                "export_token_state_store_degraded",
            )
        )

    def test_prune_dry_run_counts_expired_used_and_revoked_without_deleting(self):
        prune = _prune_fn()
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        store = _PruneTokenStateStore(
            [
                _token_state_row("artifact-token-prune-used-old", used_at=now - timedelta(days=45)),
                _token_state_row("artifact-token-prune-revoked-old", revoked_at=now - timedelta(days=60)),
                _token_state_row("artifact-token-prune-used-fresh", used_at=now - timedelta(days=3)),
                _token_state_row("artifact-token-prune-active-old", last_seen_at=now - timedelta(days=90)),
            ]
        )

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            summary = prune(retention_days=30, dry_run=True, now=now)

        self.assertIsInstance(summary, dict)
        self.assertIs(summary.get("dry_run"), True)
        self.assertEqual(
            _summary_count(summary, "candidate_count", "eligible_count", "matched_count", "would_delete_count"),
            2,
        )
        self.assertEqual(_summary_count(summary, "deleted_count", "deleted", "pruned_count"), 0)
        self.assertEqual(
            store.session.remaining_ids(),
            {
                "artifact-token-prune-used-old",
                "artifact-token-prune-revoked-old",
                "artifact-token-prune-used-fresh",
                "artifact-token-prune-active-old",
            },
        )

    def test_prune_execution_deletes_expired_used_and_revoked_states(self):
        prune = _prune_fn()
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        store = _PruneTokenStateStore(
            [
                _token_state_row("artifact-token-prune-delete-used", used_at=now - timedelta(days=45)),
                _token_state_row("artifact-token-prune-delete-revoked", revoked_at=now - timedelta(days=45)),
                _token_state_row("artifact-token-prune-keep-used-fresh", used_at=now - timedelta(days=2)),
            ]
        )

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            summary = prune(retention_days=30, dry_run=False, now=now)

        self.assertIsInstance(summary, dict)
        self.assertIs(summary.get("dry_run"), False)
        self.assertEqual(
            _summary_count(summary, "candidate_count", "eligible_count", "matched_count", "would_delete_count"),
            2,
        )
        self.assertEqual(_summary_count(summary, "deleted_count", "deleted", "pruned_count"), 2)
        self.assertEqual(store.session.remaining_ids(), {"artifact-token-prune-keep-used-fresh"})

    def test_prune_execution_keeps_active_state_even_when_last_seen_is_expired(self):
        prune = _prune_fn()
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        store = _PruneTokenStateStore(
            [
                _token_state_row("artifact-token-prune-active-expired", last_seen_at=now - timedelta(days=120)),
                _token_state_row("artifact-token-prune-used-expired", used_at=now - timedelta(days=120)),
            ]
        )

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=store.run_with_session_retry,
            create=True,
        ):
            summary = prune(retention_days=30, dry_run=False, now=now)

        self.assertEqual(_summary_count(summary, "deleted_count", "deleted", "pruned_count"), 1)
        self.assertEqual(store.session.remaining_ids(), {"artifact-token-prune-active-expired"})

    def test_prune_database_unavailable_uses_memory_fallback_degraded_without_raising(self):
        prune = _prune_fn()
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        old_used_payload = _token_payload(
            artifact_id="artifact-token-prune-memory-used",
            used_at=(now - timedelta(days=45)).isoformat(),
            last_seen_at=(now - timedelta(days=45)).isoformat(),
        )

        with patch(
            "app.services.llm_report_export_token_state.run_with_session_retry",
            side_effect=RuntimeError("db down"),
            create=True,
        ):
            llm_report_export_token_state.mark_llm_report_export_token_used_persistent(old_used_payload)
            summary = prune(retention_days=30, dry_run=False, now=now)

        self.assertIsInstance(summary, dict)
        self.assertFalse(summary.get("dry_run", True))
        self.assertTrue(_summary_is_degraded(summary))
        self.assertGreaterEqual(_summary_count(summary, "candidate_count", "eligible_count", "matched_count") or 0, 1)


if __name__ == "__main__":
    unittest.main()
