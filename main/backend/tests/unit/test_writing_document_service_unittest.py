from __future__ import annotations

import sys
import unittest
from pathlib import Path
from contextlib import nullcontext
from dataclasses import replace as dataclasses_replace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.projects.context import ProjectNotWritableError
    from app.services.writing import citation_service, document_service
    from app.services.writing import document_edit
    from app.services.writing.document_service import (
        WritingVersionConflictError,
        _build_conflict_details,
        _compute_etag,
        _serialize_document,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeDocument:
    def __init__(self):
        self.id = 11
        self.project_key = "demo_proj"
        self.title = "Draft"
        self.body_md = "body"
        self.status = "draft"
        self.head_version = 2
        self.etag = "etag-2"
        self.updated_by_user_id = "tester"
        self.updated_at = None
        self.created_at = None
        self.metadata_json = {}


class WritingDocumentServiceUnitTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing document service tests require backend dependencies: {_IMPORT_ERROR}")

    def test_compute_etag_changes_with_version(self):
        first = _compute_etag(body_md="body", version=1)
        second = _compute_etag(body_md="body", version=2)
        self.assertNotEqual(first, second)

    def test_build_conflict_details(self):
        details = _build_conflict_details(_FakeDocument(), expected_version=1)
        self.assertEqual(details["conflict_code"], "VERSION_CONFLICT")
        self.assertEqual(details["expected_version"], 1)
        self.assertEqual(details["current_version"], 2)

    def test_version_conflict_error_carries_snapshot(self):
        exc = WritingVersionConflictError(expected_version=1, current_version=2, server_snapshot={"conflict_code": "VERSION_CONFLICT"})
        self.assertEqual(exc.expected_version, 1)
        self.assertEqual(exc.current_version, 2)
        self.assertEqual(exc.server_snapshot["conflict_code"], "VERSION_CONFLICT")

    def test_serialize_document_uses_view_shape(self):
        serialized = _serialize_document(_FakeDocument())
        self.assertEqual(serialized["id"], 11)
        self.assertEqual(serialized["version"], 2)
        self.assertEqual(serialized["etag"], "etag-2")

    def test_upsert_citations_persists_the_canonical_source_material_identity(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = True

        def _run(operation, **_kwargs):
            return operation(session)

        with (
            patch.object(citation_service, "run_with_session_retry", side_effect=_run),
            patch.object(
                citation_service,
                "serialize_writing_citation",
                side_effect=lambda row: {"source_material_id": row.source_material_id},
            ),
        ):
            saved = citation_service.upsert_citations(
                doc_id=11,
                project_key="demo_proj",
                citations=[{"source_material_id": 42, "card_id": "card-1"}],
            )

        row = session.add.call_args.args[0]
        self.assertEqual(row.source_material_id, 42)
        self.assertEqual(saved, [{"source_material_id": 42}])

    def test_archived_project_rejects_each_writing_mutation_before_effect(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = False
        project = {"project_key": "demo_proj"}
        document = {**project, "doc_id": 11}
        operations = (
            (document_service.create_document, {**project, "title": "Draft"}),
            (document_service.delete_document, document),
            (document_service.save_document_with_conflict, {**document, "body_md": "Edit"}),
            (document_service.save_draft_autosave, {
                **document, "draft_body_md": "Draft", "autosave_token": "token",
            }),
            (citation_service.upsert_citations, {**document, "citations": []}),
        )

        def run(operation, **_kwargs):
            return operation(session)

        with (
            patch.object(document_service, "run_with_session_retry", side_effect=run),
            patch.object(citation_service, "run_with_session_retry", side_effect=run),
        ):
            for mutate, arguments in operations:
                with self.subTest(mutate=mutate.__name__):
                    session.reset_mock()
                    with self.assertRaisesRegex(ProjectNotWritableError, "restore it before writing"):
                        mutate(**arguments)
                    session.execute.assert_called_once()
                    query, bindings = session.execute.call_args.args
                    self.assertIn("public.projects", str(query))
                    self.assertIn("FOR SHARE", str(query))
                    self.assertEqual(bindings, project)
                    session.add.assert_not_called()
                    session.flush.assert_not_called()

    def test_native_writing_operation_definitions_drive_schema_and_dispatch(self):
        self.assertEqual(
            document_edit.writing_edit_operation_schema()["enum"],
            [
                "append",
                "prepend",
                "after_heading",
                "replace_text",
                "replace_range",
                "insert_at_offset",
                "insert_after_text",
                "insert_before_text",
            ],
        )
        self.assertEqual(
            document_edit.apply_writing_body_operation(
                "First\n\nSecond",
                operation="append",
                content_md="Third",
            ),
            "First\n\nSecond\n\nThird\n",
        )
        self.assertEqual(
            document_edit.apply_writing_body_operation(
                "abcdef",
                operation="replace_range",
                content_md="XY",
                range_start=2,
                range_end=5,
            ),
            "ab\n\nXY\n\nf\n",
        )

    def test_remaining_native_writing_operations_keep_their_special_kernels(self):
        from functorial_kit import Failure

        body = "# Head\n\nOld\n\nTail"
        cases = (
            ("prepend", {"content_md": "Top"}, "Top\n\n# Head\n\nOld\n\nTail\n"),
            (
                "after_heading",
                {"content_md": "New", "anchor_heading": "Head"},
                "# Head\n\n\nNew\n\nOld\n\nTail\n",
            ),
            (
                "replace_text",
                {"content_md": "New", "anchor_text": "Old"},
                "# Head\n\nNew\n\nTail",
            ),
            (
                "insert_at_offset",
                {"content_md": "X", "cursor_offset": 3},
                "# H\n\nX\n\nead\n\nOld\n\nTail\n",
            ),
            (
                "insert_after_text",
                {"content_md": "New", "anchor_text": "Old"},
                "# Head\n\nOld\n\nNew\n\nTail\n",
            ),
            (
                "insert_before_text",
                {"content_md": "New", "anchor_text": "Old"},
                "# Head\n\nNew\n\nOld\n\nTail\n",
            ),
        )
        for operation, kwargs, expected in cases:
            with self.subTest(operation=operation):
                self.assertEqual(
                    document_edit.apply_writing_body_operation(
                        body, operation=operation, **kwargs
                    ),
                    expected,
                )

        failures = (
            ("after_heading", {"content_md": "New"}, "writing_anchor_required"),
            ("replace_text", {"content_md": "New"}, "writing_anchor_required"),
            ("insert_at_offset", {"content_md": "New"}, "writing_cursor_offset_required"),
            ("insert_after_text", {"content_md": "New"}, "writing_anchor_required"),
            ("insert_before_text", {"content_md": "New"}, "writing_anchor_required"),
            (
                "replace_range",
                {"content_md": "New", "range_start": 2, "range_end": 99},
                "writing_range_invalid",
            ),
        )
        for operation, kwargs, code in failures:
            with self.subTest(operation=operation, failure=code):
                outcome = document_edit.apply_writing_body_operation(
                    body, operation=operation, **kwargs
                )
                self.assertIsInstance(outcome, Failure)
                self.assertEqual(outcome.code, code)

    def test_edit_document_append_reaches_original_writer_and_readback(self):
        from unittest.mock import patch

        current = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Market brief",
            "body_md": "Existing analysis",
            "version": 4,
            "etag": "etag-4",
            "metadata_json": {},
        }
        saved = {
            **current,
            "body_md": "Existing analysis\n\nNew paragraph\n",
            "version": 5,
            "etag": "etag-5",
        }
        command = document_edit.EditDocumentCommand(
            project_key="demo_proj",
            call_id="call-writing",
            content_md="New paragraph",
            operation="append",
            doc_id=7,
            base_version=4,
            if_match="etag-4",
            idempotency_key="stable-writing-key",
            source_refs=("record:94",),
            provenance={"message_id": "message-94"},
        )
        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=current),
            patch.object(
                document_edit, "save_document_with_conflict", return_value=saved
            ) as mocked_save,
        ):
            result = document_edit.edit_document(command)

        mocked_save.assert_called_once()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.structured_content["document"]["version"], 5)
        self.assertEqual(result.structured_content["agent_update"]["idempotency_key"], "stable-writing-key")
        metadata = mocked_save.call_args.kwargs["metadata_json"]
        self.assertEqual(metadata["agent_update_count"], 1)
        self.assertNotIn("idempotency_identity", metadata["agent_updates"][0])

    def test_replay_preserves_original_idempotency_key_semantics(self):
        from unittest.mock import patch

        current = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Market brief",
            "body_md": "Existing analysis\n\nFirst insert\n",
            "version": 5,
            "etag": "etag-5",
            "metadata_json": {},
        }
        saved = {**current, "version": 6, "etag": "etag-6"}
        command = document_edit.EditDocumentCommand(
            project_key="demo_proj",
            call_id="call-first",
            content_md="First insert",
            operation="replace_range",
            doc_id=7,
            range_start=19,
            range_end=19,
            base_version=5,
            if_match="etag-5",
            idempotency_key="stable-writing-key",
            provenance={"message_id": "message-94"},
        )
        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=dict(current, metadata_json={"agent_updates": []})),
            patch.object(document_edit, "save_document_with_conflict", return_value=saved),
        ):
            first = document_edit.edit_document(command)

        applied = first.structured_content["agent_update"]
        replay_current = {**current, "metadata_json": {"agent_updates": [applied]}}
        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=replay_current),
            patch.object(document_edit, "save_document_with_conflict", return_value=saved) as mocked_save,
        ):
            replayed = document_edit.edit_document(
                dataclasses_replace(command, call_id="call-retry")
            )

        self.assertTrue(replayed.structured_content["replayed"])
        mocked_save.assert_not_called()

        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=replay_current),
            patch.object(document_edit, "save_document_with_conflict", return_value=saved) as mocked_save,
        ):
            changed = document_edit.edit_document(
                dataclasses_replace(command, call_id="call-changed", content_md="Changed insert")
            )

        self.assertTrue(changed.structured_content["replayed"])
        mocked_save.assert_not_called()

    def test_default_idempotency_key_uses_original_ten_fields(self):
        command = document_edit.EditDocumentCommand(
            project_key="demo_proj",
            call_id="call-default-key",
            content_md="New paragraph",
            operation="replace_range",
            doc_id=7,
            anchor_heading="Head",
            anchor_text="Old",
            range_start=2,
            range_end=5,
            cursor_offset=9,
            selection_snapshot={"text": "Old", "start": 2, "end": 5},
            provenance={"session_id": "session-1"},
        )
        current = {"id": 7, "title": "Market brief"}
        expected = document_edit._stable_hash(
            {
                "session_anchor": "session-1",
                "doc_id": 7,
                "operation": "replace_range",
                "anchor_heading": "Head",
                "anchor_text": "Old",
                "range_start": 2,
                "range_end": 5,
                "cursor_offset": 9,
                "selection": {
                    "text": "Old",
                    "start": 2,
                    "end": 5,
                },
                "content_hash": document_edit._stable_hash({"content_md": "New paragraph"}),
            }
        )
        self.assertEqual(
            document_edit._agent_writing_idempotency_key(
                command=command,
                current=current,
                content_md="New paragraph",
                operation="replace_range",
            ),
            expected,
        )

    def test_preview_precedes_version_lock_and_conflict_readback_is_preserved(self):
        from unittest.mock import patch

        current = {
            "id": 7,
            "project_key": "demo_proj",
            "title": "Market brief",
            "body_md": "Existing analysis",
            "version": 4,
            "etag": "etag-4",
            "metadata_json": {},
        }
        command = document_edit.EditDocumentCommand(
            project_key="demo_proj",
            call_id="call-writing",
            content_md="New paragraph",
            operation="append",
            doc_id=7,
            dry_run=True,
        )
        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=current),
            patch.object(document_edit, "save_document_with_conflict") as mocked_save,
        ):
            preview = document_edit.edit_document(command)

        self.assertEqual(preview.status, "completed")
        self.assertTrue(preview.structured_content["dry_run"])
        mocked_save.assert_not_called()

        conflict = WritingVersionConflictError(
            expected_version=3,
            current_version=4,
            server_snapshot={"conflict_code": "VERSION_CONFLICT", "version": 4},
        )
        with (
            patch.object(document_edit, "bind_project", return_value=nullcontext()),
            patch.object(document_edit, "get_document", return_value=current),
            patch.object(
                document_edit, "save_document_with_conflict", side_effect=conflict
            ) as mocked_save,
        ):
            failed = document_edit.edit_document(
                dataclasses_replace(command, dry_run=False, base_version=3)
            )

        mocked_save.assert_called_once()
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error["code"], "writing_version_conflict")
        self.assertEqual(failed.structured_content["conflict"]["version"], 4)


if __name__ == "__main__":
    unittest.main()
