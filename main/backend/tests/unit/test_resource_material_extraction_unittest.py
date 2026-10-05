from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.resource_pool import extract

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
            result = extract.extract_from_documents(project_key="demo", scope=scope, document_ids=[42])
        assert result["materials_scanned"] == result["documents_scanned"] == 1
        assert append.call_args.args[1] == [("https://example.test/report", {"material_id": 42, "document_id": 42})]
        assert append.call_args.args[2:4] == ("material", scope)
