"""Explicit kit contribution catalog for the retained source failure metadata."""

from __future__ import annotations

from functorial_kit.contributions import (
    ContributionCatalog,
    ContributionSpec,
    define_contribution,
)
from mrw_functorial_kit.core.source_semantics import source_contract_failures
from mrw_functorial_kit.core.w06_semantics import (
    source_provider_acquisition_failures,
    source_runtime_binding_failures,
    source_single_source_guard_failures,
)


source_contribution = define_contribution(
    ContributionSpec[None, None](
        id="mrw.source.failure.metadata.v1",
        owner="mrw.source",
        failures=(
            source_contract_failures,
            source_provider_acquisition_failures,
            source_runtime_binding_failures,
            source_single_source_guard_failures,
        ),
    )
)

source_contribution_catalog = (source_contribution,)

contribution_catalog = ContributionCatalog(
    contributions=source_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["source_contribution_catalog", "contribution_catalog"]
