from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.successor_runtime.capabilities import build_first_specimen_bundle, build_first_specimen_catalog
from app.successor_runtime.language.combinators import build_first_specimen_program, default_registries
from app.successor_runtime.research.sources import SourceRef, material_locator_identity
from app.successor_runtime.runtime.facade_contracts import C9Unavailable
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres import projection_query_read_port as reader
from app.successor_runtime.substrate.postgres.c7_document_readback import DocumentRef
from app.successor_runtime.substrate.postgres.c7_projector_driver import projection_offset_key

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("source_ref", [
    "material:object:1", "document:object:1", "material://p0/object:1",
    "document://p0/object:1", "object:1",
])
def test_public_material_refs_read_one_identity(source_ref):
    assert reader._object_id_from_source_ref(source_ref, project_key="p0") == "object:1"


@pytest.mark.parametrize("source_ref", [
    "material://other/1", "document://other/1", "material://p0/",
    "material://p0/1?override=1", "document:", "material:",
])
def test_public_material_refs_reject_missing_or_wrong_project(source_ref):
    with pytest.raises(C9Unavailable):
        reader._object_id_from_source_ref(source_ref, project_key="p0")


def test_locator_alias_comparison_preserves_source_bytes_and_rejects_duplicate():
    def source(scheme):
        return SourceRef(
            source_ref_id=f"source:{scheme}:1", owner_id="owner", locator=f"{scheme}://p0/1",
            source_class="existing_project_material", observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            access_profile_ref="DocumentCanonicalReadPort",
        )
    legacy, current = source("document"), source("material")
    digest = legacy.content_digest
    assert material_locator_identity(legacy.locator) == material_locator_identity(current.locator)
    bundle = build_first_specimen_bundle()
    with pytest.raises(ValueError, match="two distinct material locators"):
        build_first_specimen_program(
            catalog=build_first_specimen_catalog(bundle.operations), program_id="duplicate",
            project_key="p0", project_scope_digest="0" * 64, registries=default_registries(),
            source_refs=(legacy, current),
        )
    assert legacy.locator == "document://p0/1"
    assert legacy.content_digest == digest


@pytest.mark.parametrize("source_ref", ["material:object:1", "document:object:1", "material://p0/object:1"])
def test_public_read_is_canonical_without_changing_persisted_projector_identity(monkeypatch, source_ref):
    scope = RuntimeScope(ProjectScopeRef("p0", "mrw_p0", 1, "scope-1", "1" * 64), "actor")
    ref = DocumentRef.from_content(
        project_key="p0", object_id="object:1", revision=1, incarnation="material-1", content_digest="2" * 64,
    )
    monkeypatch.setattr(reader.PostgresProjectionQueryReadPort, "_require_current_scope", lambda self: None)
    reads = []
    def read_document(self, object_id):
        reads.append(object_id)
        return ref
    monkeypatch.setattr(reader.C7ProjectorDriver, "read_document", read_document)
    query = SimpleNamespace(
        project_scope_ref=scope.project_scope, actor_ref=scope.actor_id, query_kind="projection_snapshot",
        meta=SimpleNamespace(project_key="p0", trace_id="trace"),
        params={
            "projector_id": reader.MATERIAL_SEARCH_PROJECTOR_ID,
            "projector_version": reader.MATERIAL_SEARCH_PROJECTOR_VERSION,
            "projection_id": reader.MATERIAL_SEARCH_PROJECTION_ID,
            "source_kind": reader.MATERIAL_CANONICAL_SOURCE_KIND,
            "source_ref": source_ref,
        },
    )
    result = reader.PostgresProjectionQueryReadPort(None, scope).read(query)
    assert reads == ["object:1"]
    assert result.meta.source_ref == result.data.source_ref == "material:object:1"
    payload = result.data.candidate_values[0].payload
    assert payload["material_ref"] == payload["document_ref"]
    assert payload["material_ref"]["schema_version"] == "mrw.runtime.document_ref.v1"
    assert payload["read_only"] and payload["no_postgres_write"]
    assert projection_offset_key("search", ref).source_ref == "document:object:1"
