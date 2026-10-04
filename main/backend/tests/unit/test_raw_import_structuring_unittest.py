from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.raw_import import (
        _derive_publish_date_from_extracted,
        _resolve_extraction_flags,
    )
    from app.services.ingest.structured_extraction import (
        build_structured_summary as _build_structured_summary,
    )
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class RawImportStructuringTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"raw import structuring tests require backend dependencies: {_IMPORT_ERROR}")

    def test_auto_mode_uses_comprehensive_for_raw_note(self):
        flags = _resolve_extraction_flags("auto", "raw_note")
        self.assertEqual(flags["mode"], "comprehensive")
        self.assertTrue(flags["include_policy"])
        self.assertTrue(flags["include_market"])
        self.assertTrue(flags["include_sentiment"])
        self.assertTrue(flags["include_company"])
        self.assertTrue(flags["include_product"])
        self.assertTrue(flags["include_operation"])

    def test_auto_mode_keeps_market_specific_profile(self):
        flags = _resolve_extraction_flags("auto", "market_info")
        self.assertEqual(flags["mode"], "market")
        self.assertFalse(flags["include_policy"])
        self.assertTrue(flags["include_market"])
        self.assertFalse(flags["include_sentiment"])
        self.assertTrue(flags["include_company"])
        self.assertTrue(flags["include_product"])
        self.assertTrue(flags["include_operation"])

    def test_build_structured_summary_counts_entities_relations(self):
        summary = _build_structured_summary(
            {
                "entities_relations": {
                    "entities": [{"text": "A", "type": "ORG"}, {"text": "B", "type": "LOC"}],
                    "relations": [{"subject": "A", "predicate": "affects", "object": "B"}],
                },
                "policy": {"state": "CA"},
                "company_structured": {"company_name": "ACME"},
            },
            extraction_enabled=True,
            chunks_used=3,
            extraction_mode="comprehensive",
        )
        self.assertEqual(summary["entity_count"], 2)
        self.assertEqual(summary["relation_count"], 1)
        self.assertTrue(summary["has_policy"])
        self.assertTrue(summary["has_company"])
        self.assertEqual(summary["chunks_used"], 3)
        self.assertEqual(summary["extraction_mode"], "comprehensive")

    def test_derive_publish_date_from_extracted_prefers_policy_effective_date(self):
        derived = _derive_publish_date_from_extracted(
            {
                "policy": {"effective_date": "2026-02-01"},
                "market": {"report_date": "2026-01-31"},
            }
        )
        self.assertIsNotNone(derived)
        self.assertEqual(str(derived), "2026-02-01")



class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RawImportSession:
    def __init__(self, existing=None):
        self._existing = existing
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _statement):
        return _ScalarResult(self._existing)

    def add(self, *_args, **_kwargs):
        return None

    def flush(self):
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        return None


