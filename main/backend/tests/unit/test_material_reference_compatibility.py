from datetime import datetime, timezone
import pytest

from app.successor_runtime.capabilities import build_first_specimen_bundle, build_first_specimen_catalog
from app.successor_runtime.language.combinators import build_first_specimen_program, default_registries
from app.successor_runtime.research.sources import SourceRef, material_locator_identity

pytestmark = pytest.mark.unit


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
