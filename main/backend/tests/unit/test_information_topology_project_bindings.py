from dataclasses import dataclass

from functorial_kit import Failure

from app.services.information_topology.bindings import resolve_project_semantics
from app.services.information_topology.contracts import BoundRef, ElementRef
from app.services.information_topology.profiles import ProfileSpec, TypeRule


@dataclass(frozen=True)
class ExampleProjectSemantics:
    source_ref: BoundRef
    item_type: str


def profile_for(semantics: ExampleProjectSemantics) -> ProfileSpec:
    return ProfileSpec(
        f"project.{semantics.item_type}", "1", {semantics.item_type: TypeRule()}, frozenset()
    )


class Reader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *, source_ref, observed_revision, content_digest):
        self.calls.append((source_ref, observed_revision, content_digest))
        return self.result


def test_project_semantics_parameterize_the_shared_topology_profile():
    ref = BoundRef(ElementRef("hk-water", "project", "semantics", "domain", "vocabulary"), "rev-7", "sha256:x")
    semantics = ExampleProjectSemantics(ref, "water_site")
    reader = Reader(semantics)

    binding = resolve_project_semantics(
        reader, ref, project_key="hk-water", expected_profile_id="project.water_site",
        expected_profile_version="1", profile_factory=profile_for,
    )

    assert not isinstance(binding, Failure)
    assert binding.project_key == "hk-water"
    assert binding.semantics is semantics
    assert binding.profile.types.keys() == {"water_site"}
    assert reader.calls == [(ref.ref, "rev-7", "sha256:x")]


def test_project_semantic_binding_rejects_cross_project_and_revision_drift():
    ref = BoundRef(ElementRef("project-a", "project", "semantics", "domain", "vocabulary"), "rev-7")
    other_project = BoundRef(ElementRef("project-b", "project", "semantics", "domain", "vocabulary"), "rev-7")
    reader = Reader(ExampleProjectSemantics(ref, "site"))

    cross_project = resolve_project_semantics(
        reader, other_project, project_key="project-a", expected_profile_id="project.site",
        expected_profile_version="1", profile_factory=profile_for,
    )
    stale = resolve_project_semantics(
        reader, BoundRef(ref.ref, "older"), project_key="project-a", expected_profile_id="project.site",
        expected_profile_version="1", profile_factory=profile_for,
    )

    assert isinstance(cross_project, Failure) and cross_project.code == "UNRESOLVABLE_REFERENCE"
    assert isinstance(stale, Failure) and stale.code == "STALE_REFERENCE"
    assert len(reader.calls) == 1


def test_project_semantic_binding_rejects_unregistered_profile_identity():
    ref = BoundRef(ElementRef("p", "module", "semantics", "domain", "one"), "r1")
    reader = Reader(ExampleProjectSemantics(ref, "site"))
    result = resolve_project_semantics(
        reader, ref, project_key="p", expected_profile_id="project.wrong",
        expected_profile_version="1", profile_factory=profile_for,
    )
    assert isinstance(result, Failure) and result.code == "STALE_REFERENCE"
