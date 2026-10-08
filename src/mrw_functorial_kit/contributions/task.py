"""Contribution metadata for the retained Runtime failure authority."""

from __future__ import annotations

from functorial_kit.contributions import (
    ContributionCatalog,
    ContributionSpec,
    define_contribution,
)
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)
from mrw_functorial_kit.core.w06_semantics import (
    capability_primitive_contract_failures,
    projection_evidence_surface_failures,
)
from mrw_functorial_kit.core.w07_semantics import runtime_failures


task_contribution = define_contribution(
    ContributionSpec[None, None](
        id="mrw.task.failure.metadata.v1",
        owner="mrw.task",
        failures=(
            runtime_failures,
            successor_capability_contract_failures,
            capability_primitive_contract_failures,
            projection_evidence_surface_failures,
        ),
    )
)

task_contribution_catalog = (task_contribution,)

contribution_catalog = ContributionCatalog(
    contributions=task_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["task_contribution_catalog", "contribution_catalog"]
