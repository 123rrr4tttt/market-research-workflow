"""Generic business survey project (default when no project exists)."""
from __future__ import annotations

from dataclasses import dataclass

from ...defaults import DefaultProjectCustomization


@dataclass(slots=True)
class BusinessSurveyCustomization(DefaultProjectCustomization):
    """Default project for first install: generic business survey."""

    project_key: str = "business_survey"
