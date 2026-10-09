from contextlib import nullcontext
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from functorial_kit import Failure

from app.services.resource_pool import extract
from mrw_functorial_kit.core.provider_port_failures import resource_pool_contract_failures

pytestmark = pytest.mark.unit


def test_material_url_extraction_preserves_body_identity_for_both_pool_scopes():
    row = SimpleNamespace(id=42, uri="https://example.test/report", content="", extracted_data=None)
    for scope in ("project", "shared"):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [row]
        with (
            patch.object(extract, "bind_project", side_effect=lambda _: nullcontext()),
            patch.object(extract, "bind_schema", side_effect=lambda _: nullcontext()),
            patch.object(extract, "SessionLocal", return_value=nullcontext(session)),
            patch.object(extract, "_append_urls_batch", return_value=(1, 0)) as append,
        ):
            result = extract.extract_from_materials(project_key="demo", scope=scope, material_ids=[42])
        assert result["materials_scanned"] == 1
        assert append.call_args.args[1] == [("https://example.test/report", {"material_id": 42})]
        assert append.call_args.args[2:4] == ("material", scope)


def test_append_urls_batch_constructs_the_native_pool_entity_for_each_scope():
    for scope, project_key in (("project", "demo"), ("shared", None)):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None

        result = extract._append_urls_batch(
            session,
            [("https://example.test/report", {"material_id": 42})],
            "material",
            scope,
            project_key,
        )

        assert result == (1, 0)
        row = session.add.call_args.args[0]
        assert row.url == "https://example.test/report"
        assert row.domain == "example.test"
        assert row.source == "material"
        assert row.source_ref == {"material_id": 42}
        if scope == "project":
            assert row.project_key == "demo"


def test_resource_extract_classifies_malformed_record_fields():
    cases = (
        (extract._try_record_int, SimpleNamespace(id=True), "id", "integer", "bool"),
        (extract._try_record_int, SimpleNamespace(id=None), "id", "integer", "NoneType"),
        (extract._try_record_text, SimpleNamespace(uri=7), "uri", "text or null", "int"),
        (extract._try_record_text, SimpleNamespace(job_type=[]), "job_type", "text or null", "list"),
    )

    for parse, row, field, expected, actual in cases:
        failure = parse(row, field)

        assert isinstance(failure, Failure)
        assert resource_pool_contract_failures.matches(failure)
        assert failure.code == "record_field_type_invalid"
        assert failure.context == {
            "actual": actual,
            "expected": expected,
            "field": field,
            "operation": "extract_resource_urls",
            "owner": "resource_pool.extract.record_parser",
            "public_exception": "TypeError",
            "public_message": failure.message,
            "record_type": "SimpleNamespace",
            "witness": "test:test_resource_extract_classifies_malformed_record_fields",
        }


def test_resource_extract_preserves_type_error_abi_cause_and_no_write():
    cases = (
        (
            extract.extract_from_materials,
            SimpleNamespace(id=True, uri=None, content=None, extracted_data=None),
            "SimpleNamespace.id must be an integer",
        ),
        (
            extract.extract_from_materials,
            SimpleNamespace(id=42, uri=7, content=None, extracted_data=None),
            "SimpleNamespace.uri must be text or null",
        ),
        (
            extract.extract_from_tasks,
            SimpleNamespace(id=None, job_type="crawl", params={}),
            "SimpleNamespace.id must be an integer",
        ),
        (
            extract.extract_from_tasks,
            SimpleNamespace(id=42, job_type=7, params={}),
            "SimpleNamespace.job_type must be text or null",
        ),
    )

    for operation, row, message in cases:
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [row]
        with (
            patch.object(extract, "bind_project", side_effect=lambda _: nullcontext()),
            patch.object(extract, "SessionLocal", return_value=nullcontext(session)) as session_local,
            patch.object(extract, "_append_urls_batch") as append,
            pytest.raises(TypeError, match=f"^{re.escape(message)}$") as captured,
        ):
            operation(project_key="demo")

        assert isinstance(captured.value.__cause__, TypeError)
        assert str(captured.value.__cause__) == message
        assert session_local.call_count == 1
        append.assert_not_called()
        session.add.assert_not_called()
        session.commit.assert_not_called()
