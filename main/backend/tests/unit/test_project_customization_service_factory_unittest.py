from __future__ import annotations

from typing import cast

import pytest

from app.project_customization.defaults import DefaultProjectCustomization
from app.project_customization.projects.business_survey.customization import BusinessSurveyCustomization
from app.project_customization.projects.demo_proj import PROJECT_KEY_PREFIX_ALIASES as DEMO_PREFIX_ALIASES
from app.project_customization.projects.hk_water_investigation.customization import (
    HkWaterInvestigationCustomization,
)
from app.project_customization.projects.hk_water_macro_registration_trial_20260928.customization import (
    HkWaterMacroRegistrationTrialCustomization,
)
from app.project_customization.interfaces import CustomizationJsonObject, ProjectCustomization
from app.project_customization.registry import register_project_customization
from app.project_customization.service import _factory_for  # pyright: ignore[reportPrivateUsage]
from app.project_customization.service import get_project_customization
from app.subprojects.demo_proj.extraction_adapter import DemoProjExtractionAdapter
from app.subprojects.registry import get_extraction_adapter


HK_TRIAL_KEY = "hk_water_macro_registration_trial_20260928"


class _LongPrefixCustomization(DefaultProjectCustomization):
    project_key = "long_prefix"


class _ShortPrefixCustomization(DefaultProjectCustomization):
    project_key = "short_prefix"


class _AlternateExtractionAdapter(DemoProjExtractionAdapter):
    pass


def _graph_projections(customization: ProjectCustomization) -> list[CustomizationJsonObject]:
    field_mapping = cast(
        dict[str, list[CustomizationJsonObject]],
        customization.get_field_mapping(),
    )
    return field_mapping["graph_projections"]


def test_project_customization_factory_rejects_invalid_plugin() -> None:
    class InvalidCustomization:
        pass

    factory = _factory_for(InvalidCustomization)

    with pytest.raises(
        TypeError,
        match="project customization class does not implement ProjectCustomization",
    ):
        factory()


def test_builtin_customizations_preserve_default_exact_and_historical_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.project_customization.registry as registry
    import app.project_customization.service as service

    monkeypatch.setattr(registry, "_REGISTRY", {})
    monkeypatch.setattr(registry, "_PREFIX_REGISTRY", [])
    monkeypatch.setattr(service, "_bootstrapped", False)

    default = get_project_customization("business_survey")
    demo = get_project_customization("demo_proj")
    embodied = get_project_customization(DEMO_PREFIX_ALIASES[0])
    unknown = get_project_customization("unregistered_project")

    assert default.project_key == "business_survey"
    assert demo.project_key == "demo_proj"
    assert embodied.project_key == "demo_proj"
    assert unknown.project_key == "default"


def test_customization_prefixes_select_longest_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.project_customization.registry as registry

    monkeypatch.setattr(registry, "_REGISTRY", {})
    monkeypatch.setattr(registry, "_PREFIX_REGISTRY", [])

    registry.register_project_customization_prefix("emb", lambda: _ShortPrefixCustomization())
    registry.register_project_customization_prefix("embodied", lambda: _LongPrefixCustomization())

    assert isinstance(
        registry.get_project_customization_factory("embodied_ai_trial")(),
        _LongPrefixCustomization,
    )


def test_hk_trial_reuses_recipe_without_borrowing_hk_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.project_customization.registry as registry
    import app.project_customization.service as service

    monkeypatch.setattr(registry, "_REGISTRY", {})
    monkeypatch.setattr(registry, "_PREFIX_REGISTRY", [])
    monkeypatch.setattr(service, "_bootstrapped", False)

    hk = get_project_customization("hk_water_investigation")
    trial = get_project_customization(HK_TRIAL_KEY)
    hk_projection = _graph_projections(hk)[0]
    trial_projection = _graph_projections(trial)[0]
    trial_projection["label"] = "trial scope"

    assert isinstance(hk, HkWaterInvestigationCustomization)
    assert not isinstance(hk, HkWaterMacroRegistrationTrialCustomization)
    assert hk.project_key == "hk_water_investigation"
    assert isinstance(trial, HkWaterMacroRegistrationTrialCustomization)
    assert trial.project_key == HK_TRIAL_KEY
    assert hk_projection["label"] == "总图"
    assert trial_projection["label"] == "trial scope"


def test_duplicate_customization_registration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.project_customization.registry as registry

    monkeypatch.setattr(
        registry,
        "_REGISTRY",
        {"duplicate": lambda: BusinessSurveyCustomization()},
    )
    monkeypatch.setattr(
        registry,
        "_PREFIX_REGISTRY",
        [("embodied", lambda: BusinessSurveyCustomization())],
    )

    with pytest.raises(ValueError, match="^project customization already registered: duplicate$"):
        register_project_customization("duplicate", lambda: BusinessSurveyCustomization())
    with pytest.raises(ValueError, match="^project customization prefix already registered: embodied$"):
        registry.register_project_customization_prefix(
            "embodied",
            lambda: BusinessSurveyCustomization(),
        )


def test_extraction_adapter_keeps_exact_prefix_and_traversal_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.subprojects.registry as registry
    from app.services.projects.context import bind_project

    monkeypatch.setattr(registry, "_EXACT_REGISTRY", {})
    monkeypatch.setattr(registry, "_PREFIX_REGISTRY", {})
    monkeypatch.setattr(registry, "_bootstrapped", False)

    with bind_project("demo_proj"):
        exact = get_extraction_adapter()
    with bind_project("embodied_ai_trial"):
        prefix = get_extraction_adapter()
    with bind_project("unregistered_project"):
        fallback = get_extraction_adapter()

    registry.register_extraction_adapter_prefix("aa", DemoProjExtractionAdapter)
    registry.register_extraction_adapter_prefix("ab", _AlternateExtractionAdapter)
    with bind_project("aa_project"):
        traversal = get_extraction_adapter()

    assert isinstance(exact, DemoProjExtractionAdapter)
    assert isinstance(prefix, DemoProjExtractionAdapter)
    assert not isinstance(fallback, DemoProjExtractionAdapter)
    assert isinstance(traversal, DemoProjExtractionAdapter)
    assert not isinstance(traversal, _AlternateExtractionAdapter)

    with pytest.raises(ValueError, match="^extraction adapter already registered: demo_proj$"):
        registry.register_extraction_adapter("demo_proj", DemoProjExtractionAdapter)
    with pytest.raises(ValueError, match="^extraction adapter prefix already registered: embodied$"):
        registry.register_extraction_adapter_prefix("embodied", DemoProjExtractionAdapter)
