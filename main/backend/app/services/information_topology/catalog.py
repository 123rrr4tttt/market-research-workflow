"""Project-independent declarations for the information-topology profiles.

The catalog owns profile definitions, not project topology records. Retrieval
profiles are resolved from each persisted domain-vocabulary snapshot.
"""
from __future__ import annotations

from typing import Mapping
from .modules.graph_view import graph_view_profile
from .modules.method import method_profile
from .modules.report import report_profile
from .profiles import ProfileSpec


def profile_catalog() -> Mapping[tuple[str, str], ProfileSpec]:
    profiles = (report_profile, method_profile, graph_view_profile)
    return {(profile.profile_id, profile.version): profile for profile in profiles}


__all__ = ["profile_catalog"]