class TestRawImportDocumentBranch:
    @pytest.fixture(autouse=True)
    def require_raw_import_imports(self):
        if _IMPORT_ERROR is not None:
            pytest.skip(f"raw import tests require backend dependencies: {_IMPORT_ERROR}")

    def _install_runtime(
        self,
        monkeypatch,
        *,
        writer_results,
    ):
        from app.services.ingest import raw_import

        session = _RawImportSession()
        envelopes = []
        completed = []
        failed = []

        def build_envelope(**kwargs):
            envelope = {"collection_payload": {}}
            envelopes.append(envelope)
            return envelope

        def frontdoor(*, ingress_envelope, run_writer):
            outcome = writer_results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(raw_import, "SessionLocal", lambda: session)
        monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 88)
        monkeypatch.setattr(
            raw_import,
            "complete_job",
            lambda job_id, status="completed", result=None: completed.append(
                (job_id, status, result)
            ),
        )
        monkeypatch.setattr(
            raw_import,
            "fail_job",
            lambda job_id, error: failed.append((job_id, error)),
        )
        monkeypatch.setattr(
            raw_import,
            "build_raw_import_ingress_envelope",
            build_envelope,
        )
        monkeypatch.setattr(raw_import, "run_postprocess_frontdoor", frontdoor)
        return raw_import, session, envelopes, completed, failed

    def test_new_document_uses_empty_extraction_base(self, monkeypatch):
        raw_import, session, envelopes, completed, failed = self._install_runtime(
            monkeypatch,
            writer_results=[
                {"data": {"writer_result": {"inserted": 1, "doc_id": 42}}}
            ],
        )
        payload = {
            "items": [
                {
                    "title": "MRW 本地启动说明摘录 2026-09-21",
                    "text": "来源当前仓库README的非空文本",
                    "doc_type": "raw_note",
                }
            ],
            "infer_from_links": False,
            "enable_extraction": False,
            "default_doc_type": "raw_note",
        }

        result = raw_import.run_raw_import_documents(payload, "local_user_20260921")

        assert result["inserted"] == 1
        assert result["error_count"] == 0
        assert failed == []
        candidate = envelopes[0]["collection_payload"]["document_candidate"]
        assert "_raw_input" in candidate["extracted_data_base"]
        assert completed == [(88, "completed", result)]
        assert session.committed

    def test_all_item_failures_mark_job_failed(self, monkeypatch):
        raw_import, _session, _envelopes, completed, failed = self._install_runtime(
            monkeypatch,
            writer_results=[RuntimeError("frontdoor writer failed")],
        )
        result = raw_import.run_raw_import_documents(
            {
                "items": [{"title": "one", "text": "one", "doc_type": "raw_note"}],
                "enable_extraction": False,
            },
            "demo",
        )

        assert result["error_count"] == 1
        assert result["errors"][0]["error"] == "frontdoor writer failed"
        assert completed[0][:2] == (88, "failed")
        assert failed == []

    def test_partial_failure_keeps_completed_batch_status(self, monkeypatch):
        raw_import, _session, _envelopes, completed, _failed = self._install_runtime(
            monkeypatch,
            writer_results=[
                {"data": {"writer_result": {"inserted": 1, "doc_id": 42}}},
                RuntimeError("frontdoor writer failed"),
            ],
        )
        result = raw_import.run_raw_import_documents(
            {
                "items": [
                    {"title": "ok", "text": "ok", "doc_type": "raw_note"},
                    {"title": "bad", "text": "bad", "doc_type": "raw_note"},
                ],
                "enable_extraction": False,
            },
            "demo",
        )

        assert result["inserted"] == 1
        assert result["error_count"] == 1
        assert completed[0][:2] == (88, "completed")

    def _install_sqlite_runtime(self, monkeypatch):
        from app.models.entities import Document, Source
        from app.services.ingest import raw_import, terminal_writer

        engine = create_engine(
            "sqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        sqlite_metadata = MetaData()
        source_table = Source.__table__.to_metadata(sqlite_metadata)
        document_table = Document.__table__.to_metadata(sqlite_metadata)
        source_table.c.id.type = Integer()
        document_table.c.id.type = Integer()
        document_table.c.extracted_data.type = JSON()
        source_table.create(engine)
        document_table.create(engine)
        TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            future=True,
            expire_on_commit=False,
        )
        monkeypatch.setattr(raw_import, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(terminal_writer, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(raw_import, "start_job", lambda *_args, **_kwargs: 99)
        monkeypatch.setattr(raw_import, "complete_job", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(raw_import, "fail_job", lambda *_args, **_kwargs: None)
        return raw_import, TestingSessionLocal

    @staticmethod
    def _payload(text, **kwargs):
        return {
            "source_name": "readiness_repair_recovery",
            "source_kind": "manual",
            "items": [{"text": text, "doc_type": "raw_note"}],
            "infer_from_links": False,
            "enable_extraction": False,
            **kwargs,
        }

    def test_repeated_real_imports_reuse_one_terminal_writer_source(self, monkeypatch):
        from app.models.entities import Document, Source

        raw_import, testing_session = self._install_sqlite_runtime(monkeypatch)

        first = raw_import.run_raw_import_documents(self._payload("first body"), "local-user")
        second = raw_import.run_raw_import_documents(self._payload("second body"), "local-user")

        assert first["inserted"] == second["inserted"] == 1
        assert first["source_name"] == second["source_name"] == "readiness_repair_recovery"
        with testing_session() as session:
            sources = session.query(Source).all()
            documents = session.query(Document).all()
            assert [(source.name, source.kind) for source in sources] == [
                ("readiness_repair_recovery", "manual")
            ]
            assert {document.content for document in documents} == {"first body", "second body"}
            assert {document.source_id for document in documents} == {sources[0].id}

    def test_existing_duplicate_sources_do_not_crash_new_import(self, monkeypatch):
        from app.models.entities import Document, Source

        raw_import, testing_session = self._install_sqlite_runtime(monkeypatch)
        with testing_session() as session:
            original = Source(
                name="readiness_repair_recovery", kind="manual", base_url="original", enabled=True
            )
            duplicate = Source(
                name="readiness_repair_recovery", kind="manual", base_url="duplicate", enabled=True
            )
            session.add_all([original, duplicate])
            session.commit()
            original_id = original.id

        result = raw_import.run_raw_import_documents(self._payload("new body"), "local-user")

        assert result["inserted"] == 1
        assert result["error_count"] == 0
        with testing_session() as session:
            assert session.query(Source).count() == 2
            document = session.query(Document).one()
            assert document.source_id == original_id

    def test_overwrite_reuses_first_matching_source_and_preserves_skip_semantics(
        self, monkeypatch
    ):
        from app.models.entities import Document, Source

        raw_import, testing_session = self._install_sqlite_runtime(monkeypatch)
        with testing_session() as session:
            original = Source(
                name="readiness_repair_recovery", kind="manual", base_url="original", enabled=True
            )
            duplicate = Source(
                name="readiness_repair_recovery", kind="manual", base_url="duplicate", enabled=True
            )
            session.add_all([original, duplicate])
            session.flush()
            document = Document(
                source_id=duplicate.id,
                doc_type="raw_note",
                content="old body",
                text_hash="old-hash",
                uri="https://example.test/readiness",
            )
            session.add(document)
            session.commit()
            original_id, duplicate_id = original.id, duplicate.id

        overwritten = raw_import.run_raw_import_documents(
            self._payload(
                "new body",
                overwrite_on_uri=True,
                items=[{
                    "text": "new body",
                    "uri": "https://example.test/readiness",
                    "doc_type": "raw_note",
                }],
            ),
            "local-user",
        )

        assert overwritten["updated"] == 1
        assert overwritten["skipped"] == 0
        with testing_session() as session:
            assert session.query(Source).count() == 2
            persisted = session.query(Document).one()
            assert persisted.content == "new body"
            assert persisted.source_id == original_id

        skipped = raw_import.run_raw_import_documents(
            self._payload(
                "newer body",
                items=[{
                    "text": "newer body",
                    "uri": "https://example.test/readiness",
                    "doc_type": "raw_note",
                }],
            ),
            "local-user",
        )

        assert skipped["updated"] == 0
        assert skipped["skipped"] == 1
        with testing_session() as session:
            persisted = session.query(Document).one()
            assert persisted.content == "new body"
            assert persisted.source_id == original_id
            assert duplicate_id != original_id


if __name__ == "__main__":
    unittest.main()
