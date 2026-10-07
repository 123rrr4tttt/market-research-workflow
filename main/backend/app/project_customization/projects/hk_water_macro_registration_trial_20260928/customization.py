from __future__ import annotations

from dataclasses import dataclass

from ...projects.hk_water_investigation.customization import HkWaterInvestigationCustomization


@dataclass(slots=True)
class HkWaterMacroRegistrationTrialCustomization(HkWaterInvestigationCustomization):
    """Trial registration scope reusing the immutable HK water recipe."""

    project_key: str = "hk_water_macro_registration_trial_20260928"
