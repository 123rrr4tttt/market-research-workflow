from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.services.document_queries.identity import document_identity, material_identity
from app.services.information_topology.document_materials import project_document_materials, read_document


pytestmark = pytest.mark.unit


def _session_returning(document: object) -> Session:
    session = MagicMock(spec=Session)
    session.execute.return_value.scalar_one_or_none.return_value = document
    return session


def test_read_document_accepts_exact_canonical_and_legacy_material_addresses() -> None:
    document = SimpleNamespace(id=42)
    session = _session_returning(document)

    assert read_document(session, "demo", material_identity("demo", 42)) is document
    assert read_document(session, "demo", document_identity("demo", 42)) is document
    assert read_document(session, "demo", {**material_identity("demo", 42), "extra": "forged"}) is None
    assert session.execute.call_count == 2


def test_project_document_materials_hydrates_only_the_derived_read_model() -> None:
    document = SimpleNamespace(
        id=42,
        title="Canonical material",
        uri="https://example.test/material/42",
        summary="Evidence summary",
        status="active",
        updated_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        text_hash=None,
    )
    session = _session_returning(document)
    wire = {
        "kind": "information_topology.state.v1",
        "elements": [
            {
                "ref": {
                    "ref": {
                        "project_key": "demo",
                        "module_id": "materials",
                        "namespace": "materials",
                        "type_id": "material",
                        "local_id": "placement-1",
                    },
                    "observed_revision": "r1",
                },
                "attributes": {"material_ref": document_identity("demo", 42)},
                "endpoints": [],
            }
        ],
    }

    projected = project_document_materials(session, "demo", wire)
    attrs = projected["elements"][0]["attributes"]

    assert attrs["material_ref"] == material_identity("demo", 42)
    assert "material_id" not in attrs
    assert attrs["title"] == "Canonical material"
    assert attrs["material_revision"] == "2026-10-06T00:00:00+00:00"
    assert wire["elements"][0]["attributes"] == {"material_ref": document_identity("demo", 42)}
