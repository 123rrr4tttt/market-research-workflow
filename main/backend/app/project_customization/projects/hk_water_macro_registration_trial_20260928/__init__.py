from .customization import HkWaterMacroRegistrationTrialCustomization
from ..hk_water_investigation.customization import HkWaterInvestigationCustomization

PROJECT_CUSTOMIZATION_CLASS = HkWaterMacroRegistrationTrialCustomization
PROJECT_KEY_PREFIX_ALIASES: list[str] = []

__all__ = [
    "HkWaterInvestigationCustomization",
    "HkWaterMacroRegistrationTrialCustomization",
    "PROJECT_CUSTOMIZATION_CLASS",
    "PROJECT_KEY_PREFIX_ALIASES",
]
